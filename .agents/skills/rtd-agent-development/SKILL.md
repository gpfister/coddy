---
name: rtd-agent-development
description: Guidelines, architectural patterns, and standards for creating, modifying, and testing Recursive Task Decomposition (RTD) agents, graph workflows, Pydantic schemas, and markdown mappers in Coddy.
---

# RTD Agent Development Skill

This skill guides engineers and agents in developing, extending, and maintaining multi-agent components within Coddy's Recursive Task Decomposition (RTD) system.

## 1. System Invariants & Philosophy

Every agent in Coddy must respect the **Core Invariant Rules**:
1. **Rule R1 (Strict Schemas)**: All generative outputs from worker agents MUST conform to explicit Pydantic schemas with `model_config = ConfigDict(extra="forbid")`. Unstructured JSON or conversational markdown is forbidden.
2. **Rule R2 (Automated Markdown Mapping)**: For every structured JSON artifact, there must be a deterministic Python mapper that generates human-readable Markdown without making network or LLM calls.
3. **Rule R3 (Recursive Completeness)**: Complex requirements must never be output as shallow summaries. They must be broken into lists of items, and each item recursively expanded.
4. **Rule R4 (Human Approval Gates)**: Execution transitions between phases require explicit human approval via interactive callbacks or ACP events.
5. **Rule R5 (Enforced Structured Output & Grounding)**: Every worker agent MUST enforce its Pydantic output schema via `output_schema` in `google.adk.agents.LlmAgent` (with mix of Cloud Gemini and Local Gemma models), ground deliberations in sanitized requirements, and leverage ADK's native `Session` and `State` engine.
6. **Rule R6 (No Filesystem Read/List Tools)**: LLM agents must NEVER be provided filesystem read or directory listing tools (such as `read_file`, `list_files`, or `read_file_snippet`). Codebase and documentation exploration is conducted strictly through GraphRAG tools and FunctionNode context injection.

---

## 2. Graph Workflow Architecture (coding-orchestrate)

The workflow orchestrator (`CodingOrchestratorWorkflow` in [`app/coddy/agentic/workflows/coding_orchestrate/workflow.py`](../../../app/coddy/agentic/workflows/coding_orchestrate/workflow.py)) coordinates the RTD pipeline (`START -> step_1_node -> _coding_sanitize_agent -> step_2_node -> _coding_ambiguity_clarifier_agent -> step_3_node -> _coding_research_plan_agent -> Episodic Research Loop -> step_4_node -> step_5_node -> _finalize_output`).

### Graph Decision Nodes, Routers & Associate Coding

When workflows require conditional branching or iterative loops (e.g., episodic research loops), decisions must be expressed directly in workflow edges using tuple routing maps:

```python
(
    setup_episodic_research_context,
    coding_researcher,
    has_remaining_research,   # --> this is a @route / :DecisionNode / :Router
    {
        "YES": setup_episodic_research_context, 
        "NO": (
            # ...
        ), 
    },
),
```

> [!IMPORTANT]
> **Decision Nodes (:DecisionNode, :Router) & Conditional Edges (CALLS_IF)**:
> - **Node Taxonomy**: Any node or function that inspects context state and selects an execution route (by returning an `Event(actions=EventActions(route=...))`) is classified as both `:DecisionNode` and `:Router`.
> - **Edge Taxonomy**: All conditional transitions exiting a decision node MUST use the relationship type `CALLS_IF` and document the descriptive `logical_text` (plain-language or boolean condition) alongside the `route` key.
> - **Complete Workflow Documentation in intents.json**: `docs/intents.json` MUST document the **entire workflow** end-to-end, including all linear steps, worker agent invocations, decision nodes (`:DecisionNode`, `:Router`), and conditional branches (`CALLS_IF`).

### Native ADK Nodes, Callbacks & Tiered Storage

The orchestrator owns workflow routing, state transitions, telemetry, and user interaction. Responsibilities and persistence are partitioned cleanly:

