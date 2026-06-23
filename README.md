# orchia-auto

A reusable, project-agnostic **multi-agent workflow** for coordinating AI coding agents (Claude or Codex CLIs) on a single project. It ships a clean three-role core — **Planner**, **Worker**, **Reviewer** — backed by a small local task-board server, a JSON board, and a read-only HTML viewer.

Copy this repo into a new project, adjust a few config values and role files, and start coordinating multiple agents on real work without them stepping on each other.

---

## What is this for?

When you run more than one AI coding agent on the same project at the same time, two things go wrong: agents duplicate each other's work, and they edit the same files with no idea the other is mid-change. `orchia-auto` solves that with a shared, auditable **task board** that acts as the single source of truth and the coordination lock.

It gives you a clear separation between **planning**, **doing**, and **reviewing**, so each agent has one job and one job only:

- **Planner** — turns your requirements into small, deduplicated `todo` tasks on the board. Never writes product code.
- **Worker** — claims exactly one task at a time, implements it, and moves it to `review`. Never reviews or marks its own work done.
- **Reviewer** — reviews completed work and either approves it to `done` or opens a follow-up `todo`. Never implements fixes.

Each agent runs in its own chat and never switches roles. Because every claim and status change goes through the board, you (the owner) always have one place to see what is planned, in progress, under review, and finished — and a full audit log of who did what.

### When to use it

- You want to **parallelize** work across several agent sessions (e.g. three Workers building three features at once).
- You want a clear, enforced boundary between *planning*, *doing*, and *reviewing*.
- You want a **single, auditable source of truth** for everything in flight.
- You're mixing tools — some agents on **Claude**, some on **Codex** — and want them on one board.

### When it's overkill

- A single agent doing a single task. The board's coordination value only shows up with concurrency or a deliberate plan→do→review handoff.

---

## How it works

The board (`task-board/board.json`) is the single source of truth and the coordination lock. A small Python server exposes a REST API so that claiming a task and moving it between states are **atomic** — two agents can never grab the same task. If the server isn't running, agents fall back to editing the JSON directly using the same rules.

Tasks flow through six columns:

```
todo → claimed → review → reviewing → done → archived
```

| Column | Meaning |
| --- | --- |
| `todo` | Planned, unclaimed work (created by the Planner). |
| `claimed` | A Worker has claimed it and is actively working. |
| `review` | Worker finished; waiting for review. |
| `reviewing` | A Reviewer has claimed it and is actively reviewing. |
| `done` | Accepted work (or failed work closed and replaced by a follow-up). |
| `archived` | Accepted work hidden from the main board. |

The **read-only HTML viewer** (`task-board/viewer.html`) is your window into the board. It collapses the six columns into three visual ones (**To Do**, **Review**, **Done**) and shows each active agent as a colored chip — **background = model** (orange Claude, blue Codex), **border = role**. Agents never read or edit the viewer; it's purely for you.

The board is the **lock**: a task in `claimed` reserves its files and scope for that Worker. Shared files alone don't block — same-file work can proceed when scopes differ. Before creating a task, the Planner and Reviewer scan every column for duplicates so the board never fills with overlapping work.

See [`workflow/workflow-overview.md`](workflow/workflow-overview.md) for the full model and rules, and [`workflow/api-guide.md`](workflow/api-guide.md) for the REST API contract.

---

## Requirements

- **Python 3.10+** (standard library only — no third-party packages, no `pip install`).
- A coding-agent CLI: **Claude** (`claude`) and/or **Codex** (`codex`). Both are supported; configure the command names in `task-board/config.json`.

---

## Setup

### 1. Get the repo

Clone it into (or alongside) your project:

```bash
git clone https://github.com/reatured/orchia-auto.git
cd orchia-auto
```

### 2. Configure for your project

Edit [`task-board/config.json`](task-board/config.json). Every project-specific value lives here — **nothing is hardcoded in the server**:

```json
{
  "projectName": "Your Project Name",
  "boardTitle": "Project Task Board",
  "owner": "owner",
  "ownerLabel": "the project owner",
  "devServerUrl": "http://localhost:3000",
  "host": "127.0.0.1",
  "port": 4177,
  "projectRoot": "..",
  "spawn": { "claudeCommand": "claude", "codexCommand": "codex" }
}
```

