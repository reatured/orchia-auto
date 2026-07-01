# Research Track B: Robotics Behavior Infrastructure And Testing Workflows For Orchia

Date: 2026-06-27  
Context: User works at Artly AI and is considering Orchia for software engineers developing robotic behavior infrastructure and testing.  
Deliverable: Strategy research handoff for Orchia.  
Path: `/Users/richard26/2026/6 - orchia-auto/handoffs/strategy-research/robotics-behavior-infra-testing-2026-06-27.md`

## Executive Summary

Orchia can plausibly support robotics behavior infrastructure, but the right product is not another simulator, ROS IDE, fleet monitor, or log viewer. The strongest robotics framing is:

> Orchia is a visual behavior-release control plane for robot software teams: it coordinates AI-assisted development, simulation, hardware-in-the-loop testing, safety review, field validation, and regression evidence before a behavior reaches the fleet.

This is an attractive but demanding vertical. Robotics teams already have powerful point tools: ROS 2 for middleware, BehaviorTree.CPP/Groot/Nav2 for behavior logic, Gazebo and Isaac Sim for simulation, Foxglove for robot data and visualization, Formant/InOrbit for fleet operations, Open-RMF for multi-vendor fleet coordination, and CI helpers such as action-ros-ci and industrial_ci. The gap is cross-tool workflow governance: who owns a behavior change, what evidence proves it is safe enough, which simulations and bags reproduce the issue, who approved hardware testing, which field robots are in canary, and how failures flow back into regression suites.

For Artly-like service robotics, Orchia's current Planner/Worker/Reviewer/handoff model maps well to real behavior work:

- Planner: decomposes a behavior change or field incident into code, test, simulation, telemetry, and review tasks.
- Worker: implements code, writes scenario tests, runs simulation, extracts logs, compares metrics, or prepares HIL evidence.
- Reviewer: evaluates safety gates and evidence before merge, bench test, canary, or fleet rollout.
- Auditor/handoff roles: inspect Foxglove/MCAP/rosbag data, CI logs, simulation videos, HIL runs, field incidents, and write structured handoffs.
- Board/control plane: provides visible work state, task locks, review gates, pause/resume, logs, and repeatable templates.

Recommendation: do not lead Orchia's public company positioning with robotics unless Artly or 3-5 other robot teams validate willingness to pay. Do run a focused Artly-style pilot because the workflow pain is real, the evidence requirements are concrete, and the vertical makes Orchia's safety/review primitives feel necessary rather than decorative. The narrow wedge should be "behavior release manager for ROS-powered service robots," not broad "robotics DevOps platform."

## Top Conclusions

1. Robotics is a high-value control-plane use case because behavior changes require evidence across code, ROS launch/config, behavior trees/state machines, simulation, HIL, logs, telemetry, and field validation.
2. Orchia should integrate with ROS/Foxglove/Isaac/Gazebo/Formant rather than compete with them. The product opportunity is the workflow/evidence layer across those tools.
3. Artly-like robots are a strong design-partner fit: drink recipes, robot-arm motion, machine vision, cleaning/recovery behaviors, kiosk order flow, and multi-location rollouts create repeatable behavior-release templates.
4. Safety and review gates must be first-class. Orchia should never imply it certifies safety; it should enforce evidence collection, approvals, rollback plans, and audit trails.
5. Robotics is a credible premium vertical but a slower, more technical go-to-market than ecommerce or generic AI workflow. Treat it as a validation track unless a design partner commits budget and integration access.

## Source Notes

This report uses local Orchia context from the current repository plus current public sources:

