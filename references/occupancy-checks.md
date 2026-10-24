# Occupancy evidence and macOS compatibility

Tidvo 0.2.2 retains three results: `idle`, `active` and `unknown`. Only `idle`
within a permitted observation scope can proceed. Process evidence, configuration
references, source/parent identities, tree fingerprints, ownership, sensitive
files and Trash requirements are independent guards; none is overridden here.

## Why PID 1 cannot be the only prerequisite

On the reported Mac, unprivileged `lsof -p 1` returned no records. A separate
temporary-file probe could observe current-user processes and open files.
The old prerequisite therefore rejected ordinary cache work before checking
its actual target. This observation does not identify or change a macOS security
setting. Tidvo never invokes sudo or changes permissions to obtain visibility.

## Narrow current-user cache mode

Only the fixed `USER_CACHE_RULES` set in `macdev/occupancy.py` is eligible:
browser resources/component downloads, editor installer/compiled caches, known
application page caches, npm prebuild downloads and Python bytecode/test/tool
caches. The engine must already have validated the candidate against its rule
and verified its owned tree. The target must be a regular invoking-user-owned
file/directory inside Home, without path redirection or a shared-root boundary.

When the root probe is unavailable on macOS:

1. Hold a private temporary file open and require lsof to report this process,
   its UID and that exact canonical filename. Close/remove this canary normally.
2. Observe invoking-user lsof PID/UID/descriptor records and compare them with
   a subsequent process census. Every live current-user process in that census
   must be represented; only the census subprocess itself and zombies are exempt.
   Missing or malformed records, warnings and failed calls return `unknown`.
3. Check the target using unfiltered lsof. Any visible process holding it makes
   it active, even if lsof exits nonzero with positive records. Only exit 1 with
   no records and no diagnostics is an idle observation.

Logs, installed tools, rollback versions, build/delivery outputs, offline site
stores, databases and unspecified rules do not receive this mode. Non-macOS and
root callers cannot use it. The original stricter probe remains for other rules.

## Receipts and limits

Apply entries and restore results record `occupancy`: status, scope and reason.
Current-user mode explicitly sets `other_users_certified=false`. It is a bounded
observation for regenerable user caches, not proof of globally invisible processes
being absent. New/invisible user processes, permission loss, tool failures and
timeouts cause retention. Like other instantaneous checks, it cannot rule out
future activity; metadata and owning-app checks still apply immediately before
the move. No file bodies or command arguments are exported as occupancy evidence.

Validation uses temporary homes and held-open fixture files. The native test
forces the PID 1 probe unavailable, verifies open-file refusal, then exercises
the pinned Trash backend and conflict-safe restore after closing the file.
It does not clean real user data to validate the change.

Primary references: [lsof options](https://lsof.readthedocs.io/en/latest/options/)
and [lsof manual](https://github.com/lsof-org/lsof/blob/master/Lsof.8).
Tests cover selection/evidence behavior rather than assuming an empty result is
reliable merely because one system process or one user PID is visible.