| Tier / Subsystem | Storage / Location | Responsibilities |
| :--- | :--- | :--- |
| **Workflow Engine** | `Workflow` / `BaseAgent` | Native ADK graph execution chaining `LlmAgent` instances with callbacks. |
| **Session & State** | SQLite (`~/.coddy/data.db`) | Native ADK `Session` and `State` storage for cross-agent variables. |
| **Artifacts** | Disk (`~/.coddy/<session_id>/artifacts/`) | Typed JSON models (`sanitized_user_request.json`, `research_plan.json`) and rendered Markdown artifacts (`SANITIZED_USER_REQUEST.md`, `RESEARCH_PLAN.md`) via `ArtifactService`. |
| **Long-Term Memory** | LadybugDB (`~/.coddy/memory.db`) | GraphRAG knowledge graph and semantic memory store. |
| **Metrics** | DuckDB (`~/.coddy/metrics.db`) | Token counts, execution durations, and step performance analytics. |

### Orchestrator vs. Worker Invariant

> [!IMPORTANT]
> **Orchestrators and callbacks own state capture; Workers are declarative LlmAgents.**
> Worker agents do not manage file persistence directly. They define `output_schema`, system instructions, and tool sets. The workflow callbacks (`on_after_coding_sanitize_agent`, `on_after_coding_research_plan_agent`) extract structured outputs and persist state into `context.state` and `ArtifactService`.

---

## 3. Worker Agent Architecture (coding-sanitize & coding-research-plan)

Specialized worker agents inherit directly from `google.adk.agents.LlmAgent`.

### Worker Directory & Code Structure

Every worker agent lives in its own dedicated package under `app/coddy/agentic/agents/<agent_name>/`:

```
app/coddy/agentic/agents/<agent_name>/
├── agent.py              # Worker agent subclassing LlmAgent
└── INSTRUCTIONS.md        # System prompt, persona disregard directives, schema rules
```

Worker schemas and mappers reside under `app/coddy/agentic/schemas/` and `app/coddy/agentic/mappers/`. Agent tools reside under `app/coddy/agentic/tools/` as standalone functions.

---

## 4. Agent Configuration Matrix

| Agent | Framework | Model ID (Cloud / Local) | Context Size | Reasoning / Budget | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`coding_orchestrator_workflow`** | `google-adk` (`Workflow`) | Graph Engine | N/A | N/A | Central multi-agent orchestrator & callback telemetry |
| **`coding_sanitizer`** | `google-adk` (`LlmAgent`) | `gemini-3.5-flash-lite` / `google/gemma-4-12b` | 256K | `ThinkingLevel.LOW` | Input sanitization, ambiguous terms extraction, and local instructions sanitization |
| **`coding_research_planner`** | `google-adk` (`LlmAgent`) | `gemini-3.8-flash` / `google/gemma-4-26b-a4b-qat` | 256K | `ThinkingLevel.MEDIUM` | Heavy reasoning decomposition of user request into subjects grouped by topic |

---

## 5. Creating & Modifying Schemas (Rule R1)

Schemas reside in [`app/coddy/agentic/schemas/`](../../../app/coddy/agentic/schemas/):
* Always specify `model_config = ConfigDict(extra="forbid")` on all models.
* Use descriptive `Field(description="...")` attributes to guide model generation.
* Implement a defensive `normalize_*_data` function to normalize loose JSON outputs (handling synonym keys and string lists).

---

## 6. Markdown Mappers (Rule R2)

Mappers reside in [`app/coddy/agentic/mappers/`](../../../app/coddy/agentic/mappers/):
* Must be purely deterministic functions taking a Pydantic schema instance and returning a Markdown string.
* Must not make network or LLM calls.
* Must format output with clear headings, tables, and lists suitable for terminal rendering and human review.

---

## 7. Testing Patterns & Hermetic Execution

Unit tests must never contact real LLM endpoints or external networks:
* Test workflow orchestration hermetically by initializing `CodingOrchestratorWorkflow` and asserting graph structure and callback outputs:

```python
from app.coddy.agentic.workflows.coding_orchestrate.workflow import (
    CodingOrchestratorWorkflow,
)


def test_workflow_initialization():
    workflow = CodingOrchestratorWorkflow()
    assert workflow.name == "coding_orchestrator_workflow"
    assert len(workflow._workflow.edges) == 1
```
