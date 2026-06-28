# Changelog

## 0.3.1 - 2026-06-27

### Added

- Added `init.py`, a drop-in initializer. Place the starter folder inside a project and run `python3 init.py` (Windows `py -3 init.py`) to point the board at the holding project, write `CLAUDE.md` and `AGENTS.md` entry-point pointers into that project so Claude Code and Codex auto-load the workflow, pick a free port, and start the backend. Supports `--no-start`, `--port N`, and an explicit project-root path; pointer writes preserve existing files and are idempotent.

### Changed

- Renamed the agent entry-point document `AGENTS.md` to `TEAMWORK.md`.

### Removed

- Removed the Web Front-End Auditor role and the entire upstream handoff-intake subsystem, narrowing the starter to its three-role core (Planner, Worker, Reviewer). This deleted `roles/web-frontend-auditor.md`, the handoff endpoints/state/auto-processing in `task-board/server.py`, the handoff-intake panel and agent-graph nodes in `task-board/viewer.html`, the `sourceHandoffs` task field, and related documentation.
- Removed the bundled regression test scripts under `task-board/` (`test_*.py`).

### Notes For Upgrading Existing Projects

- Copy the updated `task-board/server.py`, `task-board/viewer.html`, `workflow/workflow-overview.md`, `roles/planner.md`, `TEAMWORK.md`, `init.py`, `VERSION`, and `CHANGELOG.md`.
- If you used the Web Front-End Auditor or handoff intake, those features are gone; remove any `handoffs/` inputs and drop the `sourceHandoffs` field from existing tasks in `task-board/board.json`.
- Keep project-specific `task-board/config.json`, `task-board/board.json`, and `task-board/agent-color-schema.json` unless you intentionally want starter defaults.

## 0.3.0 - 2026-06-24

### Added

- Added PID-aware spawned-agent tracking so hidden non-interactive Worker and Reviewer processes can be shown as running, exited, reused, or unknown.
- Added latest spawned-agent log previews to `/api/agents`, alongside registered active agents and pending spawned processes.
- Added a top agent strip to the board viewer. To Do and Review lanes show registered and spawned agents as compact hoverable tabs; Done keeps matching blank spacing.
- Added compact hover logs for agent tabs so owners can inspect what a hidden spawned agent last printed without opening the log file directly.
- Added version tracking with `VERSION` and this changelog.

### Changed

- Auto-dispatch now ignores exited or PID-reused spawned processes when deciding whether another Worker or Reviewer can be spawned.
- Auto-dispatch persists cleaned pending-spawn state even when no new agent is spawned.
- The viewer keeps the existing three-column layout while separating agent activity tabs from the main task cards.
- Documentation now calls out compact role-specific read APIs, hidden spawned process logs, PID-backed pending-agent status, and the `/api/agents` response shape.

### Notes For Upgrading Existing Projects

- Copy the updated `task-board/server.py`, `task-board/viewer.html`, `workflow/api-guide.md`, `workflow/workflow-overview.md`, `AGENTS.md`, `VERSION`, and `CHANGELOG.md`.
- Keep project-specific `task-board/config.json`, `task-board/board.json`, and `task-board/agent-color-schema.json` unless you intentionally want starter defaults.
- Runtime files such as `task-board/task-board-api.log`, `task-board/task-board-viewer.log`, `task-board/active-agents.json`, `task-board/agent-dispatch-settings.json`, and `task-board/spawned-agent-logs/` should remain local runtime artifacts.
