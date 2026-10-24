# Command contract, schema version 1

Run from this self-contained skill directory, or use absolute script paths.
The public skill is `tidvo`, with entry point `scripts/tidvo.py`. The legacy
`scripts/mac_cleanup.py` delegates to the same implementation. Config/state
paths retain the pre-release name `mac-dev-cleanup` to preserve existing records.
Current support is macOS beta; Windows is planned, not implemented.
Terminal output defaults to a readable Chinese summary with next-step commands.
Use `--json` on any subcommand for machine-readable output. An explicit scan/agents
`--output` file always contains full JSON regardless of the terminal format.
No command installs dependencies or invokes Mole's broad CLI.

```bash
python3 scripts/tidvo.py scan --root ~/Projects --exclude ~/Projects/active --output scan.json
python3 scripts/tidvo.py agents --root ~/Projects --output agent-audit.json
python3 scripts/tidvo.py agents --catalog --json
python3 scripts/tidvo.py plan --scan scan.json --ids CANDIDATE_ID ANOTHER_ID
python3 scripts/tidvo.py apply --plan PLAN_ID --confirmed
python3 scripts/tidvo.py history --json
python3 scripts/tidvo.py restore --run RUN_ID --confirmed
```

`--output` creates a new private file and refuses existing paths and symlinks.
Save the scan before planning; an earlier terminal-only scan must be repeated
with `--output`. The human scan lists candidate IDs and a planning command;
the human plan lists the exact selection and its apply command. Neither moves
files. Only run the apply command after reviewing that selection.
Choose explicit IDs; `plan --all-actionable` is available only when the user
really wants every currently actionable candidate reviewed together. The final
plan must still be presented. `--confirmed` is an acknowledgement by the caller,
not an authenticated proof of human consent.

## Discovery and configuration

With no `--root`, discover project containers below eligible Home children and
known agent worktree roots. Both default and explicit roots allow up to six
container levels and their recognized artifact children, at most 20,000 visited
directories across roots, within the scan time budget. Dependency directories
are never traversed; an explicit root inside them is refused.
Home, Library and external volumes cannot be project cleanup boundaries.
Use a nearer root for deeply nested projects. Symbolic project roots are skipped.
`--budget` is 1–600 seconds (default 120), with individually bounded system probes.

Optional `~/.config/mac-dev-cleanup/config.json`:

```json
{
  "roots": ["~/Projects", "~/Work"],
  "excludes": ["~/Work/current-release"],
  "agent_roots": {"custom_agent": ["~/AgentData/custom"]}
}
```

CLI roots replace configured roots; CLI exclusions add to configured exclusions.
Settings are not written by the product. Configuration changes are rechecked
before moving candidates. Bad or unreadable configuration stops mutation.

Since 0.2.1, ordinary scans include `disk_usage` for the filesystem containing
Home: `total_bytes`, `used_bytes`, `free_bytes`, scope/path and measurement status.
Unavailable capacity is null and reported as a gap. These filesystem statistics
are separate from candidate capacity: discovery covers known cache/development
paths and is not a complete inventory of all disk usage.

Supported project metadata includes package.json, pyproject.toml, requirements.txt,
Cargo.toml, go.mod, Maven/Gradle, Package.swift and Git/worktrees. Candidate types
include dependency folders and virtual environments for reporting, bytecode/tool
caches, recognized frontend/native outputs, npx installations,
VS Code installers/obsolete extensions, Codex old daemon releases, known app
resource caches, Chrome site caches and user cache/temporary entries.

Version 0.1.2 adds these narrowly scoped rules:

- `Code/logs/<timestamp>` diagnostic sessions and `Code/CachedData/<version-hash>`.
- `Code/WebStorage/<numeric-partition>/CacheStorage/<cache-id>` payload directories;
  index metadata and sibling user state are retained. Unknown layouts are report-only.
- Dia HTTP/code/GPU caches in the known Caches and Application Support User Data
  layouts, component/extension download caches, and per-origin Service Worker caches.
- Feishu/Lark `aha/users/<account>/profile_explorer` and
  `iron/users/<account>/profile_main` Service Worker CacheStorage payloads, including
  LarkInternational and the known sandboxed Feishu layout. No account/profile root,
  Cookies, ScriptCache, IndexedDB or Local Storage is targeted.
