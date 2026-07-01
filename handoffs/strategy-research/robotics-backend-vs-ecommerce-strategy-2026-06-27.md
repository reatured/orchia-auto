# Robotics / Backend vs Ecommerce Strategy

Date: 2026-06-27  
Research track: D - Strategic comparison of robotics/backend engineering workflow wedge versus ecommerce/creator workflow wedge  
Question: Should Orchia shift from the previously recommended ecommerce seller workflow wedge toward backend infrastructure development, robotic behavior infrastructure development/testing, and robotic behavior workflows, potentially using Artly AI as a design-partner context?

## Executive Recommendation

Orchia should **test the robotics/backend wedge immediately**, but only in a narrow form:

> Orchia is the safe AI engineering control plane for physical-AI teams: it turns robot behavior and backend changes into planned, implemented, simulated, hardware-tested, reviewed, and auditable releases.

This is a stronger investor story than the ecommerce seller wedge **if and only if** Richard can get fast access to a real robotics design partner such as Artly AI, including real issues, logs, code-adjacent workflows, deployment checklists, or behavior-test pain. Without that access, robotics becomes slower and more speculative than the ecommerce path.

The best strategic move is a **2-4 week head-to-head validation sprint**:

- Robotics path: use Artly or 2-3 robotics teams to test a "robot behavior engineering control plane" workflow.
- Ecommerce path: keep the prior "improve one listing and find 20 likely buyers" seller workflow as the faster public validation fallback.
- Generic AI coding path: use as internal dogfood and demo substrate, but do not lead with it as the company wedge unless external AI-heavy engineering teams pull strongly.

Ranked recommendation:

| Rank | Direction | Recommendation |
| --- | --- | --- |
| 1 | Robotics/backend control plane for robot behavior engineering | **Lead if Artly/design-partner access is real in the next 1-2 weeks.** Highest ACV, strongest Orchia fit, strongest investor narrative. |
| 2 | Hybrid ecommerce seller workflow powered by Orchia | **Keep as fallback and parallel test.** Faster public validation and clearer nontechnical buyer, but lower ACV and higher platform commoditization risk. |
| 3 | Generic AI coding/backend workflow control plane | **Do not lead standalone.** Excellent dogfood and technical proof, but too crowded and likely to be absorbed by GitHub/OpenAI/Anthropic/Cursor-style tools. |

The robotics wedge should **not** start as "autonomous robot behavior" or "let agents control robots." Start with engineering workflow control: issue intake, task decomposition, code/backend implementation, simulation/replay, hardware-in-loop testing, safety review, staged rollout, and incident-to-fix loops. Live robot action should remain human-approved until trust and liability boundaries are clear.

## Top Conclusions

1. **Robotics/backend is more fundable than ecommerce if there is immediate design-partner access.** Physical-AI teams have higher willingness to pay, more painful failure modes, and a clearer need for audit/review/control than solo sellers.
2. **The sharp wedge is robot behavior infrastructure/testing, not generic backend development.** Generic backend workflows collapse into the crowded AI coding-agent category; robot-specific workflows add simulation, hardware scarcity, logs, safety review, and staged fleet release.
3. **Artly is a highly relevant public design-partner archetype.** Public materials describe robot baristas, AI/robotics R&D, deployment in retail/corporate settings, and robots priced around $2,500-$4,000/month or more, implying meaningful operational stakes.
4. **Ecommerce remains faster to validate publicly but weaker on ACV and defensibility.** The prior seller wedge has clear pain and a low-friction concierge MVP, but Shopify/Etsy/eBay/Klaviyo/Canva/Zapier can absorb isolated listing/content/outreach features.
5. **Generic AI coding is the wrong public wedge unless pulled by users.** It has huge market size and close current-product fit, but the platform risk is severe: GitHub Copilot coding agent, OpenAI Codex, Claude Code, Cursor, Devin, Factory, DevPlan, and agent-workflow startups are converging on the same coordination pain.

## What Changes From The Prior Recommendation

The prior synthesis recommended:

> Orchia helps skilled product sellers improve one listing, find 20 likely buyers, and run approved follow-up without becoming full-time marketers.

That remains a good customer-facing wedge because it is easy to explain and validate. The robotics/backend wedge is strategically different:

> Orchia helps robotics teams safely ship behavior and backend changes by coordinating AI-agent work through simulation, hardware tests, logs, review gates, and staged release.

