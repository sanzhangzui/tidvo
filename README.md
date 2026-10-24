# Tidvo

**Cleanup tailored for AI Agent workflows.**

[中文说明](README.zh-CN.md)

An open-source skill with protections tailored for Codex, Claude Code, OpenClaw,
Pi and related Agent products: inspect storage, preserve sessions and memory,
keep shared Skills and MCP references, and retain development dependencies while
reviewing disposable caches. It uses a pinned Mole safety backend.
Python 3.11+ standard library; Bash/system tools on macOS. Beta 0.2.0.

It discovers project artifacts and AI tooling, explains activity/reference
evidence, and moves only a reviewed, signed candidate plan into Trash. It keeps
durable receipts and supports conflict-safe restore. It never empties Trash.

**Moved to Trash is not disk space freed.** Same-volume moves usually retain
the same storage. Recovery is possible only while the recorded payload exists.

## Platform status

| Platform | Status |
| --- | --- |
| macOS | Beta. Actual changes require macOS 14+, Python 3.11+ and a normal user account. Local validation is on Apple Silicon; other environments depend on published CI results. |
| Windows | Planned. Windows discovery, process evidence, file locking and Recycle Bin execution are not implemented. |
| Linux | Portable fixture tests only; not a supported desktop cleanup platform. |

The Tidvo brand is platform-neutral. Current capabilities and the future roadmap
are separate; see [validation evidence](references/validation.md).

## Install the skill

Download `tidvo-0.2.0.tar.gz` and its `.sha256` file from this repository's GitHub
Releases. Verify the checksum, then unpack the archive into an unused directory:

```bash
shasum -a 256 -c tidvo-0.2.0.tar.gz.sha256
tar -xzf tidvo-0.2.0.tar.gz
```

The resulting `tidvo/` folder is a self-contained skill with one `SKILL.md`.
Install that whole folder using your Agent's local-skill mechanism, or ask the
Agent to read its `SKILL.md` directly. Use an unused destination; retain an
existing installation's contents until you have reviewed the update. A separate
Mole installation is not required. Never recursively install skills from `vendor/`.

## Use locally

The primary skill experience is conversational. Ask the agent to read this
folder's `SKILL.md` and, for example, "保留项目依赖，分析应用缓存和项目缓存，
把建议清理的内容分组给我确认。" The agent scans, maps that scope to internal
candidate IDs, presents an exact batch plan, and applies after one confirmation.
Users of the skill do not need to copy candidate IDs or type each cleanup command.
Recommendations account for the user's current development work and keep build
outputs separate from routine caches. After every operation, the agent summarizes
the outcome, retained/skipped items, space accounting where relevant, and the
most useful next action. See [the decision and reporting guide](references/recommendations.md).

For direct script use, the following is the lower-level manual interface:

```bash
# 1. Scan and save the report; the terminal shows a readable Chinese summary.
python3 scripts/tidvo.py scan --root ~/Projects --output scan.json
# 2. Copy the IDs of the items you want to clean from that summary.
python3 scripts/tidvo.py plan --scan scan.json --ids CANDIDATE_ID
# 3. Review the exact plan and confirm it before executing the shown command.
python3 scripts/tidvo.py apply --plan PLAN_ID --confirmed
python3 scripts/tidvo.py history
python3 scripts/tidvo.py restore --run RUN_ID --confirmed
```

Replace `CANDIDATE_ID`, `PLAN_ID` and `RUN_ID` with the IDs returned by the tool;
multiple candidate IDs can follow `--ids`. Only `apply` moves anything to Trash.
`plan --scan scan.json --all-actionable` generates one batch plan when you intend
to review every currently actionable item. It does not execute cleanup; eligibility
does not mean every item is recommended for removal. Review the exact paths first.
`scan.json` is always JSON; add `--json` to any command for machine-readable
terminal output. A prior scan printed without `--output` must be rerun with it
before planning. Existing output files are never overwritten.

Project `node_modules`, `.venv` and `venv` are **kept by default**. Reinstallable
dependencies are still needed for development. These directories cannot enter a
cleanup plan, including through `--all-actionable`. Previous-version plans must be
rescanned under the new policy.

Check `python3 --version` first: your interactive terminal can resolve a different
Python from your agent. If it is older than 3.11, use the absolute path to an
existing 3.11+ interpreter. The tool never installs or replaces your runtime.

Use `SKILL.md` with an agent or run these bundled scripts directly. An agent must
show the precise plan and its consequences before applying. No global `mo`
installation is needed. See [the full command contract](references/commands.md).

## First-version focus

