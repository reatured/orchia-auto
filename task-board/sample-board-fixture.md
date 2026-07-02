# Sample Board Fixture

`sample-board.fixture.json` is non-production data for task-board viewer QA. It is intentionally separate from `task-board/board.json`; do not copy, rename, or save it over the live board.

## Safe Use

1. Start the local backend and open `http://127.0.0.1:4177/viewer.html`.
2. Click `Load JSON file`.
3. Select `task-board/sample-board.fixture.json`.
4. Inspect card rendering, lane collapse, task collapse, keyboard focus, the Review and Done states, and the Archived tray.
5. Click `Reload JSON` to return to the live `board.json`.

The fixture is loaded client-side by the viewer file input. Loading it does not update `task-board/board.json` and does not call a task-board mutation API.

## Coverage

- `todo`: long To Do cards, dependency metadata, related task IDs, blockers, files, and inspection targets.
- `claimed`: worker ownership fields and claimed-card styling.
- `review`: waiting review card with multiple inspection targets.
- `reviewing`: active reviewer ownership and review notes.
- `done`: approved and replaced cards, review notes, failure metadata, owner feedback, and redo count.
- `archived`: archived card data, archive timestamp, archive owner, and archive-tray count.

All sample task IDs use the `SAMPLE-QA-` prefix so they do not collide with normal `TASK-YYYYMMDD-###` board records.

## Mutation Controls

Use this fixture for visual, layout, collapse, focus, and tray inspection. Do not use it as a source of truth for live workflow actions. If a QA pass needs to verify destructive or state-changing controls, create disposable real tasks through the backend and clean them up afterward with evidence. The fixture path is for safe rendering coverage only.
