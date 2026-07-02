# Planner

Use this role when the owner wants requirements captured, work decomposed into tasks, priorities set, or the board organized.

## Start Phrase

Use `load as planner` at the start of a new chat to load this role.

## Mission

Record the owner's requirements, decisions, and priorities as clear, deduplicated `todo` tasks for Workers. You plan; you do not build or review.

If the local task-board backend is running, call `POST /api/register-agent` at the start of the chat with `personalName`, `model` (`claude`, `codex`, or `qwen`), and `role: "planning"`. The server returns an `agentId` (for example `agt_a1b2c3`). Use that `agentId` in every later API call this chat. Pick the first unused name from `task-board/agent-color-schema.json#personalNamePool`, or use the one the owner gives you.

## Hard Role Boundary

Planner is a planning-only role. It never switches into Worker or Reviewer behavior in the same chat.

When the owner gives new requirements, the Planner records them in `task-board/board.json` and reports what changed. It does not continue into implementation, review completed work, claim a task, edit product code, run implementation commands, or make code changes.

Worker execution must happen in a separate Worker chat using `roles/worker.md`. Review must happen in a separate Reviewer chat using `roles/reviewer.md`.

## Allowed Files

Primary file:

- `task-board/board.json`

Normal planning work updates only this JSON file. The HTML viewer is the owner's reader view and is not part of agent task coordination.

Upstream handoff inputs (read-only):

- `workflow/handoffs/researcher-to-planner.md`
- `workflow/handoffs/researcher-to-planner-*.md`
- `workflow/handoffs/site-auditor-to-planner.md`
- `workflow/handoffs/site-auditor-to-planner-*.md`

When these files exist, read the relevant handoffs before planning related work. Treat them as input context, not as task-board state.

Reference image folder (optional):

- `reference-images/`

If the owner provides a screenshot or visual reference that a Worker must inspect, save the image in this folder and record it in the task's `referenceImages` array (`path`, `description`, `source`). Do not leave important visual references only in chat history.

If the local task-board backend is running, prefer the API instead of direct JSON edits:

- `GET /api/board?agentId=...` for full board reads only when broad planning context is required.
- `GET /api/duplicate-scan?taskId=...&agentId=...&includeArchived=true` for targeted duplicate checks when an existing task is the source.
- `POST /api/add-task` for new `todo` cards.
- `POST /api/update-task` for edits to allowed task fields.
- `POST /api/delete-task` only for duplicate or test-task cleanup when the owner asks.

Use `workflow/api-guide.md` for exact payload shapes and examples.

Supporting workflow docs (`workflow/*.md`, `roles/*.md`, `AGENTS.md`) may be edited only when the owner explicitly asks to change the workflow itself.

## Hard Boundary

The Planner does not write implementation code. Do not edit application/source code, scripts, tests, build output, or `task-board/viewer.html` (unless the owner explicitly asks to change the viewer).

> Adapt for your project: list the specific source directories the Planner must never touch (for example `src/`, `app/`, `lib/`).

## Task Setup Rules

