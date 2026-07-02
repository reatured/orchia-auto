# Site Audit Handoff to Planner

## Audit Metadata

- Target: `http://127.0.0.1:4177/viewer.html`
- Date: 2026-07-01 19:29 PDT
- Auditor: Site Auditor
- Viewports: Desktop and mobile requested by role default, but not visually inspected.
- Auth/state: Local task-board backend running at `http://127.0.0.1:4177`; no authentication required.
- BrowserOS coverage summary: BrowserOS/in-app browser was unavailable in this session, so the audit used read-only backend endpoints plus static viewer HTML checks. No task-board tasks were created or mutated.
- Blockers: No browser target was exposed for click-through, hover, keyboard, screenshot, or responsive validation. Board has no tasks, so task expansion, review, done, and archive flows could not be exercised with real cards.

## Executive Summary

The task-board viewer and backend are reachable, and the main viewer surfaces are present in the served HTML. Core read APIs for board data, agents, logs, system status, workflow map, handoff files, pause status, agent schema, and dispatch settings all responded successfully. The main actionable concern is that system status is currently `watch` because one stale worker record remains in active-agent state. Several UI features still need a true BrowserOS pass because they depend on click, hover, focus, responsive layout, or safe mutation.

## Coverage Map

| Area / route | Features checked | Result | Notes |
| --- | --- | --- | --- |
| `/viewer.html` | Viewer shell load | Pass | Returned `200 text/html`; served size was 310,893 bytes. |
| `/board.json` | Board load source | Pass | Returned `200 application/json`; board has valid columns and zero tasks. |
| `/api/board` | Board API data | Pass | Returned valid board with empty `todo`, `claimed`, `review`, `reviewing`, `done`, and `archived` arrays. |
| Viewer top controls | Reload JSON, auto refresh, file load | Partial | Controls exist in HTML; click behavior was not browser-tested. |
| Visual lanes | To Do / Review / Done rendering | Pass with limited data | Source data is valid, but all counts are `0`; no populated-card rendering was verified. |
| Task cards | Expand/collapse behavior | Partial | Collapse code/control exists; no task cards available to exercise. |
| Agents lane | Active/stale agent chips and log previews | Partial | Agent APIs work; one active planner and one stale worker are reported. Hover popover was not verified. |
| Dispatch controls | Spawn controls, model selectors, auto-dispatch settings | Partial | Dispatch settings API works; worker/review auto-dispatch disabled with max `1`. Spawn was not triggered. |
| Pause controls | Pause status, pause/resume/hard-stop controls | Partial | Pause status API reports not paused. Mutating pause controls were not used to avoid side effects. |
| Archive tray | Archived task count and archive flow | Partial | Tray exists; no archived tasks and archive action was not exercised. |
| Workflow panel | Workflow graph, handoff files | Pass | Workflow map and handoff-file endpoints respond; no handoff files were present before this audit. |
| Planner chat / settings / logs | Planner chat controls, settings, agent logs tray | Partial | Controls and backing endpoints exist. Agent logs endpoint returned one worker log. Click-through was not verified. |

## Functional Findings

### Stale Worker Record Keeps System In Watch State

- Severity: normal
- Area: Agent/system status
- Evidence: `/api/system-status?agentId=agt_4cce56f2` returned `"status": "watch"` and warning `"1 stale agent record(s)"`. `/api/agents` shows stale worker `ada` / `agt_89de2a01` with `currentTaskId` `TASK-20260630-001`.
- Expected: The owner can quickly distinguish active work from stale historical records, and stale records should not create ambiguity about current board health.
- Actual: The system status is not `ok` because a stale worker remains in active-agent state.
- Planner task suggestion: Add or verify a stale-agent cleanup/recovery workflow in the viewer, or improve stale-agent messaging so the owner knows whether action is required.

### Interactive Features Still Need BrowserOS Verification

- Severity: normal
- Area: Viewer interactions
- Evidence: BrowserOS/in-app browser discovery returned no available browser targets, so click, hover, keyboard, screenshot, and responsive checks could not be performed.
- Expected: Site Auditor can verify controls by interacting with the live viewer and capturing visual evidence.
- Actual: This audit could only confirm that controls and backing endpoints exist.
- Planner task suggestion: Schedule a follow-up QA audit with BrowserOS enabled to exercise reload, auto refresh, lane collapse, task collapse, logs tray, workflow panel, settings panel, planner chat, hover popovers, and responsive layouts.

### Empty Board Prevents End-To-End Card Flow Testing

