---
paths:
  - "mole"
  - "mo"
  - "install.sh"
  - "bin/*.sh"
  - "lib/**/*.sh"
  - "scripts/*.sh"
  - "scripts/audit_function_duplication.py"
  - "tests/*.bats"
  - "tests/helpers/*.bash"
---

# Shell portability and code hygiene

- **BSD-only flags never resolve through PATH.** Homebrew coreutils, findutils, grep, sed or gawk often sit first in PATH. GNU `stat -f` prints a file-system `File:` block on stdout while failing, so `$(stat -f %m x || echo 0)` captures text: under `set -u` that aborted `mo clean` (#1752), and elsewhere it silently misread mtimes (#1196 fixed one site).
  - Call `"$STAT_BSD"` for every stat (including `find -exec`, `run_with_timeout`, `sudo -n` and a command continued onto the next line) and `"$_DATE_CMD"` for `date -r` / `-j` / `-v`.
  - Write depth limits as `-mindepth N -maxdepth N`, never BSD `-depth N`, which GNU find reads as a path.
  - A scan that depends on BSD find's error format or on how it passes File Provider mounts calls `"$FIND_BSD"` (the uninstall same-bundle scan, project-cache roots, hint child listings) or `$_MOLE_PURGE_FIND` (purge's `-flags +dataless` probe and walks); GNU find quotes paths in its errors and failed on an OPPO cloud mount, which skipped the whole CloudStorage root.
  - A locale-aware case fold uses `/usr/bin/tr`, because GNU tr folds byte by byte and `mo uninstall écrivain` stopped finding `Écrivain`; an `LC_ALL=C tr` is ASCII on both.
  - Escape ERE input with `_mole_regex_escape`, which escapes only metacharacters, since `\-` is undefined and GNU grep warns on it.
  - `mo analyze` runs `/usr/bin/du` (`duBinary`) because GNU du has no `-I`.
  - `sysctl` lives in `/usr/sbin`, which a shell PATH (a Python or conda environment, a hand-written profile) may leave out; the lookup then fails and every caller silently takes its fallback, which refused `mo slim` on Apple Silicon and read total memory as 0 (#1804). Shell code calls `"$SYSCTL_CMD"` (assigned in `lib/core/base.sh`, rebindable like `STAT_BSD`; a test that stubs a `sysctl` function sets `SYSCTL_CMD=sysctl`), `bin/slim.sh` the literal `/usr/sbin/sysctl`, and Go `runCmd` the absolute path. Locked by `sysctl never resolves through PATH (#1804)` in `tests/core_common.bats` and `get_memory_info reads total memory without /usr/sbin in PATH (#1804)` in `tests/health_json.bats`.
  - The other `/usr/sbin` and `/sbin` tools Mole runs by name (`diskutil`, `lsof`, `pkgutil`, `ioreg`, `scutil`, `spctl`, `pmset`, `mdutil`) are found because `lib/core/base.sh` appends both folders to PATH when they are missing, after the user's own entries so a test stub or user override earlier in PATH still wins; the Go TUIs inherit it through the router. Before that, a missing `diskutil` read as an empty answer and skipped the internal-volume refusal of `mo clean --external`. Locked by `loading Mole appends /usr/sbin and /sbin to a PATH without them` in `tests/core_common.bats`.
  - `STAT_BSD` and `FIND_BSD` are assigned on every load and are not readonly so a test can point them at a stub after sourcing (`STAT_BSD=stat`, `FIND_BSD=find`; `useDuStub` in Go).
  - Locked by `BSD-only stat, date, find and tr forms never resolve through PATH (#1196, #1752)` in `tests/core_common.bats`, which joins continued lines before matching, plus `GNU stat earlier in PATH does not break stale profile cleanup (#1752)`, `purge keeps the dataless prune with GNU find first in PATH`, `clean_service_worker_cache finds depth-two entries with GNU find first in PATH`, `project cache and hint scans ignore a failing find earlier in PATH`, `same-bundle scan names the unreadable path verbatim with GNU find first in PATH`, `match_apps_by_name folds non-ASCII case with a byte-only tr first in PATH`, `_mole_regex_escape matches names literally without undefined ERE escapes` and `TestDuIgnoresUseSystemDuWhenGNUDuIsFirstInPath`.
  - To recheck the whole surface, install `coreutils findutils gnu-sed grep gawk` (each keeps its GNU names in a gnubin directory, off the default PATH) and run `scripts/test.sh` and `go test ./...` with those gnubins prepended; test code pins its own BSD forms too, so that run is expected to be green.
- `run_with_timeout` keeps an early SIGKILL as 137, including fractional budgets. The native timeout backend may translate 137 to timeout only after its deadline plus the `-k` grace period; integer `SECONDS` must not round a sub-second deadline down to immediate expiry. Locked by the fractional-deadline cases in `tests/core_timeout.bats`.
- **Judge duplication by body and purpose, not by name.** `scripts/audit_function_duplication.py` hashes normalized bodies and gates new same-body groups, including renamed copies a grep sweep misses. It cannot find two differently written helpers that duplicate one decision, so pair the audit with a caller-and-purpose sweep. Treat generated counts as command output, not durable prose in a rule file.
- **Test-orphan pattern:** before declaring a symbol dead, grep `lib`, `bin`, `cmd`, `scripts`, `tests`, and top-level entry/install scripts; check dynamic lookup through `eval`, `declare -f`, and `compgen`; then re-grep after removal. Trace variables and config written by a removed helper. Tests alone are not production callers, and sub-agent reports are leads, not verdicts.
