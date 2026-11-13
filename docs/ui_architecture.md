# Terminal UI Architecture

Coddy features a reactive, styled terminal user interface powered by [**Rich**](https://github.com/Textualize/rich).

## 1. Design Principles

1. **Decoupled Lifecycle**: Workflow nodes and worker agents trigger high-level UI events (`start_node_view`, `finish_agent_view`, etc.) without managing terminal layout directly.
2. **Transient Status Indicators**: Progress spinners and live agent thinking indicators disappear upon completion, leaving only clean results in terminal history.
3. **Piping & Headless Support**: Diagnostic messages target `stderr` (`console_err`), while live Markdown box rendering can be toggled off via `--no-markdown`.

---

## 2. Core UI Services & Components

### 2.1 UIService

Located in [`app/coddy/utils/services/ui_service.py`](file:///Users/gpfister/Development/Projects/gpfister/coddy/coddy/app/coddy/utils/services/ui_service.py), `UIService` acts as the single entrypoint for console rendering:

- Standard console (`stdout`) and error console (`stderr`).
- Progress indicator manager (`show_progress(description)`).
- Markdown box renderer (`markdown_box(title, markdown_content, border_style)`).
- Interactive user prompt (`ask_user(question, options)`).

### 2.2 AgentExecutionView

Defined in [`app/coddy/utils/ui/agent_view.py`](file:///Users/gpfister/Development/Projects/gpfister/coddy/coddy/app/coddy/utils/ui/agent_view.py), renders live execution telemetry for worker agents:

```
╭─ coding_sanitizer (gemini-3.5-flash-lite) ─ [generating] ─────────────────────╮
│ Latency: 1.45s  │  TTFT: 0.32s  │  Tok/Sec: 48.2  │  Tokens: 2,140 in / 185 out│
├──────────────────────────────────────────────────────────────────────────────┤
│ • [tool_call] read_file: ./README.md                                         │
│ • [thought] Analyzing user requirements against project scope...            │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### 2.3 NodeExecutionView

Defined in [`app/coddy/utils/ui/node_view.py`](file:///Users/gpfister/Development/Projects/gpfister/coddy/coddy/app/coddy/utils/ui/node_view.py), wraps workflow steps in structured boundary panels:

- Tracks start time, end time, and status (`running`, `success`, `failed`).
- Computes human-friendly durations via [`format_duration`](file:///Users/gpfister/Development/Projects/gpfister/coddy/coddy/app/coddy/utils/ui/duration_formatter.py).
- Embeds child `AgentExecutionView` instances during agent deliberation.
