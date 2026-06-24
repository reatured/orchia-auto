# Workflow Overview

This is a simple, JSON-backed task board for coordinating multiple AI agents on one project. It has three roles: **Planner**, **Worker**, and **Reviewer**. It works with both the Claude and Codex CLIs.

> This is the generic three-role core. Projects can extend it (see "Extending the workflow" at the end), but start here.

## Source of Truth

The task board JSON is the source of truth:

- `task-board/board.json`

The visual board is a read-only display of that JSON for the owner:

- `task-board/viewer.html`

Agents do not read, parse, or update the HTML viewer during normal workflow. They coordinate by updating `board.json` (directly, or through the API when the backend is running).

When the local task-board backend is running, agents should use its API for card creation, edits, and status changes:

- `workflow/api-guide.md`

Every agent that talks to the task board API registers at the start of the chat by calling `POST /api/register-agent` with `personalName`, `model` (`claude` or `codex`), and `role`. The server returns an `agentId` (for example `agt_a1b2c3`). Send that `agentId` in every later API payload — it is the contract key. `personalName` is a short lowercase token (pick the first unused name from `task-board/agent-color-schema.json#personalNamePool`, or use the one the owner or the Spawn button gave you). The backend records the resolved display name in `lastApiActor`, each task's `apiHistory`, and the board-level `apiAuditLog`. The HTML viewer renders each agent as a colored chip: the model determines the background color (orange for Claude, blue for Codex) and the role determines the border color.

The backend writes an append-only API audit log at `task-board/task-board-api.log` (JSON Lines: request time, method, endpoint, task ID, agent name, status, error). The viewer uses separate `/viewer/...` endpoints and writes to `task-board/task-board-viewer.log`, so viewer activity does not mix with agent activity. These logs are for troubleshooting only; the source of truth remains `board.json`.

The viewer's Spawn buttons launch Worker and Reviewer agents as hidden non-interactive CLI processes (they do not open terminal tabs). Each spawned process receives the current `backendBaseUrl` and writes output to `task-board/spawned-agent-logs/`. The backend exposes spawned processes through `GET /api/agents` with PID-backed status (`running`, `exited`, `pid-reused`, or `unknown`) and latest log previews. The viewer also has optional auto-dispatch controls per role (selected model, max active agents, Auto toggle) stored in `task-board/agent-dispatch-settings.json`; when Auto is on, the backend spawns hidden agents only when matching work exists and active + still-running pending agents are below that role's maximum.

Every task must have a real, nonblank title. `Untitled`, `Untitled task`, and blank titles are invalid; the API rejects them and the viewer hides malformed records.

When a task depends on an image, the Planner or Reviewer saves the reference under `reference-images/` and records it in the task's `referenceImages` array (`path`, `description`, `source`). Workers inspect those paths before implementing.

## Roles

Use one of three role files when starting a new agent:

- `roles/planner.md`
- `roles/worker.md`
- `roles/reviewer.md`

Use these start phrases in a new chat:

| Start phrase | Agent role |
| --- | --- |
| `load as planner` | Planner |
| `load as worker` | Worker |
| `load as reviewer` | Reviewer |

## Hard Role Separation

Planner, Worker, and Reviewer are separate agents. Agents do not switch roles inside the same chat.

If the owner gives requirements to a Planner, the Planner records them in `board.json` and does not continue into implementation or review. It does not claim tasks, edit product code, run implementation, or make code changes.

Worker execution starts only in a separate Worker chat or when the owner explicitly starts an agent with the Worker role.

Review starts only in a separate Reviewer chat or when the owner explicitly starts an agent with the Reviewer role. The Reviewer inspects the result but does not plan general work or implement fixes.

The Reviewer may update only `board.json`, plus reference images under `reference-images/` when those paths are recorded on a follow-up task. It must not modify code, scripts, tests, markdown docs, `AGENTS.md`, or `task-board/viewer.html`.

## Columns

Tasks move through six columns:

| Column | Meaning | Who moves tasks here |
| --- | --- | --- |
| `todo` | Planned, unclaimed work. | Planner |
| `claimed` | A Worker has claimed the task and is actively working on it. | Worker |
| `review` | Worker finished the task and it is waiting for review. | Worker |
| `reviewing` | A Reviewer has claimed the task and is actively reviewing it. | Reviewer |
| `done` | Accepted work, or failed reviewed work closed as replaced by a follow-up task. | Reviewer or owner |
| `archived` | Accepted work hidden from the main board. | owner or cleanup API |

The HTML viewer keeps the six JSON columns for locking but displays the main interface as three visual columns: **To Do** combines `claimed` above `todo`, **Review** combines `reviewing` above `review`, and **Done** displays `done`. Claimed and Reviewing cards are highlighted. To Do and Review have top lane strips for active registered agents and pending spawned agents, with hoverable latest log previews. Column headers show active Worker/Reviewer counts and dispatch controls from `/api/agents` and `task-board/agent-dispatch-settings.json`.

