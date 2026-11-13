"""Service for ingesting and converting research material files for coding-research-planner."""

import logging
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter

logger = logging.getLogger(__name__)

PLAIN_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".text",
        ".md",
        ".markdown",
        ".rst",
        ".log",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".csv",
        ".tsv",
    }
)


class ResearchMaterialError(Exception):
    """Raised when research material cannot be ingested or converted."""


class ResearchMaterialService:
    """Ingests and converts research material files into structured text/markdown."""

    def __init__(self, converter: DocumentConverter | None = None) -> None:
        self._converter = converter

    @property
    def converter(self) -> DocumentConverter:
        """Lazy-instantiated DocumentConverter to avoid cold-start overhead when not needed."""
        if self._converter is None:
            self._converter = DocumentConverter()
        return self._converter

    def is_plain_text(self, path: Path) -> bool:
        """Checks if a file has a plain-text extension."""
        return path.suffix.lower() in PLAIN_TEXT_EXTENSIONS

    def ingest_file(self, file_path: str | Path) -> dict[str, Any]:
        """Ingests a single research material file.

        - Plain text files are read directly as UTF-8 text strings.
        - Non-plain text files (PDF, DOCX, PPTX, XLSX, HTML, Images) are converted
          to Markdown using Docling.

        Args:
            file_path: Absolute or relative path to the research material file.

        Returns:
            Dictionary containing:
                - 'file_path': str (canonical absolute or relative path)
                - 'file_name': str (basename)
                - 'content': str (clean markdown or plain text)
                - 'format': str ('plain_text' or 'docling')

        Raises:
            ResearchMaterialError: If the file does not exist, cannot be read, or fails conversion.
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise ResearchMaterialError(f"Research material file not found: {file_path}")

        file_name = path.name

        if self.is_plain_text(path):
            try:
                content = path.read_text(encoding="utf-8")
                return {
                    "file_path": str(file_path),
                    "file_name": file_name,
                    "content": content,
                    "format": "plain_text",
                }
            except Exception as exc:
                raise ResearchMaterialError(f"Failed to read plain text file '{file_path}': {exc}") from exc

        # Use Docling for rich documents and binary formats
        try:
            conv_res = self.converter.convert(path)
            markdown_content = conv_res.document.export_to_markdown()
            return {
                "file_path": str(file_path),
                "file_name": file_name,
                "content": markdown_content,
                "format": "docling",
            }
        except Exception as exc:
            raise ResearchMaterialError(
                f"Failed to convert research material file '{file_path}' with docling: {exc}"
            ) from exc

    def ingest_files(self, file_paths: list[str | Path]) -> list[dict[str, Any]]:
        """Ingests a list of research material files."""
        return [self.ingest_file(p) for p in file_paths]

    @staticmethod
    def format_materials_for_context(materials: list[dict[str, Any]]) -> str:
        """Formats a list of ingested materials into a Markdown context block for agent instructions."""
        if not materials:
            return ""

        parts: list[str] = [
            "### Pre-loaded Research Materials",
            "",
            "The following research material files have been provided by the user to ground this research plan:",
            "",
        ]

        for idx, mat in enumerate(materials, start=1):
            parts.append(f"#### Material {idx}: `{mat['file_path']}` ({mat.get('format', 'document')})")
            parts.append("```markdown")
            parts.append(mat.get("content", "").strip())
            parts.append("```")
            parts.append("")

        return "\n".join(parts).strip()
