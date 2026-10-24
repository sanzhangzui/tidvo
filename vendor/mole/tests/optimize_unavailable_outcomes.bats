#!/usr/bin/env bats

load helpers/common

setup_file() {
	mole_test_setup_project_root

	TEST_HOME="$(mktemp -d "${BATS_TEST_DIRNAME}/tmp-optimize-unavailable.XXXXXX")"
	export TEST_HOME
}

teardown_file() {
	if [[ "$TEST_HOME" == "${BATS_TEST_DIRNAME}/tmp-optimize-unavailable."* ]]; then
		rm -rf "$TEST_HOME" # SAFE: Only this file's private test HOME is removed.
	fi
}

# A directory the caller cannot read (chmod 000, or a privacy-protected path
# without Full Disk Access) is out of reach, not a failed scan. GNU/BSD find
# exits 1 with a permission error; that must not publish a task failure.
@test "shared file list scan reports unavailable when the directory is unreadable" {
	# run_with_timeout execs a binary, so the mock must be a PATH command,
	# not a shell function the child bash would never see.
	# shellcheck disable=SC2016  # $1 expands when the generated stub runs, not here.
	mole_test_fake_command find 'printf "find: %s: Operation not permitted\n" "$1" >&2; exit 1'

	run env HOME="$TEST_HOME/shared-list-unreadable" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"

mkdir -p "$HOME/Library/Application Support/com.apple.sharedfilelist"

execute_optimization shared_file_list_repair
[[ "$(optimize_outcome_count failed)" == "0" ]] || exit 1
[[ "$(optimize_outcome_count unavailable)" == "1" ]] || exit 1
EOF

	[[ "$status" -eq 0 ]] || { echo "$output"; return 1; }
	[[ "$output" == *"Shared file lists not readable (check directory permissions and Full Disk Access)"* ]] || return 1
	[[ "$output" != *"Failed to scan shared file lists"* ]] || return 1
}

# A time ceiling is a capability limit, not a failed operation: the audit
# published no conclusions, so it must not badge the run as failed.
@test "login items audit reports unavailable when a probe times out" {
	run env HOME="$TEST_HOME/login-probe-timeout" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"

# The scripted test run sets this to skip the audit entirely; this test is
# exercising the audit, so it must not leak in.
unset MOLE_TEST_NO_AUTH

_login_items_snapshot() { printf 'Stale Entry\tmissing value\n'; }
_login_item_build_app_inventory() { : > "$1"; return 0; }
_login_item_app_exists() { return 124; }

execute_optimization login_items_audit
[[ "$(optimize_outcome_count failed)" == "0" ]] || exit 1
[[ "$(optimize_outcome_count unavailable)" == "1" ]] || exit 1
EOF

	[[ "$status" -eq 0 ]] || { echo "$output"; return 1; }
	[[ "$output" == *"time limit reached"* ]] || return 1
}

@test "login items audit reports unavailable when the snapshot times out" {
	run env HOME="$TEST_HOME/login-snapshot-timeout" PROJECT_ROOT="$PROJECT_ROOT" \
		MOLE_TIMEOUT_HINT_SCAN_SEC=0 /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"

unset MOLE_TEST_NO_AUTH

# A zero audit budget expires the deadline before the snapshot can run.
execute_optimization login_items_audit
[[ "$(optimize_outcome_count failed)" == "0" ]] || exit 1
[[ "$(optimize_outcome_count unavailable)" == "1" ]] || exit 1
EOF

	[[ "$status" -eq 0 ]] || { echo "$output"; return 1; }
	[[ "$output" == *"Login items unavailable (snapshot timed out)"* ]] || return 1
	[[ "$output" != *"Failed to inspect login items"* ]] || return 1
}

