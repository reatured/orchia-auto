# Multi-Agent Project Workflow

> Paste this whole page into Notion as your human-readable master spec. It documents the generic Planner / Worker / Reviewer workflow and the backend/frontend/API so a new project's AI can set itself up — or rebuild the system — from this single page. The runnable code lives in the `agent-workflow-starter` git repo.

---

## 1. Overview & when to use

This is a lightweight system for running **several AI coding agents on one project at the same time** without them stepping on each other. It works with both the **Claude** and **Codex** CLIs.

Use it when:
- You want to parallelize work across multiple agent sessions.
- You want a clear separation between *planning*, *doing*, and *reviewing*.
- You want a single, auditable source of truth for what's in flight.

Three roles, each in its own chat, never switching roles:

| Role | Does | Never does |
| --- | --- | --- |
| **Planner** | Turns requirements into deduplicated `todo` tasks | Implement code, review work, claim tasks |
| **Worker** | Claims one task, implements it, moves it to review | Move work to `done`, review work, plan |
| **Reviewer** | Reviews completed work; approves or opens a follow-up | Implement fixes, plan general work |

The owner (you) requests work, can return reviewed work with feedback, and archives accepted work.

---

## 2. The three roles

### Planner
- **Mission:** record the owner's requirements as clear, small, deduplicated `todo` tasks.
- **Start phrase:** `load as planner`
- **Boundaries:** edits only the board (`board.json`) and, when asked, workflow docs. Writes no product code. Before creating a task, scans all six columns for duplicates/overlap.
- **Output:** well-formed task cards with `requirements`, `acceptanceCriteria`, `files`, and (optionally) `inspectionTargets` and `referenceImages`.

### Worker
- **Mission:** claim exactly one unclaimed `todo` task, implement it, move it to `review`.
- **Start phrase:** `load as worker`
- **Boundaries:** works only within the claimed task's scope; never moves its own task to `done`; adds `inspectionTargets` (where to inspect) when finishing. Continues to the next safe task until told to stop.

### Reviewer
- **Mission:** claim one `review` task into `reviewing`, judge it, then approve to `done` or open a follow-up `todo`.
- **Start phrase:** `load as reviewer`
- **Boundaries:** edits only the board (plus reference images on a follow-up task). Never implements fixes. Reviews through two lenses — **quality** (clear, coherent, polished, consistent) and **correctness** (meets acceptance criteria, no regressions). Specialize these lenses per project.

---

## 3. Task board model (six columns)

The board JSON has six columns used for coordination and locking:

`todo → claimed → review → reviewing → done → archived`

| Column | Meaning |
| --- | --- |
| `todo` | Planned, unclaimed work (Planner). |
| `claimed` | A Worker is actively working on it. |
| `review` | Worker finished; waiting for review. |
| `reviewing` | A Reviewer is actively reviewing it. |
| `done` | Accepted, or a failed task closed as replaced by a follow-up. |
| `archived` | Accepted work hidden from the board. |

The viewer collapses these into **three visual columns**: To Do (`claimed` above `todo`), Review (`reviewing` above `review`), and Done.

---

## 4. Workflow loop

1. Owner gives requirements to a **Planner** → Planner creates `todo` tasks.
2. A **Worker** reads the worker board, claims one `todo` task (→ `claimed`), implements it, moves it to `review` with `inspectionTargets`, then checks for the next safe task.
3. A **Reviewer** claims a `review` task (→ `reviewing`), inspects it, and either:
   - **approves** → `done`, or
   - **requests changes** → closes the failed task into `done` as replaced and creates/updates a follow-up `todo`.
4. The owner can return a `done` task to `review` with feedback, or archive accepted work.

**Optional upstream extension:** research/audit agents can write Markdown *handoff files* (they never touch the board); the Planner reads handoffs and converts useful findings into tasks. Add only if your project needs it.

---

## 5. Conflict & duplicate rules

- The board is the **coordination lock**. A task in `claimed` reserves its files, project area, and scope for that Worker.
- Only `claimed` (and `reviewing` for reviewers) blocks. Shared files alone do **not** block — same-file work can proceed when scopes differ or when tasks link via `relatedTaskIds` / `dependsOn` / `sourceReviewTaskId`.
- If two agents want the same task, the one already in `claimed`/`reviewing` wins; the other picks another task.
- Planner and Reviewer must **deduplicate before creating** a task: scan every column by title, scope, files, acceptance criteria, and relationship fields. If a match exists, update it instead of creating a new task.

---

## 6. Backend spec (task-board server)

A small **Python 3.10+ HTTP server** (standard library only) owns the board file and exposes a REST API so claims and moves are **atomic**. Key responsibilities:

- Reads project-specific values from a **`config.json`** (project name, board title, owner label, dev-server URL, host/port, CLI command names). Nothing project-specific is hardcoded.
- Persists the board with an **atomic write** (write a temp file, then replace) so a crash never corrupts it.
- Validates task titles (rejects blank / "Untitled").
- Maintains **active-agent presence** (register / heartbeat / unregister) and an **append-only audit log** (JSON Lines) separate from the viewer's log.
- Can **spawn** Worker/Reviewer agents as hidden non-interactive CLI processes (branches for `claude` vs `codex`), with optional **auto-dispatch** (per-role model, max agents, on/off).

