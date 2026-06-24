# Task Board API Guide

Use this guide when the local task-board backend is running:

- Backend: `task-board/server.py`
- Base URL: `http://127.0.0.1:4177` (host/port come from `task-board/config.json`)
- Board data: `task-board/board.json`
- API audit log: `task-board/task-board-api.log`
- Viewer log: `task-board/task-board-viewer.log`
- Dispatch settings: `task-board/agent-dispatch-settings.json`
- Spawned agent output: `task-board/spawned-agent-logs/`

Spawned agents are given the current `backendBaseUrl` in their start prompt. Use that exact URL, including port.

Agents use `/api/...` endpoints. The HTML viewer uses `/viewer/...` endpoints and writes to `task-board-viewer.log`, so viewer reads and the owner's viewer actions do not mix with agent API calls.

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
4. `model` is `claude` or `codex`. `role` is `planning`, `worker`, or `review`.
5. Send JSON objects only, with `Content-Type: application/json`.
6. Reload the role-appropriate compact board after every successful status change before choosing more work. Workers use `GET /api/worker-board`; Reviewers use `GET /api/review-board`; Planners may use `GET /api/board`.
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
| `POST /api/register-agent` | Register at chat start; returns `agentId`. |
| `POST /api/heartbeat-agent` | Refresh presence + current task ID. |
| `POST /api/unregister-agent` | Remove an active agent before the chat ends. |
| `POST /api/add-task` | Create one new task in `todo`. |
| `POST /api/update-task` | Update allowed task fields without changing ID or status. |
| `POST /api/claim-task` | Move one task `todo` → `claimed`. |
| `POST /api/unclaim-task` | Recovery: `claimed` → `todo`. |
| `POST /api/move-to-review` | Move one task `claimed` → `review`. |
| `POST /api/claim-review` | Move one task `review` → `reviewing`. |
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
```
```powershell
Invoke-RestMethod -Uri "$base/api/worker-board?agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/review-board?agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/task-detail?taskId=TASK-YYYYMMDD-001&agentId=$agentId"
Invoke-RestMethod -Uri "$base/api/duplicate-scan?taskId=TASK-YYYYMMDD-001&agentId=$agentId&includeArchived=true&limit=25"
```

`GET /api/worker-board` and `GET /api/review-board` return only the role's active columns as compact summaries; they omit `done`, `archived`, the top-level `tasks` index, `apiAuditLog`, and policy text. After choosing a task, load full details with `GET /api/task-detail`.

`GET /api/agents` is mainly for the owner-facing viewer and diagnostics. Registered agents appear in `activeAgents`. Hidden spawned processes that have not registered yet appear in `pendingSpawns` with `processId`, `processStatus.state` (`running`, `exited`, `pid-reused`, or `unknown`), and `latestLog.preview`. Workers and Reviewers should not use this endpoint to choose tasks; use `/api/worker-board` or `/api/review-board`.

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
```

## Error Handling

- `400` means the payload is invalid or the requested transition is not allowed.
- `404` means the task ID was not found in the expected column.
- If a claim call fails, reload the role-specific board view (`GET /api/worker-board` or `GET /api/review-board`); another agent may have claimed the task first.
- Do not edit around failed claims by manually moving tasks unless the owner explicitly asks.
- If the backend is unavailable, fall back to direct `board.json` edits using the same role rules.
