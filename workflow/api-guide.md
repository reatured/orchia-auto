# Task Board API Guide

Use this guide when the local task-board backend is running:

- Backend: `task-board/server.py`
- Base URL: `http://127.0.0.1:4177` (host/port come from `task-board/config.json`)
- Board data: `task-board/board.json`
- API audit log: `task-board/task-board-api.log`
- Viewer log: `task-board/task-board-viewer.log`
- Dispatch settings: `task-board/agent-dispatch-settings.json`
- Spawned agent output: `task-board/spawned-agent-logs/`

Dispatch settings normalize and persist independent model selections for `planner.model`, `worker.model`, and `review.model`. Missing or invalid `planner.model` values fall back to `claude`, matching the resumable Planner chat default; missing or invalid Worker and Review model values fall back to `codex`. `planner.model` controls the Planner chat selector only; Worker and Review settings keep their existing auto-dispatch `enabled` and `maxAgents` fields.

Spawned agents are given the current `backendBaseUrl` in their start prompt. Use that exact URL, including port.

Agents use `/api/...` endpoints. The HTML viewer uses `/viewer/...` endpoints and writes to `task-board-viewer.log`, so viewer reads and the owner's viewer actions do not mix with agent API calls.

The backend terminal intentionally filters routine successful viewer polling and static reads, including `/viewer/pause-status`, `/viewer/agents`, and `/board.json`. Successful write actions and request failures still print concise terminal lines; structured audit history remains in `task-board-api.log` and `task-board-viewer.log`.

The API is the preferred way to create, claim, move, review, approve, return, archive, update, or delete tasks. Direct JSON edits are the fallback only when the backend is not running.

Examples below are shown for both **curl** (macOS/Linux/Git Bash) and **PowerShell** (Windows). Replace `$BASE`/`$base`, `$agentId`, and task IDs with your values.

```bash
# curl: set once
BASE="http://127.0.0.1:4177"
```
```powershell
# PowerShell: set once
$base = "http://127.0.0.1:4177"
```

## Required Rules

1. At the start of the chat, call `POST /api/register-agent` with `personalName`, `model`, and `role`. The server returns an `agentId` (for example `agt_a1b2c3`). Keep it for the lifetime of the chat.
2. Include that `agentId` in every later API payload. `personalName`/`agentName` are display fields only; `agentId` is the contract key.
3. `personalName` is a single short lowercase token (e.g. `ada`, `finn`, `iris`). The Spawn button picks one from `agent-color-schema.json#personalNamePool`. If the owner gives a name, use it.
4. `model` is `claude`, `codex`, or `qwen`. `role` is `planning`, `worker`, or `review`.
5. Send JSON objects only, with `Content-Type: application/json`.
6. After every successful status change, call the next-work API to find the next eligible task. Workers use `POST /api/claim-next-worker`; Reviewers use `POST /api/claim-next-review`. For diagnostics or broad context only, Workers may also use `GET /api/worker-board` and Reviewers `GET /api/review-board`; Planners may use `GET /api/board`.
7. After choosing or claiming a task, use `GET /api/task-detail?taskId=...` to load full details for that one task.
8. Use `GET /api/duplicate-scan` for duplicate checks instead of loading the whole board.
9. Do not use the HTML viewer as an agent input.
10. Do not use `/api/delete-task` for normal workflow; only for duplicate/test cleanup.
11. Treat `task-board-api.log` as audit history only. The source of truth remains `board.json`.

## Endpoint Summary

