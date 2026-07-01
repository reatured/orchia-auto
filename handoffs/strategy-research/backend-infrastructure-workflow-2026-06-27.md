# Backend Infrastructure Workflow Wedge for Orchia

Date: 2026-06-27  
Research track: A - backend infrastructure software development workflows  
Context: Assess whether Orchia's multi-agent workflow/control-plane can support software engineers developing backend infrastructure, including a possible Artly AI-style robotics/cloud backend environment.

## Executive Summary

Backend infrastructure is a strong conditional wedge for Orchia. The winning framing is not "AI task board for engineers" or "generic coding-agent manager." The stronger wedge is:

> Orchia is an AI change-control board for backend and platform teams: plan risky work, lock scope, run agents, verify with tests/logs, require approvals, and pause or hard-stop delegated work before it reaches production.

This matters because backend/platform work has expensive failure modes: broken APIs, failed migrations, bad Terraform applies, security patch regressions, noisy alerts, release miscoordination, and incident follow-up that quietly dies after the postmortem. Current tools split that work across GitHub, Linear/Jira, Slack, CI, Datadog/Grafana, PagerDuty, Terraform/Argo, and docs. AI coding agents add throughput, but they also increase the need for coordination, review, reproducibility, and an emergency stop.

For an Artly AI-like company, the wedge is especially legible. Artly appears to combine robotics, coffee operations, app/backend systems, telemetry, and analytics; ClickHouse's Artly case study describes real-time robot telemetry and dashboard workloads for its robotic baristas ([ClickHouse Artly case study](https://clickhouse.com/blog/artly-clickhouse-barista)). That kind of environment has backend APIs, cloud data pipelines, fleet operations, observability, and release safety needs. Orchia's Planner/Worker/Reviewer model maps well to small teams where one or two senior engineers are bottlenecked reviewing infra changes and operational follow-ups.

Verdict: **strong as a narrow backend/platform change-control wedge; weak as a generic developer productivity tool.** The first product should handle lower-risk but high-volume work first: security patches, CI failures, test coverage, observability chores, and incident follow-ups. Then expand into migrations, infrastructure changes, and release management once trust is earned.

## User Persona

Primary buyer/user:

- Staff/backend infrastructure engineer, platform engineering lead, SRE lead, or DevOps owner at a 20-300 engineer company.
- Responsible for API services, cloud infrastructure, CI/CD, observability, incident response, database migrations, security patching, and release coordination.
- Already uses GitHub plus Linear/Jira, CI, Slack, observability tools, and maybe an internal developer portal.
- Is experimenting with AI coding tools, but does not fully trust them around production-affecting changes.

Artly-style persona:

- Small robotics/cloud team supporting robot fleet operations, customer/mobile ordering systems, telemetry ingestion, dashboards, internal ops tooling, and production deploys.
- Pain is not only "write code faster." It is "make safe changes across backend, data, cloud, robot/fleet ops, and observability without overloading the senior reviewer."

Economic buyer:

- VP Engineering, Head of Platform, Head of Infrastructure, CTO, or technical founder.
- Buys if Orchia reduces review bottlenecks, closes reliability/security backlog, improves release confidence, and keeps AI-agent work auditable.

## Pain Orchia Can Solve

### 1. AI creates more work-in-progress than teams can safely review

GitHub Copilot coding agent can be assigned to issues and create pull requests from GitHub work ([GitHub Copilot coding agent docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/assign-copilot-to-an-issue)). Cursor, Devin, Factory, Codex, Claude Code, and similar agents can produce implementation artifacts quickly. The bottleneck moves to scoping, coordination, validation, and approval.

Orchia's opportunity: make the AI work queue visible, lock risky scopes, separate planning from execution and review, and force evidence before approval.

### 2. Backend/platform changes need explicit locks

Ordinary tickets do not always prevent two people or agents from touching the same migration, Terraform workspace, API contract, service area, alert, or release train. Orchia's task lock can become a first-class operational lock:

- API route or service lock.
- Database migration/table lock.
- Terraform workspace/environment lock.
- Incident follow-up lock.
- Release train lock.
- Security advisory lock.
- Observability dashboard/alert lock.