- `.npm/_prebuilds/<hash>-<package>.<archive>` download files. Unknown files and
  directories remain report-only; installed node_modules remain retained.

Browser and messaging Service Worker caches require one identifiable HTTP(S) origin;
mixed, unknown and extension origins are retained. Webview caches have their own
known VS Code layout rule and require review of possible offline-resource loss.
The index's content digest and filesystem identity are checked again when planning
and immediately before moving the payload. An absent Webview index appearing
after review also invalidates the move. Feishu and Lark process aliases guard
both families, and each candidate gets fresh activity/file-occupancy checks.

Reference adapters read selected command/path fields in Codex, Claude, Cursor,
Pi and project `.mcp.json`/`.vscode/mcp.json` configurations. Secrets and raw
command lines are not exported. These adapters are deliberately bounded: no
match does not mean unused. Malformed known configs make tool decisions uncertain.
Unknown applications, browser extension caches, managed uv/pnpm stores and
unproven browser runtime versions are report-only. They are not trashable through
`plan`. Native prune commands are suggestions, never automatically executed.

Project `node_modules`, `.venv` and `venv` are always report-only: they are needed
for development even if a process is not using them at scan time. A rebuild
manifest does not change that policy. Download caches are separate candidates.
There is no dependency-removal override in this interface. Policy version 0.2.4
rejects earlier-version plans; rescan and review a fresh plan.

Since 0.2.3, `scan` reports application installation separately from process
activity. `scan --uninstalled-app Dia` acknowledges prior user confirmation of
uninstallation and authorization to remove that app's exclusive residuals,
including its private history/settings/databases. This is not a generic path
override; installed/unknown/active/referenced apps stay retained. A scoped negative
search by itself is not proof of uninstall. Unconfirmed possible residuals appear
in `uninstalled_residual_inventory` without enabling plans and may overlap ordinary
cache candidates; do not sum their sizes. See [uninstalled-apps.md](uninstalled-apps.md)
for exact adapters, authorization, immediate rechecks and recovery limits.

## Agent inventory and protection (0.2.0)

`agents` accepts `--root`, `--exclude`, `--budget`, `--json`, `--output` and
`--catalog`. Scope and budgets follow scan rules. `--catalog` returns the
declarative capability list; it does not establish what is installed. The regular
Agent check discovers project markers without measuring project cleanup candidates
or invoking Git, npm, uv, native Agent CLIs, hooks, SQL or cloud APIs. It uses a
read-only process listing, bounded local config/extension manifests, filesystem
metadata and known app Info.plist files. No product state is created, apart from
the explicit new private output file requested by `--output`.

`agents` output has `detected_tools`, `issues`, `scan_status`, `catalog_version`,
`total_unique_allocated_bytes`, `metadata_entries_visited` and `action=report_only`.
Each tool records identity/evidence, roots, optional app versions and observed
process PIDs. `activity=not_observed` is not proof of idle/background-task completion.
Root rows contain categories, protection/basis, resolved shared-link paths,
allocated bytes, completeness and lower-bound status. No `candidates` or cleanup
IDs are generated. An Agent report is not input to `plan`.

Regular `scan` adds `agent_audit` with its own completeness; it is separate from
candidate totals and may be partial even when the ordinary scan completed. Its
metadata walk has a global time/100,000-entry budget and a five-second budget
per root. Regular scans allot at most 20 seconds of remaining budget to this
walk. Discovery and native probes have their own bounded operations; this is a
soft time budget, not a guaranteed wall-clock cutoff for filesystem calls.
Exclusions skip matching roots/subtrees, but never remove their protection.
Shared inode capacity is deduplicated in the unique total; root/category rows
can overlap and must not be summed. APFS clones are not block-deduplicated.

Protection covers registered defaults and environment overrides, discovered
project resources, extension identities, shared-link sources and selected declared
local resource paths. It is checked during discovery and planning and refreshed
for recorded projects before mutation, including after occupancy probes. Known
Agent extension packages stay protected unless an exact obsolete program package
has positive newer-registration evidence, no known persistent state, and passes
the separately reviewed rule in cleanup-coverage.md. User `agent_roots`
may only add protection, not enable deletion or executable plugins. Invalid/broad
explicit roots fail closed. Unsupported or malformed native configuration is
reported as incomplete; it does not establish a complete reference graph.

See [agent-adapters.md](agent-adapters.md) for exact scope, evidence and limits.