The robotics version better matches Orchia's existing control-plane strengths: tasks, ownership, review, logs, pause/resume, handoffs, role separation, and workflow state. The ecommerce version better matches fast public customer discovery and "do things that don't scale."

The decision should be based on **access**, not abstract market size. Robotics wins if the next month produces a real pilot or strong LOIs. Ecommerce wins if robotics conversations stay theoretical.

## Public Artly AI Context

Publicly available Artly materials make it a plausible design-partner context for this wedge:

- Artly says it operates AI-powered robotic coffee bars and has served more than one million cups. Its blog describes a team of 20+ people, retail and corporate campus deployments, collaborations with Boston University and the University of Maryland, and partners including Microsoft, MUJI, and Salesforce. Source: [Artly blog, "From AI to Espresso"](https://artly.coffee/blogs/artly-blog/from-ai-to-espresso-the-story-behind-artly-s-one-million-cups).
- Artly's Barista Bot site describes AI work including anomaly detection, structure from motion, obstacle avoidance, path planning, physical reasoning, and control improvement. Source: [Artly Barista Bot](https://www.artlybaristabot.com/).
- The same site lists pricing signals: Standard Lease at $2,500/month with a 36-month term, Premium Lease at $4,000/month with a 36-month term, and purchase starting at $175,000. Source: [Artly Barista Bot pricing](https://www.artlybaristabot.com/).
- Locations pages show Artly deployed in multiple public settings, including Seattle-area and Portland-area locations. Source: [Artly locations](https://www.artlybaristabot.com/locations).
- BusinessWire reported in 2022 that Artly raised $8M in Pre-A financing. Source: [BusinessWire Artly funding announcement](https://www.businesswire.com/news/home/20220802005171/en/Artly-the-Robot-Barista-Startup-Secures-%248M-to-Expand-Its-Retail-Network).
- GeekWire reported Artly's robot barista deployments and funding history, including Artly's pandemic-era shift toward robotics and public cafe expansion. Source: [GeekWire Artly coverage](https://www.geekwire.com/2022/robot-barista-startup-artly-raising-more-cash-as-it-plans-to-open-its-own-seattle-coffeeshops/).

Strategic interpretation: Artly is not just a generic food-service company. Public context suggests real robot behavior, fleet operations, backend configuration, customer-facing reliability, and R&D iteration. That makes it a strong place to test whether Orchia's control-plane primitives matter in physical-world AI.

Important caveat: the public sources do not prove Artly has the exact workflow pain Orchia should target. The validation sprint must discover that directly.

## Market And Timing

### Robotics / Physical AI

Robotics is receiving strong strategic attention because embodied AI, humanoids, service robots, warehouse automation, manufacturing, and logistics all depend on reliable physical-world deployment. The International Federation of Robotics reported global service robot growth and tracked professional service robot categories such as transportation/logistics, hospitality, professional cleaning, medical robotics, and inspection/maintenance. Source: [IFR service robots growth release](https://ifr.org/ifr-press-releases/news/service-robots-see-global-growth-boom).

Investors also have a clear "physical AI" narrative. Crunchbase has reported strong robotics startup funding and investor interest around AI-enabled robotics. Source: [Crunchbase robotics funding coverage](https://news.crunchbase.com/robotics/startup-venture-funding-surges-2026-data/). F-Prime's State of Robotics work also frames robotics as a large and active venture category. Source: [F-Prime 2026 State of Robotics report](https://fprimecapital.com/wp-content/uploads/2026/03/State-of-Robotics-2026.pptx.pdf).

The robotics workflow pain is structurally different from normal software:

- A behavior change can pass unit tests and still fail in the real world.
- Hardware time is scarce and expensive.
- Reproducing a field issue may require logs, video, sensor traces, configs, and environment context.
- Simulation, log replay, hardware-in-loop testing, and staged rollout matter.
- A bad release can damage hardware, interrupt revenue, embarrass a customer-facing deployment, or create safety risk.

That is exactly where Orchia's review gates, audit logs, task ownership, and pause/resume controls are more than a productivity feature.

### Backend Infrastructure Development

Backend infrastructure is a large, urgent market, but as a wedge it is too broad. Every engineering team has backend work: APIs, deployment, observability, auth, data pipelines, integrations, cloud costs, incident response, and internal tools. The issue is that generic backend work is already inside the AI coding-agent battlefield.

GitHub Copilot coding agent can be assigned software tasks from GitHub issues and work toward pull requests. Source: [GitHub Copilot coding agent docs](https://docs.github.com/en/copilot/concepts/coding-agent/coding-agent). OpenAI Codex is positioned as a software engineering agent that can work on tasks in cloud environments and produce code changes. Source: [OpenAI Codex](https://openai.com/index/introducing-codex/). Claude Code is a terminal coding agent for software engineering workflows. Source: [Claude Code overview](https://docs.anthropic.com/en/docs/claude-code/overview). DevPlan's public positioning and funding coverage directly target the coordination work created by AI coding. Source: [DevPlan](https://www.devplan.com/) and [GeekWire on DevPlan funding](https://www.geekwire.com/2026/devplan-raises-2-5m-to-take-on-the-product-coordination-work-that-ai-coding-is-leaving-behind/).

Therefore, Orchia should not pitch "backend infrastructure development workflows" by itself. It should pitch backend only where backend changes affect robots:

- Robot fleet APIs.
- Device identity and provisioning.
- Menu/config/payment/order systems for robot deployments.
- Telemetry and observability.
- Remote operations workflows.
- Deployment and rollback across physical sites.
- Incident-to-fix workflows involving logs and field state.

The wedge is **robotics backend plus behavior release safety**, not generic backend.

### Ecommerce / Seller Workflows

The ecommerce wedge has a much larger self-serve population. Etsy reports millions of active sellers and tens of billions of dollars of marketplace activity. Source: [Etsy investor company information](https://investors.etsy.com/company-information). Shopify has millions of merchants and sells plans from solo-entrepreneur tiers through enterprise Plus. Source: [Shopify pricing](https://www.shopify.com/pricing).

The pain is real: many sellers can make products but struggle with listings, trust, traffic, conversion, outreach, and follow-up. The prior Orchia reports correctly identify a narrow first promise: "fix one listing and find 20 likely buyers."

The weakness is that ecommerce workflows are heavily platform-exposed. Shopify Sidekick/Magic, eBay AI listing tools, Etsy platform features, Klaviyo AI, Canva, Zapier, Make, n8n, and vertical AI marketing startups can absorb isolated capabilities. Orchia must differentiate through a full approved sales loop, not listing generation.

## Competitive Landscape

### Robotics Workflow Competitors

Orchia would enter a real but fragmented robotics software stack:

| Category | Examples | Competitive implication |
| --- | --- | --- |
| Robotics simulation and synthetic data | [NVIDIA Isaac Sim](https://developer.nvidia.com/isaac/sim), Isaac Lab, Gazebo | Strong at simulation/runtime tooling; not necessarily a human-readable multi-agent engineering workflow board. |
| Robot software frameworks | [ROS 2](https://docs.ros.org/), [Gazebo](https://gazebosim.org/) | Deep community and standards; Orchia should integrate with these rather than replace them. |
| Robot data/logging/dev tools | [Foxglove](https://foxglove.dev/) | Strong visualization and robotics data workflows; Orchia can sit above as task/review/release control. |
| Fleet operations | [Formant](https://formant.io/), [InOrbit](https://www.inorbit.ai/), [Viam](https://www.viam.com/) | Strong for deployed robot fleets, teleop, monitoring, and device/platform operations. Orchia must focus on engineering workflow and agent coordination. |
| Robotic foundation/model platforms | [Intrinsic Flowstate](https://www.intrinsic.ai/flowstate), [NVIDIA robotics stack](https://developer.nvidia.com/robotics) | Large strategic players can absorb parts of simulation and robot programming. Orchia needs a model/vendor-agnostic control-plane angle. |

The opportunity is not to replace these tools. It is to coordinate the work around them:

> GitHub issue or field incident -> Orchia plan -> coding-agent tasks -> simulation/replay test -> hardware test slot -> human review -> release checklist -> staged rollout -> post-release audit.

### Ecommerce Competitors

Ecommerce competition is broader and more direct:

- Shopify Sidekick/Magic and Shopify Flow: native platform AI and automations.
- Etsy/eBay/Amazon seller tools: native listing, ads, and marketplace workflows.
- Klaviyo, Mailchimp, HubSpot, Omnisend: retention and lifecycle marketing.
- Canva, CapCut, Adobe: creative asset production.
- Zapier, Make, n8n, Gumloop: generic automation.
- YC/startup products such as Amboras, Reacher, Lapis, Wildcard, Kinect, Boom AI, Bezel, Cohesive, CharacterQuilt, and Channel3.

The ecommerce wedge has more obvious users but more commoditization risk. Orchia can still win if it stays focused on capacity-aware seller execution, but it is less differentiated technically.

### Generic AI Coding Competitors

This is the most crowded narrative:

- GitHub Copilot coding agent.
- OpenAI Codex.
- Claude Code.
- Cursor agent workflows.
- Devin, Factory, Codegen, and other AI software-engineering agents.
- DevPlan and other AI coordination/product-intelligence tools.
- LangGraph/LangSmith, CrewAI, n8n, Make, Zapier Agents, and agent workflow platforms.

Generic AI coding has huge demand, but the most natural control surfaces are already GitHub, IDEs, issue trackers, CI, and model-vendor tools. Orchia should use generic coding as dogfood, not the first pitch.

## Scorecard

Scores are 1-5. Robotics assumes credible access to Artly or equivalent robotics design partners. Without that access, reduce robotics validation speed and founder-market fit by 1.0-1.5 points.

| Criterion | Robotics/backend workflow | Ecommerce seller workflow | Generic AI coding workflow |
| --- | ---: | ---: | ---: |
| Investor attractiveness | 4.5 | 3.5 | 3.5 |
| Market size / upside | 4.0 | 4.0 | 5.0 |
| Urgency | 4.5 | 3.5 | 4.0 |
| Willingness to pay | 4.5 | 3.0 | 4.0 |
| Founder-market fit | 4.5 with Artly access; 3.0 without | 3.5-4.0 | 4.0 |
| Current Orchia product fit | 4.0 | 2.5 | 5.0 |
| Speed to validation | 3.0 with access; 2.0 without | 4.5 | 4.0 |
| Competitive risk | 3.0 | 2.5 | 1.5 |
| Expansion path | 4.5 | 3.5 | 4.0 |
| Overall | **4.1 conditional** | **3.5** | **3.7 but crowded** |

Interpretation:

- Robotics is the best company wedge if design-partner access exists.
- Ecommerce is the best fast public wedge if robotics access is weak.
- Generic AI coding has the best product fit but worst strategic differentiation.

## Why Robotics Is A Better Use Of Orchia

Orchia's current primitives map unusually well to robotics engineering:

| Orchia primitive | Robotics meaning |
| --- | --- |
| Planner / Worker / Reviewer roles | Behavior spec, implementation, and safety/test review. |
| Task claiming and conflict avoidance | Avoid multiple agents modifying overlapping robot/backend modules or test fixtures. |
| Handoff files | Field incident reports, visual/audit notes, log summaries, and test-result handoffs. |
| Review column | Human approval before robot-affecting changes, outbound commands, or production deployment. |
| Logs and board history | Audit trail for why a behavior/config/backend change was made. |
| Pause / hard stop | Important mental model for AI workflows that can touch hardware, spend, customers, or fleet state. |
| Viewer/status board | Shared engineering/ops surface for "what is blocked, what needs hardware, what needs approval." |

In ecommerce, these same primitives are useful but easier for competitors to mimic. In robotics, the control-plane is closer to the actual pain.

## Best First Robotics Workflows

### 1. Robot Behavior Change Control Plane

User: robotics software engineer, behavior engineer, engineering lead.  
Input: issue, desired behavior, affected robot/site/version, logs or reproduction notes.  
Workflow:

1. Planner decomposes the behavior change.
2. Worker prepares implementation tasks and test plan.
3. Coding agent edits backend/robot code or test scaffolding.
4. Simulation/replay test runs.
5. Hardware-in-loop checklist is created or executed.
6. Reviewer summarizes results and risks.
7. Human approves staged release.
8. Orchia records outcome and follow-up.

This should be the first flagship workflow.

### 2. Field Incident To Fix Loop

User: robot ops engineer, support engineer, fleet engineer.  
Input: incident report, robot ID, site, timestamp, logs, video/sensor trace if available.  
Workflow:

1. Gather relevant logs, configs, code version, and timeline.
2. Classify incident: backend, perception, manipulation, UI/payment/order, hardware, operator, environment.
3. Produce reproduction hypothesis.
4. Create engineering tasks.
5. Run replay/sim or unit regression.
6. Review fix and update runbook.

This is compelling because field incidents are urgent and measurable.

### 3. Robot Backend / Fleet Config Rollout

User: backend engineer or fleet operations lead.  
Input: API/config/menu/payment/order/telemetry change.  
Workflow:

1. Identify affected robot/site workflows.
2. Create test matrix for backend and robot interaction.
3. Run integration tests.
4. Generate staged rollout plan and rollback checklist.
5. Require approval before production deploy.
6. Monitor post-release signals.

This makes backend infrastructure a robotics-specific wedge.

### 4. Test Resource Scheduler

User: robotics team lead.  
Input: tasks needing robot hardware, simulation environments, datasets, or lab time.  
Workflow:

1. Queue hardware-dependent tasks.
2. Allocate robot/testbed slots.
3. Attach test checklists and pass/fail evidence.
4. Block releases until required evidence exists.

This is less glamorous but likely painful inside real robotics teams.

## Pricing And Willingness To Pay

Robotics/backend customers can likely pay more than solo sellers because the workflow is tied to engineering time, robot utilization, field reliability, and customer-facing deployments.

Near-term pricing hypotheses:

| Stage | Price hypothesis | Notes |
| --- | ---: | --- |
| Concierge design partner | $0-$2,000/month | Free is acceptable for a 2-week pilot if access is high quality; ask for paid conversion terms. |
| Paid pilot | $2,500-$10,000/month | Reasonable if Orchia handles real issues/logs/tests and saves engineering time. |
| Team plan | $500-$2,000/month | For small robotics teams coordinating agents, issues, test workflows, and release review. |
| Business plan | $12K-$60K/year | For teams needing integrations, run history, multi-project boards, GitHub/Slack/Foxglove/Formant/Viam hooks, and support. |
| Enterprise / fleet org | $50K-$150K+/year | Requires security, deployment controls, RBAC, retention, audit export, SSO, and procurement readiness. |

Do not price by raw agent steps. Better units:

- Active robot project/workspace.
- Completed behavior release workflow.
- Reviewed field incident.
- Connected robot/site or testbed.
- Retention/log volume.
- Team seats and approval roles.

Ecommerce pricing is lower and faster:

- One-off seller sprint: $99-$299.
- Seller subscription: $79-$149/month.
- Serious seller/operator: $299-$500/month.
- Agency/team: $399-$799/month.

Generic AI coding pricing likely fits $20-$100/user/month, but the market will compare Orchia to tools already bundled into GitHub, IDEs, ChatGPT, Claude, and Cursor.

## Validation Plan: 2-4 Weeks

### Week 1: Confirm The Robotics Pull

Goal: prove this is not just an interesting internal use case.

Actions:

1. Identify one Artly-facing workflow owner or equivalent robotics design partner.
2. Collect the last 5-10 real workflow examples:
   - behavior bug,
   - backend/fleet config change,
   - field incident,
   - release checklist,
   - hardware-test bottleneck,
   - log/debugging handoff.
3. Ask each person:
   - "What change took too long because code, logs, tests, hardware, and review were scattered?"
   - "What do you not trust an AI coding agent to touch?"
   - "Where would a visible review/control board reduce anxiety?"
   - "What failure would make this worth $2K-$10K/month?"
4. Choose one workflow for a concierge run.
5. Define baseline metrics: time from issue to tested fix, number of handoffs, hardware wait time, review wait time, regression escapes, and engineer hours spent.

Pass signal:

- At least one robotics team gives access to real artifacts and agrees to run 3+ real work items through Orchia.
- Someone names a recent painful failure without being prompted.
- A buyer or lead says the workflow would justify a paid pilot if it saves time or catches regressions.

### Week 2: Run A Concierge Workflow With Current Orchia

Goal: create proof before building deep robotics integrations.

Actions:

1. Use the existing Orchia board to model one workflow:
   - "Field incident to fix,"
   - "behavior change to test/review,"
   - or "backend config rollout."
2. Manually attach links to GitHub issues/PRs, logs, test output, video, Foxglove/Grafana snapshots, or runbooks.
3. Use AI agents for bounded tasks only:
   - summarize logs,
   - draft reproduction steps,
   - propose test matrix,
   - write test scaffolding,
   - draft release checklist,
   - summarize PR risk.
4. Keep human approval before any production or robot-affecting change.
5. Record before/after evidence and a 90-second demo video.

Pass signal:

- A robotics engineer asks to use it again on the next issue.
- Orchia reduces coordination/review time by at least 30% or catches a concrete missing test/risk.
- The board becomes the shared source of truth for at least one real change.

### Week 3: Add Thin Integrations

Goal: make the workflow feel productized without overbuilding.

Build only what the pilot needs:

- GitHub issue/PR import.
- Test-result attachment and reviewer checklist.
- "Needs simulation," "needs hardware," and "needs release approval" task tags.
- Robot/site/version fields.
- Incident template.
- Release checklist template.
- Exportable audit summary.

Avoid deep robot control, credential handling, or live deployment automation at this stage.

Pass signal:

- Pilot users can create a new robotics workflow without founder handholding.
- At least 5 real tasks move through todo -> claimed -> review -> done.
- The team identifies the next integration they would pay for.

### Week 4: Compare Against Ecommerce

Goal: make the strategic choice with evidence.

Run parallel ecommerce validation if possible:

- 5 seller interviews.
- 3 listing/buyer-discovery concierge runs.
- Ask for $99-$299 one-off payment or $79-$149/month commitment.

Choose robotics if:

- Artly or another robotics team completes 3+ real workflows.
- A lead agrees to a paid pilot or signed LOI at $2K+/month.
- Orchia demonstrably improves release/test coordination or catches a risk.
- Users treat Orchia as a workflow surface, not a novelty.

Choose ecommerce if:

- Robotics access is blocked or political.
- Robotics users like it but cannot expose code/logs/workflows.
- No one will pay or sign a pilot.
- Seller concierge runs produce payments faster and clearer pull.

## YC / AI House Messaging If Robotics Is Chosen

### One-Liner

> Orchia is the AI engineering control plane for robotics teams: it coordinates coding agents, simulation, hardware tests, review gates, and staged releases so physical-AI teams can ship robot behavior safely.

### Short YC-Style Pitch

> AI coding agents are starting to write software, but robotics teams cannot treat robot code like ordinary SaaS code. A behavior change can pass unit tests and still fail in the real world. Orchia gives robotics teams a visible control plane for AI-agent engineering work: issues become tasks, agents implement bounded changes, simulation and hardware-test evidence is attached, humans approve risky steps, and every behavior/backend release has an audit trail. We are starting with robot behavior and fleet-backend workflows because the pain is urgent, high-stakes, and expensive.

If Artly is a real pilot, say it concretely:

> We are piloting this on real robot barista workflows with Artly-style physical-AI deployments, where backend changes, behavior logic, logs, hardware tests, and customer-facing reliability all meet.

Only use Artly's name in applications if there is permission or a public/accurate relationship. Otherwise say "robot coffee deployments" or "robotics design partner."

### Why Now

> Robotics is moving from demos to deployed fleets, while AI coding agents are becoming capable enough to touch larger engineering tasks. The missing layer is trust: teams need to know what the agents changed, which robot/site/version is affected, what tests passed, what still needs hardware, and who approved release.

### What Users Buy

> Users buy a workflow product, not a generic agent OS: field incident to tested fix, behavior change to hardware-approved release, and backend/fleet rollout with rollback evidence.

### What Is Technically Hard

> The hard part is not just generating code. It is preserving operational state across agents, logs, simulation, hardware availability, review gates, and staged release, then making that legible enough for a human to trust.

### AI House / AI2 Angle

AI House / AI2 is a particularly good fit for the robotics version because the wedge is applied AI with a real-world deployment loop, not a generic productivity assistant. Message it as:

> We are building the control layer that lets AI agents safely participate in physical-AI engineering workflows. We need design partners, evaluation architecture, and pilot discipline around robotics teams where failures are observable and expensive.

Relevant AI House application themes:

- Applied AI.
- Customer discovery and design partners.
- AI architecture and evals.
- Pilot design.
- Seattle/robotics ecosystem relevance.

Source: [AI2 Incubator application](https://apply.ai2incubator.com/).

## Risks And Mitigations

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Robotics access is not real | Without real workflows, robotics is slower than ecommerce. | Require concrete artifacts and 3 real tasks in week 1-2. |
| Too much internal customization | Artly-specific workflows may not generalize. | Interview 2-3 additional robotics teams before overbuilding. |
| Liability / safety | Live robot control can be dangerous. | Stay in planning/testing/review first; human approval for actuation/deployment. |
| Existing robotics tools absorb it | Foxglove/Formant/Viam/Intrinsic/NVIDIA can add workflow features. | Integrate across tools and own AI-agent work state, not robot runtime. |
| Generic coding tools absorb it | GitHub/OpenAI/Anthropic can add task/review queues. | Emphasize robot-specific simulation, hardware, fleet, and release evidence. |
| Sales cycle is longer | Robotics teams have more technical evaluation. | Start with founder-led pilot and paid design partners; keep ecommerce fallback alive. |
| Artly name creates dependency | Investor story may look like one-customer consulting. | Position Artly as first design partner in a broader physical-AI/team category. |

## Final Decision Rule

Use this rule after 2-4 weeks:

> Choose robotics if a real robotics team runs real behavior/backend workflows through Orchia and agrees to pay for continued use. Otherwise keep ecommerce as the primary wedge and use robotics/backend as an internal credibility story.

The highest-upside version of Orchia is not "AI seller assistant" and not "generic AI coding board." It is:

> A safe, visible control plane for delegated AI work in domains where mistakes are expensive.

Robotics is the best first proof of that thesis if access exists. Ecommerce is the best proof if access does not.

## Source Appendix

Artly and robotics:

- Artly blog, "From AI to Espresso": https://artly.coffee/blogs/artly-blog/from-ai-to-espresso-the-story-behind-artly-s-one-million-cups
- Artly Barista Bot: https://www.artlybaristabot.com/
- Artly locations: https://www.artlybaristabot.com/locations
- BusinessWire Artly Pre-A funding: https://www.businesswire.com/news/home/20220802005171/en/Artly-the-Robot-Barista-Startup-Secures-%248M-to-Expand-Its-Retail-Network
- GeekWire Artly coverage: https://www.geekwire.com/2022/robot-barista-startup-artly-raising-more-cash-as-it-plans-to-open-its-own-seattle-coffeeshops/
- International Federation of Robotics service robots release: https://ifr.org/ifr-press-releases/news/service-robots-see-global-growth-boom
- Crunchbase robotics funding coverage: https://news.crunchbase.com/robotics/startup-venture-funding-surges-2026-data/
- F-Prime 2026 State of Robotics report: https://fprimecapital.com/wp-content/uploads/2026/03/State-of-Robotics-2026.pptx.pdf
- NVIDIA Isaac Sim: https://developer.nvidia.com/isaac/sim
- NVIDIA robotics: https://developer.nvidia.com/robotics
- ROS 2 documentation: https://docs.ros.org/
- Gazebo: https://gazebosim.org/
- Foxglove: https://foxglove.dev/
- Formant: https://formant.io/
- InOrbit: https://www.inorbit.ai/
- Viam: https://www.viam.com/
- Intrinsic Flowstate: https://www.intrinsic.ai/flowstate

Generic AI coding / backend:

- GitHub Copilot coding agent docs: https://docs.github.com/en/copilot/concepts/coding-agent/coding-agent
- OpenAI Codex: https://openai.com/index/introducing-codex/
- Claude Code overview: https://docs.anthropic.com/en/docs/claude-code/overview
- DevPlan: https://www.devplan.com/
- GeekWire on DevPlan funding: https://www.geekwire.com/2026/devplan-raises-2-5m-to-take-on-the-product-coordination-work-that-ai-coding-is-leaving-behind/

Ecommerce / seller context:

- Etsy investor company information: https://investors.etsy.com/company-information
- Shopify pricing: https://www.shopify.com/pricing
- Shopify Sidekick: https://www.shopify.com/sidekick
- Shopify Magic: https://www.shopify.com/magic
- Shopify Flow: https://help.shopify.com/en/manual/shopify-flow
- eBay Magical Listing: https://innovation.ebayinc.com/tech/features/magical-listing/
- Klaviyo AI: https://www.klaviyo.com/features/ai
- Zapier AI: https://zapier.com/ai
- Make AI agents: https://www.make.com/en/ai-agents
- n8n AI workflow automation: https://n8n.io/

Accelerators:

- Y Combinator apply: https://www.ycombinator.com/apply
- AI2 Incubator application: https://apply.ai2incubator.com/
