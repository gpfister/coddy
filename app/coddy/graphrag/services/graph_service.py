"""Graph service for AST code extraction, documentation chunking, intent linking, and Cypher queries."""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.coddy.graphrag.schemas.graphrag import GraphExport
from app.coddy.utils.services.falkordb_service import FalkorDBService

logger = logging.getLogger(__name__)

EXCLUDED_DIRS: set[str] = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".cache",
    "out",
    "tmp",
    "site-packages",
    "tests",
}

STRUCTURAL_FACT_TYPES = {"function", "class", "method", "file", "interface", "type"}


def is_excluded_path(p: Path) -> bool:
    """Returns True if any path component is in EXCLUDED_DIRS."""
    return any(part in EXCLUDED_DIRS for part in p.parts)


def get_visibility(name: str) -> str:
    """Determine PUBLIC, PRIVATE, or PROTECTED visibility from identifier name."""
    clean = name.lstrip(".")
    if clean.startswith("__") and clean.endswith("__"):
        return "PUBLIC"
    if clean.startswith("_"):
        return "PRIVATE"
    return "PUBLIC"


def format_annotation(node: ast.AST | None) -> str:
    """Convert an AST type annotation node to human-readable type string."""
    if node is None:
        return ""
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def format_signature(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract standard signature string for a function or method."""
    args_strs: list[str] = []
    args = func_node.args

    for a in getattr(args, "posonlyargs", []):
        ann = f": {format_annotation(a.annotation)}" if a.annotation else ""
        args_strs.append(f"{a.arg}{ann}")
    if getattr(args, "posonlyargs", []):
        args_strs.append("/")

    for a in args.args:
        ann = f": {format_annotation(a.annotation)}" if a.annotation else ""
        args_strs.append(f"{a.arg}{ann}")

    if args.vararg:
        ann = f": {format_annotation(args.vararg.annotation)}" if args.vararg.annotation else ""
        args_strs.append(f"*{args.vararg.arg}{ann}")

    for a in getattr(args, "kwonlyargs", []):
        ann = f": {format_annotation(a.annotation)}" if a.annotation else ""
        args_strs.append(f"{a.arg}{ann}")

    if args.kwarg:
        ann = f": {format_annotation(args.kwarg.annotation)}" if args.kwarg.annotation else ""
        args_strs.append(f"**{args.kwarg.arg}{ann}")

    ret_ann = f" -> {format_annotation(func_node.returns)}" if func_node.returns else ""
    async_prefix = "async " if isinstance(func_node, ast.AsyncFunctionDef) else ""
    return f"{async_prefix}def {func_node.name}({', '.join(args_strs)}){ret_ann}"


def synthesize_fact_content(props: dict[str, Any]) -> str:
    """Synthesize a structured textual representation of an AST code fact for dense/sparse embedding."""
    entity_type = props.get("type") or props.get("entity_type") or "code"
    name = props.get("qualified_name") or props.get("clean_name") or props.get("name") or ""
    path = props.get("file_path") or props.get("path") or ""
    l_start = props.get("start_line") or props.get("line_start")
    l_end = props.get("end_line") or props.get("line_end")
    loc = f"{path}:{l_start}-{l_end}" if l_start and l_end else path
    sig = props.get("signature") or ""
    doc = props.get("docstring") or ""

    parts = [f"[{str(entity_type).capitalize()}] {name}"]
    if loc:
        parts.append(f"File: {loc}")
    if sig:
        parts.append(f"Signature: {sig}")
    if doc:
        parts.append(f"Docstring: {doc.strip()}")
    return "\n".join(parts)


@dataclass
class ExtractedFactNode:
    """Represents an extracted code fact node in the AST graph."""

    id: str
    label_str: str  # Colon-separated labels, e.g. "Method:Code:Fact"
    properties: dict[str, Any]

    @property
    def type(self) -> str:
        return self.label_str.split(":")[0]

    @property
    def label(self) -> str:
        return str(self.properties.get("label", self.properties.get("name", self.id)))

    @property
    def clean_name(self) -> str:
        return str(self.properties.get("clean_name", self.properties.get("name", self.id)))

    @property
    def source_file(self) -> str:
        return str(self.properties.get("source_file", self.properties.get("path", "")))


@dataclass
class ExtractedFactEdge:
    """Represents a directed relationship between extracted AST fact nodes."""

    src: str
    tgt: str
    relation: str
    properties: dict[str, Any] = field(default_factory=dict)


class PythonASTExtractor:
    """Extracts fine-grained graph facts from Python ASTs mirroring py-graphrag-oskey-io."""

    def __init__(self, repo_dir: Path) -> None:
        self.repo_dir = repo_dir
        self.nodes: dict[str, ExtractedFactNode] = {}
        self.edges: list[ExtractedFactEdge] = []
        self.symbol_table: dict[str, str] = {}
        self.file_imports: dict[str, dict[str, str]] = {}

    def extract_from_file(
        self, py_path: Path
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], list[tuple[str, str, str, dict[str, Any]]]]:
        """Parses a Python file and returns nodes and edges formatted for upsert."""
        try:
            rel_path = str(py_path.relative_to(self.repo_dir))
        except ValueError:
            rel_path = py_path.name

        try:
            code = py_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(code, filename=rel_path)
        except Exception:
            return [], []

        file_id = rel_path
        filename = py_path.name
        self._add_node(
            node_id=file_id,
            labels=["File", "Code", "Fact"],
            props={
                "name": filename,
                "label": filename,
                "clean_name": py_path.stem,
                "source_file_path": rel_path,
                "source_file": rel_path,
                "path": rel_path,
                "file_path": rel_path,
                "type": "file",
                "is_fact": True,
                "kind": "fact",
            },
        )

        self.file_imports[rel_path] = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    name = alias.asname or alias.name
                    self.file_imports[rel_path][name] = alias.name
            elif isinstance(stmt, ast.ImportFrom):
                mod = stmt.module or ""
                for alias in stmt.names:
                    name = alias.asname or alias.name
                    target = f"{mod}.{alias.name}" if mod else alias.name
                    self.file_imports[rel_path][name] = target

        for stmt in tree.body:
            if isinstance(stmt, ast.ClassDef):
                self._extract_class(rel_path, file_id, stmt)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function(rel_path, file_id, stmt)
            elif isinstance(stmt, ast.Assign):
                self._extract_module_types_and_vars(rel_path, file_id, stmt)
            elif isinstance(stmt, ast.AnnAssign):
                self._extract_module_annotated_type(rel_path, file_id, stmt)

        self.resolve_dangling_calls()

        nodes_out = [(n.id, n.label_str, n.properties) for n in self.nodes.values()]
        edges_out = [(e.src, e.tgt, e.relation, e.properties) for e in self.edges]
        return nodes_out, edges_out

    def _add_node(self, node_id: str, labels: list[str], props: dict[str, Any]) -> None:
        if "Code" not in labels:
            labels.append("Code")
        if "Fact" not in labels:
            labels.append("Fact")
        label_str = ":".join(dict.fromkeys(labels))
        path_val = str(props.get("path") or props.get("source_file_path") or props.get("source_file") or "")
        if path_val:
            props.setdefault("path", path_val)
            props.setdefault("file_path", path_val)
            props.setdefault("source_file", path_val)
            props.setdefault("source_file_path", path_val)
        self.nodes[node_id] = ExtractedFactNode(id=node_id, label_str=label_str, properties=props)
        clean = props.get("clean_name") or props.get("name") or node_id
        self.symbol_table[clean] = node_id
        if props.get("qualified_name"):
            self.symbol_table[str(props["qualified_name"])] = node_id

    def _add_edge(self, src: str, tgt: str, relation: str, props: dict[str, Any] | None = None) -> None:
        p = props.copy() if props else {}
        p["is_fact"] = True
        p["kind"] = "fact"
        self.edges.append(ExtractedFactEdge(src=src, tgt=tgt, relation=relation, properties=p))

    def _is_interface(self, cls_node: ast.ClassDef) -> bool:
        for base in cls_node.bases:
            base_str = ast.unparse(base).strip() if hasattr(ast, "unparse") else ""
            if base_str in ("Protocol", "typing.Protocol", "abc.ABC", "ABC"):
                return True
        if (
            cls_node.name.endswith("Interface")
            or cls_node.name.endswith("Protocol")
            or (cls_node.name.startswith("I") and len(cls_node.name) > 1 and cls_node.name[1].isupper())
        ):
            return True
        for item in cls_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in item.decorator_list:
                    if hasattr(ast, "unparse") and "abstractmethod" in ast.unparse(d):
                        return True
        return False

    def _extract_class(self, rel_path: str, file_id: str, cls_node: ast.ClassDef) -> None:
        cls_id = f"{rel_path}::{cls_node.name}"
        is_iface = self._is_interface(cls_node)
        primary_label = "Interface" if is_iface else "Class"
        mod_stem = Path(rel_path).stem
        self._add_node(
            node_id=cls_id,
            labels=[primary_label, "Code", "Fact"],
            props={
                "name": cls_node.name,
                "label": cls_node.name,
                "clean_name": cls_node.name,
                "qualified_name": f"{mod_stem}.{cls_node.name}",
                "path": rel_path,
                "source_file": rel_path,
                "file_path": rel_path,
                "start_line": cls_node.lineno,
                "end_line": getattr(cls_node, "end_lineno", cls_node.lineno),
                "docstring": ast.get_docstring(cls_node) or "",
                "type": primary_label.lower(),
                "is_interface": is_iface,
                "is_fact": True,
                "kind": "fact",
            },
        )
        self._add_edge(file_id, cls_id, "DEFINES")

        for base in cls_node.bases:
            base_name = ast.unparse(base).strip() if hasattr(ast, "unparse") else ""
            if not base_name or base_name in ("object", "BaseModel", "dict", "str", "int"):
                continue
            base_id = self.symbol_table.get(base_name, base_name)
            is_base_iface = (
                base_name.endswith("Interface")
                or base_name.endswith("Protocol")
                or (base_name.startswith("I") and len(base_name) > 1 and base_name[1].isupper())
                or (base_id in self.nodes and "Interface" in self.nodes[base_id].label_str)
            )
            if is_base_iface:
                self._add_edge(cls_id, base_id, "IMPLEMENTS", {"interface": base_name})
            else:
                self._add_edge(cls_id, base_id, "INHERITS", {"base_class": base_name})

        for item in cls_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_method(rel_path, cls_id, cls_node.name, item)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                self._extract_class_parameter(
                    rel_path, cls_id, item.target.id, is_static=True, annotation_node=item.annotation
                )
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        self._extract_class_parameter(rel_path, cls_id, target.id, is_static=True, annotation_node=None)

    def _extract_class_parameter(
        self,
        rel_path: str,
        cls_id: str,
        param_name: str,
        is_static: bool,
        annotation_node: ast.AST | None,
    ) -> None:
        if param_name.startswith("__") and param_name.endswith("__"):
            return
        param_id = f"{cls_id}::.{param_name}"
        vis = get_visibility(param_name)
        ann_str = format_annotation(annotation_node)

        self._add_node(
            node_id=param_id,
            labels=["ClassParameter", "Code", "Fact"],
            props={
                "name": f".{param_name}",
                "label": f".{param_name}",
                "clean_name": param_name,
                "path": rel_path,
                "source_file": rel_path,
                "file_path": rel_path,
                "is_static": is_static,
                "visibility": vis,
                "type_annotation": ann_str,
                "type": "class_parameter",
                "is_fact": True,
                "kind": "fact",
            },
        )
        self._add_edge(cls_id, param_id, "DEFINES")

        if ann_str:
            clean_type = ann_str.split("[")[0].strip().split(".")[-1]
            type_target = self.symbol_table.get(clean_type, clean_type)
            self._add_edge(param_id, type_target, "HAS_TYPE", {"type_name": ann_str})

    def _extract_method(
        self,
        rel_path: str,
        cls_id: str,
        class_name: str,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        fn_name = func_node.name
        method_id = f"{cls_id}::.{fn_name}()"
        sig = format_signature(func_node)
        vis = get_visibility(fn_name)

        if fn_name == "__init__":
            m_type = "CONSTRUCTOR"
        elif fn_name == "__del__":
            m_type = "DECONSTRUCTOR"
        else:
            m_type = "METHOD"

        is_static = any(
            (isinstance(d, ast.Name) and d.id == "staticmethod")
            or (isinstance(d, ast.Attribute) and d.attr == "staticmethod")
            for d in func_node.decorator_list
        )

        self._add_node(
            node_id=method_id,
            labels=["Method", "Fact"],
            props={
                "name": fn_name,
                "label": f".{fn_name}()",
                "clean_name": fn_name,
                "qualified_name": f"{class_name}.{fn_name}",
                "class_name": class_name,
                "signature": sig,
                "type": m_type,
                "method_type": m_type,
                "static": is_static,
                "is_static": is_static,
                "visibility": vis,
                "path": rel_path,
                "source_file": rel_path,
                "file_path": rel_path,
                "start_line": func_node.lineno,
                "end_line": getattr(func_node, "end_lineno", func_node.lineno),
                "docstring": ast.get_docstring(func_node) or "",
                "is_fact": True,
                "kind": "fact",
            },
        )
        self._add_edge(cls_id, method_id, "DEFINES")

        for arg in func_node.args.args:
            if arg.arg in ("self", "cls"):
                continue
            self._extract_variable(
                rel_path=rel_path,
                callable_id=method_id,
                var_name=arg.arg,
                is_param=True,
                ann_node=arg.annotation,
            )

        if func_node.returns:
            ret_str = format_annotation(func_node.returns)
            clean_type = ret_str.split("[")[0].strip().split(".")[-1]
            if clean_type and clean_type not in ("None", "bool", "int", "str", "float"):
                type_target = self.symbol_table.get(clean_type, clean_type)
                self._add_edge(method_id, type_target, "USES_TYPE", {"return_type": ret_str})

        for child in ast.walk(func_node):
            if m_type == "CONSTRUCTOR" and isinstance(child, ast.Assign):
                for target in child.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        self._extract_class_parameter(
                            rel_path, cls_id, target.attr, is_static=False, annotation_node=None
                        )
            elif isinstance(child, ast.Call):
                self._extract_call(rel_path, method_id, child, caller_class=class_name)

    def _extract_function(
        self,
        rel_path: str,
        file_id: str,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        fn_name = func_node.name
        mod_stem = Path(rel_path).stem
        fn_id = f"{rel_path}::{fn_name}()"
        sig = format_signature(func_node)
        vis = get_visibility(fn_name)

        self._add_node(
            node_id=fn_id,
            labels=["Function", "Code", "Fact"],
            props={
                "name": fn_name,
                "label": f"{fn_name}()",
                "clean_name": fn_name,
                "qualified_name": f"{mod_stem}.{fn_name}",
                "signature": sig,
                "type": "function",
                "visibility": vis,
                "path": rel_path,
                "source_file": rel_path,
                "file_path": rel_path,
                "start_line": func_node.lineno,
                "end_line": getattr(func_node, "end_lineno", func_node.lineno),
                "docstring": ast.get_docstring(func_node) or "",
                "is_fact": True,
                "kind": "fact",
            },
        )
        self._add_edge(file_id, fn_id, "DEFINES")

        for arg in func_node.args.args:
            self._extract_variable(
                rel_path=rel_path,
                callable_id=fn_id,
                var_name=arg.arg,
                is_param=True,
                ann_node=arg.annotation,
            )

        if func_node.returns:
            ret_str = format_annotation(func_node.returns)
            clean_type = ret_str.split("[")[0].strip().split(".")[-1]
            if clean_type and clean_type not in ("None", "bool", "int", "str", "float"):
                type_target = self.symbol_table.get(clean_type, clean_type)
                self._add_edge(fn_id, type_target, "USES_TYPE", {"return_type": ret_str})

        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                self._extract_call(rel_path, fn_id, child)

    def _extract_variable(
        self,
        rel_path: str,
        callable_id: str,
        var_name: str,
        is_param: bool,
        ann_node: ast.AST | None,
    ) -> None:
        var_id = f"{callable_id}::${var_name}"
        vis = get_visibility(var_name)
        ann_str = format_annotation(ann_node)

        self._add_node(
            node_id=var_id,
            labels=["Variable", "Code", "Fact"],
            props={
                "name": f"${var_name}",
                "label": f"${var_name}",
                "clean_name": var_name,
                "path": rel_path,
                "source_file": rel_path,
                "file_path": rel_path,
                "is_param": is_param,
                "visibility": vis,
                "type_annotation": ann_str,
                "type": "parameter" if is_param else "variable",
                "is_fact": True,
                "kind": "fact",
            },
        )
        self._add_edge(callable_id, var_id, "DECLARES")

        if ann_str:
            clean_type = ann_str.split("[")[0].strip().split(".")[-1]
            type_target = self.symbol_table.get(clean_type, clean_type)
            self._add_edge(var_id, type_target, "HAS_TYPE", {"type_name": ann_str})

    def _extract_call(
        self,
        rel_path: str,
        caller_id: str,
        call_node: ast.Call,
        caller_class: str = "",
    ) -> None:
        expr = ast.unparse(call_node.func).strip() if hasattr(ast, "unparse") else ""
        callee_name = ""
        if isinstance(call_node.func, ast.Name):
            callee_name = call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            callee_name = call_node.func.attr

        if not callee_name or callee_name in ("len", "print", "range", "isinstance", "getattr", "setattr"):
            return

        target_id = self.symbol_table.get(callee_name, callee_name)
        self._add_edge(
            src=caller_id,
            tgt=target_id,
            relation="CALLS",
            props={
                "callee": callee_name,
                "caller_file": rel_path,
                "caller_class": caller_class,
                "expr": expr,
            },
        )

    def _extract_module_types_and_vars(self, rel_path: str, file_id: str, assign_node: ast.Assign) -> None:
        for target in assign_node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                val_str = ast.unparse(assign_node.value) if hasattr(ast, "unparse") else ""
                is_type_alias = (
                    "TypeVar" in val_str
                    or "NewType" in val_str
                    or "Union" in val_str
                    or "TypeAlias" in val_str
                    or (name[0].isupper() and not name.isupper())
                    or name.startswith("TYPE_")
                    or name.endswith("_TYPE")
                )
                if is_type_alias:
                    type_id = f"{rel_path}::{name}"
                    self._add_node(
                        node_id=type_id,
                        labels=["Type", "Code", "Fact"],
                        props={
                            "name": name,
                            "label": name,
                            "clean_name": name,
                            "source_file": rel_path,
                            "path": rel_path,
                            "file_path": rel_path,
                            "type": "type",
                            "is_fact": True,
                            "kind": "fact",
                        },
                    )
                    self._add_edge(file_id, type_id, "DEFINES")

    def _extract_module_annotated_type(self, rel_path: str, file_id: str, ann_node: ast.AnnAssign) -> None:
        if isinstance(ann_node.target, ast.Name):
            name = ann_node.target.id
            ann_str = format_annotation(ann_node.annotation)
            if "TypeAlias" in ann_str or name[0].isupper():
                type_id = f"{rel_path}::{name}"
                self._add_node(
                    node_id=type_id,
                    labels=["Type", "Code", "Fact"],
                    props={
                        "name": name,
                        "label": name,
                        "clean_name": name,
                        "source_file": rel_path,
                        "path": rel_path,
                        "file_path": rel_path,
                        "type": "type",
                        "is_fact": True,
                        "kind": "fact",
                    },
                )
                self._add_edge(file_id, type_id, "DEFINES")

    def resolve_dangling_calls(self) -> int:
        """Resolve forward references and dangling target IDs across all extracted nodes."""
        by_clean_name: dict[str, list[str]] = {}
        by_qualified_name: dict[str, list[str]] = {}
        by_class_and_method: dict[tuple[str, str], str] = {}
        by_file_and_clean_name: dict[tuple[str, str], list[str]] = {}
        by_stem_and_clean_name: dict[tuple[str, str], list[str]] = {}

        for nid, node in self.nodes.items():
            props = node.properties
            clean = props.get("clean_name") or props.get("name") or nid
            by_clean_name.setdefault(str(clean), []).append(nid)

            qname = props.get("qualified_name")
            if qname:
                by_qualified_name.setdefault(str(qname), []).append(nid)

            cls_name = props.get("class_name")
            if cls_name and clean:
                by_class_and_method[(str(cls_name), str(clean))] = nid

            src_file = props.get("source_file") or props.get("path")
            if src_file:
                by_file_and_clean_name.setdefault((str(src_file), str(clean)), []).append(nid)
                stem = Path(str(src_file)).stem
                by_stem_and_clean_name.setdefault((stem, str(clean)), []).append(nid)

        resolved_count = 0

        for edge in self.edges:
            if edge.tgt in self.nodes:
                continue

            callee = edge.properties.get("callee") or edge.tgt
            caller_file = edge.properties.get("caller_file", "")
            caller_class = edge.properties.get("caller_class", "")
            expr = edge.properties.get("expr", "")
            resolved_id: str | None = None

            if (
                caller_class
                and (expr.startswith("self.") or expr.startswith("cls."))
                and (caller_class, callee) in by_class_and_method
            ):
                resolved_id = by_class_and_method[(caller_class, callee)]

            if not resolved_id and caller_file in self.file_imports:
                imports = self.file_imports[caller_file]
                if callee in imports:
                    imported = imports[callee]
                    imported_stem = imported.split(".")[-2] if "." in imported else ""
                    if (imported_stem, callee) in by_stem_and_clean_name:
                        candidates = by_stem_and_clean_name[(imported_stem, callee)]
                        if candidates:
                            resolved_id = candidates[0]
                    if not resolved_id:
                        q_candidates = by_qualified_name.get(f"{imported_stem}.{callee}") or by_qualified_name.get(
                            imported
                        )
                        if q_candidates:
                            resolved_id = q_candidates[0]

            if not resolved_id and caller_file:
                local_candidates = by_file_and_clean_name.get((caller_file, callee))
                if local_candidates:
                    resolved_id = local_candidates[0]

            if not resolved_id and callee in by_clean_name:
                candidates = by_clean_name[callee]
                resolved_id = candidates[0]

            if not resolved_id and callee in self.symbol_table:
                sym_id = self.symbol_table[callee]
                if sym_id in self.nodes:
                    resolved_id = sym_id

            if resolved_id and resolved_id in self.nodes:
                edge.tgt = resolved_id
                resolved_count += 1

        return resolved_count


CodeASTExtractor = PythonASTExtractor


class DoclingChunker:
    """Parses markdown documentation and slices it into semantic chunks."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    def extract_chunks(self, md_path: Path) -> list[dict[str, Any]]:
        """Splits a markdown document into heading-based sections."""
        rel_path = str(md_path.relative_to(self.repo_dir))
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        chunks: list[dict[str, Any]] = []
        sections = re.split(r"(?m)^(?=#{1,3}\s+)", text)
        idx = 0
        for sec in sections:
            clean = sec.strip()
            if not clean:
                continue
            first_line = clean.splitlines()[0].strip("# ")
            chunk_id = f"{rel_path}#chunk_{idx}"
            headings = [h.strip("# ") for h in re.findall(r"(?m)^#{1,4}\s+(.+)$", clean)]
            chunks.append(
                {
                    "id": chunk_id,
                    "path": rel_path,
                    "doc_path": rel_path,
                    "title": first_line,
                    "text": clean,
                    "content": clean,
                    "headings": headings,
                    "chunk_index": idx,
                    "char_length": len(clean),
                    "preview": clean[:150].replace("\n", " "),
                }
            )
            idx += 1
        return chunks


def extract_deterministic_mentions(text: str) -> set[str]:
    """Extract backticked identifiers, code blocks, and file paths from text."""
    mentions: set[str] = set()

    backticks = re.findall(r"`([^`\n\r]+)`", text)
    for b in backticks:
        b_clean = b.strip().strip("()")
        if len(b_clean) > 1 and not b_clean.isspace():
            mentions.add(b_clean)
            if "." in b_clean and not b_clean.startswith("."):
                for part in b_clean.split("."):
                    part_clean = part.strip().strip("()")
                    if len(part_clean) > 1:
                        mentions.add(part_clean)

    md_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
    for text_part, link_part in md_links:
        mentions.add(text_part.strip())
        mentions.add(link_part.strip())

    paths = re.findall(r"\b(?:app|src|lib|pkg|tests)/[a-zA-Z0-9_\-\./]+\b", text)
    for p in paths:
        mentions.add(p.strip())

    py_files = re.findall(r"\b([a-zA-Z0-9_\-]+)\.py\b", text)
    for f in py_files:
        mentions.add(f"{f}.py")
        mentions.add(f)

    fn_calls = re.findall(r"\b([a-zA-Z0-9_]{3,})\(\)", text)
    for fn in fn_calls:
        mentions.add(fn.strip())

    qual_refs = re.findall(r"\b([A-Z][a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b", text)
    for cls_part, m_part in qual_refs:
        mentions.add(f"{cls_part}.{m_part}")
        mentions.add(cls_part)
        mentions.add(m_part)

    return mentions


def resolve_intent_direction(category: str) -> str:
    """Deterministically maps an intent category to inbound, internal, or outbound."""
    cat = category.lower().strip()
    if cat.startswith("inbound") or cat.startswith("entrypoint") or "entrypoint" in cat or "cli" in cat:
        return "inbound"
    if cat.startswith("outbound") or "outbound" in cat or "api" in cat or "db" in cat or "storage" in cat:
        return "outbound"
    return "internal"


def resolve_outbound_verb(category: str, metadata: dict[str, Any] | None = None) -> str:
    """Returns Cypher relationship verb: CALLS, SEND, PUBLISHES."""
    cat_lower = str(category or "").lower()
    meta_type = str((metadata or {}).get("type", "")).lower() if metadata else ""
    combined = f"{cat_lower} {meta_type}"
    if any(k in combined for k in ["pubsub", "event", "publish", "queue"]):
        return "PUBLISHES"
    if any(k in combined for k in ["webhook", "push", "notification", "send"]):
        return "SEND"
    return "CALLS"


class GraphService:
    """Service managing code AST graph parsing, FalkorDB execution, and graph exports."""

    def __init__(self, falkordb_service: FalkorDBService | None = None):
        self.falkor = falkordb_service or FalkorDBService()

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        return self.falkor.query(cypher, params)

    def upsert_nodes(self, nodes: list[tuple[str, str, dict[str, Any]]]) -> int:
        return self.falkor.upsert_nodes(nodes)

    def upsert_edges(self, edges: list[tuple[str, str, str, dict[str, Any]]]) -> int:
        return self.falkor.upsert_edges(edges)

    def export_graph(self, commit_sha: str) -> GraphExport:
        return self.falkor.export_graph(commit_sha)

    def import_graph(self, export: GraphExport) -> tuple[int, int]:
        return self.falkor.import_graph(export)

    def get_stats(self) -> dict[str, int]:
        return self.falkor.get_stats()

    def close(self) -> None:
        self.falkor.close()