## Operating Rules

1. Every agent that hits the API calls `/api/register-agent` first with `personalName`, `model`, and `role`, then sends the returned `agentId` in every later payload. Workers and Reviewers also call `/api/heartbeat-agent` after claiming or moving a task, and `/api/unregister-agent` before ending the chat for any reason.
2. The Planner records the owner's requirements and decomposes them into tasks. Before creating or materially changing a task, it reloads the board and checks all six columns for duplicate or overlapping work by title, scope, files, acceptance criteria, `relatedTaskIds`, `dependsOn`, and `sourceReviewTaskId`. Prefer `POST /api/add-task` and `POST /api/update-task` when the backend is running.
3. The Planner only edits `board.json` and workflow docs (and only edits workflow docs when asked). It does not write product code, scripts, tests, or implementation files, and never switches into Worker or Reviewer behavior.
4. Workers read the worker board (`todo` + `claimed`) before doing any work, then claim exactly one `todo` task by moving it to `claimed` (`claimedBy`, `claimedAt`). Prefer `POST /api/claim-task`.
5. A Worker claims based on `columns.claimed` conflicts only, not as a broad lock from `review`/`done`.
6. When a Worker finishes, it records the result and moves the task to `review`, adding `inspectionTargets` (URL/path, viewport, state, notes). Prefer `POST /api/move-to-review`.
7. If a Worker is killed or abandons a task, the owner can use the viewer's expanded claimed-card "Unclaim task" button (`/viewer/unclaim-task`) to move it back to `todo` and clear the claim fields.
8. A Worker reloads the board after finishing each task and checks `todo` again; if another safe task exists it claims the next one and continues unless the owner asked to stop.
9. A Reviewer claims one task from `columns.review` by moving it to `reviewing` (prefer `POST /api/claim-review`), inspects it, then approves or requests changes.
10. A Reviewer uses `inspectionTargets` as the primary places to inspect when present.
11. If approved, the Reviewer moves the task from `reviewing` to `done` (prefer `POST /api/approve-review`).
12. If not approved, the Reviewer closes the task into the top of `done` as replaced, records a failure brief (`failureExpected`, `failureActual`, `failureDecision`), and creates or updates a follow-up `todo`. Before creating a follow-up, it uses `GET /api/duplicate-scan?...&includeArchived=true` to check every column. The failed original records `replacedByTaskId`/`latestFollowUpTaskId`. Prefer `POST /api/request-changes`.
13. The owner may return a `done` task to `review` from the viewer with feedback. The Reviewer treats `ownerFeedback`, `returnedToReviewAt`, and `Owner feedback for re-review` notes as the owner's active review question.
14. A Reviewer must not claim, review, move, or duplicate work for a task already in `columns.reviewing`.
15. A Reviewer reloads the board after every decision and continues with the next unclaimed `review` task, or reports the review list clear.
16. The Reviewer writes only to `board.json`, except for reference images under `reference-images/` recorded on a follow-up task.
17. The owner may also review `review` tasks and move accepted tasks to `done`.
18. Agents ignore `task-board/viewer.html` unless the owner explicitly asks to change the viewer itself.

## Conflict Rule

`board.json` is the coordination lock. A task in `claimed` reserves its listed files, project area, and direct scope for the claiming Worker.

Before claiming work, Workers treat `claimed` tasks as blocking only if:

- the task IDs indicate the same scope, or
- acceptance criteria are clearly overlapping/conflicting and target the same implementation scope.

Shared files/scripts alone are not blockers. Same-file work can proceed when scope differs or when tasks explicitly record `relatedTaskIds`, `dependsOn`, or `sourceReviewTaskId` links.

If two agents want the same task, the task already in `claimed` (or `reviewing` for reviewers) wins. The later agent chooses another task or reports that none is available.

The Planner and Reviewer must avoid creating duplicate or conflicting `todo` tasks. Before either creates a task, it checks all columns for matching work. If the owner gives a requirement that overlaps claimed work, the Planner records it as a separate dependent `todo` or asks how to merge it. If Reviewer feedback overlaps an existing follow-up, the Reviewer updates that follow-up instead.

Tasks in `review` or `done` are closed to Workers unless the owner explicitly reopens or assigns follow-up work.

## Extending the workflow

This core ships three roles. Some projects add **upstream handoff roles** that feed better inputs into planning — for example a research agent that surveys references, or an audit agent that inspects an existing system. The pattern: upstream agents write a Markdown **handoff file** (they never create or move tasks), and the Planner reads those handoffs, compares them against the current state and board, and converts the useful, actionable findings into `todo` tasks (recording the handoff path in a `sourceHandoffs` field or task notes). Add such roles only when your project needs them; keep upstream agents read-only with respect to the board.
