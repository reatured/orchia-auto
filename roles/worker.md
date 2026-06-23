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
3. Read the compact worker board. If the backend is running, prefer `GET /api/worker-board?agentId=...`; otherwise read only `columns.todo` and `columns.claimed` from `task-board/board.json`.
4. Choose one task from `columns.todo`.
5. If the task includes `referenceImages`, inspect those image paths before planning implementation. Do not rely on chat-only screenshots when the task data gives a workflow image path.
6. Before touching implementation files, claim the task. If the backend is running, prefer `POST /api/claim-task` and include your `agentId`; otherwise update `board.json` directly:
   - Move the whole task object from `columns.todo` to `columns.claimed`.
   - Set `status` to `claimed`, `claimedBy` to your agent name, `claimedAt` to the current timestamp.
   - Update board `updatedAt`.
7. After claiming, call `POST /api/heartbeat-agent` with `currentTaskId` set to the claimed task ID, then call `GET /api/task-detail?taskId=...&agentId=...` for the full details of only the claimed task.

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