@test "shared file list scan keeps mixed errors and classifier failures failed" {
	for scenario in mixed classifier blank; do
		run env HOME="$TEST_HOME/shared-$scenario" SCENARIO="$scenario" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'SH'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
mkdir -p "$HOME/Library/Application Support/com.apple.sharedfilelist"
candidate="$HOME/Library/Application Support/com.apple.sharedfilelist/fixture.sfl3"
printf 'corrupt fixture\n' > "$candidate"
plutil() { return 1; }
run_with_timeout() {
    printf '%s\0' "$candidate"
    if [[ "$SCENARIO" == blank ]]; then
        printf '\n' >&2
    else
        printf 'find: fixture: Permission denied\n' >&2
        [[ "$SCENARIO" != mixed ]] || printf 'find: fixture: Input/output error\n' >&2
    fi
    return 1
}
if [[ "$SCENARIO" == classifier ]]; then
    grep() { printf 'classifier-called\n' >> "$HOME/trace"; return 2; }
fi
safe_remove() { printf '%s\n' "$1" >> "$HOME/removal.trace"; }
execute_optimization shared_file_list_repair
[[ "$(optimize_outcome_count failed)" == 1 ]] || exit 1
[[ "$(optimize_outcome_count unavailable)" == 0 ]] || exit 1
[[ ! -e "$HOME/removal.trace" ]] || exit 1
if [[ "$SCENARIO" == classifier ]]; then
    [[ -s "$HOME/trace" ]] || exit 1
fi
# The same eligible corrupt file reaches the mocked sink after a complete scan.
optimize_outcomes_reset
run_with_timeout() { printf '%s\0' "$candidate"; }
execute_optimization shared_file_list_repair
[[ "$(cat "$HOME/removal.trace")" == "$candidate" ]] || exit 1
[[ "$(optimize_outcome_count applied)" == 1 ]] || exit 1
SH
		[[ "$status" -eq 0 ]] || { echo "$scenario: $output"; return 1; }
		[[ "$output" == *"Failed to scan shared file lists"* ]] || return 1
	done
}

@test "login items audit reports unavailable when app inventory times out" {
	run env HOME="$TEST_HOME/login-inventory-timeout" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'SH'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
unset MOLE_TEST_NO_AUTH
_login_items_snapshot() { printf 'Stale Entry\tmissing value\n'; }
_login_item_build_app_inventory() { return 124; }
_login_item_app_exists() { printf 'owner probe\n' >> "$HOME/probes"; return 0; }
execute_optimization login_items_audit
[[ "$(optimize_outcome_count failed)" == 0 ]] || exit 1
[[ "$(optimize_outcome_count unavailable)" == 1 ]] || exit 1
[[ ! -e "$HOME/probes" ]] || exit 1
optimize_outcomes_reset
_login_item_build_app_inventory() { : > "$1"; }
execute_optimization login_items_audit
[[ "$(cat "$HOME/probes")" == 'owner probe' ]] || exit 1
SH
	[[ "$status" -eq 0 ]] || { echo "$output"; return 1; }
	[[ "$output" == *"app inventory timed out"* ]] || return 1
}

@test "login items audit propagates signals from every inspection stage" {
	for stage in snapshot inventory probe; do
		run env HOME="$TEST_HOME/login-signal-$stage" STAGE="$stage" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'SH'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
unset MOLE_TEST_NO_AUTH
_login_items_snapshot() {
    [[ "$STAGE" != snapshot ]] || return 130
    printf 'Stale Entry\tmissing value\nNext Entry\tmissing value\n'
}
_login_item_build_app_inventory() {
    [[ "$STAGE" != inventory ]] || return 130
    :
}
_login_item_app_exists() {
    printf '%s\n' "$1" >> "$HOME/probes"
    [[ "$1" != 'Stale Entry' ]] || return 130
    return 0
}
mkdir -p "$HOME"
optimize_task_start
rc=0
opt_login_items_audit || rc=$?
[[ "$rc" -eq 130 ]] || exit 1
[[ "$MOLE_OPTIMIZE_TASK_OUTCOME" == failed ]] || exit 1
if [[ "$STAGE" == probe ]]; then
    [[ "$(cat "$HOME/probes")" == 'Stale Entry' ]] || exit 1
else
    [[ ! -e "$HOME/probes" ]] || exit 1
fi
SH
		[[ "$status" -eq 0 ]] || { echo "$stage: $output"; return 1; }
		[[ "$output" == *"interrupted"* ]] || return 1
	done
}
