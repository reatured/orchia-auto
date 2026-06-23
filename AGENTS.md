# Agent Instructions

This project uses a simple JSON-backed task board with three separate agent roles: **Planner**, **Worker**, and **Reviewer**. The Planner turns requirements into tasks, Workers implement tasks, and Reviewers review completed work. The workflow is compatible with both the Claude and Codex CLIs.

> **New to this repo?** This is a reusable starter. Edit `task-board/config.json` and the role files for your project — see `README.md` ("Adapt to your project").

## Start Here

- Workflow overview: `workflow/workflow-overview.md`
- Planner role: `roles/planner.md`
- Worker role: `roles/worker.md`
- Reviewer role: `roles/reviewer.md`
- Task board API guide: `workflow/api-guide.md`
- Task board source of truth: `task-board/board.json`
- Project config: `task-board/config.json`
- Dispatch settings: `task-board/agent-dispatch-settings.json`

## Agent Start Phrases

Use these phrases at the start of a new chat to load the intended role:

| Start phrase | Role file |
| --- | --- |
| `load as planner` | `roles/planner.md` |
| `load as worker` | `roles/worker.md` |
| `load as reviewer` | `roles/reviewer.md` |

## Backend (Task Board Server)

Start the local task-board backend (Python 3.10+, no third-party dependencies):

```bash
# macOS / Linux / Git Bash
cd <path-to>/agent-workflow-starter
python task-board/server.py
```
```powershell
# Windows PowerShell
cd <path-to>\agent-workflow-starter
python task-board\server.py
```

It serves the board API and the read-only viewer at the host/port from `task-board/config.json` (default `http://127.0.0.1:4177/viewer.html`).

When the backend is running, use its API instead of manually editing or moving tasks in JSON:

- `GET /api/board`, `GET /api/worker-board`, `GET /api/review-board`
- `GET /api/task-detail?taskId=TASK-YYYYMMDD-###`, `GET /api/duplicate-scan`, `GET /api/agents`
- `POST /api/register-agent`, `POST /api/heartbeat-agent`, `POST /api/unregister-agent`
- `POST /api/add-task`, `POST /api/update-task`, `POST /api/claim-task`, `POST /api/unclaim-task`
- `POST /api/move-to-review`, `POST /api/claim-review`, `POST /api/approve-review`, `POST /api/request-changes`
- `POST /api/return-to-review`, `POST /api/archive`
- `POST /api/delete-task` (cleanup only — not for normal workflow)

For payload shapes, examples (curl + PowerShell), and error handling, read `workflow/api-guide.md`.

Every agent that talks to the API registers at chat start with `POST /api/register-agent` (`personalName`, `model` = `claude` or `codex`, `role`), receives an `agentId`, and includes that `agentId` in every later payload. Workers and Reviewers also heartbeat after claiming/moving a task and unregister before ending the chat.

If the backend is not running, agents coordinate by editing `task-board/board.json` directly using the same role rules.

## Hard Role Separation

Planner, Worker, and Reviewer are separate agents. Agents do not switch roles inside the same chat. See `workflow/workflow-overview.md` for the full rules, the six board columns (`todo`, `claimed`, `review`, `reviewing`, `done`, `archived`), and the conflict rule.
