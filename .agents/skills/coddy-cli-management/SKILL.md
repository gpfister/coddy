---
name: coddy-cli-management
description: Guidelines, command architecture, option handling, and standards for the Typer CLI commands, subcommands, arguments, and piping in Coddy.
---

# Coddy CLI Management Skill

This skill guides engineers and agents in developing, extending, and maintaining the command-line interface (CLI) for Coddy.

## 1. Architectural Structure & Subcommands

Coddy uses [**`Typer`**](https://typer.tiangolo.com/) for CLI routing. The entrypoint is [`app/coddy/app.py`](../../../app/coddy/app.py) which registers subcommands and command groups:

```
coddy
├── code [PROMPT]            # Run workflow on user prompt, file, or piped stdin
├── graphrag                 # GraphRAG knowledge base management
│   ├── ingest [--force]     # Index codebase AST and documentation
│   └── status               # Inspect cache, commit SHA, and entity counts
├── metrics                  # DuckDB execution and token telemetry
│   ├── summary [-s] [-n]    # High-level model and session analytics
│   ├── sessions [-s] [-n]   # Detailed session records and steps
│   └── tools [-s] [-n]      # Tool invocation counts, latency, and errors
└── schemas                  # Dump JSON schemas for specifications and plans
```

---

## 2. Command Implementations

### 2.1 Code Command (`coddy code`)

Located in [`app/coddy/cli/code.py`](../../../app/coddy/cli/code.py):
- **Flexible Input Routing**:
  - Direct positional argument: `coddy code "Build a rate limiter"`
  - Stdin stream / pipe: `cat prompt.md | coddy code -`
  - Dedicated file option: `coddy code --file prompt.md`
- **Workflow Options**:
  - `--yes` (`-y`): Auto-approve mode bypassing interactive human approval gates.
  - `--markdown / --no-markdown` / `--display-markdown`: Toggle live Markdown rendering in terminal panels.
  - `--research-material-file` (`-r`): Ingest research material files (text, Markdown, PDF, Office docs, images) into `coding-research-planner` context. May be specified multiple times.

### 2.2 GraphRAG Subcommands (`coddy graphrag`)

Located in [`app/coddy/cli/graphrag.py`](../../../app/coddy/cli/graphrag.py):
- `coddy graphrag ingest`: Runs [`GraphRAGService.run_ingestion_pipeline`](../../../app/coddy/graphrag/services/graphrag_service.py) on repository AST, docling chunks, and intent links. Caches results under `.cache/graphrag/<commit_sha>/`.
- `coddy graphrag status`: Reports cache validity, current git commit SHA, node counts, and vector store indexing status.

### 2.3 Metrics Subcommands (`coddy metrics`)

Located in [`app/coddy/cli/metrics.py`](../../../app/coddy/cli/metrics.py):
- Queries persistent DuckDB telemetry at `~/.coddy/metrics.db` via [`MetricsService`](../../../app/coddy/agentic/services/metrics_service.py).
- `summary`: Prints Rich formatted tables for model latency, tokens/sec, and session totals.
- `sessions`: Lists recent execution sessions or inspects step-by-step timings for a given `--session-id`.
- `tools`: Aggregates tool call counts, durations, and error rates.

### 2.4 Schema Dumping (`coddy schemas`)

Located in [`app/coddy/app.py`](../../../app/coddy/app.py):
- Outputs formatted JSON Schema specifications for `Specification`, `Plan`, `SanitizedUserRequest`, and `ResearchPlan`.

---

## 3. CLI Conventions & Guidelines

1. **Option Consistency**: Use kebab-case for CLI flags (`--session-id`, `--no-markdown`, `--auto-approve`).
2. **Help Documentation**: Every command and option must provide a concise, user-facing `help="..."` string.
3. **Exit Codes**:
   - `0`: Success.
   - `1`: User/Environment errors (missing required input, file not found, pre-flight check failure).
   - `2`: CLI argument parsing error (enforced by Typer).
4. **Clean Stderr for Diagnostics**: Informational status and error messages must target `stderr` or `UIService.console_err` so `stdout` remains pipe-friendly.