| Endpoint | Purpose |
| --- | --- |
| `GET /api/board` | Read the full board (Planner broad context). |
| `GET /api/worker-board` | Compact `todo` + `claimed` summaries. |
| `GET /api/review-board` | Compact `review` + `reviewing` summaries. |
| `GET /api/task-detail?taskId=...` | One full task and its current column. |
| `GET /api/duplicate-scan?taskId=...` | Server-side duplicate scan; matching candidates only. |
| `GET /api/agents` | Active registered agents plus pending spawned processes, PID status, and latest log previews. |
| `GET /api/agent-schema` | Color/role/name schema for rendering chips. |
| `GET /api/pause-status` or `GET /api/pause` | Read board-wide pause status and remaining time. |
| `POST /api/register-agent` | Register at chat start; returns `agentId`. |
| `POST /api/heartbeat-agent` | Refresh presence + current task ID. |
| `POST /api/unregister-agent` | Remove an active agent before the chat ends. |
| `POST /api/spawn-agent` | Launch one hidden Worker/Reviewer process with the configured CLI. |
| `POST /api/agent-health-check` | Test a configured CLI command with the same command shape used for spawning. |
| `POST /api/pause-plus-one-hour` or `POST /api/pause` | Add one hour to the board-wide pause. |
| `POST /api/resume-now` | Clear the active board-wide pause. |
| `POST /api/hard-stop-spawned-agents` or `POST /api/hard-stop` | Stop running backend-spawned Worker/Reviewer processes during an active pause. |
| `POST /api/add-task` | Create one new task in `todo`. |
| `POST /api/update-task` | Update allowed task fields without changing ID or status. |
| `GET /api/next-worker-task` | Read-only preview of the next eligible unblocked `todo` task. |
| `POST /api/claim-next-worker` | Select and claim the next eligible `todo` task atomically. |
| `GET /api/next-review-task` | Read-only preview of the next eligible unblocked `review` task. |
| `POST /api/claim-next-review` | Select and claim the next eligible `review` task atomically. |
| `POST /api/claim-task` | Move one specific task `todo` → `claimed`. |
| `POST /api/unclaim-task` | Recovery: `claimed` → `todo`. |
| `POST /api/move-to-review` | Move one task `claimed` → `review`. |
| `POST /api/claim-review` | Move one specific task `review` → `reviewing`. |
| `POST /api/approve-review` | Move one task `reviewing` → `done`. |
| `POST /api/request-changes` | Close failed task into `done` as replaced; create/update follow-up `todo`. |
| `POST /api/return-to-review` | Move one `done` task back to `review` with owner feedback. |
| `POST /api/archive` | Move one `done` task to `archived`. |
| `POST /api/delete-task` | Cleanup only; not for normal workflow. |

## Register, Heartbeat, Unregister

```bash
# Register (worker) — returns agentId
curl -s -X POST "$BASE/api/register-agent" -H "Content-Type: application/json" \
  -d '{"personalName":"ada","model":"claude","role":"worker","startPhrase":"load as worker"}'
```
```powershell
$body = @{ personalName = "ada"; model = "claude"; role = "worker"; startPhrase = "load as worker" } | ConvertTo-Json
$response = Invoke-RestMethod -Uri "$base/api/register-agent" -Method Post -ContentType "application/json" -Body $body
$agentId = $response.agentId   # keep for the rest of the chat
```

```bash
# Heartbeat after claiming/moving a task
curl -s -X POST "$BASE/api/heartbeat-agent" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"currentTaskId\":\"TASK-YYYYMMDD-001\"}"
# Unregister before ending the chat
curl -s -X POST "$BASE/api/unregister-agent" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"notes\":\"No safe todo tasks remain.\"}"
```
```powershell
Invoke-RestMethod -Uri "$base/api/heartbeat-agent" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; currentTaskId = "TASK-YYYYMMDD-001" } | ConvertTo-Json)
Invoke-RestMethod -Uri "$base/api/unregister-agent" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; notes = "No safe todo tasks remain." } | ConvertTo-Json)
```

## Read APIs

