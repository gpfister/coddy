# Coddy: System Overview

## 1. Executive Brief
**Coddy** is a professional-grade coding CLI tool designed to bridge the gap between high-level business requirements and low-level code implementation. Built upon the `google-adk` orchestration principles and powered by an agentic runtime, Coddy specializes in **Recursive Task Decomposition (RTD)**.

The tool breaks complex engineering tasks into granular, validated lists, expanding items into detailed technical documentation. Designed for professional developers, Coddy provides a dual-interface: a powerful CLI and an **ACP (Agent Communication Protocol)** for seamless integration into IDEs like JetBrains.

---

## 2. Business Requirements

### Goals
- **Eliminate Shallow Outputs**: Prevent the "one-shot" limitation of LLMs by forcing recursive expansion of every list item.
- **Structural Integrity**: Enforce a rigid, professional documentation standard for every project through strict JSON schemas.
- **Human-Centric Validation**: Ensure that while the agents work with structured data, the human user interacts with clear, mapped Markdown documentation.

### Target KPIs
- **Expansion Completeness**: Percentage of list items in the `SPECIFICATION` that successfully transition to detailed content (Target: 100%).
- **Mapping Accuracy**: Zero discrepancies between the structured JSON and the human-readable Markdown output.

### The 4 Core Rules
- **R1: The Structured Output Mandate**: All agentic outputs must be valid JSON following the strict project schemas (`extra="forbid"`). No arbitrary keys are permitted.
- **R2: The Mapping Requirement**: For every JSON artifact generated, the system must automatically invoke a **Mapper** utility to generate a human-readable `.md` (Markdown) file for user review.
- **R3: The Recursive Mandate**: An agentic loop is not "Complete" until every item in the pre-generated list has been expanded with technical detail.
- **R4: The Human Gate**: No transition from `SPECIFICATION` to `PLAN`, or `PLAN` to `IMPLEMENTATION`, can occur without human approval of the mapped Markdown.

---

## 3. Use Cases
- **UC-1: The IDE Developer**: A developer in JetBrains uses the ACP to trigger a planning task. The agent runs its recursive loops, and results are streamed back via the ACP.
- **UC-2: The Architect's Prompt**: A user provides a business request via the CLI. Coddy generates a rigid, multi-section specification through recursive expansion.

---

## 4. Agent Architecture & Storage Strategy
Coddy is driven by `coding-orchestrate` (`CodingOrchestratorWorkflow`), an orchestrator that executes a `google-adk` graph workflow. It coordinates specialized worker agents running as native `google-adk` `LlmAgent` instances:
- **Framework**: `google-adk` SDK fully replaces `google-antigravity` across all workflows and agents.
- **Model Flexibility**: Supports a mix of cloud models (Gemini 3.5 Flash Lite, Gemini 3.8 Flash) and local models (e.g., Gemma 4 12B/26B via an OpenAI-compatible endpoint at `http://localhost:1234/v1`).
- **`coding-sanitize`**: Normalizes input and user requests (`SanitizedUserRequest`) with low thinking budget.
- **`coding-research-plan`**: Breaks down sanitized user requests into topics and subjects (`ResearchPlan`) with medium thinking budget.
- **Tiered Storage Architecture**:
  - **ADK Sessions & State (Working Memory)**: Managed via SQLite (`~/.coddy/data.db`).
  - **Artifacts**: Stored on disk under `~/.coddy/<session_id>/artifacts/`.
  - **Long-Term Memory & Knowledge Graph**: Managed via LadybugDB (`~/.coddy/memory.db`) (current FalkorDBLite/Qdrant GraphRAG scheduled for migration).
  - **Execution & Token Metrics**: Managed via DuckDB (`~/.coddy/metrics.db`).