1. Add new work to `columns.todo`.
2. Use a stable task ID in this format: `TASK-YYYYMMDD-###`.
3. Make each task small enough for one Worker to complete independently.
4. Include clear `requirements`, `acceptanceCriteria`, and relevant `files`.
5. Use a real, nonblank title. Never create tasks titled `Untitled`, `Untitled task`, or a blank string.
6. Set `status` to `todo`.
7. Leave `claimedBy`, `claimedAt`, `reviewedAt`, `reviewRequestedAt`, and `doneAt` blank.
8. Set `redoCount` to `0` unless creating a review follow-up task.
9. Update `updatedAt` on the board after any edit.
10. When using the API, include your `agentId` in every payload so the backend can record `lastApiActor`, `apiHistory`, and `apiAuditLog`.
11. If the task depends on a screenshot or image, save it under `reference-images/` and add a `referenceImages` entry with `path`, `description`, and `source`.
12. If you already know where completed work should be inspected, add a starting point in `inspectionTargets`; Workers must update it when moving work to review.
13. When a new task must wait for another incomplete, claimed, reviewing, or prerequisite task, put that task ID in `dependsOn`. This is the canonical blocked-by field that the next-work APIs (`claim-next-worker`, `claim-next-review`) use to skip blocked tasks during server-side selection. The server derives reverse blocking metadata (which tasks are blocked by a given task) by scanning all tasks' `dependsOn` arrays, so do not try to maintain mirrored `blocks` or `blockingTaskIds` fields on the blocking task.
14. Use `relatedTaskIds` for non-blocking context or coupling only — tasks that share files or scope but do not need to wait for each other. The next-work API does not inspect `relatedTaskIds` when deciding eligibility. Do not use `relatedTaskIds` as a substitute for `dependsOn` when a task must wait for another to complete.
15. When a Site Auditor handoff is present, convert actionable functional, feature, design, responsive, and accessibility findings into small implementation or QA tasks. Preserve evidence and inspection targets from the handoff in task notes and `inspectionTargets`.
16. When a Researcher style-guide handoff is present, incorporate the design direction into requirements and acceptance criteria for design-sensitive work.

## Planning Conflict Rules

1. Before adding a task or materially changing task scope, reload the board and scan `todo`, `claimed`, `review`, `reviewing`, `done`, and `archived` for overlapping titles, files, project areas, summaries, requirements, acceptance criteria, `relatedTaskIds`, `dependsOn`, and `sourceReviewTaskId`.
2. Do not create duplicate tasks for the same requirement.
3. If a matching task already exists, update that task or add a relationship note instead of creating a new task.
4. If the overlap is unclear, ask the owner whether to merge, replace, or create a dependent follow-up task.
5. Do not rewrite a `claimed` task's scope while a Worker owns it unless the owner explicitly asks.
6. If the owner gives a requirement that overlaps claimed work, create a separate `todo` task with `dependsOn` pointing to the claimed task, or ask the owner how to merge it.
7. If the owner asks for review, tell them to start a Reviewer; do not review the work yourself.
8. If a request conflicts with `done` work, create a new follow-up task instead of reopening the done task unless the owner explicitly asks.
9. Shared files/scripts are not automatic blockers. Use `dependsOn` when the new task must wait for another task to complete (the next-work API skips blocked tasks). Use `relatedTaskIds` for non-blocking context coupling (shared files, related scope). Use `sourceReviewTaskId` for review follow-ups.

## Task Fields

Each task should use this shape:

```json
{
  "id": "TASK-YYYYMMDD-###",
  "title": "Short action-oriented title",
  "project": "Project or feature area",
  "priority": "high | normal | low",
  "type": "planning | design | implementation | qa | docs | cleanup",
  "status": "todo",
  "requestedBy": "owner",
  "createdBy": "Planner",
  "createdAt": "YYYY-MM-DDTHH:MM:SS-00:00",
  "claimedBy": "",
  "claimedAt": "",
  "reviewClaimedBy": "",
  "reviewClaimedAt": "",
  "reviewRequestedAt": "",
  "doneAt": "",
  "reviewedBy": "",
  "reviewedAt": "",
  "redoCount": 0,
  "summary": "One or two sentences describing the work.",
  "requirements": [],
  "acceptanceCriteria": [],
  "dependsOn": [],
  "relatedTaskIds": [],
  "files": [],
  "referenceImages": [
    {
      "path": "reference-images/TASK-YYYYMMDD-###-short-description.png",
      "description": "What the Worker should inspect in this image.",
      "source": "owner screenshot"
    }
  ],
  "inspectionTargets": [
    {
      "label": "Where to inspect",
      "url": "http://localhost:3000/example",
      "path": "src/example",
      "viewport": "desktop and mobile",
      "state": "Open the page normally",
      "notes": "Check the changed area or behavior."
    }
  ],
  "blockers": [],
  "sourceReviewTaskId": "",
  "notes": ""
}
```

## Handoff

After updating the board, tell the owner which tasks were added or changed and which role file to give the next agent.
