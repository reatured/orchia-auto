---
name: reviewer-workflow
description: Systematic process for acting as a reviewer agent in the task board workflow, including code review techniques when browser inspection is unavailable.
source: auto-skill
extracted_at: '2026-06-24T22:04:30.406Z'
---

# Reviewer Agent Workflow

When loaded as a reviewer agent, follow this systematic process to review completed work and make approval decisions.

## Role Setup Sequence

1. **Read role files**: Load `roles/reviewer.md` and `workflow/workflow-overview.md`
2. **Read API guide**: Load `workflow/api-guide.md` for exact endpoint payloads
3. **Register with backend**: `POST /api/register-agent` with `personalName`, `model`, `role: "review"`
   - Capture the returned `agentId` and use it for every subsequent API call
4. **Check review board**: `GET /api/review-board?agentId=...` to see pending tasks
5. **Claim a task**: `POST /api/claim-review` with `taskId`
6. **Heartbeat**: `POST /api/heartbeat-agent` with `currentTaskId` to stay active

## Review Process

### 1. Get Full Task Details
```bash
curl -s "http://127.0.0.1:4177/api/task-detail?taskId=TASK-YYYYMMDD-###&agentId=$agentId"
```

Extract:
- **Acceptance criteria**: The specific pass conditions to verify
- **Requirements**: The implementation requirements
- **Inspection targets**: URLs/paths/viewport states where the reviewer should check the work
- **Files changed**: Which files were modified

### 2. Code-Level Review (Always Do This)

#### For JS/HTML/CSS changes:
- **Verify JS syntax**: Extract inline `<script>` and parse with `new Function(scriptContent)`
  ```bash
  node -e "
  var fs = require('fs');
  var html = fs.readFileSync('task-board/viewer.html', 'utf8');
  var scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  try {
    new Function(scriptMatch[1]);
    console.log('JS syntax OK');
  } catch(e) {
    console.log('JS syntax ERROR:', e.message);
    process.exit(1);
  }
  "
  ```

- **Verify Python compiles**: `python3 -m py_compile task-board/server.py`

- **Check for dead CSS**: Grep for old class names mentioned in requirements to confirm removal
  ```bash
  grep -n "old-class-name" task-board/viewer.html
  # Should return 0 matches if properly removed
  ```

- **Verify data-driven patterns**: If a requirement says "build from data structure, not hardcoded HTML", check that the function uses objects/arrays as input rather than string literals

- **Check responsive breakpoints**: Grep for `@media` queries and verify they match requirements (e.g., mobile fallback at `< 768px`)

#### For acceptance criteria verification:
- Map each criterion to a specific code location or test
- Mark each as ✅ (verified), ⚠️ (cannot verify, explain why), or ❌ (failed)

### 3. Visual Inspection (When Browser Tools Available)

If browser/computer_use tools are available:
- Navigate to the inspection target URL
- Open the relevant UI section (e.g., workflow tray, settings panel)
- Check at required viewport widths (desktop, mobile)
- Click interactive elements to verify they work (e.g., detail modals)
- Take screenshots if issues are found

**If browser tools are unavailable**: Note this in review comments and rely on code-level verification. Explain what could not be visually confirmed but why the code logic is sound.

### 4. Make the Decision

#### Approve when:
- All acceptance criteria are verified (or unverifiable but code is sound)
- JS/Python syntax is clean
- No obvious regressions
- The implementation matches requirements

```bash
curl -s -X POST http://127.0.0.1:4177/api/approve-review \
  -H "Content-Type: application/json" \
  -d '{
    "agentId":"$agentId",
    "taskId":"TASK-YYYYMMDD-###",
    "reviewNotes":"Approved after checking [specific criteria]. [Evidence for each check]."
  }'
```

#### Request changes when:
- Acceptance criteria fail
- Syntax errors found
- Dead code remains when removal was required
- Implementation doesn't match requirements

```bash
curl -s -X POST http://127.0.0.1:4177/api/request-changes \
  -H "Content-Type: application/json" \
  -d '{
    "agentId":"$agentId",
    "taskId":"TASK-YYYYMMDD-###",
    "failureExpected":"What should be true",
    "failureActual":"What is actually happening",
    "failureDecision":"Short reason for failure",
    "reviewNotes":"Detailed evidence",
    "followUpTask":{...}
  }'
```

