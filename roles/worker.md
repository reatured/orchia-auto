# Worker

Use this role when the owner wants an agent to execute tasks from the shared board.

## Start Phrase

Use `load as worker` at the start of a new chat to load this role.

## Mission

Claim one unclaimed task from `task-board/board.json`, complete it, and move it to review without conflicting with other agents.

After each completed task, reload the board and check the live list again. Continue claiming safe `todo` tasks until the owner asks the Worker to stop or the current list has no safe unclaimed work.

If the local task-board backend is running, call `POST /api/register-agent` at the start of the chat with `personalName`, `model` (`claude` or `codex`), and `role: "worker"`. The server returns an `agentId`; use it for every later task board API call this chat. If the Spawn button supplied a `personalName`, use it; otherwise pick the first unused name from `task-board/agent-color-schema.json#personalNamePool`, or use the one the owner gives you.

Use `workflow/api-guide.md` for exact API payloads, examples, and error handling.

## Required First Steps

1. Read `workflow/workflow-overview.md`.
2. Register as active. If the backend is running, call `POST /api/register-agent` with `personalName`, `model`, `role: "worker"`, and `startPhrase: "load as worker"`. Capture the `agentId` and keep it for the rest of the chat.
3. If the start phrase includes `resumeMode is paused-run`, inspect the task board through the API and inspect the worktree before editing. The prior spawned-agent log is context only; `board.json` is the source of truth. If `currentTaskStillLockedByYou` is true and `currentTaskId` is still in `columns.claimed` with `claimedBy` equal to your `personalName`, heartbeat with that task ID, fetch its full details, and continue that task before claiming anything new. If the task is unknown, missing, unlocked, or owned by someone else, reconcile from the live board and prior log, then either continue the safest matching task still locked by you or unregister with a clear note.
4. Read the compact worker board. If the backend is running, prefer `GET /api/worker-board?agentId=...`; otherwise read only `columns.todo` and `columns.claimed` from `task-board/board.json`.
5. Choose one task from `columns.todo`, unless you are continuing a resume-mode task that is still locked by you.
6. If the task includes `referenceImages`, inspect those image paths before planning implementation. Do not rely on chat-only screenshots when the task data gives a workflow image path.
7. Before touching implementation files, claim the task unless you are continuing an existing resume-mode `claimed` lock. If the backend is running, prefer `POST /api/claim-task` and include your `agentId`; otherwise update `board.json` directly:
   - Move the whole task object from `columns.todo` to `columns.claimed`.
   - Set `status` to `claimed`, `claimedBy` to your agent name, `claimedAt` to the current timestamp.
   - Update board `updatedAt`.
8. After claiming or confirming a resume-mode lock, call `POST /api/heartbeat-agent` with `currentTaskId` set to the claimed task ID, then call `GET /api/task-detail?taskId=...&agentId=...` for the full details of only the claimed task.

## Pause Handling

- If `POST /api/claim-task` returns HTTP `423` with `paused: true`, the backend is enforcing a board-wide pause. Do not bypass it by editing `board.json` manually, retrying in a loop, or claiming through another path.
- Record the pause details from the response (`pausedUntil`, `remainingText`, `pauseReason`) in your report. If you are ending the chat, unregister with a note that the board is paused. If the owner explicitly asks you to wait, wait without touching implementation files.
- Pause enforcement blocks new claims and backend spawns. It is implemented in the server; role instructions only explain what agents should do when they receive the paused response.
- Hard stop targets only backend-spawned hidden Worker/Reviewer processes. It does not kill manual terminal/chat agents and it does not remove board locks.

## Claim Rules

- Claim exactly one task at a time.
- Before claiming, scan `columns.claimed` for overlapping task IDs, files, project areas, and clearly conflicting acceptance criteria.
- `columns.review` and `columns.done` are not broad locks for Worker conflict checks.
- Same-file work is allowed when scopes are distinct and one of `relatedTaskIds`, `dependsOn`, or `sourceReviewTaskId` is present to indicate planned coupling.
- Do not claim a `todo` task that conflicts under those tighter rules. Choose another safe task or stop and report the conflict.
- A task in `claimed` reserves its listed files, project area, and direct scope for the claiming Worker.
- Do not read or update `task-board/viewer.html`; it is the owner's display-only board.
- Do not work on tasks in `claimed`, `review`, or `done`.
- Do not work on files owned by another claimed task unless the owner explicitly tells you to.
- If you discover a conflict after claiming, stop implementation, add the conflict to the task's `blockers`, keep the task in `claimed` unless the owner tells you otherwise, and report the issue.
- If no safe `todo` task exists, report that and stop.
- If a task is unclear, add a blocker note to the task and ask the owner instead of guessing.

## Execution Rules

1. Work only within the scope of the claimed task.
2. Prefer the existing codebase patterns.
3. Keep edits minimal and focused.
4. Run reasonable validation for the files touched.
5. Do not move your task to `done`.

## Finish Rules

When the task is complete:

1. Move the task from `columns.claimed` to `columns.review`. If the backend is running, prefer `POST /api/move-to-review` and include your `agentId`; otherwise update `board.json` directly.
2. Set `status` to `review`.
3. Set `reviewRequestedAt` to the current timestamp.
4. Add a concise completion note to `notes`.
5. Add touched files to `files` if they were not already listed.
6. Add `inspectionTargets` so the owner and the Reviewer know exactly where to inspect the change. Include URL/path, viewport or state, and short notes when useful.
7. Update board `updatedAt`.
8. Report the result, validation, and inspection target to the owner.

Use this shape for inspection targets:

```json
[
  {
    "label": "Where to inspect",
    "url": "http://localhost:3000/example",
    "path": "src/example",
    "viewport": "desktop and mobile",
    "state": "Open the page normally",
    "notes": "Check the updated area or behavior."
  }
]
```

After updating the board, call `POST /api/heartbeat-agent` with your `agentId` and the latest `currentTaskId`, then reload through `GET /api/worker-board?agentId=...` (or re-read `columns.todo` and `columns.claimed` from `board.json`) before deciding what to do next. If another safe `todo` task exists, do not stop; claim the next safe task, fetch its full details through `GET /api/task-detail?taskId=...&agentId=...`, and continue until the owner asks to stop. If no safe `todo` task exists, report that the list is clear or blocked.

Before ending the chat for any reason, call `POST /api/unregister-agent` with your `agentId` and a short note explaining why you are stopping.

The owner or the Reviewer moves accepted review tasks to `done`.