- Orchia local baseline: `README.md`, `workflow/workflow-overview.md`, `workflow/api-guide.md`, and prior strategy handoffs under `handoffs/strategy-research/`.
- ROS 2 testing and quality: [ROS 2 launch_testing integration tests](https://docs.ros.org/en/rolling/Tutorials/Intermediate/Testing/Integration.html), [ROS 2 Quality Guide](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Quality-Guide.html), [rosbag2](https://github.com/ros2/rosbag2), [ros2_tracing](https://github.com/ros2/ros2_tracing).
- ROS CI: [ros-tooling/action-ros-ci](https://github.com/ros-tooling/action-ros-ci), [ros-industrial/industrial_ci](https://github.com/ros-industrial/industrial_ci).
- Behavior logic: [BehaviorTree.CPP docs](https://www.behaviortree.dev/docs/intro), [Groot2](https://www.behaviortree.dev/groot/), [Nav2 behavior tree walkthrough](https://docs.nav2.org/behavior_trees/overview/detailed_behavior_tree_walkthrough.html).
- Simulation and fleet tools: [Gazebo docs](https://gazebosim.org/docs/latest/getstarted/), [NVIDIA Isaac Sim](https://developer.nvidia.com/isaac/sim), [Foxglove](https://foxglove.dev/), [Foxglove MCAP](https://foxglove.dev/product/mcap), [Formant](https://formant.io/), [InOrbit](https://www.inorbit.ai/), [Open-RMF](https://www.open-rmf.org/).
- Market and Artly context: [IFR industrial robot operating stock press release](https://ifr.org/ifr-press-releases/news/record-of-4-million-robots-working-in-factories-worldwide), [IFR US robot industry press release](https://ifr.org/ifr-press-releases/news/service-robots-global-sales-value-up-30), [Artly Coffee](https://artly.coffee/).

## Orchia Baseline And Robotics Translation

The local Orchia starter is not robotics-specific. It is a visual, JSON-backed control plane for delegated AI work:

- Board states: `todo -> claimed -> review -> reviewing -> done -> archived`.
- Hard role separation: Planner, Worker, Reviewer, plus upstream handoff roles.
- Atomic claiming and conflict avoidance through a local task-board server.
- Human review gates: Workers cannot mark their own work done.
- Owner-visible viewer with active agents, spawned-process logs, pause/resume, and dispatch controls.
- Handoff files for upstream audits that can become planned work.

This maps surprisingly well to robotics because robot behavior work is rarely a single code change. It is a chain:

1. Requirement, bug, or field incident.
2. Hypothesis and reproduction assets.
3. Code/config/behavior tree/state machine change.
4. Unit and launch/integration tests.
5. Simulation regression.
6. Hardware-in-the-loop or lab robot run.
7. Safety review.
8. Canary deployment.
9. Fleet rollout and monitoring.
10. Postmortem/regression capture if the field outcome is bad.

Orchia's product truth becomes more valuable if it can hold a behavior change open until every required evidence artifact is attached and reviewed.

## Market Need

### Robotics software is growing, but workflow maturity is uneven

The International Federation of Robotics reported more than 4 million industrial robots operating in factories worldwide in its 2024 release, with annual installations above half a million for the third consecutive year. Its 2026 US release says US industrial robot installations reached 38,000 units in 2025, with growth driven partly by food and non-manufacturing sectors. Sources: [IFR factory robots](https://ifr.org/ifr-press-releases/news/record-of-4-million-robots-working-in-factories-worldwide), [IFR US robot industry](https://ifr.org/ifr-press-releases/news/service-robots-global-sales-value-up-30).

As robots move from labs to factories, hospitals, restaurants, warehouses, campuses, and consumer-adjacent sites, software changes become operational risk. A minor change to a behavior tree, ROS parameter, perception threshold, recovery branch, lifecycle node, or timing assumption can break a real robot in ways normal web CI does not catch.

### Behavior bugs are cross-layer

Robotics behavior failures often span layers:

- Behavior tree or state machine logic.
- ROS topics, services, actions, QoS, TF frames, and lifecycle states.
- Motion planning and control constraints.
- Perception model confidence thresholds.
- Hardware limits, calibration, end-effector wear, fixtures, fluids, consumables, lighting, and humans nearby.
- Fleet deployment versions and site-specific configuration.

This makes bug reproduction difficult. A GitHub issue or Linear ticket usually cannot hold the entire context: rosbag/MCAP links, Foxglove layouts, simulation worlds, CI logs, HIL videos, robot serial numbers, calibration snapshots, safety checklist signoff, and rollout rings.

### Existing tools solve important slices, not the release workflow

The ecosystem is rich:

- ROS 2 gives the middleware, package, launch, testing, bagging, tracing, and build patterns.
- BehaviorTree.CPP/Groot/Nav2 give behavior authoring, runtime monitoring, logs, and navigation behavior-tree patterns.
- Gazebo and Isaac Sim give simulation.
- Foxglove gives robot data collection, visualization, MCAP, and fleet/data tooling.
- Formant and InOrbit give robot operations/fleet visibility.
- Open-RMF coordinates heterogeneous robot fleets and facility resources.
- GitHub Actions, GitLab CI, action-ros-ci, industrial_ci, Jenkins, and container runners give build/test automation.

The missing product is not another one of those. The gap is a cross-tool control plane that asks: "Is this behavior change allowed to move to the next stage, and what evidence proves it?"

## Artly-Like Use Cases

Artly positions itself as "The Barista Bot" where artisan coffee meets AI and robotics. Source: [Artly Coffee](https://artly.coffee/). An Artly-like service robot has a particularly good fit for Orchia because it blends manipulation, perception, food-service operations, kiosk/order systems, routine cleaning, quality consistency, customer-facing uptime, and multi-location fleet rollout.

### 1. New drink or recipe behavior release

Example: add a seasonal drink, adjust milk foam sequence, modify cup handoff behavior, or update ingredient timing.

Orchia value:

- Generate a behavior-release task from the drink requirement.
- Split work into recipe config, robot sequence, perception checks, simulation fixture, HIL bench run, and store canary.
- Require evidence: behavior tree diff, config diff, simulation run, lab video, machine telemetry, taste/quality checklist, and rollback plan.
- Prevent fleet rollout until a human reviewer approves.

### 2. Latte art or precision manipulation regression

Example: after a motion-control update, latte art quality drops at one site.

Orchia value:

- Ingest field logs, camera frames, telemetry, and operator notes as a handoff.
- Create tasks for reproduction, calibration comparison, parameter audit, HIL run, and metric definition.
- Attach before/after media and quantitative thresholds.
- Convert the incident into a regression scenario.

### 3. Spill, collision, or unsafe recovery behavior

Example: robot arm recovery motion after a failed cup pickup risks a spill or moves too close to a customer-facing area.

Orchia value:

- Classify as safety-sensitive.
- Freeze broad rollout with pause/hold semantics.
- Require dual review, HIL evidence, fail-safe proof, E-stop verification, and rollback.
- Track exactly which robots/site versions are allowed to receive the change.

### 4. Field incident reproduction from robot logs

Example: a store reports "robot gets stuck after order cancellation when cup is already placed."

Orchia value:

- Field-auditor role extracts time window, robot serial, software version, ROS topics, MCAP/rosbag links, and screenshots.
- Planner creates reproduction and fix tasks.
- Worker replays bag/sim and writes a deterministic test.
- Reviewer requires replay evidence before closing.

### 5. Fleet canary and site-specific validation

Example: rollout a behavior change to one lab robot, one internal cafe, one low-traffic store, then a broader fleet.

Orchia value:

- Represent deployment rings visually.
- Require per-ring pass/fail metrics and rollback readiness.
- Collect field telemetry and operator notes.
- Auto-open follow-up tasks for any incident class triggered during canary.

## Workflow Templates

### Template 1: Behavior Change PR

Best for: behavior tree, state machine, launch/config, or ROS package changes.

Steps:

1. Planner creates a behavior-change card from a GitHub issue, incident, PRD, or product request.
2. Worker claims implementation and updates code/config/BT XML.
3. Test Worker adds or updates unit, launch, and integration tests.
4. Simulation Worker runs the scenario suite in Gazebo, Isaac Sim, or a team-specific sim runner.
5. Evidence Auditor summarizes CI results, sim videos, metrics, and logs.
6. Reviewer checks evidence gates and either approves or requests follow-up tasks.
7. Deployment Owner starts canary card only after review approval.

Required evidence:

- Git commit and PR link.
- Affected packages, launch files, behavior trees, parameter files, and robot models.
- BT/state-machine diff with explanation.
- `colcon test` or equivalent CI result.
- Simulation scenario matrix with pass/fail and metric thresholds.
- HIL or lab run if behavior touches motion, safety, hardware interaction, perception, recovery, or customer-facing flow.
- Rollback plan.

Safety gate:

- No fleet rollout until Reviewer approval and canary card creation.

### Template 2: Field Bug Reproduction

Best for: failures discovered in production robots.

Steps:

1. Field Auditor creates a handoff from Formant/InOrbit/Foxglove/robot logs/operator notes.
2. Planner turns the handoff into reproduction, triage, fix, and regression-test cards.
3. Worker retrieves rosbag/MCAP, robot version, config snapshot, and site metadata.
4. Worker replays logs locally or in sim.
5. Worker creates a minimal reproduction scenario and marks gaps.
6. Reviewer verifies that reproduction evidence exists before approving a fix path.

Required evidence:

- Robot ID, site ID, software version, config/calibration version.
- Incident time window and timezone.
- Rosbag/MCAP/Foxglove links.
- Logs/traces around failure.
- Operator/customer impact summary.
- Reproduction status: deterministic, probabilistic, not reproduced, or blocked.
- Regression test added or explicit reason why not.

Safety gate:

- If field incident involves collision, spill, abnormal force, human proximity, food safety, or recovery deadlock, Orchia blocks ordinary "done" status until a safety reviewer signs off.

### Template 3: Simulation Regression Matrix

Best for: nightly or pre-merge simulation suites.

Steps:

1. Planner generates scenario cards from a scenario library.
2. Worker launches jobs by simulator/backend.
3. Metrics Worker compares outputs against thresholds.
4. Auditor attaches videos, logs, MCAP files, and failure summaries.
5. Reviewer decides whether failures are blockers, flaky tests, or accepted known issues.

Scenario dimensions:

- Robot model/version.
- Site layout or station geometry.
- Lighting/perception conditions.
- Object/cup/ingredient variants.
- Network latency and sensor delay.
- Recovery branch activation.
- Human/operator interruption.
- Low consumables or hardware fault injection.

Required evidence:

- Scenario manifest and seed.
- Simulator version and container image.
- Robot model assets.
- Pass/fail matrix.
- Metrics: task success, duration, collisions, retry count, recovery count, path length, control-limit violations, dropped frames, CPU/GPU load.
- Video/log links for all failures.

Safety gate:

- High-risk behavior changes must pass required scenarios with no unreviewed failure class.

### Template 4: Hardware-In-The-Loop Bench Certification

Best for: changes that touch hardware movement, recovery, calibration, perception thresholds, or end-effectors.

Steps:

1. Planner creates HIL checklist from risk class.
2. Lab Worker reserves bench/robot and runs scripted trial.
3. Evidence Worker attaches telemetry, videos, and pass/fail notes.
4. Reviewer approves bench certification or opens follow-up tasks.

Required evidence:

- Hardware ID, sensor set, calibration version, firmware version.
- Test operator and witness if required.
- Physical safety checklist: E-stop, workspace clear, fixture status, consumables, liquid/electrical risk.
- Trial count and pass/fail count.
- Video and telemetry.
- Deviations and anomalies.

Safety gate:

- HIL card must be approved before canary if the change affects physical motion or recovery behavior.

### Template 5: Safety Envelope Change

Best for: speed limits, force/torque limits, workspace limits, recovery constraints, human-zone rules, or disable/enable of safety monitors.

Steps:

1. Planner classifies change as safety-sensitive.
2. Worker implements change behind a flag or site-scoped config.
3. Test Worker adds assertions for limits and failure modes.
4. Simulation Worker runs boundary scenarios and fault injection.
5. HIL Worker runs physical checks.
6. Reviewer requires dual approval.

Required evidence:

- Rationale and risk class.
- Old vs new envelope values.
- Failure modes considered.
- Unit/integration tests proving limits are enforced.
- Sim/HIL evidence at boundary conditions.
- Rollback path.
- Explicit signoff by robotics lead/safety owner.

Safety gate:

- Dual human approval and no auto-merge. Orchia should make this boringly strict.

### Template 6: Fleet Canary And Field Validation

Best for: rollout after merge or bench approval.

Steps:

1. Release Owner creates rollout rings: lab, internal, one quiet site, selected sites, all fleet.
2. Orchia creates evidence checklist per ring.
3. Field Auditor watches telemetry, incidents, and operator notes.
4. Reviewer approves ring promotion or rollback.

Required evidence:

- Version and config deployed.
- Robot/site list.
- Start and end times per ring.
- Health metrics: uptime, incident rate, task success, manual intervention rate, retries, customer/order impact.
- Field notes.
- Rollback execution proof or dry run.

Safety gate:

- Automatic hold if incident rate exceeds threshold or safety event appears.

### Template 7: Telemetry/Log Auditor Handoff

Best for: periodic review of fleet logs or suspicious metric drift.

Steps:

1. Auditor pulls metric anomalies, rosbag/MCAP snippets, traces, and screenshots.
2. Handoff groups findings by probable subsystem.
3. Planner creates task cards for root-cause work.
4. Worker confirms or rejects hypotheses.
5. Reviewer requires regression capture for confirmed bugs.

Required evidence:

- Query/filter used.
- Time range and fleet subset.
- Metric baseline and anomaly.
- Representative logs, traces, screenshots, bags, and videos.
- Suggested reproduction path.

Safety gate:

- If anomaly suggests unsafe behavior, planner classifies as high priority and creates a safety-sensitive card.

### Template 8: Behavior Tree Review

Best for: BehaviorTree.CPP, Nav2-style behavior trees, or equivalent state-machine changes.

Steps:

1. Worker attaches BT XML diff and rendered tree view.
2. BT Reviewer checks branch reachability, recovery behavior, timeouts, retries, blackboard inputs/outputs, and failure propagation.
3. Simulation Worker exercises all changed branches.
4. Evidence Auditor attaches Groot/Foxglove/log replay where available.

Required evidence:

- BT XML diff.
- Rendered tree or Groot screenshot/link.
- List of changed nodes and blackboard variables.
- Branch coverage: success path, failure path, timeout path, recovery path.
- Transition logs or replay.
- Scenario results.

Safety gate:

- No approval for changed recovery or fallback behavior without failure-path evidence.

## Evidence Requirements

Orchia should make evidence a typed artifact system rather than a free-form note. Each robotics task should have an evidence manifest.

### Core evidence fields

- Requirement or incident source.
- Risk class: low, medium, high, safety-sensitive.
- Affected robot(s), site(s), ROS packages, launch files, config files, BT/state-machine files, firmware, and hardware.
- Branch, commit, PR, build ID, container image, ROS distro, dependency lockfile.
- Test commands and outputs.
- CI provider, job links, artifacts, and logs.
- Simulation backend, scenario manifest, seed, world/asset versions, and metrics.
- HIL bench/robot ID, calibration version, firmware version, operator, trial count, videos, telemetry.
- Log assets: rosbag2, MCAP, Foxglove link/layout, trace file, raw logs.
- Fleet evidence: robot IDs, site IDs, deployment ring, telemetry queries, incident summaries.
- Reviewer signoff and open risks.
- Rollback plan and rollback proof.

### Minimum evidence by task type

| Task type | Minimum evidence |
| --- | --- |
| Pure docs or runbook change | Diff, reviewer signoff, affected workflow. |
| ROS package code change | PR link, build result, `colcon test` or equivalent, package-level tests, logs. |
| Launch/config/parameter change | Config diff, affected robots/sites, dry-run or launch test, rollback config. |
| Behavior tree/state machine change | Visual/diff evidence, branch coverage plan, simulation or HIL for changed branches. |
| Motion/control change | Unit tests, sim metrics, HIL video/telemetry, safety checklist, rollback. |
| Perception threshold/model change | Dataset/eval result, sim or replay evidence, false positive/negative analysis, field canary plan. |
| Recovery/safety envelope change | Failure-mode analysis, boundary tests, HIL, dual review, rollout hold. |
| Fleet rollout | Version manifest, ring plan, telemetry thresholds, rollback proof, post-rollout report. |

## Safety And Review Gates

Orchia should encode gates as policy templates. These are not a substitute for formal safety certification, ISO compliance, regulatory review, or a robotics company's safety management system. They are operational gates that reduce casual drift and missing evidence.

### Gate 0: Scope and risk classification

Every task gets one of four classes:

- Low: docs, non-runtime tooling, test-only changes.
- Medium: code/config changes that do not affect robot motion, customer interaction, hardware limits, or recovery.
- High: behavior logic, perception threshold, motion, recovery, deployment, or timing changes.
- Safety-sensitive: anything involving collision, force/torque, end-effector motion near people, fluid/heat/electrical risk, E-stop, safety monitors, or autonomous recovery.

Required action:

- High and safety-sensitive tasks require explicit evidence checklist generation.
- Safety-sensitive tasks require dual review and cannot be auto-approved.

### Gate 1: Build, quality, and ROS test gate

Use ROS-native testing wherever possible:

- ROS 2 `launch_testing` for integration/system-style launch tests: [ROS 2 launch_testing](https://docs.ros.org/en/rolling/Tutorials/Intermediate/Testing/Integration.html).
- ROS 2 quality practices and package quality declarations where appropriate: [ROS 2 Quality Guide](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Quality-Guide.html).
- CI helpers such as [action-ros-ci](https://github.com/ros-tooling/action-ros-ci) and [industrial_ci](https://github.com/ros-industrial/industrial_ci) for building and testing ROS workspaces.

Required action:

- No review if build/test artifacts are missing, unless the reviewer explicitly waives with a reason.

### Gate 2: Behavior logic gate

For behavior trees and state machines:

- Require visual/diff evidence.
- Require branch coverage for success, failure, timeout, recovery, and cancellation paths.
- Require blackboard/input/output review if using BehaviorTree.CPP-style BTs.
- Require logging/replay evidence for nontrivial changes.

Relevant tools:

- [BehaviorTree.CPP](https://www.behaviortree.dev/docs/intro) provides a C++ behavior tree framework with XML trees and logging/profiling infrastructure.
- [Groot2](https://www.behaviortree.dev/groot/) is an IDE for behavior tree editing, monitoring, transition logs, breakpoints, and replay.
- [Nav2 behavior tree docs](https://docs.nav2.org/behavior_trees/overview/detailed_behavior_tree_walkthrough.html) are a useful reference pattern for ROS navigation behavior trees.

Required action:

- Changed recovery/fallback behavior cannot pass on happy-path evidence only.

### Gate 3: Simulation regression gate

Use Gazebo, Isaac Sim, or internal simulators depending on robot domain:

- [Gazebo](https://gazebosim.org/docs/latest/getstarted/) is the open-source simulator commonly used in ROS ecosystems.
- [NVIDIA Isaac Sim](https://developer.nvidia.com/isaac/sim) is positioned for physically based simulation, testing, training, and synthetic data generation for AI-based robots.

Required action:

- High-risk behavior changes must attach a simulation matrix.
- Every sim failure must be triaged as blocker, flaky, known issue, environment issue, or accepted with signoff.

### Gate 4: Log/replay and trace gate

Robot bug evidence should preserve enough runtime data to reproduce or diagnose:

- [rosbag2](https://github.com/ros2/rosbag2) records and plays back ROS 2 system communications.
- [ros2_tracing](https://github.com/ros2/ros2_tracing) provides tracing instrumentation and tools for ROS 2.
- [Foxglove](https://foxglove.dev/) and [MCAP](https://foxglove.dev/product/mcap) are strong robot data/visualization assets.

Required action:

- Field bugs cannot be closed without either reproduction assets or a documented reason reproduction is unavailable.
- Confirmed field bugs should create or update a regression scenario.

### Gate 5: Hardware-in-the-loop gate

Required for behavior changes touching physical motion, recovery, safety, calibration, perception thresholds, or hardware interaction.

Required action:

- Bench operator recorded.
- Robot/hardware ID recorded.
- Calibration/firmware versions recorded.
- Video and telemetry attached.
- E-stop and safety checklist completed.

### Gate 6: Human review and rollback gate

Reviewer must validate:

- Evidence completeness.
- Risk classification.
- Known issues and waivers.
- Rollback plan.
- Deployment scope.

Required action:

- Workers cannot self-approve.
- High-risk work cannot move directly from implementation to fleet rollout.

### Gate 7: Canary and post-deployment gate

Required action:

- Deployment rings are explicit.
- Telemetry thresholds are defined before rollout.
- Rollback owner is named.
- Post-rollout report attaches metrics and incidents.

## Competitive Landscape

### ROS 2 ecosystem

Strengths:

- ROS is the de facto open ecosystem for robot middleware and tooling.
- ROS 2 has launch testing, bagging, tracing, lifecycle nodes, build/test workflows, and broad package ecosystem.
- CI helpers like action-ros-ci and industrial_ci already solve build/test setup for ROS workspaces.

Orchia gap:

- ROS does not provide a visual, human/agent workflow board for cross-tool evidence, safety gates, task ownership, and staged release decisions.

Risk:

- ROS-native teams may prefer GitHub/GitLab plus scripts unless Orchia saves real debugging or review time.

### BehaviorTree.CPP, Groot, Nav2, SMACH/FlexBE-style tools

Strengths:

- BehaviorTree.CPP and Groot focus directly on behavior authoring, monitoring, transition logs, and replay.
- Nav2 shows mature behavior-tree use in navigation.
- These tools solve "build and inspect the behavior" better than Orchia should.

Orchia gap:

- Orchia can coordinate the release lifecycle around behavior changes: tests, sim runs, HIL, review, rollout, and incident feedback.

Risk:

- If Orchia tries to become a behavior tree IDE, it competes where Groot is already purpose-built.

### Foxglove

Strengths:

- Foxglove positions itself as a multimodal data platform for robotics teams, including collection, analysis, visualization, MCAP, fleet, integrations, SDK/API, and webhooks.
- It owns an important part of robot debugging: data visibility and replay.

Orchia gap:

- Orchia can use Foxglove links/layouts/MCAPs as evidence artifacts in a broader review and release workflow.

Risk:

- Foxglove can move upward into issue/release workflows; Orchia must stay complementary and workflow-specific.

### Formant and InOrbit

Strengths:

- Formant is oriented around operational clarity, investigation workflows, industrial AI/fleet context, and turning robot data into operational actions.
- InOrbit describes itself as an AI-powered robot orchestration platform for software-defined operations at scale.

Orchia gap:

- Orchia is stronger upstream in engineering development, CI, simulation, HIL review, and AI-agent coordination before field deployment.

Risk:

- Fleet operations platforms can become the system of record for incidents and field validation, reducing Orchia to an engineering-side tool.

### Gazebo and Isaac Sim

Strengths:

- Gazebo is broadly used with ROS and open simulation.
- Isaac Sim is strong for physically based simulation, synthetic data, and AI robot training/testing.

Orchia gap:

- Orchia can schedule, summarize, compare, and gate simulation runs rather than simulate itself.

Risk:

- Simulation stacks often come with their own dashboards and experiment management; Orchia must be simulator-agnostic.

### Open-RMF

Strengths:

- Open-RMF addresses interoperability and coordination across heterogeneous fleets, facility resources, traffic, doors, elevators, and task adapters.

Orchia gap:

- Orchia can coordinate software changes and validation around RMF adapters, task flows, and site-specific behaviors.

Risk:

- Open-RMF users may be more facility-integration focused than behavior-infrastructure focused.

### Generic CI/CD and DevOps

Strengths:

- GitHub Actions, GitLab CI, Jenkins, Buildkite, Kubernetes, containers, artifact stores, and existing scripts are familiar and flexible.

Orchia gap:

- General CI says pass/fail. Orchia can say "this behavior change has the required robot-specific evidence for the next physical-world gate."

Risk:

- If Orchia only wraps CI status, it will be easy to ignore. It needs typed robotics evidence and workflow templates.

## Product Concept: Orchia Robotics Behavior Control Plane

### What it should be

A narrow product layer that coordinates robot behavior changes from requirement or incident to tested rollout.

Core primitives:

- Behavior task board with risk classes and evidence requirements.
- Agent roles for planning, implementation, simulation, log audit, HIL audit, review, and rollout.
- Policy templates for gates.
- Artifact manifest for bags, MCAPs, traces, videos, CI jobs, sim runs, and deployment rings.
- Integrations that link out to primary tools.
- Pause/hold/rollback semantics for high-risk work.
- Review history and decision records.

### What it should not be

- Not a replacement for ROS.
- Not a simulator.
- Not a behavior-tree IDE.
- Not a fleet operations platform.
- Not a teleoperation system.
- Not a formal safety certification system.

### Minimum integration set

For a credible Artly-like pilot:

- GitHub or GitLab PR/issues.
- GitHub Actions/GitLab/Jenkins CI status.
- ROS workspace metadata: package names, launch files, config files, BT XML/state-machine files.
- Artifact links: rosbag2, MCAP, Foxglove layouts, logs, traces, videos.
- Simulation runner adapter: shell command, container job, or existing CI workflow.
- HIL/lab evidence upload or link capture.
- Deployment/canary manifest: robot/site/version/config.

Nice-to-have later:

- Foxglove API/webhook integration.
- Formant/InOrbit incident links.
- Open-RMF task/fleet adapter awareness.
- Scenario library and metric parser.
- BT XML visual diff.
- Automatic risk-class suggestions from file paths and diff analysis.

## Robotics DevOps Practices To Encode

### Test pyramid for robot behavior

1. Unit tests for pure logic, geometry, parsing, state transitions, and thresholds.
2. ROS launch/integration tests for node graphs, lifecycle, topics, actions, services, QoS, and TF assumptions.
3. Bag/replay tests for known field incidents.
4. Simulation regression for behavior scenarios and fault injection.
5. HIL bench runs for physical-world changes.
6. Canary deployment with telemetry thresholds.
7. Fleet rollout with rollback.

Orchia should make the pyramid visible and task-specific.

### Scenario library

Each scenario should have:

- Name and owner.
- Robot model/hardware assumptions.
- Simulator/runtime backend.
- Seed and environment version.
- Expected metrics.
- Known flake notes.
- Related field incidents.
- Required risk classes.

### Field-to-regression loop

The most valuable workflow is:

field incident -> logs/bags -> reproduction -> fix -> regression scenario -> release gate -> canary -> monitoring.

This is where Orchia can feel essential.

### Release rings

Suggested default:

1. Developer local.
2. CI simulation.
3. Lab sim/HIL.
4. One internal robot.
5. One low-risk site/shift.
6. Selected sites.
7. Fleet.

Each ring has explicit promotion and rollback criteria.

## MVP Pilot For Artly-Like Robotics

### Pilot goal

Prove that Orchia reduces behavior-release ambiguity and increases evidence completeness for robotics engineers.

### 30-day plan

Week 1: Map current workflow

- Interview robotics/software engineers.
- Inventory tools: ROS distro, CI, simulator, logs, fleet ops, deployment process.
- Select two workflow templates: Field Bug Reproduction and Behavior Change PR.
- Define risk classes and evidence checklist.

Week 2: Concierge field incident workflow

- Take 2-3 real incidents.
- Manually create Orchia handoffs with logs/bags/screenshots/videos.
- Convert each into Planner/Worker/Reviewer tasks.
- Track time to reproduction and quality of evidence.

Week 3: Behavior release workflow

- Take one real behavior/config change.
- Run the Orchia template through code, CI, sim, HIL, and review.
- Attach all evidence artifacts.
- Record where engineers resist, duplicate work, or ask for integrations.

Week 4: Canary and decision review

- Track one small rollout ring.
- Attach telemetry and field validation.
- Run a retrospective.
- Decide whether this is a product wedge, internal tool, or dead end.

### Pilot success metrics

Quantitative:

- Percent of behavior changes with complete evidence before review.
- Time from field incident to first reproduction hypothesis.
- Time from field incident to confirmed reproduction.
- Number of missing-evidence review loops.
- Number of field bugs converted into regression scenarios.
- Reviewer time per behavior change.
- Rate of rollback/canary holds caused by objective thresholds.

Qualitative:

- Engineers trust the board as the source of truth.
- Reviewers say it saves mental load.
- Managers can tell what is blocked without interrupting engineers.
- Field/operator notes become engineering tasks without manual archaeology.
- The process catches one issue that would likely have reached a robot.

### Minimum pilot data to collect

- Three representative behavior changes.
- Three representative field incidents.
- At least one safety-sensitive or high-risk change.
- One simulation matrix.
- One HIL run.
- One canary/field validation.
- Engineer feedback and willingness-to-pay signal.

## Pricing And Packaging Hypothesis

This vertical likely supports higher ACV than ecommerce solo creators, but with longer sales cycles and heavier integration.

Possible packages:

- Internal/design-partner pilot: $5k-$20k for 4-8 weeks of concierge setup and workflow design.
- Small robotics team SaaS: $500-$2,000/month for 5-20 engineers if it links to existing tools.
- Pro/enterprise: $15k-$75k/year for teams with fleets, safety gates, custom integrations, artifact retention, and SSO/VPC needs.
- Services-heavy initial motion: $10k-$50k setup for custom ROS/CI/Foxglove/Formant integration.

Good value metrics:

- Behavior releases reviewed.
- Field incidents reproduced.
- Regression scenarios added.
- HIL certifications completed.
- Fleet canary rollouts managed.

Bad value metrics:

- Raw agent runs.
- Number of tasks.
- Token usage.
- Generic seats without robotics evidence workflow.

## Strategic Assessment

### Why this is attractive

- High pain: physical robots make incomplete software review expensive.
- Strong Orchia fit: review gates, logs, evidence, handoffs, role separation, pause/resume.
- Concrete artifacts: bags, MCAPs, videos, CI jobs, sim results, HIL runs.
- Artly proximity: the user has real domain access and likely knows the pain firsthand.
- Differentiation: most tools are point solutions; Orchia can be the cross-tool release record.

### Why this is hard

- Integration burden is high.
- Robotics teams have bespoke stacks.
- Trust bar is high because the system touches safety-adjacent workflows.
- Market is smaller and more technical than broad AI workflow/ecommerce.
- Existing incumbents can expand upward from data/fleet/sim into workflow.
- Buyers may expect deep domain expertise and enterprise controls.

### Best wedge

Do not pitch "robotics DevOps" broadly. It sounds too large and collides with CI, sim, fleet ops, and observability.

Better wedge:

> Behavior release manager for ROS-powered service robots.

Even narrower:

> Turn field robot failures into reproducible tests, reviewed fixes, HIL evidence, and safe canary rollouts.

This wedge is concrete, painful, and compatible with Artly-like systems.

## Recommendation

Run this as a serious validation track, but do not replace the current broader Orchia strategy yet.

Recommended next action:

1. Build one robotics template pack in Orchia:
   - Field Bug Reproduction.
   - Behavior Change PR.
   - Simulation Regression Matrix.
   - HIL Bench Certification.
   - Fleet Canary.
2. Pilot it with Artly-like real data for 30 days.
3. Keep integrations lightweight at first: links and evidence manifests before deep API sync.
4. Require safety/review gates from day one.
5. After the pilot, continue only if at least two of these are true:
   - Engineers use it without being forced.
   - It reduces incident reproduction/review time by at least 25%.
   - It catches a meaningful missing-evidence or safety issue.
   - A robotics team agrees to pay for a pilot or annual plan.
   - Another robotics team asks for the same workflow after seeing the template.

Decision:

- Robotics is a compelling control-plane demonstration and a plausible premium vertical.
- It is not the easiest first market unless Artly access creates an unfair wedge.
- The winning product should coordinate evidence and review across ROS/sim/HIL/fleet tools, not compete with those tools.

## Source Appendix

- Artly: <https://artly.coffee/>
- IFR factory robot operating stock: <https://ifr.org/ifr-press-releases/news/record-of-4-million-robots-working-in-factories-worldwide>
- IFR US robot industry 2026 press release: <https://ifr.org/ifr-press-releases/news/service-robots-global-sales-value-up-30>
- ROS 2 launch_testing integration docs: <https://docs.ros.org/en/rolling/Tutorials/Intermediate/Testing/Integration.html>
- ROS 2 Quality Guide: <https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Quality-Guide.html>
- rosbag2: <https://github.com/ros2/rosbag2>
- ros2_tracing: <https://github.com/ros2/ros2_tracing>
- action-ros-ci: <https://github.com/ros-tooling/action-ros-ci>
- industrial_ci: <https://github.com/ros-industrial/industrial_ci>
- BehaviorTree.CPP: <https://www.behaviortree.dev/docs/intro>
- Groot2: <https://www.behaviortree.dev/groot/>
- Nav2 behavior tree walkthrough: <https://docs.nav2.org/behavior_trees/overview/detailed_behavior_tree_walkthrough.html>
- Gazebo docs: <https://gazebosim.org/docs/latest/getstarted/>
- NVIDIA Isaac Sim: <https://developer.nvidia.com/isaac/sim>
- Foxglove: <https://foxglove.dev/>
- Foxglove MCAP: <https://foxglove.dev/product/mcap>
- Formant: <https://formant.io/>
- InOrbit: <https://www.inorbit.ai/>
- Open-RMF: <https://www.open-rmf.org/>
