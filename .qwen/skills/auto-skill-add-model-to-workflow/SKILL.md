---
name: add-model-to-workflow
description: Add a new CLI model/tool (e.g. qwen, gemini) as a spawnable agent option across all workflow config and role files.
source: auto-skill
extracted_at: '2026-06-24T19:41:10.795Z'
---

# Add a New Model to the Agent Workflow

When adding a new CLI tool as a spawnable model in the agent workflow, these files must all be updated:

## Files to Update

### 1. `task-board/agent-dispatch-settings.json`
- Add the model name to the `"commands"` block, e.g. `"qwen": "qwen"`
- Optionally set `"model"` on `worker` and/or `review` roles to the new model name
- The server reads this at runtime to know which binary to spawn per role

### 2. `task-board/config.json`
- Add a `<name>Command` key under `"spawn"`, e.g. `"qwenCommand": "qwen"`
- The server uses this as the default command path for the model

### 3. Role files in `roles/`
- Update `roles/planner.md`, `roles/worker.md`, and `roles/reviewer.md`
- Each has a registration line mentioning valid model values: `model` (`claude`, `codex`, or `<new>`)
- Add the new model name to the parenthetical list

### 4. `AGENTS.md`
- Update the compatibility statement (e.g. "compatible with the Claude, Codex, and Qwen CLIs")
- Update the `POST /api/register-agent` docs line listing valid model values

## Server-Side Support (already built in)

The server (`task-board/server.py`) already supports adding models via:
- `SPAWNABLE_TOOLS` set — must include the model name
- `normalize_agent_model()` — must have a mapping for the model's aliases (e.g. `"qwen"`, `"qwen-code"` → `"qwen"`)
- `QWEN_COMMAND`-style fallback variable read from `config.json` spawn section

If the server doesn't already know the model, add it to those three locations as well.

## Spawn Command Quirks (per-model flags in `server.py`)

Each CLI tool has different flags for non-interactive headless spawning. When adding a new model, check its `--help` output and update the spawn code in `server.py` accordingly:

### Agent spawn (`~line 3168`)
```python
if tool == "codex":
    args.extend(["exec", "--skip-git-repo-check", start_phrase])
else:
    args.extend(["-p", start_phrase])
    if tool == "qwen":
        args.extend(["-y", "-o", "stream-json"])  # YOLO + detailed JSON event output
```

### Health check (`~line 1968`)
Same pattern — add model-specific flags after `-p`. Health checks don't need `stream-json` since they're short-lived.

### stdin handling
- **Always use `subprocess.DEVNULL` for stdin.** Do NOT pipe the prompt to stdin if `-p` already delivers it — the agent receives the prompt twice and cancels with "Operation cancelled".
- This was a real bug: qwen spawns were writing `start_phrase` to stdin in addition to passing it via `-p`, causing every spawned agent to fail silently.

### Quick reference of per-model flags

| Model  | Non-interactive prompt | Auto-approve | Output format | stdin   |
|--------|----------------------|--------------|---------------|---------|
| claude | `-p <prompt>`        | `-y` (implicit) | text (default) | DEVNULL |
| codex  | `exec --skip-git-repo-check <prompt>` | N/A | text (verbose by default) | DEVNULL |
| qwen   | `-p <prompt> -y -o stream-json` | `-y` (explicit, required) | `stream-json` (see below) | DEVNULL |

Always test a new model with a manual CLI invocation first:
```bash
<cli> -p "simple test prompt" -y 2>&1 | head -20
```
…before relying on the server spawn path.

## Detailed Agent Logging (Critical for Debugging)

Different CLIs produce wildly different levels of log detail. Codex is naturally verbose — its logs show every tool call, command, full output, and reasoning. Qwen's default text output is extremely concise (just the final response), making agents appear stuck.

### The stream-json solution (for qwen)

Qwen supports `-o stream-json` which outputs every event as a JSON line: system init, thinking blocks, tool_use (name + input), tool_result (full output), text responses, and result (with duration/token stats).

**Architecture:** `qwen stdout (JSONL) → Python formatter subprocess → log file`

1. **Formatter script**: `task-board/format_qwen_log.py` — reads stream-json from stdin, writes human-readable text to stdout. Handles all event types with tool-specific formatting (shows commands, file paths, edit diffs, search patterns, etc.)
2. **Spawn pipeline**: For qwen, use `subprocess.PIPE` for stdout instead of writing directly to the log file. A daemon thread starts a formatter subprocess (`python3 -u format_qwen_log.py`) that reads from the pipe and writes formatted output to the log file. stderr goes directly to the log file for startup warnings.

```python
# In the spawn code (qwen branch):
formatter_script = str(Path(__file__).parent / "format_qwen_log.py")
process = subprocess.Popen(
    args, cwd=working_dir, env=env,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,    # pipe to formatter, not log file
    stderr=log_file,           # warnings go directly to log
    ...
)
# Daemon thread runs formatter and closes pipe/file when done
```

### Environment variables for qwen spawns

Set in `agent_subprocess_env()` when `tool == "qwen"`:
- `FORCE_COLOR=0` — prevents ANSI color codes in log files
- `NO_COLOR=1` — additional color suppression
- `QWEN_CODE_DEBUG=1` — enables debug-level output from qwen internals

### Other qwen CLI flags worth knowing

- `-d` / `--debug` — writes a comprehensive debug log to `~/.qwen/debug/<session-id>.txt` (useful for manual debugging but not integrated into the spawn pipeline)
- `--json-file <path>` — dual output mode: TUI on stdout, structured JSON events to a file (didn't work reliably in headless/spawned mode during testing)
- `--max-tool-calls N` — cap tool calls to prevent runaway agents
- `--openai-logging` — logs raw API calls (useful for API-level debugging)

### When adding a new model, check its output verbosity

Run `<cli> --help` and look for: `--output-format`, `--verbose`, `--debug`, `--json`, `--stream`. If the default output is too concise for log files, build a similar formatter pipeline.

## Verification

After updating, restart the task-board server and check:
- `GET /api/agents` returns the new model in spawn entries
- The viewer's spawn button can select the new model
- A test spawn launches the correct CLI binary
- The spawned agent's log file shows it registered and claimed a task (not just "Operation cancelled")
- For qwen: the log file contains detailed tool calls, commands, results, and thinking (not just a final summary line)