- Project containers beyond conventional folder names; bounded Git/worktree-aware discovery.
- Project artifact candidates, preserved dependency environments, npx tools and known MCP configuration reference evidence.
- Editor package caches, obsolete extensions and inactive old Codex daemon releases.
- Known app resource caches, Chrome site attribution and selected user temporary caches.
- VS Code diagnostic logs, versioned compiled caches and per-partition Webview caches.
- Dia resource/component caches and Feishu/Lark per-account Service Worker caches.
- npm native-module prebuild download archives, separate from installed dependencies.
- Explicit uncertainty: active, tracked, referenced, partial and unmanaged items are explained.
- Agent metadata inventory with a declarative catalog, custom roots, unknown-tool
  hints and protection rechecks at scan, plan and immediately before moving.
- Strict Trash-only execution and persistent, signed audit/restore records.

Uninstall, system optimization, slimming, sudo, process termination and permanent
cleanup are out of scope. Managed cache pruning remains a manual suggestion.
Permission/occupancy failures are refusals, not permission to bypass protections.

Default project discovery now walks up to six container levels with a directory
count and time budget, including nested workspaces such as Documents/software/MCP.
It never descends into installed project dependency folders. Browser/messaging
site caches need a single identified HTTP(S) origin; unknown or extension origins
stay report-only. Cache index evidence is rechecked at plan/apply time. Webview
and site caches may contain offline resources, so their impact is shown separately
from ordinary download caches. Cookies, IndexedDB, local storage and editor user
history are outside these new rules.

## Agent read-only inventory

Ask the agent: **“用这个 Skill 给我的 Agent 工具做只读体检，按会话、记忆、
数据库、工作区和共享资源汇总占用，说明保护项与适配缺口，先不清理。”**

```bash
python3 scripts/tidvo.py agents --root ~/Projects
python3 scripts/tidvo.py agents --json --output agent-audit.json
python3 scripts/tidvo.py agents --catalog
```

The initial catalog has 38 entries: 31 Agent/editor tools, three desktop AI
clients, Feishu/Lark integration, two model runtimes and shared Agent resources.
It includes Codex, Claude Code, Pi, OpenClaw, Gemini CLI, OpenCode, Cursor,
Windsurf, Cline, WorkBuddy, CodeBuddy, TRAE, Qoder, Kimi, Qwen Code and iFlow.
This is a detection/protection catalog, **not 38 certified cleanup adapters**.
Evidence levels and version/layout limits are explicit. Marker detection,
extension manifests and custom roots extend coverage to tools outside the list;
unmarked, remote and cloud-only tools cannot be discovered reliably this way.

`agents` never generates cleanup candidates, connects to databases, executes an
Agent or queries cloud accounts. It measures filesystem metadata, parses bounded
known config/manifest files, reads known application version metadata and observes
process PIDs. Secrets, conversations and database bodies are not exported or read
for size analysis. All inventory data stays protected, including `tmp` and `cache`
subdirectories. Normal `scan` includes the same inventory under `agent_audit`.
Partial measurements are lower bounds, not reclaimable space. See the
[Agent adapter and protection guide](references/agent-adapters.md) for current
coverage, exclusions, environment overrides, shared links and custom roots.

## Development and release

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_release.py
```

Tests use temporary fixture homes and never clean real user directories. The
pinned Bash integration is tested on macOS; portable fixture tests can also run
on Linux. Intended mutation support is macOS 14+ on Apple Silicon and Intel.
Do not treat intended support as validated release coverage: see
[validation evidence](references/validation.md). No public release is implied by
building a package, and this repository does not auto-upload anything.

The release archive is a self-contained skill folder. Review its contents before
installing it into an agent. Personal cleanup histories are not packaged.
Install the unpacked release folder as the `tidvo` skill. The source
checkout preserves upstream development material; do not bulk-install every
skill found recursively inside `vendor/`.

## Source and license

GPL-3.0-only, including the incorporated Mole source. This is an independent
derivative, not an official Mole product. [UPSTREAM.md](UPSTREAM.md) identifies
the exact upstream commit, local adaptations, and corresponding source. Product
uses the Tidvo brand; make no unsupported “cleans more GB” claim.

Tidvo was developed locally as Mac Dev Cleanup before its first public beta.
`scripts/mac_cleanup.py` remains a compatibility entry point. The internal
`macdev` module, `~/.config/mac-dev-cleanup/config.json`,
`~/.local/state/mac-dev-cleanup`, existing Trash payload prefixes and backend
flags retain their original names to preserve configuration and recovery records.
Renaming the product does not migrate or delete user data.
