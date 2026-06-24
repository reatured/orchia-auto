# Changelog

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
