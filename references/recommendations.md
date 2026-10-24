# Development context, recommendations and follow-through

Use this guide when turning scan evidence into a conversational recommendation,
and when reporting an operation's result. The agent makes these decisions from
evidence; the scanner does not implement a complete usage/reference graph or
Mole's seven-day default-selection heuristic. Do not claim otherwise.

## Make ordinary requests sufficient

Disk cleanup is the primary workflow. Agent-specific evidence improves protection
and recommendations; users do not need an Agent-focused prompt to get it.
For “帮我清理一下”, start a normal scan, choose a conservative ordinary-cache
batch and show its exact plan for one confirmation. For “看看哪里占空间”, scan
and explain only. The skill entry point defines routing and default retention.
Do not ask users to repeat retention rules, pick IDs or specify technical groups.

The first report should answer: how much disk space is used/available, what this
scan found, what is worth cleaning, what will be retained, and the next action.
Keep optional Agent inventories behind that disk-cleanup decision unless asked.
Volume used space and known candidate sizes are different measurements. If the
known candidates explain only a small part of used capacity, say which scope is
unexamined rather than presenting the candidate list as a complete disk analysis.

## Understand the current work

Start with facts already in the conversation: projects being developed, upcoming
builds/releases, tools the user needs, requested exclusions and approved scope.
Add bounded scanner evidence: project manifests, Git tracking, app ownership,
process/file occupancy, known configuration references and scan completeness.
Do not execute project scripts or read credentials to infer usage.

Separate facts from inference. No running process, no configuration match and
an old timestamp do not establish that a project or tool is abandoned. Where a
missing fact changes the decision, ask one targeted question while completing
independent analysis; otherwise retain the item and explain the uncertainty.
Current-run choices remain current-run choices unless persistence is requested.

## Recommend useful scope

| Group | Default recommendation and impact to explain |
| --- | --- |
| Project dependencies (`node_modules`, `.venv`, `venv`) | Retain; needed for development even while idle. The script makes these report-only. |
| Agent sessions, memory, configuration, databases, workspaces, Skills/plugins/models | Retain. `agent_audit` and `agents` are inventories without cleanup authority. Separate occupied capacity from removable candidates; explain incomplete/heuristic coverage. |
| Known application and download caches | Consider within requested scope when ownership and activity are verified. Explain cache regeneration, downloads, and an initially slower launch. |
| VS Code logs and compiled caches | Separate loss of historical diagnostics from regenerated compiled resources. Preserve User/History, globalStorage and workspace state. |
| VS Code Webview, Dia and Feishu/Lark site caches | Explain possible loss of offline resources and re-downloads; retain while the owning application is active. Unknown browser/messaging origins stay report-only. |
| npm prebuild archives | These are native-module download packages, not installed dependencies. Explain that a later install/rebuild may need another download. |
| Project bytecode/test/tool caches | Consider individually verified candidates; explain recomputation and avoid source, test inputs, history and needed tool state. |
| Build/release outputs (`dist`, `build`, `.next`, `target`, `.build`) | Review separately. They may be needed for running, packaging or delivery. A generic request to clear caches is not consent to remove these outputs. Retain when current purpose is uncertain. |
| Installed AI/npx tools and old editor/daemon versions | Review separately. Explain reinstall/network needs or loss of local rollback; retain active, referenced or explicitly needed tools. |
| Partial, unknown or protected data | Retain. Explain the actual missing evidence or protection, even when large. |

Backend eligibility is a prerequisite, not a recommendation. Prioritize candidates
that reduce clutter with less disruption to the user's next development task.
Never upgrade `report_only` to removable based on agent judgment, and never
recommend dependency removal just to maximize a space total.

Group recommendations by application or project and purpose. Show actual paths,
sizes or unavailable measurements, reason and expected effect; summarize large
sets without hiding different consequences. Distinguish retained groups clearly.
Map natural-language choices to candidate IDs internally. If a user says
"保留依赖，只清应用缓存", select that scope yourself and present its exact plan
for one confirmation. Never convert it to every actionable candidate. Changed
scope or evidence needs a fresh reviewed plan; unchanged consent does not need
repeated permission prompts.

## Always finish with outcome and next action

Scale the report to the work. Lead with the outcome, explain important exceptions,
then recommend a concrete next action. Do not require a rigid template or repeat
empty categories. The following information is useful for each operation:

| Operation | Report | Recommend next |
| --- | --- | --- |
| Scan | Actual coverage, completeness, largest relevant groups, recommended vs retained scope; no cleanup occurred | Present a concrete batch matching the request, or resolve a material ambiguity. If nothing is suitable, say no cleanup is recommended. |
| Agent check | Tools/data actually observed, purpose and protected state, shared paths, metadata-size lower bounds and coverage gaps; no cleanup occurred | Verify an uncertain local data root or request it explicitly; review existing ordinary cache candidates separately. Do not recommend deleting sessions/memory just because they are large. |
| Plan | Exact selected scope, estimated capacity and consequences; no cleanup occurred | Obtain one confirmation for this batch, unless already authorized for the same reviewed scope. |
| Cleanup | Receipt-backed moved/skipped/recovery-required counts and meaningful groups; unprocessed items; moved capacity and separately observed free-space change | After success, suggest normal use of affected apps. For a blocked group, name the missing precondition; for interruption, inspect the receipt before another action. |
| Restore | Which recorded payloads were restored, which were not, and conflict/missing-payload reasons | Resume normal use after success, or review the specific source/Trash locations without overwriting conflicts. |
| History | Relevant operations and statuses; identify unresolved entries without treating old moved totals as current disk savings | Offer recovery only when relevant; otherwise state that no action is required. |
| Refusal/error | What completed, what did not, whether any mutation may have occurred, and where its receipt is | Give the specific remedy supported by evidence. Do not blindly retry mutations or work around safeguards. |

An interruption outranks an invitation to clean more. Do not suggest another
cleanup run while the current move outcome is unresolved. In an ordinary skip,
recommend retrying only the affected scope after its precondition changes, with
a fresh plan. If the user's immediate goal is free disk space, explain that
same-volume Trash moves retain storage; any later manual Trash decision is
separate. Never automatically empty Trash or make it the routine next step.

For a documentation/tooling update, report the changed behavior and validation,
then give the next way to use it. Do not present a code change as a real cleanup,
and do not run real-user cleanup just to demonstrate that the skill works.
