---
name: coddy-coding-standards
description: Coding standards, style conventions, type safety practices, error handling policies, and testing guidelines for the Coddy repository.
---

# Coddy Coding Standards & Testing Guidelines

This skill documents the engineering and architectural conventions required across the Coddy codebase.

## 1. Python Environment & Dependencies

* **Runtime**: Python `>= 3.12`. Utilize modern syntax features (e.g. built-in generics `list[str]`, `dict[str, Any]`, type union syntax `X | Y`, and pattern matching).
* **Package Management**: Use `uv` exclusively:
  ```bash
  uv run pytest
  uv run ruff check .
  uv run coddy --help
  ```
* Do not introduce dependencies without pinning minimum versions in `pyproject.toml`.

---

## 2. Type Safety & Pydantic Conventions

### Strict Typing
* All functions, class methods, and module-level variables must include complete type annotations.
* Avoid bare `Any` unless interfacing with dynamic third-party libraries; use specific generic types or TypeVars wherever possible.

### Pydantic v2 Invariants
* All schema models must use Pydantic v2 syntax.
* Every model **must** forbid unexpected keys to enforce Rule R1:
  ```python
  from pydantic import BaseModel, ConfigDict, Field


  class ValidatedModel(BaseModel):
      model_config = ConfigDict(extra="forbid")

      id: str = Field(description="Unique entity identifier")
      score: float = Field(default=0.0, ge=0.0, le=1.0)
  ```

---

## 3. Error Handling & Pre-flight Checks

* **Fail Early, Fail Loudly**: Operations depending on local daemons (such as the local LLM server at `http://localhost:1234/v1`) must execute pre-flight checks via [`verify_models`](../../../app/coddy/helpers/pre_flight_checks.py) before initiating workflows.
* **Graceful Diagnostics**: Never display raw, unhandled tracebacks to CLI users for anticipated environment errors (e.g. server offline or missing model). Return structured error objects in ACP mode and formatted Rich panels in CLI mode.
* **JSON Extraction Resilience**: When extracting structured JSON from LLM outputs, always strip reasoning blocks (`<think>...</think>`) and markdown fences using [`extract_json_payload`](../../../app/coddy/helpers/json_helpers.py).

---

## 4. Testing Guidelines

### Unit Test Hermeticity
* Unit tests **must not** make real network requests or contact local LLM servers.
* Leverage hermetic tests and dependency injection without live LLM calls:
  ```python
  from app.coddy.agentic.workflows.coding_orchestrate.workflow import (
      CodingOrchestratorWorkflow,
  )


  def test_orchestration_hermetic():
      workflow = CodingOrchestratorWorkflow()
      assert workflow.name == "coding_orchestrator_workflow"
      assert len(workflow._workflow.edges) == 1
  ```

### Test Organization
* Place hermetic tests under `tests/`:
  * `test_agent_view.py`: Terminal execution view layouts, token metrics, and activity streams.
  * `test_agents.py`: Agent configurations and orchestration logic.
  * `test_cli.py`: Typer CLI entrypoints, options, and exit codes.
  * `test_config.py`: Model and environment configuration models.
  * `test_graphrag.py`: AST extraction, docling chunking, and intent graph caching.
  * `test_mappers.py`: Deterministic markdown mapper rendering.
  * `test_metrics_service.py`: DuckDB session, step, and tool metrics tracking.
  * `test_model_verifier.py`: Local endpoint validation logic.
  * `test_schemas.py`: Schema validation, round-trip serialization, and `extra="forbid"` tests.
  * `test_session_service.py`: SQLite session and state management.
  * `test_tools.py`: Agent tools execution and schemas.
  * `test_ui_service.py`: Console UI service, progress, and panels.
  * `test_workflows.py`: ADK graph workflow step nodes and callback state propagation.
