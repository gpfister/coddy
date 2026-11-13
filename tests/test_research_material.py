"""Hermetic unit tests for research material ingestion, schemas, and CLI options."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from app.coddy.agentic.schemas.research_plan import (
    ResearchMaterialAssessment,
    ResearchPlan,
    normalize_research_plan_data,
)
from app.coddy.agentic.services.artifact_service import ArtifactService
from app.coddy.agentic.services.research_material_service import (
    ResearchMaterialError,
    ResearchMaterialService,
)
from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
    load_research_material,
    step_3_node,
)
from app.coddy.app import app

runner = CliRunner()


def test_research_material_assessment_valid():
    """Verify ResearchMaterialAssessment creates valid instance."""
    assessment = ResearchMaterialAssessment(
        file_path="spec.pdf",
        served_information="System architecture diagram and dataflow.",
        investigation_targets="Inspect dataflow pipelines in pipeline.py.",
        requires_internet_research=True,
        internet_research_rationale="Research Kafka partitioning strategies.",
    )
    assert assessment.file_path == "spec.pdf"
    assert assessment.requires_internet_research is True
    assert assessment.internet_research_rationale == "Research Kafka partitioning strategies."


def test_research_material_assessment_rejects_placeholders():
    """Verify placeholder values are strictly rejected."""
    with pytest.raises(ValidationError):
        ResearchMaterialAssessment(
            file_path="TODO",
            served_information="Valid info",
            investigation_targets="Valid targets",
            requires_internet_research=False,
        )


def test_normalize_research_plan_data_with_materials():
    """Verify normalize_research_plan_data normalizes raw research materials."""
    raw = {
        "rationale": "High level rationale",
        "topics": [{"topic": "Networking", "description": "Net", "subjects": []}],
        "research_materials": [
            {
                "file_path": "arch.pdf",
                "served_information": "Network architecture",
                "investigation_targets": "Check socket handlers",
                "requires_internet_research": True,
                "internet_research_rationale": "Check TLS 1.3 RFC",
            }
        ],
    }
    normalized = normalize_research_plan_data(raw)
    plan = ResearchPlan.model_validate(normalized)
    assert len(plan.research_materials) == 1
    assert plan.research_materials[0].file_path == "arch.pdf"
    assert plan.research_materials[0].requires_internet_research is True


def test_research_material_service_plain_text(tmp_path: Path):
    """Verify plain text file ingestion without docling."""
    txt_file = tmp_path / "notes.md"
    txt_file.write_text("# Project Notes\n\nSample content", encoding="utf-8")

    service = ResearchMaterialService()
    result = service.ingest_file(txt_file)

    assert result["file_name"] == "notes.md"
    assert result["format"] == "plain_text"
    assert "# Project Notes" in result["content"]


def test_research_material_service_missing_file():
    """Verify missing file raises ResearchMaterialError."""
    service = ResearchMaterialService()
    with pytest.raises(ResearchMaterialError, match="Research material file not found"):
        service.ingest_file("non_existent_file_xyz.pdf")


def test_research_material_service_docling_mock(tmp_path: Path):
    """Verify binary/rich document conversion via docling DocumentConverter."""
    pdf_file = tmp_path / "spec.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 sample bytes")

    mock_conv_res = MagicMock()
    mock_conv_res.document.export_to_markdown.return_value = "# Parsed Docling Spec\n\nExtracted content."

    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_conv_res

    service = ResearchMaterialService(converter=mock_converter)
    result = service.ingest_file(pdf_file)

    assert result["file_name"] == "spec.pdf"
    assert result["format"] == "docling"
    assert result["content"] == "# Parsed Docling Spec\n\nExtracted content."
    mock_converter.convert.assert_called_once()


def test_research_material_service_format_materials_for_context():
    """Verify formatting materials into markdown instruction context."""
    materials = [
        {"file_path": "doc.pdf", "format": "docling", "content": "# Architecture\nContent"},
        {"file_path": "notes.txt", "format": "plain_text", "content": "Text content"},
    ]
    formatted = ResearchMaterialService.format_materials_for_context(materials)
    assert "### Pre-loaded Research Materials" in formatted
    assert "#### Material 1: `doc.pdf` (docling)" in formatted
    assert "#### Material 2: `notes.txt` (plain_text)" in formatted


def test_artifact_service_save_research_materials(tmp_path: Path):
    """Verify ArtifactService saves both original and converted markdown files and manifest."""
    service = ArtifactService(artifacts_dir=tmp_path / "artifacts")

    # Real file on disk to test copying
    real_file = tmp_path / "source.html"
    real_file.write_text("<p>Source HTML</p>", encoding="utf-8")

    materials = [
        {"file_path": str(real_file), "file_name": "source.html", "content": "Source HTML", "format": "docling"},
        {"file_path": "data.json", "file_name": "data.json", "content": '{"k": "v"}', "format": "plain_text"},
    ]
    saved = service.save_research_materials(materials)

    assert len(saved) == 2
    # Verify original files saved
    orig_html = Path(saved[0]["original_artifact_path"])
    orig_data = Path(saved[1]["original_artifact_path"])
    assert orig_html.exists()
    assert orig_html.read_text(encoding="utf-8") == "<p>Source HTML</p>"
    assert orig_data.exists()
    assert orig_data.read_text(encoding="utf-8") == '{"k": "v"}'

    # Verify converted markdown files saved
    html_md = Path(saved[0]["artifact_path"])
    data_md = Path(saved[1]["artifact_path"])
    assert html_md.exists()
    assert html_md.read_text(encoding="utf-8") == "Source HTML"
    assert data_md.exists()
    assert data_md.read_text(encoding="utf-8") == '{"k": "v"}'

    # Verify manifest JSON
    manifest = service.research_materials_dir / "manifest.json"
    assert manifest.exists()
    import json

    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(manifest_data) == 2
    assert manifest_data[0]["original_file_name"] == "source.html"
    assert manifest_data[0]["converted_file_name"] == "source.md"


@pytest.mark.anyio
async def test_step_3_node_and_load_research_material(tmp_path: Path):
    """Verify step_3_node prepares content and load_research_material ingests research materials."""
    doc_file = tmp_path / "notes.txt"
    doc_file.write_text("API Specifications", encoding="utf-8")

    class MockSession:
        id = "session_step3"

    class MockContext:
        state = {
            "research_material_paths": [str(doc_file)],
            "enhanced_user_request": {"user_request": "Build API client"},
        }
        session = MockSession()

    test_art_service = ArtifactService(artifacts_dir=tmp_path / "artifacts")
    with patch(
        "app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes.ArtifactService",
        return_value=test_art_service,
    ):
        ctx = MockContext()
        step3_output = await step_3_node._unwrapped_func(ctx=ctx)
        assert getattr(step3_output, "parts", None) is not None
        assert step3_output.parts[0].text == "Build API client"

        load_output = await load_research_material._unwrapped_func(ctx=ctx, node_input=step3_output)
        assert load_output is step3_output
        assert "research_materials" in ctx.state
        assert "notes.txt" in ctx.state["research_materials"]
        assert "API Specifications" in ctx.state["research_materials"]

        # Verify original and converted files were persisted
        orig_saved = test_art_service.research_materials_dir / "notes.txt"
        conv_saved = test_art_service.research_materials_dir / "notes.md"
        assert orig_saved.exists()
        assert conv_saved.exists()
        assert orig_saved.read_text(encoding="utf-8") == "API Specifications"
        assert conv_saved.read_text(encoding="utf-8") == "API Specifications"


@pytest.mark.anyio
async def test_load_research_material_with_adk_state_object(tmp_path: Path):
    """Verify load_research_material works with real ADK State instances (not dict)."""
    from google.adk.sessions.state import State

    doc_file = tmp_path / "spec.html"
    doc_file.write_text("<h1>System Design</h1>", encoding="utf-8")

    initial_vals = {"research_material_paths": [str(doc_file)]}
    delta: dict = {}
    adk_state = State(value=initial_vals, delta=delta)

    class MockSession:
        id = "session_adk_state"

    class MockContext:
        state = adk_state
        session = MockSession()

    test_art_service = ArtifactService(artifacts_dir=tmp_path / "artifacts")
    with patch(
        "app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes.ArtifactService",
        return_value=test_art_service,
    ):
        ctx = MockContext()
        await load_research_material._unwrapped_func(ctx=ctx)

        assert "research_materials" in ctx.state
        assert "spec.html" in ctx.state["research_materials"]
        assert "research_materials" in delta

        orig_html = test_art_service.research_materials_dir / "spec.html"
        conv_md = test_art_service.research_materials_dir / "spec.md"
        assert orig_html.exists()
        assert conv_md.exists()


def test_cli_code_research_material_file_missing():
    """Verify CLI fails fast with exit code 1 when research material file is missing."""
    res = runner.invoke(app, ["code", "Build feature", "--research-material-file", "non_existent_file.pdf"])
    assert res.exit_code == 1
    assert "Research material file not found" in res.stderr or "Research material file not found" in res.stdout


def test_cli_code_research_material_file_valid(tmp_path: Path):
    """Verify CLI accepts valid research material files and forwards them to workflow.start."""
    sample_file = tmp_path / "spec.md"
    sample_file.write_text("# Spec", encoding="utf-8")

    with patch("app.coddy.cli.code.CodingOrchestratorWorkflow") as mock_wf_cls:
        mock_wf = MagicMock()
        mock_wf_cls.return_value = mock_wf

        async def dummy_start(prompt, **kwargs):
            return "session_123"

        mock_wf.start = dummy_start

        res = runner.invoke(app, ["code", "Build feature", "-r", str(sample_file), "--yes"])
        assert res.exit_code == 0