```bash
curl -s "$BASE/api/worker-board?agentId=$agentId"
curl -s "$BASE/api/review-board?agentId=$agentId"
curl -s "$BASE/api/task-detail?taskId=TASK-YYYYMMDD-001&agentId=$agentId"
curl -s "$BASE/api/duplicate-scan?taskId=TASK-YYYYMMDD-001&agentId=$agentId&includeArchived=true&limit=25"
curl -s "$BASE/api/pause-status?agentId=$agentId"
```
```powershell
Invoke-RestMethod -Uri "$base/api/worker-board?agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/review-board?agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/task-detail?taskId=TASK-YYYYMMDD-001&agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/duplicate-scan?taskId=TASK-YYYYMMDD-001&agentId=$agentId&includeArchived=true&limit=25"
Invoke-RestMethod -Uri "$base/api/pause-status?agentId=$agentId"
```

`GET /api/worker-board` and `GET /api/review-board` return only the role's active columns as compact summaries; they omit `done`, `archived`, the top-level `tasks` index, `apiAuditLog`, and policy text. After choosing a task, load full details with `GET /api/task-detail`.

## Next-Work APIs

Workers and Reviewers use these endpoints for server-side task selection instead of reading the full board to choose work. The server handles priority ordering (high → normal → low), age tie-breaking (oldest first), and dependency checking (skips tasks whose `dependsOn` entries are not all in `done` or `archived`).

### Read-only preview

```bash
# Worker: preview next eligible todo task (does not claim)
curl -s "$BASE/api/next-worker-task?agentId=$agentId"
# Reviewer: preview next eligible review task (does not claim)
curl -s "$BASE/api/next-review-task?agentId=$agentId"
```
```powershell
Invoke-RestMethod -Uri "$base/api/next-worker-task?agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/next-review-task?agentId=$agentId"
```

**Eligible response** (a task is available):

```json
{
  "eligible": true,
  "taskId": "TASK-YYYYMMDD-001",
  "title": "Task title",
  "project": "Project area",
  "priority": "high",
  "type": "implementation",
  "status": "todo",
  "sourceColumn": "todo",
  "createdAt": "2026-06-24T10:00:00-07:00",
  "detailUrl": "/api/task-detail?taskId=TASK-YYYYMMDD-001",
  "blockedByTaskIds": [],
  "blockingTaskIds": ["TASK-YYYYMMDD-003"],
  "orderingTimestamp": "2026-06-24T10:00:00-07:00"
}
```

**No-work response** (no tasks or all blocked):

```json
{
  "eligible": false,
  "reason": "all-blocked",
  "blockedSummary": [
    {
      "taskId": "TASK-YYYYMMDD-002",
      "title": "Blocked task title",
      "priority": "high",
      "createdAt": "2026-06-24T10:00:00-07:00",
      "blockedByTaskIds": ["TASK-YYYYMMDD-001"]
    }
  ]
}
```

The `reason` field is `"no-work"` when the source column is empty, or `"all-blocked"` when every candidate has unresolved `dependsOn` entries. The `blockedSummary` lists each blocked task and the dependency IDs that block it.

**Paused response** (HTTP 200 with paused flag):

```json
{
  "action": "next-work",
  "paused": true,
  "isPaused": true,
  "pausedUntil": "2026-06-25T02:00:00-07:00",
  "remainingSeconds": 3600,
  "remainingText": "1h 0m",
  "pauseReason": "Rate-limit cooldown"
}
```

### Atomic claim

```bash
# Worker: select and claim the next eligible todo task
curl -s -X POST "$BASE/api/claim-next-worker" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"claimedBy\":\"workercd81\"}"
# Reviewer: select and claim the next eligible review task
curl -s -X POST "$BASE/api/claim-next-review" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"reviewClaimedBy\":\"ada\"}"
```
```powershell
Invoke-RestMethod -Uri "$base/api/claim-next-worker" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; claimedBy = "workercd81" } | ConvertTo-Json)
Invoke-RestMethod -Uri "$base/api/claim-next-review" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; reviewClaimedBy = "ada" } | ConvertTo-Json)
```

**Successful claim response** (includes all preview fields plus):