### 5. Continue or Finish

After each decision:
```bash
# Heartbeat
curl -s -X POST http://127.0.0.1:4177/api/heartbeat-agent \
  -H "Content-Type: application/json" \
  -d '{"agentId":"$agentId","currentTaskId":"TASK-YYYYMMDD-###"}'

# Reload review board
curl -s "http://127.0.0.1:4177/api/review-board?agentId=$agentId"
```

- If more unclaimed `review` tasks exist, claim the next one
- If review board is clear, unregister:
  ```bash
  curl -s -X POST http://127.0.0.1:4177/api/unregister-agent \
    -H "Content-Type: application/json" \
    -d '{"agentId":"$agentId","notes":"Review complete. Review board is clear."}'
  ```

## Common Review Scenarios

### Frontend UI Changes
- **Data-driven rendering**: Verify functions accept data structures, not hardcoded strings
- **Dead code removal**: Grep confirms 0 matches for removed classes/functions
- **Responsive design**: Check media queries at required breakpoints
- **Interactive elements**: Verify event handlers are preserved (click, close, backdrop)
- **CSS constraints**: Verify old fixed widths (e.g., `max-width: 420px`) are replaced with flexible units (e.g., `1fr`)

### Backend/API Changes
- **py_compile**: Always verify Python syntax
- **Endpoint contracts**: Check that new endpoints match documented payloads
- **Error handling**: Verify proper HTTP status codes and error messages

### When Browser Tools Timeout
This happens when the computer_use permission grant times out (600s). In this case:
1. Note the limitation in review comments
2. Focus on code-level verification
3. Explain why the code logic is sound even without visual confirmation
4. For SVG/coordinate math: verify the calculation logic distributes elements properly
5. For CSS layout: verify grid/flex properties match requirements
6. Use an **Explore subagent** to extract relevant code sections from large files (e.g., viewer.html with 5000+ lines). Ask it to find and return actual code blocks for specific functions, CSS rules, media queries, and event handlers. This is far more efficient than paginating through the file manually.

### Reviewer Race Conditions
When multiple reviewer agents are active, another reviewer may approve a task while you are still inspecting it. Handle this gracefully:
1. If `POST /api/approve-review` returns `"Task was not found in columns.reviewing"`, the task was already moved
2. Check the task detail to see who approved it and the outcome (`reviewedBy`, `reviewDecision`)
3. If already approved, your review is redundant — move on without error
4. Always reload the review board after any decision to catch state changes before claiming the next task
5. Before starting a long review, note if other active reviewer agents exist in the agents list — they may claim the same task

## Review Quality Checklist

Before approving, verify:
- [ ] All acceptance criteria addressed (verified or explained)
- [ ] JS syntax clean (if applicable)
- [ ] Python compiles (if applicable)
- [ ] Dead code removed (if required)
- [ ] Responsive behavior verified (if required)
- [ ] Interactive elements preserved (if applicable)
- [ ] Review notes are specific and evidence-based (not just "looks good")

## Key API Endpoints for Reviewers

| Action | Endpoint | Payload |
|--------|----------|---------|
| Register | `POST /api/register-agent` | `personalName`, `model`, `role: "review"` |
| Check board | `GET /api/review-board` | `agentId` |
| Claim task | `POST /api/claim-review` | `agentId`, `taskId` |
| Heartbeat | `POST /api/heartbeat-agent` | `agentId`, `currentTaskId` |
| Get details | `GET /api/task-detail` | `taskId`, `agentId` |
| Approve | `POST /api/approve-review` | `agentId`, `taskId`, `reviewNotes` |
| Request changes | `POST /api/request-changes` | `agentId`, `taskId`, failure details, follow-up task |
| Unregister | `POST /api/unregister-agent` | `agentId`, `notes` |

## File Write Boundaries

As a reviewer, you may only write to:
- `task-board/board.json` (via API)
- `reference-images/` (screenshots for follow-up tasks)

You may **not** modify:
- Product code, scripts, tests
- Markdown docs, `AGENTS.md`
- `task-board/viewer.html`
- Any workflow files

If a fix is needed, create a follow-up `todo` task via `request-changes` instead of implementing it yourself.
