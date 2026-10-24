# Tidvo validation evidence — 0.2.0 beta

Local evidence recorded on 2026-10-23. Publication and GitHub CI results are
separate from these local checks. This is not a claim of fewer false positives
or more reclaimed GB across real users.

## Environment and checks

- Local host: macOS 26.4.1, Apple Silicon arm64.
- Product suite: `python3 -m unittest discover -s tests -v`; Python 3.14.2 and
  Python 3.11.12: **143 tests passed on each interpreter**. Fixtures cover scan/plan/apply/restore, Git changes, configured
  references, update locks, invalid plans, partial evidence, path replacement,
  interrupted moves, Trash failure, restore conflicts and packaging. A reference
  probe becoming incomplete after plan creation also prevents the npx move;
  this regression was reproduced before fixing the apply-stage check.
- Version 0.1.1 adds fixture checks that idle/untracked project dependencies and
  virtual environments stay report-only, cannot enter a plan, and are refused
  again at apply time. Terminal summaries preserve JSON report files, show the
  next-step commands and escape terminal controls in untrusted filenames.
- The pinned Mole Bash bridge moves only a synthetic fixture in its integration
  test. Real user directories are not used for destructive validation.
- Version 0.1.2 adds coverage for the known VS Code logs/compiled/Webview layouts,
  Dia resource/component/site caches, all six Feishu/Lark account layouts,
  npm prebuild archives and nested project discovery. Fixtures verify active-app
  and npm guards, origin/index changes, unknown layouts/origins, preserved user
  data, exclusions, dependency pruning, directory/depth budgets and redirected or
  nonregular metadata. Seven new path families also complete actual pinned Bash
  Trash moves and conflict-safe restores in a synthetic Home.
- Version 0.2.0 adds 42 Agent fixture checks: catalog capability/evidence scope;
  protection for every registered root and project marker; credentials, history,
  memory, SQLite/WAL/SHM/journal preservation; no persistent-body reads; custom
  roots and environment overrides; unknown markers/extensions; shared-link
  canonical targets and capacity deduplication; external/permission/budget gaps;
  Pi packages, MCP references and declared resource paths; Claude custom memory;
  read-only CLI/output permissions; metadata-only app versions; and protection
  changes after planning, including another project's new reference or a change
  during occupancy checks. Explicit roots/shared resources override the narrow
  worktree-cache exception. The pre-existing 100 tests still pass.
- Bash syntax and skill frontmatter validation pass. The self-contained 0.2.0
  archive includes the catalog, protection code, Agent tests and coverage guide;
  the extracted package also passes the full 143-test suite. No personal scan
  report, user configuration or upstream skill entry point is packaged.
- The Tidvo rename adds a fixture verifying that both the new and legacy Python
  entry points read the same existing signed history without migrating state.
  The skill, archive and primary command use Tidvo; backend/config/state names
  remain compatible. Vendored source is unchanged by the rename.
- Fixture processes isolate HOME and inherited Agent/XDG directory overrides.
  The first Ubuntu CI attempt exposed host overrides leaking into simulated
  homes and correctly triggering the production protection guard. Fixture
  isolation was fixed; production still refuses overrides outside scoped Home.
  The full local suite also passes with deliberately injected host overrides.
- The one-message installation guide was checked against the published beta.1
  assets in a temporary Home: checksum, safe extraction, a shared Skills symlink,
  version/catalog entry points, existing-install refusal and absence of cleanup
  state all passed. Documentation changes do not replace published beta assets.
- Unchanged pinned backend: the prior required core regression passed 289 cases for
  `file_ops_mole_delete`, `file_ops_size`, `file_ops_safe_remove_symlink`,
  `user_file_ops`, `core_safe_functions`, and `history`.
- A prior 135-case run including `path_validation_fuzz` also passed. These runs
  overlap; do not sum them as distinct test cases.
- The sandbox causes one upstream process-visibility-dependent case to refuse;
  the unmodified pinned source reproduces that failure inside the sandbox.
  Outside it, the case and required core regression pass. No guard was weakened.
- Shell formatting, ShellCheck and syntax checks apply to changed Bash code;
  shfmt 3.10.0, ShellCheck 0.11.0 and upstream `scripts/check.sh --no-format`
  passed, including destructive-sink, duplication, timeout and test-assertion
  audits. Go tooling is unavailable and Windows branch metadata is absent, so
  those unrelated upstream checks were skipped. Go components are not changed,
  built, or used by this product interface. An initial check with the older
  ShellCheck 0.10.0 reported diagnostics in unchanged upstream files; 0.11.0
  validates the current pinned source without changing those files.
- Skill frontmatter validation is separate from deletion safety tests.

## Reproducible scoped comparison

Run `python3 tests/benchmark_fixture.py` on macOS. It creates a temporary Home
with JavaScript, Python and Rust project outputs plus two npx installs, one of
which a fixture MCP configuration references. It calls the pinned upstream
project discovery helper and npm dry-run module, not the full cleanup command.

Observed result: both discover the same seven paths. The product retains project
node_modules and virtual environments by default, and marks the configured MCP
installation report-only while distinguishing it from the unreferenced tool.
The project fixture's metadata fingerprint is unchanged after comparison.
The product uses a modeled idle process probe here: this compares discovery and
configuration evidence, not occupancy, real deletion eligibility or speed.

There is no measured additional-capacity advantage in this fixture. The product
does not turn path differences, Trash capacity or unrelated df changes into a
“cleans more GB” claim. Use `scripts/compare_baseline.py` with separately collected
real preview artifacts to inspect additional scenarios without executing cleanup.

## Release limits

- macOS 14/15 and Intel have not been locally validated. CI is configured, not
  executed merely because the workflow file exists. Keep the package beta until
  results from those combinations are available.
- Complete root-process visibility can be unavailable without broader macOS
  access. The product retains those candidates; it never invokes sudo to work
  around uncertainty.
- Known configuration adapters are not a complete reference graph; unknown
  applications and uncertain browser runtimes remain report-only.
- The 38-entry Agent catalog is detection/protection coverage, not certification
  of 38 installed products or every version/layout. Only core defaults for seven
  entries were checked against primary layout references; other entries use
  conservative hints. Unknown discovery is bounded and heuristic; unmarked,
  containerized, out-of-Home, remote and cloud-only state may be missed. Native
  JSONC/JSON5/YAML parsing is not implemented; those gaps stay explicit.
- Agent inventory never grants cleanup authority. It does not certify runtime
  health, account security, or completion of background/remote tasks. Capacity is
  metadata-based, with inode deduplication and partial lower bounds, not a claim
  of reclaimable storage. Installed-version/real-user Agent compatibility testing
  remains future work; all new checks use synthetic data or fixed app metadata.
- Snapshot limits and timeouts can make large trees unavailable. This is
  surfaced, never converted into zero size or permission to move partial data.
- Metadata fingerprints detect ordinary concurrent changes, not a hostile
  process with the same user privileges. State signatures are an integrity aid,
  not an authorization boundary against the account owner.
- Validation performs no background monitoring, permanent cleanup, automatic
  Trash empty, real-user cleanup, or existing personal-skill replacement.
  Source/release publication is a separate authorized maintainer action.
