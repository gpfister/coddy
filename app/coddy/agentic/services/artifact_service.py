"""Artifact Management Service for agentic workflows.

Handles persistence and retrieval of workflow artifacts strictly within
~/.coddy/<session_id>/artifacts/.
"""

import json
import shutil
from pathlib import Path
from typing import Any

from app.coddy.agentic.services.paths import get_artifacts_dir


class ArtifactService:
    """Manages workflow artifact persistence in the session artifacts directory."""

    def __init__(
        self,
        artifacts_dir: Path | None = None,
        session_id: str | None = None,
        # Backward compatibility alias
        brain_dir: Path | None = None,
        conversation_id: str | None = None,
    ):
        target_dir = artifacts_dir or brain_dir
        target_id = session_id or conversation_id
        self.artifacts_dir = target_dir or get_artifacts_dir(target_id)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        # Backward compatibility alias
        self.brain_dir = self.artifacts_dir

    @property
    def sanitized_user_request_path(self) -> Path:
        """Path to sanitized_user_request.json in the artifacts directory."""
        return self.artifacts_dir / "sanitized_user_request.json"

    @property
    def sanitized_user_request_md_path(self) -> Path:
        """Path to SANITIZED_USER_REQUEST.md in the artifacts directory."""
        return self.artifacts_dir / "SANITIZED_USER_REQUEST.md"

    @property
    def sanitized_local_project_instructions_path(self) -> Path:
        """Path to SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md in the artifacts directory."""
        return self.artifacts_dir / "SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md"

    @property
    def sanitized_local_project_description_path(self) -> Path:
        """Path to SANITIZED_LOCAL_PROJECT_DESCRIPTION.md in the artifacts directory."""
        return self.artifacts_dir / "SANITIZED_LOCAL_PROJECT_DESCRIPTION.md"

    @property
    def enhanced_user_request_path(self) -> Path:
        """Path to enhanced_user_request.json in the artifacts directory."""
        return self.artifacts_dir / "enhanced_user_request.json"

    @property
    def enhanced_user_request_md_path(self) -> Path:
        """Path to ENHANCED_USER_REQUEST.md in the artifacts directory."""
        return self.artifacts_dir / "ENHANCED_USER_REQUEST.md"

    @property
    def research_plan_json_path(self) -> Path:
        """Path to research_plan.json in the artifacts directory."""
        return self.artifacts_dir / "research_plan.json"

    @property
    def research_plan_md_path(self) -> Path:
        """Path to RESEARCH_PLAN.md in the artifacts directory."""
        return self.artifacts_dir / "RESEARCH_PLAN.md"

    @property
    def research_report_json_path(self) -> Path:
        """Path to research_report.json in the artifacts directory."""
        return self.artifacts_dir / "research_report.json"

    @property
    def research_report_md_path(self) -> Path:
        """Path to RESEARCH_REPORT.md in the artifacts directory."""
        return self.artifacts_dir / "RESEARCH_REPORT.md"

    @property
    def research_episodes_dir(self) -> Path:
        """Directory path for episodic research under artifacts_dir/research_episodes/."""
        p = self.artifacts_dir / "research_episodes"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def research_materials_dir(self) -> Path:
        """Directory path for research materials under artifacts_dir/research_materials/."""
        p = self.artifacts_dir / "research_materials"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_sanitized_user_request(self, user_request_model: Any) -> Path:
        """Persists the sanitized user request JSON model in the session artifacts directory."""
        if hasattr(user_request_model, "model_dump_json"):
            self.sanitized_user_request_path.write_text(user_request_model.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(user_request_model, str):
            self.sanitized_user_request_path.write_text(user_request_model, encoding="utf-8")
        else:
            self.sanitized_user_request_path.write_text(json.dumps(user_request_model, indent=2), encoding="utf-8")
        return self.sanitized_user_request_path

    def save_sanitizer_artifacts(
        self,
        sanitized_request: Any,
        user_request_md: str = "",
        local_instruction_md: str = "",
        local_description_md: str = "",
    ) -> dict[str, Path]:
        """Persists sanitized_user_request.json, SANITIZED_USER_REQUEST.md, SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md, SANITIZED_LOCAL_PROJECT_DESCRIPTION.md."""
        paths: dict[str, Path] = {
            "json": self.save_sanitized_user_request(sanitized_request),
            "user_request_md": self.sanitized_user_request_md_path,
        }
        self.sanitized_user_request_md_path.write_text(user_request_md, encoding="utf-8")

        if local_instruction_md:
            self.sanitized_local_project_instructions_path.write_text(local_instruction_md, encoding="utf-8")
            paths["local_instruction_md"] = self.sanitized_local_project_instructions_path

        if local_description_md:
            self.sanitized_local_project_description_path.write_text(local_description_md, encoding="utf-8")
            paths["local_description_md"] = self.sanitized_local_project_description_path

        return paths

    def save_enhanced_user_request_artifacts(
        self,
        enhanced_request: Any,
        user_request_md: str = "",
    ) -> dict[str, Path]:
        """Persists enhanced_user_request.json and ENHANCED_USER_REQUEST.md."""
        if hasattr(enhanced_request, "model_dump_json"):
            self.enhanced_user_request_path.write_text(enhanced_request.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(enhanced_request, str):
            self.enhanced_user_request_path.write_text(enhanced_request, encoding="utf-8")
        else:
            self.enhanced_user_request_path.write_text(json.dumps(enhanced_request, indent=2), encoding="utf-8")

        self.enhanced_user_request_md_path.write_text(user_request_md, encoding="utf-8")
        return {
            "json": self.enhanced_user_request_path,
            "user_request_md": self.enhanced_user_request_md_path,
        }

    def save_research_plan_artifacts(
        self,
        plan: Any,
        plan_md: str = "",
    ) -> tuple[Path, Path]:
        """Persists research_plan.json and RESEARCH_PLAN.md directly in the session artifacts directory."""
        if hasattr(plan, "model_dump_json"):
            self.research_plan_json_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(plan, str):
            self.research_plan_json_path.write_text(plan, encoding="utf-8")
        else:
            self.research_plan_json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

        self.research_plan_md_path.write_text(plan_md, encoding="utf-8")
        return self.research_plan_json_path, self.research_plan_md_path

    def save_research_plan(
        self,
        project_name: Any = "coddy_project",
        plan: Any = None,
        plan_md: str = "",
    ) -> tuple[Path, Path]:
        """Persists research plan JSON and Markdown artifacts under artifacts_dir/research_plans/."""
        if not isinstance(project_name, str):
            plan_md = plan if isinstance(plan, str) else plan_md
            plan = project_name
            project_name = "coddy_project"
        elif plan is None and isinstance(project_name, str):
            plan = {}

        plan_dir = self.artifacts_dir / "research_plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        json_file = plan_dir / f"{project_name}_research_plan.json"
        md_file = plan_dir / f"{project_name}_research_plan.md"

        if hasattr(plan, "model_dump_json"):
            json_file.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(plan, str):
            json_file.write_text(plan, encoding="utf-8")
        else:
            json_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")

        md_file.write_text(plan_md, encoding="utf-8")
        return json_file, md_file

    def save_episode_research(
        self,
        episode_index: int,
        subject_slug: str,
        result: Any,
        result_md: str = "",
    ) -> tuple[Path, Path]:
        """Persists an episodic research result JSON and Markdown artifact."""
        ep_dir = self.research_episodes_dir
        json_file = ep_dir / f"episode_{episode_index}_{subject_slug}.json"
        md_file = ep_dir / f"episode_{episode_index}_{subject_slug}.md"

        if hasattr(result, "model_dump_json"):
            json_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(result, str):
            json_file.write_text(result, encoding="utf-8")
        else:
            json_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

        md_file.write_text(result_md, encoding="utf-8")
        return json_file, md_file

    def save_research_report(
        self,
        report: Any,
        report_md: str = "",
    ) -> tuple[Path, Path]:
        """Persists research_report.json and RESEARCH_REPORT.md in artifacts directory."""
        if hasattr(report, "model_dump_json"):
            self.research_report_json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(report, str):
            self.research_report_json_path.write_text(report, encoding="utf-8")
        else:
            self.research_report_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        self.research_report_md_path.write_text(report_md, encoding="utf-8")
        return self.research_report_json_path, self.research_report_md_path

    def save_specification(
        self,
        project_name: str,
        spec: Any,
        spec_md: str,
    ) -> tuple[Path, Path]:
        """Persists specification JSON and Markdown artifacts under artifacts_dir/specifications/."""
        spec_dir = self.artifacts_dir / "specifications"
        spec_dir.mkdir(parents=True, exist_ok=True)
        json_file = spec_dir / f"{project_name}_spec.json"
        md_file = spec_dir / f"{project_name}_spec.md"

        if hasattr(spec, "model_dump_json"):
            json_file.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(spec, str):
            json_file.write_text(spec, encoding="utf-8")
        else:
            json_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        md_file.write_text(spec_md, encoding="utf-8")
        return json_file, md_file

    def save_plan(
        self,
        project_name: str,
        plan: Any,
        plan_md: str,
    ) -> tuple[Path, Path]:
        """Persists plan JSON and Markdown artifacts under artifacts_dir/plans/."""
        plan_dir = self.artifacts_dir / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        json_file = plan_dir / f"{project_name}_plan.json"
        md_file = plan_dir / f"{project_name}_plan.md"

        if hasattr(plan, "model_dump_json"):
            json_file.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        elif isinstance(plan, str):
            json_file.write_text(plan, encoding="utf-8")
        else:
            json_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")

        md_file.write_text(plan_md, encoding="utf-8")
        return json_file, md_file

    def save_research_materials(
        self,
        materials: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Persists ingested research materials as original files, Markdown, and a manifest JSON."""
        results: list[dict[str, Any]] = []
        target_dir = self.research_materials_dir

        for idx, item in enumerate(materials, start=1):
            raw_name = item.get("file_name", f"material_{idx}")
            file_name = Path(raw_name).name
            stem = Path(file_name).stem
            md_filename = f"{stem}.md"
            md_path = target_dir / md_filename

            # 1. Save original file
            original_artifact_path = target_dir / file_name
            orig_src = Path(item["file_path"]) if item.get("file_path") else None
            if orig_src and orig_src.is_file():
                if orig_src.resolve() != original_artifact_path.resolve():
                    shutil.copy2(orig_src, original_artifact_path)
            elif not original_artifact_path.exists():
                original_artifact_path.write_text(item.get("content", ""), encoding="utf-8")

            # 2. Save converted markdown file
            if original_artifact_path.resolve() != md_path.resolve():
                counter = 1
                while md_path.exists() and md_path.read_text(encoding="utf-8") != item.get("content", ""):
                    md_filename = f"{stem}_{counter}.md"
                    md_path = target_dir / md_filename
                    counter += 1
                md_path.write_text(item.get("content", ""), encoding="utf-8")

            results.append(
                {
                    "original_path": item.get("file_path"),
                    "original_file_name": file_name,
                    "original_artifact_path": str(original_artifact_path),
                    "artifact_path": str(md_path),
                    "file_name": md_filename,
                    "converted_file_name": md_filename,
                    "format": item.get("format", "unknown"),
                }
            )

        manifest_path = target_dir / "manifest.json"
        manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        return results

    def list_artifacts(self) -> dict[str, str]:
        """Returns a mapping of artifact labels to relative or absolute file paths."""
        artifacts: dict[str, str] = {}
        if self.sanitized_user_request_path.exists():
            artifacts["Sanitized User Request (JSON)"] = str(self.sanitized_user_request_path)
        if self.sanitized_user_request_md_path.exists():
            artifacts["Sanitized User Request (Markdown)"] = str(self.sanitized_user_request_md_path)
        if self.sanitized_local_project_instructions_path.exists():
            artifacts["Sanitized Local Project Instructions (Markdown)"] = str(self.sanitized_local_project_instructions_path)
        if self.sanitized_local_project_description_path.exists():
            artifacts["Sanitized Local Project Description (Markdown)"] = str(self.sanitized_local_project_description_path)
        if self.research_plan_json_path.exists():
            artifacts["Research Plan (JSON)"] = str(self.research_plan_json_path)
        if self.research_plan_md_path.exists():
            artifacts["Research Plan (Markdown)"] = str(self.research_plan_md_path)

        for category in ["research_plans", "specifications", "plans"]:
            cat_dir = self.artifacts_dir / category
            if cat_dir.exists():
                for p in cat_dir.glob("*"):
                    if p.is_file():
                        artifacts[f"{category.replace('_', ' ').capitalize()}: {p.name}"] = str(p)

        return artifacts