- Severity: low
- Area: Task card rendering and archive/review flows
- Evidence: `/api/board` and `/api/system-status` both report zero tasks across every board column.
- Expected: QA can inspect representative cards in To Do, Review, Done, and Archived states without risking production board state.
- Actual: Empty lanes prevent validation of task card layout, expand/collapse content, archive movement, review feedback forms, and done focus behavior.
- Planner task suggestion: Create a safe test fixture or documented local sample board path for viewer QA, separate from real coordination state.

## Design And Style Feedback

### No Visual Layout Evidence Captured

- Severity: normal
- Area: Responsive design and visual polish
- Evidence: BrowserOS screenshots were unavailable; static checks only confirmed the presence of viewer sections and controls.
- Design concern: The audit cannot confirm text fit, tray positioning, side-tab usability, hover popover placement, mobile overflow, or visual hierarchy.
- Suggested direction: Run the viewer in desktop and mobile viewports and capture screenshots for the topbar, board lanes, archive tray, workflow tray, settings tray, and agent logs tray.
- Planner task suggestion: Add a QA task for responsive visual verification of the task-board viewer once BrowserOS is available.

## Responsive And Accessibility Notes

- Finding: Keyboard and focus behavior for side trays, task toggles, Planner chat, settings, and logs was not verified.
- Evidence: BrowserOS snapshot and keyboard interaction were unavailable.
- Suggested direction: In the follow-up browser audit, verify visible focus states, escape/close behavior, tab order, accessible labels on icon-like buttons, and mobile tap target sizes.

- Finding: Hover-only agent log popovers need an accessibility check.
- Evidence: Agent log preview data exists, but hover/focus popover behavior was not exercised.
- Suggested direction: Confirm log previews are reachable by keyboard focus and remain readable without clipping on narrow screens.

## Planner-Ready Task Candidates

| Priority | Suggested task title | Area/files if known | Acceptance criteria seed |
| --- | --- | --- | --- |
| normal | Verify stale-agent cleanup and messaging | `task-board/viewer.html`, `task-board/server.py` | Owner can identify stale agents, understand whether action is needed, and clear or ignore stale state without confusing the active-agent count. |
| normal | Run BrowserOS click-through QA for viewer controls | `task-board/viewer.html` | Browser audit covers reload, auto refresh, side trays, task toggles, settings, logs, planner chat, dispatch controls, and keyboard close/focus behavior with evidence screenshots. |
| low | Add a safe sample-board fixture for viewer QA | `task-board/` | QA can load representative To Do, Review, Done, and Archived cards without mutating the real board; sample data includes long text, dependencies, agents, review feedback, and archived tasks. |
| normal | Verify responsive layout of viewer trays and board lanes | `task-board/viewer.html` | Desktop and mobile screenshots show no overlapping text, clipped controls, inaccessible side tabs, or unreadable popovers. |

## Open Questions

- Should stale active-agent records be manually clearable from the viewer, automatically aged out, or left as audit history only?
- Is it acceptable to add a non-production sample board fixture for QA, or should all viewer testing use temporary API-created tasks that are deleted afterward?
- Can BrowserOS/in-app browser access be enabled for the next audit pass?

## Evidence Index

- `GET http://127.0.0.1:4177/viewer.html` returned `200 text/html`.
- `GET http://127.0.0.1:4177/board.json` returned `200 application/json`.
- `GET http://127.0.0.1:4177/api/pause-status?agentId=agt_4cce56f2` returned not paused with `remainingText: "0s"`.
- `GET http://127.0.0.1:4177/api/board?agentId=agt_4cce56f2` returned zero tasks across all columns.
- `GET http://127.0.0.1:4177/api/agents?agentId=agt_4cce56f2` returned one active planner and one stale worker.
- `GET http://127.0.0.1:4177/api/agent-logs?agentId=agt_4cce56f2&limit=10` returned one worker log file.
- `GET http://127.0.0.1:4177/api/system-status?agentId=agt_4cce56f2` returned `status: "watch"` with warning `1 stale agent record(s)`.
- `GET http://127.0.0.1:4177/api/workflow-map?agentId=agt_4cce56f2` returned the workflow graph.
- `GET http://127.0.0.1:4177/api/workflow-handoff-files?agentId=agt_4cce56f2` returned no existing handoff files before this file was written.
- Static HTML checks found controls/sections for reload, auto refresh, board lanes, archive tray, workflow panel, agent logs, settings, pause controls, spawn controls, auto-dispatch, task collapse, and Planner chat.