## Safety and lifecycle

Since 0.2.4, `cleanup_summary` partitions known candidates into `ready_caches`,
`quit_app`, `separate_review`, `protected` and `unverified`. Each bucket reports
measured bytes, unknown-size and lower-bound counts, owners and a next action.
Buckets are exclusive; totals include retained data and are not savings. Human
output uses decimal KB/MB/GB and shows representative candidates for long lists;
the complete JSON stays available. A readable metadata-only usage observation
can report foreign-owned/incomplete capacity without making it eligible for plans.

New exact user-cache families include map tiles, Apple Media/Python/parsecd,
media-analysis temporary files, Xcode Interface Builder, Android SDK metadata,
Homebrew downloads/API, Cargo crate downloads, Ruby specs/Bundler indexes and
PyInstaller binary caches. Installed environments, models, SDK/AVD, Cargo sources,
archives, unfinished downloads and locks stay separate/protected. Unknown app
cache names are inventory-only until ownership is resolved. See
[cleanup coverage](cleanup-coverage.md) for paths and limits.

`scan --native-preview` requests `brew cleanup --dry-run` from a trusted installed
Homebrew location. It disables automatic updates/analytics and reports owner
estimates separately as `native_cleanup_previews`. It never executes native
cleanup, creates a native-mutation plan, or adds those estimates to Trash totals.

The JSON scan is not execution authority. Planning recomputes rules/evidence and
rejects stale or fabricated candidates. Plans/receipts are signed with a local
private key under `~/.local/state/mac-dev-cleanup` (0700 directories, 0600 files).
The key protects against accidental document edits, not a hostile same-UID user.
Plans are single-attempt; make a fresh plan to revisit skips. One operation runs
at a time. Mutation requires macOS 14+, a non-root process, complete activity and
file-occupancy evidence, and stable filesystem identities and metadata.

Since 0.2.2, macOS may use a narrowly scoped current-user occupancy check for
reviewed, regenerable user caches when PID 1 is not visible. A private open-file
canary must be observable, and the current-user process census must be covered
by lsof records with file descriptors. Target occupancy is then checked without
a UID filter so any visible holder blocks the move. Warnings, missing processes,
timeouts and malformed output remain unknown. The receipt records the observation
scope; it does not certify other users' processes or future activity. Other rules
retain the original root-visibility requirement. See
[occupancy evidence](occupancy-checks.md) for details and limits.

Only same-volume Trash moves are supported. The existing Trash must be private
or an absent Trash is created as 0700. A redirected, inaccessible or unsafe Trash
is a refusal, never a reason to permanently delete. Target and parent identities,
tree metadata fingerprints, Git tracking, exclusions, active processes and
relevant editor/update state are rechecked. Codex cleanup holds install.lock.
No whole shared root, sudo, chmod repair, daemon shutdown or automatic Trash empty.

Each move has a durable intent with its unique destination before it starts.
After interruption, inspect history: `moving` or `recovery_required` entries can
be restored if the recorded payload is intact. Recovery requires a second user
confirmation, a stable original parent and an absent destination. A move timeout
or signal stops later candidates and retains the write-ahead receipt even if
the final move outcome is uncertain. If a restore
itself is interrupted, inspect both recorded locations before retrying; it never
replaces a recreated file. Missing/modified content is reported, not reconstructed.

Allocated size deduplicates hard links inside each candidate. APFS clones and
links shared between candidates may still share blocks; sizes are estimates.
The receipt's `moved_allocated_bytes` and `free_space_delta_bytes` have different
meanings. Trash moves normally free no space; background system activity affects
the latter. Clearing Trash later is the user's separate action.

Exit 0 means the command produced its result, including partial discovery or
per-item skips. Read `scan_status`, `issues`, and receipt entry statuses. Exit 2
means refused/invalid input; after any interrupted mutation consult receipts.

## Packaging and comparison

`python3 scripts/build_release.py` builds a self-contained skill archive and
SHA-256 file in `dist/`. It excludes personal configuration and upstream images.
The installed skill does not need this source checkout or a separate Mole.

`python3 scripts/compare_baseline.py --scan scan.json --mole-list clean-list.txt`
compares path coverage to an already-generated Mole preview. It does not invoke
Mole or infer a winner from differing scopes. Inspect unmatched paths and partial
status rather than advertising the sum as extra recoverable space.