| Field | What it does |
| --- | --- |
| `projectName` / `boardTitle` | Shown in the viewer. |
| `owner` / `ownerLabel` | Who requests and accepts work (used in task metadata and re-review notes). |
| `devServerUrl` | Base URL used in inspection-target examples (e.g. your local app). |
| `host` / `port` | Where the server listens. Default `127.0.0.1:4177`. |
| `projectRoot` | Path (relative to `task-board/`) to your actual project root. |
| `spawn.claudeCommand` / `spawn.codexCommand` | The CLI command names on your machine. |

### 3. Tailor the role files

Edit the files in [`roles/`](roles/) to fit your project:

- In `planner.md` and `reviewer.md`, fill in the project-specific **"do not edit"** directories (the source paths agents must not touch).
- Specialize the **Reviewer's two review lenses** (quality + correctness) for your domain. The default is generic; search each file for the `> Adapt for your project` notes.

### 4. (Optional) Tweak appearance and extend

- Edit [`task-board/agent-color-schema.json`](task-board/agent-color-schema.json) to change the `personalNamePool` (the short names agents pick from) or the chip colors.
- If you need research/audit agents that feed the Planner, follow the **"Extending the workflow"** section in [`workflow/workflow-overview.md`](workflow/workflow-overview.md). Upstream agents write Markdown handoff files; only the Planner ever creates tasks.

### 5. Start the backend

```bash
# macOS / Linux / Git Bash
python task-board/server.py
```

```powershell
# Windows PowerShell
python task-board\server.py
```

It prints the viewer URL, e.g.:

```
Project Task Board: serving at http://127.0.0.1:4177/viewer.html
```

Open that URL in a browser to watch the board.

### 6. Start agents

Open a **separate chat per agent** and load a role with its start phrase:

| Start phrase | Role | What it does |
| --- | --- | --- |
| `load as planner` | Planner | Reads your requirements, creates `todo` tasks. |
| `load as worker` | Worker | Claims a task, implements it, moves it to `review`. |
| `load as reviewer` | Reviewer | Reviews completed work; approves or sends back. |

A typical first run: give requirements to a **Planner** chat → start one or more **Worker** chats to claim and build → start a **Reviewer** chat to approve. Watch it all move on the viewer.

> The viewer also has **Spawn** buttons and optional **auto-dispatch** to launch Workers/Reviewers as hidden CLI processes — handy once you're comfortable with the manual flow.

---

## Repository layout

```
orchia-auto/
  README.md                     # this file
  AGENTS.md                     # entry point both Claude and Codex read first
  CLAUDE.md                     # one-line pointer to AGENTS.md
  roles/
    planner.md  worker.md  reviewer.md
  workflow/
    workflow-overview.md        # the three-role model, columns, rules
    api-guide.md                # REST API contract + curl/PowerShell examples
  task-board/
    config.json                 # EDIT THIS for your project
    server.py                   # task-board backend (reads config.json)
    board.json                  # the board (starts empty)
    viewer.html                 # read-only board viewer
    agent-color-schema.json     # chip colors + personal-name pool
  notion-page.md                # paste-ready master spec for a Notion / wiki page
```

---

## How agents coordinate (the contract)

Every agent that talks to the API:

1. **Registers** at chat start: `POST /api/register-agent` with `personalName`, `model` (`claude` or `codex`), and `role` → receives an `agentId`.
2. **Includes that `agentId`** in every later request — it's the contract key.
3. **Reloads** its compact board view after each status change (`/api/worker-board` or `/api/review-board`) and uses `/api/duplicate-scan` instead of loading the whole board.
4. Workers and Reviewers **heartbeat** after claiming/moving a task and **unregister** before ending.

The server writes an append-only audit log (`task-board/task-board-api.log`, JSON Lines) and persists the board with an **atomic write** (temp file + `os.replace`), so a crash mid-write never corrupts `board.json`. See [`workflow/api-guide.md`](workflow/api-guide.md) for every endpoint with `curl` and PowerShell examples.

---

## Notes

- Runtime artifacts (`*.log`, `active-agents.json`, `agent-dispatch-settings.json`, `spawned-agent-logs/`, `*.json.tmp`, `__pycache__/`) are git-ignored; the server regenerates them.
- Works on Windows, macOS, and Linux. On Windows use `python task-board\server.py`.
- `notion-page.md` is a paste-ready human-readable master spec — drop it into Notion or any wiki to share the workflow with your team.