```json
{
  "eligible": true,
  "taskId": "TASK-YYYYMMDD-001",
  "claimed": true,
  "claimedAt": "2026-06-25T01:00:00-07:00",
  "taskIds": ["TASK-YYYYMMDD-001"]
}
```

For `claim-next-review`, the response includes `reviewClaimedAt` instead of `claimedAt`.

**No-work claim response** (`claimed: false`):

```json
{
  "eligible": false,
  "reason": "all-blocked",
  "claimed": false,
  "blockedSummary": [...]
}
```

**Paused claim** returns HTTP `423` with `paused: true` and pause details — same as `POST /api/claim-task`.

### Backward compatibility

The older explicit endpoints (`POST /api/claim-task`, `POST /api/claim-review`) and the compact board reads (`GET /api/worker-board`, `GET /api/review-board`) still work. Agents that need to claim a specific known task ID can continue using `POST /api/claim-task`. The next-work APIs are the preferred path for normal task selection because they handle prioritization and dependency checking server-side.

**Dependency metadata:** `dependsOn` is the canonical blocked-by field stored on each task. The Planner sets it when creating a `todo` task that must wait for another incomplete, claimed, reviewing, or prerequisite task. The server derives reverse blocking information (which other tasks are blocked by a given task) by scanning all tasks' `dependsOn` arrays; agents should not maintain mirrored `blocks` or `blockingTaskIds` fields. `relatedTaskIds` is for non-blocking context only — it links tasks that share files or scope but must not prevent the server from selecting the task. The next-work APIs respond with `blockedByTaskIds` (the task's own unresolved `dependsOn` entries) and `blockingTaskIds` (server-derived list of other tasks blocked by this task).

`GET /api/agents` is mainly for the owner-facing viewer and diagnostics. Registered agents appear in `activeAgents`. Hidden spawned processes that have not registered yet appear in `pendingSpawns` with `processId`, `processStatus.state` (`running`, `exited`, `pid-reused`, or `unknown`), and `latestLog.preview`. Hard-stopped spawned processes that are eligible for resume appear in `pausedRuns`. Workers and Reviewers should not use this endpoint to choose tasks; use the next-work APIs (`/api/claim-next-worker`, `/api/claim-next-review`) instead.

## Spawn And Health Check APIs

The viewer Settings tab uses the health-check endpoint before Spawn or auto-dispatch. A restarted backend exposes both `/api/agent-health-check` and `/viewer/agent-health-check`; if the viewer receives HTTP 404 from `/viewer/agent-health-check`, the running backend is older than the HTML and should be restarted.

```bash
curl -s -X POST "$BASE/api/agent-health-check" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'","tool":"codex","command":"codex"}'
curl -s -X POST "$BASE/api/agent-health-check" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'","tool":"claude","command":"claude"}'
curl -s -X POST "$BASE/api/agent-health-check" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'","tool":"qwen","command":"qwen"}'
```

Health checks return JSON with `ok`, `status`, `tool`, `command`, `durationMs`, and, when useful, `error`, `outputPreview`, and `suggestion`. Codex checks run `codex exec --skip-git-repo-check "Reply exactly: OK"`; Claude Code checks run `claude -p "Reply exactly: OK"`; Qwen checks run `qwen -p "Reply exactly: OK" -y`. Plain `codex`, `claude`, and `qwen` command names are resolved from `PATH` plus common install locations including Homebrew, `/usr/local/bin`, user-local bins, npm, and Windows Node/npm paths. When `CODEX_SQLITE_HOME` is not already set, Codex health checks and interactive spawned Codex agents use `task-board/codex-sqlite-state/` as a writable state folder.

## Pause, Hard Stop, Resume APIs

Pause state is stored in `task-board/agent-dispatch-settings.json` under `pause`. Use `GET /api/pause-status` or `GET /api/pause` to read it:

```bash
curl -s "$BASE/api/pause-status?agentId=$agentId"
```
```powershell
Invoke-RestMethod -Uri "$base/api/pause-status?agentId=$agentId"
```

The status response includes `isPaused`, `pausedUntil`, `pausedBy`, `pausedAt`, `pauseReason`, `remainingSeconds`, `remainingText`, and `message`. When the pause is expired or absent, `isPaused` is `false`, pause metadata is blank, and remaining time is zero.

```bash
# Pause +1h. Repeated calls add one hour from max(now, current pausedUntil).
curl -s -X POST "$BASE/api/pause-plus-one-hour" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'","pauseReason":"Rate-limit cooldown"}'
# Alias:
curl -s -X POST "$BASE/api/pause" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'","reason":"Rate-limit cooldown"}'
```
```powershell
Invoke-RestMethod -Uri "$base/api/pause-plus-one-hour" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; pauseReason = "Rate-limit cooldown" } | ConvertTo-Json)
```

Pause responses return the same status fields plus `ok: true` and `addedSeconds: 3600`. The backend calculates the new `pausedUntil` from `max(now, current pausedUntil) + 1 hour`, so Pause +1h accumulates one hour per click instead of replacing the current pause.

```bash
curl -s -X POST "$BASE/api/resume-now" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'"}'
```
```powershell
Invoke-RestMethod -Uri "$base/api/resume-now" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId } | ConvertTo-Json)
```

`POST /api/resume-now` clears the active pause and returns `ok: true`, `isPaused: false`, zero remaining time, and `resumedBy`. It does not directly edit tasks. After the board is unpaused, auto-dispatch resumes eligible `pausedRuns` before normal new Worker/Reviewer spawning. If the viewer still appears paused after an expired or resumed pause, reload the viewer and confirm `GET /api/pause-status` returns `isPaused: false`.

```bash
# Requires an active pause. Optional role may be "worker" or "review".
curl -s -X POST "$BASE/api/hard-stop-spawned-agents" -H "Content-Type: application/json" \
  -d '{"agentId":"'$agentId'","role":"worker","stopReason":"Rate-limit cooldown"}'
```
```powershell
Invoke-RestMethod -Uri "$base/api/hard-stop-spawned-agents" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; role = "worker"; stopReason = "Rate-limit cooldown" } | ConvertTo-Json)
```

Hard stop returns `ok`, `paused`, `isPaused`, `message`, `stoppedCount`, `targetedCount`, `skippedCount`, `pausedRuns`, `skippedRuns`, and `remainingPendingSpawns`. It only targets backend-spawned hidden Worker/Reviewer processes in `pendingSpawns`; it does not kill manual terminal/chat agents and it does not unclaim tasks. If the board is not paused, it returns HTTP `409`.

Each `pausedRuns` entry records resume context such as `role`, `model`, `personalName`, `processId`, `logPath`, `spawnedAt`, `stoppedAt`, `stoppedBy`, `stopReason`, inferred `currentTaskId`, `currentColumn`, `taskInference`, `activeAgentId`, `statusBeforeStop`, `stopStatus`, `resumeReady`, and `resumeState`. On the next unpaused auto-dispatch pass, waiting entries are spawned first with a resume-mode start phrase that includes `resumeMode is paused-run`, the previous process/log fields, and whether the current task is still locked by that personal name.

There is no separate checkpoint endpoint. The checkpoint for resume is board state plus active-agent state: task claim fields, review claim fields, `/api/register-agent`, `/api/heartbeat-agent` with `currentTaskId`, pending-spawn metadata, and the prior spawned-agent log. Logs help the resumed agent recover context, but `board.json` remains the source of truth.

If a resume spawn fails, the corresponding `pausedRuns` entry records `resumeState: "resume-failed"`, `lastResumeError`, and `lastResumeFailedAt`; check `task-board/task-board-viewer.log` for the auto-dispatch audit entry and check the prior spawned log path for the interrupted run. After deciding those entries are stale, the owner can clear them through the viewer Settings tab or:

```powershell
Invoke-RestMethod -Uri "$base/viewer/dispatch-settings" -Method Post -ContentType "application/json" `
  -Body (@{ clearPausedRuns = $true } | ConvertTo-Json)
```

## Planner APIs

```bash
curl -s -X POST "$BASE/api/add-task" -H "Content-Type: application/json" -d "{
  \"agentId\":\"$agentId\",
  \"title\":\"Short action title\",
  \"project\":\"Project area\",
  \"priority\":\"high\",
  \"type\":\"implementation\",
  \"summary\":\"One or two sentences describing the work.\",
  \"requirements\":[\"Concrete requirement.\"],
  \"acceptanceCriteria\":[\"Specific pass condition.\"],
  \"files\":[\"path/to/relevant-file\"]
}"
```
```powershell
$body = @{
  agentId = $agentId
  title = "Short action title"
  project = "Project area"
  priority = "high"
  type = "implementation"
  summary = "One or two sentences describing the work."
  requirements = @("Concrete requirement.")
  acceptanceCriteria = @("Specific pass condition.")
  files = @("path/to/relevant-file")
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "$base/api/add-task" -Method Post -ContentType "application/json" -Body $body
```

```powershell
# Update allowed fields without changing status
$body = @{
  agentId = $agentId
  taskId = "TASK-YYYYMMDD-001"
  updates = @{
    priority = "normal"
    acceptanceCriteria = @("Updated pass condition.")
    inspectionTargets = @(@{
      label = "Where to inspect"; url = "http://localhost:3000/example"; path = "src/example"
      viewport = "desktop and mobile"; state = "Open the page normally"; notes = "Check the changed area."
    })
  }
  notesAppend = "Reason for the update."
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "$base/api/update-task" -Method Post -ContentType "application/json" -Body $body
```

## Worker APIs

```bash
curl -s -X POST "$BASE/api/claim-task" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"taskId\":\"TASK-YYYYMMDD-001\",\"notes\":\"Claiming this task.\"}"
```
```powershell
Invoke-RestMethod -Uri "$base/api/claim-task" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; taskId = "TASK-YYYYMMDD-001"; notes = "Claiming this task." } | ConvertTo-Json)
```

```powershell
# Move to review (include inspectionTargets so the owner/Reviewer know where to look)
$body = @{
  agentId = $agentId
  taskId = "TASK-YYYYMMDD-001"
  notes = "Completed implementation. Include validation summary here."
  files = @("path/to/touched-file")
  inspectionTargets = @(@{
    label = "Where to inspect"; url = "http://localhost:3000/example"; path = "src/example"
    viewport = "desktop and mobile"; state = "Open the page normally"; notes = "Check the changed area."
  })
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "$base/api/move-to-review" -Method Post -ContentType "application/json" -Body $body
```

## Reviewer APIs

```bash
curl -s -X POST "$BASE/api/claim-review" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"taskId\":\"TASK-YYYYMMDD-001\"}"
curl -s -X POST "$BASE/api/approve-review" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$agentId\",\"taskId\":\"TASK-YYYYMMDD-001\",\"reviewNotes\":\"Approved after checking acceptance criteria.\"}"
```
```powershell
Invoke-RestMethod -Uri "$base/api/claim-review" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; taskId = "TASK-YYYYMMDD-001" } | ConvertTo-Json)
Invoke-RestMethod -Uri "$base/api/approve-review" -Method Post -ContentType "application/json" `
  -Body (@{ agentId = $agentId; taskId = "TASK-YYYYMMDD-001"; reviewNotes = "Approved after checking acceptance criteria." } | ConvertTo-Json)
```

Request changes (closes the failed task into `done` as replaced and creates/updates a follow-up `todo`):