This is more useful than a generic "assigned to" field because it is tied to execution permissions.

### 3. Approval gates are scattered

CI tools already support approvals: GitLab has deployment approvals ([GitLab docs](https://docs.gitlab.com/ci/environments/deployment_approvals/)), CircleCI supports approval jobs in workflows ([CircleCI docs](https://circleci.com/docs/workflows/#holding-a-workflow-for-a-manual-approval)), and GitHub Actions supports protected environments/reviewers ([GitHub Actions deployment environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)). But these gates usually happen at pipeline/deploy time.

Orchia's gap: approval before the agent starts, approval before sensitive commands, approval after tests/log inspection, approval before PR merge, approval before production rollout, and approval after post-deploy verification.

### 4. Incident follow-up gets lost

PagerDuty and incident tools support response and automation ([PagerDuty AIOps](https://www.pagerduty.com/use-cases/aiops/)), while observability tools show telemetry. But post-incident actions often become scattered tickets and low-priority chores. Orchia can turn a postmortem into a visible queue: regression test, dashboard, alert threshold, runbook update, rollback drill, migration cleanup, and owner review.

### 5. Teams need an emergency brake

GitHub already recognizes that agentic coding needs admin controls, such as disabling automatic commands for Copilot coding agent ([GitHub admin docs](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-enterprise/manage-agents/disable-automatic-commands)). Orchia's pause and hard-stop model is a strong product primitive if it becomes a visible operational control:

- Pause new claims during an incident, freeze, deploy window, or rate-limit event.
- Hard-stop spawned agents doing risky work.
- Resume with task context and logs.
- Keep audit history of who stopped what and why.

## Use Cases and Workflow Presets

| Preset | Trigger | Planner output | Worker execution | Reviewer gate | Why Orchia helps |
| --- | --- | --- | --- | --- | --- |
| API service change | Product request, bug, contract update | Scope endpoint, contract, tests, migration risk, rollout plan | Implement route/schema/client changes, update docs, run tests | Validate contract tests, auth, error behavior, backward compatibility | Prevents AI from making unreviewed API-breaking changes. |
| Cloud infrastructure / IaC | Terraform/Kubernetes drift, new resource, cost/risk change | Lock workspace/environment, generate plan checklist | Edit IaC, run plan, capture diff, estimate blast radius | Approve plan before apply; verify after apply | Adds human-readable change control above Terraform/CI. |
| DevOps / CI repair | Broken pipeline, flaky job, slow build | Identify failing job and affected repos | Patch workflow, isolate flakes, add retry or fixture fix | Require green CI and explanation of failure mode | Converts noisy CI failures into accountable agent tasks. |
| Observability instrumentation | Missing trace/log/metric/dashboard | Define service signals, SLO/alert expectations | Add OpenTelemetry traces/metrics/logs, dashboard JSON, alert config | Verify signal appears and alert threshold is sane | Bridges code changes and observability review. OpenTelemetry standardizes traces, metrics, and logs ([OpenTelemetry docs](https://opentelemetry.io/docs/)). |
| Database migration | Schema change, backfill, data cleanup | Expand/contract plan, lock tables, define rollback | Create migration, backfill script, dry run, tests | Approve migration plan, staging result, rollback proof | High-value because migrations are risky and hard to parallelize safely. |
| Security patch | Dependabot/Snyk alert, CVE, package update | Triage severity, owners, test matrix, rollout | Patch dependency, fix breaking changes, run tests | Verify advisory closed and no regression | GitHub Dependabot can raise security PRs ([GitHub Dependabot docs](https://docs.github.com/en/code-security/dependabot)), but Orchia can coordinate review and rollout. |
| Incident follow-up | Postmortem action item | Break postmortem into test/alert/runbook/code tasks | Implement small follow-ups with evidence | Confirm the incident class is covered | Makes reliability work visible instead of aspirational. |
| CI/CD release management | Release train, deploy freeze, hotfix | Build release checklist, owners, gate order | Prepare release notes, changelog, smoke tests, deploy checklist | Release manager approves stage/prod | Complements pipeline tools by managing the human/agent workflow around them. |
| Test coverage sprint | Low coverage, refactor risk, flaky subsystem | Prioritize target modules and risk areas | Add tests, stabilize flakes, report coverage delta | Require meaningful assertions and green CI | Good low-risk starting use case for AI workers. |
| Robotics/fleet backend change | Robot telemetry, menu/config, remote ops, analytics | Lock fleet/service scope, define canary fleet and rollback | Patch backend/data/config workflow, add telemetry checks | Verify canary telemetry and operator dashboard | Useful for Artly-style cloud robotics teams where software changes affect physical operations. |

## Product Concept

Orchia should become a visual execution layer above existing engineering systems, not a replacement for them.

Core loop:

1. Intake from GitHub issue, Linear/Jira ticket, Dependabot alert, incident report, CI failure, observability alert, or human request.
2. Planner converts it into a scoped work order with risk class, lock scope, required tests, approval gates, and rollback expectations.
3. Worker agent claims exactly one task and operates under the lock.
4. Worker produces code/config/docs plus evidence: commands run, tests, CI links, diff summary, screenshots/logs, rollout notes.
5. Reviewer checks the evidence and either approves, requests changes, or creates follow-up tasks.
6. Owner can pause new work or hard-stop spawned workers during incidents, deploy windows, or when the work looks wrong.

The user-facing product should emphasize trust primitives:

- Scope locks.
- Risk classes.
- Approval gates.
- Test/evidence requirements.
- Logs and command traces.
- Pause/hard-stop.
- PR/CI/status links.
- Post-deploy verification.
- Follow-up task generation.

## MVP

### MVP wedge

Start with:

> AI backend maintenance board for GitHub teams: security patches, CI failures, test coverage, observability follow-ups, and review-gated PRs.

Avoid starting with production Terraform applies or live database migrations. Those are valuable, but trust must be earned.

### MVP capabilities

Minimum lovable product:

- Connect to GitHub repos and issues/PRs.
- Import or create work orders from GitHub Issues, Dependabot alerts, failed CI runs, and manual prompts.
- Maintain Orchia board columns: Todo, Claimed, Review, Reviewing, Done.
- Define `lockScope` fields: repo, service, path, migration, environment, release, alert, incident.
- Run selected coding agents locally or in a controlled runner.
- Capture worker logs, commands, changed files, tests run, and PR links.
- Require Reviewer approval before marking done.
- Support pause and hard-stop for active spawned workers.
- Provide workflow presets for security patch, CI repair, test coverage, observability task, incident follow-up, and API bugfix.
- Show a compact "why this is safe" evidence panel: tests, CI, risk notes, rollback notes, pending approvals.

Nice-to-have after MVP:

- Linear/Jira sync.
- Slack notifications.
- Datadog/Grafana/PagerDuty links.
- Terraform plan artifact capture.
- Deployment environment gates.
- Service catalog integration with Backstage/Port/Cortex.
- Policy-as-code checks and compliance reports.

### First pilot

For an Artly-style pilot, use three controlled workflows:

1. Dependabot/security patch triage to PR.
2. CI failure or flaky test repair.
3. Incident follow-up from postmortem to regression test + dashboard/alert/runbook update.

Success metrics:

- Percent of AI-created PRs approved without major rework.
- Senior engineer review time saved.
- Time from alert/ticket to reviewed PR.
- Number of stale security/incident follow-ups closed.
- Reduction in duplicated/conflicting work.
- Subjective trust score from reviewers.

## Competitive Landscape

### Issue trackers and project managers

| Tool | Strength | Why it matters | Orchia gap/opportunity |
| --- | --- | --- | --- |
| GitHub Issues/Projects | Native to repos, issues, PRs, project views, automation ([GitHub Projects docs](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)). | Engineers already live here. | Orchia should sync with GitHub, not replace it. Differentiate on execution locks, agent logs, approval gates, and pause/hard-stop. |
| Linear | Fast issue tracker with engineering workflows and AI/agent ecosystem positioning ([Linear Agents](https://linear.app/agents), [Linear MCP](https://linear.app/docs/mcp)). | Strong default for startups. | Linear is the planning/status system; Orchia can be the controlled AI execution board. |
| Jira / Atlassian | Enterprise issue tracking, workflows, automation, Rovo AI agents ([Atlassian Rovo Agents](https://www.atlassian.com/software/rovo/agents), [Jira](https://www.atlassian.com/software/jira)). | Enterprise distribution and governance. | Hard to beat as system of record. Orchia should export status/evidence into Jira rather than compete head-on. |

### Coding agents and AI IDEs

| Tool | Strength | Why it matters | Orchia gap/opportunity |
| --- | --- | --- | --- |
| GitHub Copilot coding agent | Can be assigned work from GitHub and create PRs; embedded in repo workflow ([Copilot coding agent docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/assign-copilot-to-an-issue)). | Massive distribution; strong threat. | Orchia can orchestrate multiple agents/tools and add task locks, cross-system workflows, infra-specific gates, and local hard-stop. |
| Cursor | AI IDE with agentic coding, background agents, and integrations ([Cursor pricing](https://cursor.com/pricing), [Cursor docs](https://docs.cursor.com/)). | Strong developer adoption and local workflow fit. | Cursor helps one engineer code; Orchia coordinates many delegated tasks and reviewers. |
| Devin | Autonomous software engineer for coding tasks ([Devin](https://devin.ai/), [Devin pricing](https://devin.ai/pricing)). | Strong autonomous-engineer brand. | Orchia should not try to be a better Devin; it can supervise Devin/Codex/Cursor/Claude-style workers with review gates. |
| Factory | Droids for software development lifecycle work ([Factory](https://www.factory.ai/), [Factory pricing](https://www.factory.ai/pricing)). | Very close competitor if Orchia pitches "agent workforce for engineering." | Orchia must narrow to infra change-control, locks, logs, and operational gates. |
| OpenAI Codex / Claude Code | Powerful agentic coding surfaces ([Codex docs](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan), [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/overview)). | Model/platform vendors can add workflow controls. | Orchia should be model-agnostic and emphasize orchestration, policy, and audit across tools. |

### Review and CI tools

| Tool/category | Strength | Why it matters | Orchia gap/opportunity |
| --- | --- | --- | --- |
| CodeRabbit | AI pull request review, plans, and GitHub/GitLab integration ([CodeRabbit pricing](https://www.coderabbit.ai/pricing)). | Code review is an obvious AI foothold. | Orchia can treat CodeRabbit as a review signal, but still own task lifecycle, evidence, and operational approval. |
| GitHub Actions / GitLab / CircleCI | CI/CD, environments, manual approvals, test gates ([GitHub Actions environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment), [GitLab deployment approvals](https://docs.gitlab.com/ci/environments/deployment_approvals/), [CircleCI workflows](https://circleci.com/docs/workflows/)). | These already enforce build/deploy gates. | Orchia sits before and around CI: task scoping, agent execution, reviewer evidence, rollback plan, incident follow-up. |
| Argo CD / Harness | GitOps and continuous delivery workflows ([Argo CD docs](https://argo-cd.readthedocs.io/), [Harness CD](https://www.harness.io/products/continuous-delivery)). | Strong production deployment control. | Orchia should link to deploy gates, not replace them. |

### Platform engineering tools

| Tool | Strength | Why it matters | Orchia gap/opportunity |
| --- | --- | --- | --- |
| Backstage | Open-source developer portal, service catalog, templates, docs ([Backstage docs](https://backstage.io/docs/overview/what-is-backstage/)). | Many platform teams already centralize service ownership here. | Orchia can use the service catalog to define locks and owners. |
| Port | Internal developer portal, scorecards, self-service actions ([Port](https://www.getport.io/)). | Strong overlap with workflow/status around services. | Orchia must be the AI execution/review layer, not another IDP. |
| Cortex | Service catalog and scorecards ([Cortex](https://www.cortex.io/)). | Helps manage ownership, standards, reliability. | Orchia can turn scorecard gaps into AI work orders. |
| Humanitec | Platform orchestrator and internal developer platform automation ([Humanitec](https://humanitec.com/)). | Strong around self-service infrastructure. | Orchia should avoid becoming a platform orchestrator; integrate with one for approved changes. |

## Buyer and Willingness to Pay

The buyer pays for reliability, speed, and review leverage, not for another board.

Reference pricing signals:

- GitHub Copilot Business/Enterprise is priced per user and is already an approved engineering spend category ([GitHub Copilot pricing](https://github.com/features/copilot/plans)).
- Cursor sells individual and team plans for AI coding workflows ([Cursor pricing](https://cursor.com/pricing)).
- Linear and Jira price per seat as planning systems ([Linear pricing](https://linear.app/pricing), [Jira pricing](https://www.atlassian.com/software/jira/pricing)).
- CodeRabbit prices AI review per seat/repository tier ([CodeRabbit pricing](https://www.coderabbit.ai/pricing)).
- Devin and Factory show that teams will pay materially more for autonomous coding labor than for ordinary project management ([Devin pricing](https://devin.ai/pricing), [Factory pricing](https://www.factory.ai/pricing)).

Pricing hypothesis:

- Solo/staff engineer trial: $29-$79/month for local board, GitHub sync, BYO agents.
- Small infra team: $299-$999/month for 5-15 users, shared board, agent logs, PR/CI integration, workflow presets, pause/hard-stop.
- Platform team: $1,500-$5,000/month for multi-repo, Linear/Jira sync, SSO, policy templates, observability links, audit exports.
- Enterprise/on-prem/VPC: $15k-$75k/year depending on security, compliance, runner isolation, and integration scope.

WTP is highest when Orchia is tied to:

- Reducing senior reviewer time.
- Closing security patch backlog.
- Reducing incident recurrence.
- Making AI-generated infra work auditable.
- Avoiding production mistakes.
- Coordinating many parallel agents without file/service conflicts.

WTP is low if Orchia is perceived as:

- Another Kanban board.
- A thin wrapper around GitHub Issues.
- A coding agent without a differentiated model.
- A local hobbyist tool.

## Investor Appeal

Why this can be fundable:

- AI coding adoption creates a new coordination problem: more generated work needs human-grade control.
- Backend/platform teams have budget and acute reliability stakes.
- The wedge sits next to expensive outcomes: downtime, security exposure, migration failure, release risk, senior engineer bottlenecks.
- Orchia already has differentiated primitives: Planner/Worker/Reviewer separation, locks, audit logs, hidden agent dispatch, review gates, pause/hard-stop, and handoff intake.
- The product can expand from maintenance workflows into a broader "agentic SDLC control plane" after proving trust in one narrow surface.
- DORA-style software delivery metrics give a familiar executive language: deployment frequency, lead time, change failure rate, and time to restore service ([DORA metrics](https://dora.dev/guides/dora-metrics-four-keys/)).

Investor-grade one-liner:

> Orchia is the control plane that lets engineering teams safely delegate backend and infrastructure work to AI agents, with task locks, approval gates, logs, tests, and emergency stops.

Best wedge narrative:

> AI agents can now write backend code. Orchia makes that work safe enough for production teams.

## Competitive Risks

### 1. GitHub can absorb the workflow

GitHub owns repos, issues, PRs, Actions, Copilot, Dependabot, code review, and enterprise admin. It can add better agent queues, logs, approvals, and stop controls close to the source of truth. This is the largest platform risk.

Mitigation: be model-agnostic, local/on-prem friendly, multi-repo/multi-system, and focused on infra workflows that span GitHub, CI, observability, incidents, and platform tools.

### 2. Linear/Jira can become agent-native systems of record

Linear is already advertising agents as first-class collaborators, and Atlassian is pushing Rovo agents. If they own planning plus AI execution status, Orchia cannot win as a tracker.

Mitigation: sync with them. Do not compete for the issue database. Compete for controlled execution, locks, logs, and approval evidence.

### 3. Coding agents can add lightweight boards

Cursor, Devin, Factory, Codex, and Claude Code can add queue management, logs, and approvals. Factory is especially close because it already frames agents across the SDLC.

Mitigation: avoid the broad "agent workforce" claim. Own backend/platform change-control presets, risky-operation gates, and integrations with CI/observability/incidents.

### 4. CI/CD and platform tools own production gates

GitHub Actions, GitLab, CircleCI, Harness, Argo CD, Port, Backstage, Cortex, and Humanitec already control parts of the platform workflow.

Mitigation: Orchia should orchestrate the human/AI work before and around those gates, then link to their artifacts. It should not replace deploy systems or internal developer portals.

### 5. Trust and security are non-negotiable

Backend infra teams will require secrets isolation, command restrictions, repo permissions, audit logs, SSO, policy controls, and clear failure recovery. A local JSON board is great for transparency, but enterprise buyers will eventually ask for hardened runners, RBAC, and compliance evidence.

Mitigation: start with local/team pilots and BYO credentials; add policy and runner isolation as paid tiers.

## Is This a Strong Orchia Wedge?

Yes, but only with a narrow position.

Strong version:

- "AI change-control board for backend/platform teams."
- "Safely delegate infra maintenance to AI agents."
- "Locks, tests, logs, approvals, pause/hard-stop."
- "Start with security patch, CI repair, test coverage, observability, incident follow-up."

Weak version:

- "Visual AI task board for developers."
- "Multi-agent coding workflow."
- "Alternative to GitHub Projects/Linear/Jira."
- "Generic agent control plane."

Recommendation:

1. Keep Orchia's visual board and role separation as the product's trust core.
2. Build GitHub-first import/export and PR/CI evidence capture.
3. Use backend maintenance presets before production-change presets.
4. Pilot with small, high-context infra teams where senior review is scarce.
5. If Artly is available as a pilot, frame around fleet/backend reliability: security patches, CI/test repair, observability gaps, incident follow-ups, and safe rollout checklists.

## Top 5 Conclusions

1. Backend infrastructure is a credible Orchia wedge because AI increases implementation throughput while infra teams still need locks, evidence, review, and stop controls.
2. Orchia should not compete with GitHub Issues, Linear, Jira, CI, or platform portals as a system of record; it should integrate with them and own the controlled AI execution layer.
3. The safest MVP starts with maintenance work: security patches, CI failures, tests, observability, and incident follow-ups. Production deploys, Terraform applies, and database migrations come later.
4. Artly-style robotics/cloud teams are a good fit because backend, fleet operations, telemetry, analytics, and releases intersect with real-world reliability risk.
5. The wedge is strong if positioned as "AI change-control for backend/platform teams"; it is weak if positioned as a generic multi-agent workflow board.

## Source URLs

- Artly/ClickHouse case study: https://clickhouse.com/blog/artly-clickhouse-barista
- GitHub Projects: https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects
- GitHub Copilot coding agent: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/assign-copilot-to-an-issue
- GitHub Copilot agent admin controls: https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-enterprise/manage-agents/disable-automatic-commands
- GitHub Copilot pricing: https://github.com/features/copilot/plans
- GitHub Actions environments: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- GitHub Dependabot: https://docs.github.com/en/code-security/dependabot
- Linear Agents: https://linear.app/agents
- Linear MCP: https://linear.app/docs/mcp
- Linear pricing: https://linear.app/pricing
- Jira: https://www.atlassian.com/software/jira
- Jira pricing: https://www.atlassian.com/software/jira/pricing
- Atlassian Rovo Agents: https://www.atlassian.com/software/rovo/agents
- Cursor docs: https://docs.cursor.com/
- Cursor pricing: https://cursor.com/pricing
- Devin: https://devin.ai/
- Devin pricing: https://devin.ai/pricing
- Factory: https://www.factory.ai/
- Factory pricing: https://www.factory.ai/pricing
- OpenAI Codex docs: https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
- Claude Code docs: https://docs.anthropic.com/en/docs/claude-code/overview
- CodeRabbit pricing: https://www.coderabbit.ai/pricing
- GitLab deployment approvals: https://docs.gitlab.com/ci/environments/deployment_approvals/
- CircleCI workflows: https://circleci.com/docs/workflows/
- Argo CD: https://argo-cd.readthedocs.io/
- Harness CD: https://www.harness.io/products/continuous-delivery
- OpenTelemetry: https://opentelemetry.io/docs/
- PagerDuty AIOps: https://www.pagerduty.com/use-cases/aiops/
- DORA metrics: https://dora.dev/guides/dora-metrics-four-keys/
- Backstage: https://backstage.io/docs/overview/what-is-backstage/
- Port: https://www.getport.io/
- Cortex: https://www.cortex.io/
- Humanitec: https://humanitec.com/