### `board.json` shape (top level)

```json
{
  "schemaVersion": "1.0",
  "boardName": "Project Task Board",
  "updatedAt": "",
  "columns": {
    "todo": [], "claimed": [], "review": [],
    "reviewing": [], "done": [], "archived": []
  }
}
```

### Task shape (core fields)

```json
{
  "id": "TASK-YYYYMMDD-###",
  "title": "Short action-oriented title",
  "project": "Feature area",
  "priority": "high | normal | low",
  "type": "planning | design | implementation | qa | docs | cleanup",
  "status": "todo",
  "requestedBy": "owner",
  "createdBy": "Planner",
  "summary": "1–2 sentences.",
  "requirements": [],
  "acceptanceCriteria": [],
  "files": [],
  "dependsOn": [],
  "relatedTaskIds": [],
  "sourceReviewTaskId": "",
  "referenceImages": [{ "path": "", "description": "", "source": "" }],
  "inspectionTargets": [{ "label": "", "url": "", "path": "", "viewport": "", "state": "", "notes": "" }],
  "redoCount": 0,
  "notes": ""
}
```
Status/transition fields (`claimedBy`, `claimedAt`, `reviewClaimedBy`, `reviewClaimedAt`, `reviewRequestedAt`, `doneAt`, `reviewedBy`, `reviewedAt`, `reviewDecision`) are managed by the API as tasks move.

### REST API contract

Base URL from config (default `http://127.0.0.1:4177`). Agents use `/api/...`; the viewer uses `/viewer/...`.

**Reads:** `GET /api/board`, `/api/worker-board` (`todo`+`claimed`), `/api/review-board` (`review`+`reviewing`), `/api/task-detail?taskId=…`, `/api/duplicate-scan?taskId=…&includeArchived=true`, `/api/agents`, `/api/agent-schema`.

**Presence:** `POST /api/register-agent` (→ returns `agentId`), `/api/heartbeat-agent`, `/api/unregister-agent`.

**Planner:** `POST /api/add-task`, `/api/update-task`, `/api/delete-task` (cleanup only).

**Worker:** `POST /api/claim-task` (`todo`→`claimed`), `/api/move-to-review` (`claimed`→`review`), `/api/unclaim-task` (recovery).

**Reviewer:** `POST /api/claim-review` (`review`→`reviewing`), `/api/approve-review` (`reviewing`→`done`), `/api/request-changes` (close failed + create/update follow-up).

**Owner/viewer:** `POST /viewer/return-to-review` (`done`→`review` with feedback), `/viewer/archive`, `/viewer/unclaim-task`, `/viewer/dispatch-settings`.

**Contract rules:** register first, then include `agentId` in every payload; send `Content-Type: application/json`; reload the role's compact board after each status change; use `duplicate-scan` instead of loading the whole board. `400` = invalid/disallowed transition, `404` = task not found in the expected column. If the backend is down, edit `board.json` directly using the same rules.

---

## 7. Frontend spec (read-only viewer)

A single static **HTML page** served by the backend. It is the **owner's reader view** — agents never read or edit it during normal work. It:

- Polls the board and renders the three visual columns (To Do, Review, Done), highlighting `claimed` and `reviewing` cards.
- Renders each active agent as a **chip**: background color = model (orange Claude, blue Codex), border color = role. Colors come from a shared `agent-color-schema.json`.
- Shows active Worker/Reviewer counts in column headers.
- Provides owner controls: return a `done` task to review with feedback, archive, unclaim a dead worker's task, and Spawn / auto-dispatch agents.

---

## 8. Codex + Claude compatibility

- Agents are launched by their CLI and read **`AGENTS.md`** (and `CLAUDE.md`) at session start — both Claude and Codex honor `AGENTS.md`. (A Notion page like this one is for humans; a CLI can't read it at startup, which is why the runnable spec lives in the repo.)
- The spawn logic branches per tool: Codex runs `codex exec --skip-git-repo-check "<prompt>"`; Claude runs `claude -p "<prompt>"`. Command names are configurable.
- The `model` field on every agent (`claude` or `codex`) drives the chip color and spawn behavior, so a single board can mix both tools.

---

## 9. Set up a new project (checklist)

1. **Clone the starter repo** into (or alongside) your project.
2. **Edit `task-board/config.json`:** `projectName`, `boardTitle`, `owner`/`ownerLabel`, `devServerUrl`, `host`/`port`, `spawn` command names.
3. **Tailor the role files** (`roles/*.md`): list the source directories agents must not edit; specialize the Reviewer's quality + correctness lenses for your domain.
4. **(Optional)** edit `agent-color-schema.json` (`personalNamePool`); add upstream research/audit roles if needed.
5. **Run the backend:** `python task-board/server.py` → open the viewer URL it prints.
6. **Start agents** in separate chats with `load as planner` / `load as worker` / `load as reviewer`.
7. Keep this Notion page as the shareable master copy; keep `AGENTS.md` + the repo as what the agents actually read.