```powershell
$body = @{
  agentId = $agentId
  taskId = "TASK-YYYYMMDD-001"
  failureExpected = "What should be true if this review passed."
  failureActual = "What is actually happening."
  failureDecision = "Short reason the reviewer is failing this task."
  reviewNotes = "Longer evidence and context."
  followUpTask = @{
    title = "Fix specific reviewed issue"
    project = "Project area"
    priority = "high"
    type = "implementation"
    summary = "What needs to be corrected."
    requirements = @("Concrete fix requirement.")
    acceptanceCriteria = @("Specific pass condition for the follow-up.")
    files = @("path/to/relevant-file")
  }
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "$base/api/request-changes" -Method Post -ContentType "application/json" -Body $body
```

## Owner / Viewer APIs

```powershell
# Return a done task to review with feedback
Invoke-RestMethod -Uri "$base/viewer/return-to-review" -Method Post -ContentType "application/json" `
  -Body (@{ agentName = "owner via task board viewer"; taskId = "TASK-YYYYMMDD-001"; feedback = "Feedback to consider during re-review." } | ConvertTo-Json)
# Archive an accepted done task
Invoke-RestMethod -Uri "$base/viewer/archive" -Method Post -ContentType "application/json" `
  -Body (@{ agentName = "owner via task board viewer"; taskId = "TASK-YYYYMMDD-001" } | ConvertTo-Json)
# Release a claimed task whose worker died
Invoke-RestMethod -Uri "$base/viewer/unclaim-task" -Method Post -ContentType "application/json" `
  -Body (@{ agentName = "owner via task board viewer"; taskId = "TASK-YYYYMMDD-001"; reason = "Worker was killed before finishing." } | ConvertTo-Json)
# Control auto-dispatch
Invoke-RestMethod -Uri "$base/viewer/dispatch-settings" -Method Post -ContentType "application/json" `
  -Body (@{ role = "worker"; enabled = $true; model = "codex"; maxAgents = 2 } | ConvertTo-Json)
# Persist the Planner chat model selector independently from Worker/Review
Invoke-RestMethod -Uri "$base/viewer/dispatch-settings" -Method Post -ContentType "application/json" `
  -Body (@{ role = "planner"; model = "codex" } | ConvertTo-Json)
# Persist Review or Worker model selectors from Settings/column controls
Invoke-RestMethod -Uri "$base/viewer/dispatch-settings" -Method Post -ContentType "application/json" `
  -Body (@{ role = "review"; model = "qwen" } | ConvertTo-Json)
# Update spawn command names
Invoke-RestMethod -Uri "$base/viewer/dispatch-settings" -Method Post -ContentType "application/json" `
  -Body (@{ commands = @{ codex = "codex"; claude = "cc" } } | ConvertTo-Json)
# Test command setup from the viewer Settings equivalent
Invoke-RestMethod -Uri "$base/viewer/agent-health-check" -Method Post -ContentType "application/json" `
  -Body (@{ agentName = "owner via task board viewer"; tool = "codex"; command = "codex" } | ConvertTo-Json)
```

## Error Handling

- `400` means the payload is invalid or the requested transition is not allowed.
- `404` means the task ID was not found in the expected column.
- `409` from hard stop means the board is not currently paused; pause first, then hard stop spawned agents if needed.
- `423` from `POST /api/claim-task`, `POST /api/claim-next-worker`, `POST /api/claim-next-review`, `POST /api/claim-review`, or `POST /api/spawn-agent` means the board is paused. The viewer Spawn button uses the same spawn path. The response includes `paused: true`, `pausedUntil`, `remainingSeconds`, `remainingText`, and `pauseReason`; do not bypass it by editing `board.json` manually.
- If a claim call fails, reload the role-specific board view (`GET /api/worker-board` or `GET /api/review-board`); another agent may have claimed the task first.
- Do not edit around failed claims by manually moving tasks unless the owner explicitly asks.
- If the backend is unavailable, fall back to direct `board.json` edits using the same role rules.
