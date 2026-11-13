---
name: coddy-ui-management
description: Guidelines, architecture, and standards for terminal UI presentation, Rich consoles, Live views, progress indicators, panels, and activity streams in Coddy.
---

# Coddy UI Management Skill

This skill guides engineers and agents in developing, extending, and maintaining terminal user interface (UI) components within Coddy.

## 1. Architectural Overview & Single Responsibility

Coddy provides rich, interactive terminal feedback via [**`UIService`**](../../../app/coddy/utils/services/ui_service.py).
The UI layer is decoupled from workflow orchestration and worker agent logic:

- **Orchestrators and Plugins** trigger UI lifecycle events (`start_node_view`, `start_agent_view`, `finish_agent_view`, `finish_node_view`, `markdown_box`).
- **`UIService`** manages consoles, live rendering buffers, status spinners, and user input prompts.
- **View Components** ([`AgentExecutionView`](../../../app/coddy/utils/ui/agent_view.py) and [`NodeExecutionView`](../../../app/coddy/utils/ui/node_view.py)) encapsulate display layout, token metrics, activity streams, and status styling.
- **Formatting Helpers** ([`format_duration`](../../../app/coddy/utils/ui/duration_formatter.py)) provide uniform duration strings (`<1s`, `1.23s`, `2m 14s`).

---

## 2. Core UI Components

### 2.1 UIService Singleton

The central UI entrypoint is accessed via `get_ui_service()` from `app.coddy.utils.services`:

```python
from app.coddy.utils.services import get_ui_service

ui = get_ui_service()
```

Key capabilities:
- `start_node_view(node_name)` / `finish_node_view(node_name, status)`: Wraps workflow graph node execution in a visual context.
- `start_agent_view(agent_name, model, step_name)` / `finish_agent_view(agent_name, status)`: Displays live status, token counts, latency, and activity items.
- `show_progress(description)`: Context manager displaying a transient Rich status spinner.
- `markdown_box(title, markdown_content, border_style)`: Displays rendered Markdown in a framed box.
- `ask_user(question, options)`: Prompts the user interactively with numbered multiple choices.

### 2.2 AgentExecutionView

Defined in [`app/coddy/utils/ui/agent_view.py`](../../../app/coddy/utils/ui/agent_view.py), this component renders:
1. **Header**: Agent name, model ID, and current execution phase.
2. **Metrics Grid**: Latency, time-to-first-token (TTFT), tokens per second (tok/sec), and prompt/candidate token counts.
3. **Activity Log**: Chronological stream of agent events (tool calls, reasoning blocks, streaming updates).

### 2.3 NodeExecutionView

Defined in [`app/coddy/utils/ui/node_view.py`](../../../app/coddy/utils/ui/node_view.py), this component manages the outer pipeline step visual frame:
- Displays node status (`running`, `success`, `failed`).
- Computes execution duration via [`format_duration`](../../../app/coddy/utils/ui/duration_formatter.py).
- Embeds child `AgentExecutionView` when an agent executes within the node.

---

## 3. Terminal Live Display Invariants

1. **Transient Spinners**: Progress indicators must never leak into persistent console history after completion; use transient `Status` or `Live` contexts with `transient=True` when appropriate.
2. **Markdown Suppression**: Respect `display_markdown=False` (configured via CLI `--no-markdown`) for quiet terminal outputs or headless pipelines.
3. **Stderr Isolation**: Diagnostic errors and traceback panels must always target `console_err` (`sys.stderr`) to preserve `stdout` clean for piped workflows.
4. **Hermetic Testing**: Unit tests must pass mock consoles (`Console(file=io.StringIO(), force_terminal=False)`) to verify UI output without terminal escape sequence pollution.
