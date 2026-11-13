# CLI Reference

The `coddy` command-line tool provides a streamlined interface for software engineering workflows.

## Execution Command

```bash
uv run coddy code [PROMPT] [OPTIONS]
```

## `code` Command Arguments and Options

| Argument / Flag | Short | Type | Description |
| :--- | :--- | :--- | :--- |
| `PROMPT` | | `string` | User prompt for the engineering task, or `-` to read from standard input. |
| `--file` | `-f` | `path` | Path to a markdown/text file containing the task request. |
| `--yes` | `-y` | `flag` | Automatically approve review gates (non-interactive mode). |
| `--markdown / --no-markdown` | | `flag` | Display live rendered Markdown panels during execution (default: true). |
| `--help` | | `flag` | Show help message. |

## Subcommands

- `uv run coddy code "<prompt>"`: Executes the workflow on the provided prompt string.
- `cat prompt_file.md | uv run coddy code -`: Reads requirements from stdin and executes the workflow.
- `uv run coddy code --file prompt_file.md`: Reads requirements from a specified file.
- `uv run coddy graphrag ingest [--force]`: Ingests codebase AST, docs, and architectural intents into `.cache/graphrag/<commit_sha>/`.
- `uv run coddy graphrag status`: Displays GraphRAG cache presence, git commit SHA, tree dirtiness, and entity counts.
- `uv run coddy metrics summary [-s <id>] [-n <limit>]`: Displays aggregated model performance and session overviews.
- `uv run coddy metrics sessions [-s <id>] [-n <limit>]`: Lists execution sessions or inspects step-by-step timings.
- `uv run coddy metrics tools [-s <id>] [-n <limit>]`: Inspects tool invocation counts, durations, and error rates.
- `uv run coddy schemas`: Dumps the JSON schemas for `Specification`, `Plan`, `SanitizedUserRequest`, and `ResearchPlan`.

## Examples

### 1. Interactive Workflow from Command Line
```bash
uv run coddy code "Build a real-time collaborative whiteboard"
```
Coddy guides you through:
1. Local model pre-flight check on `http://localhost:1234/v1`.
2. Process indicator spinner while running the step.
3. Clean Markdown output rendered directly to the terminal.
4. Session state managed in SQLite (~/.coddy/data.db) and artifacts saved in ~/.coddy/<session_id>/artifacts/.

### 2. Piping Requirements File via Stdin
```bash
cat requirements.md | uv run coddy code -
```

### 3. Automated Non-Interactive Run
```bash
uv run coddy code "Implement Redis distributed lock" --yes
```

### 4. GraphRAG Status and Cache Management
```bash
# Check cache status and entity statistics
uv run coddy graphrag status

# Force re-ingestion of the codebase
uv run coddy graphrag ingest
```

