#!/usr/bin/env bats

load helpers/common

setup() {
    mole_test_setup_project_root
    SANDBOX=$(mktemp -d "${BATS_TEST_DIRNAME}/tmp-ime-timeout.XXXXXX")
    export SANDBOX
    export HOME="$SANDBOX/home"
    export MOLE_TEST_NO_AUTH=1 MOLE_TEST_MODE=1 MOLE_DELETE_MODE=trash
    export MOLE_TEST_TRASH_DIR="$SANDBOX/Trash"
    export MOLE_DELETE_LOG="$SANDBOX/deletions.log"
    mkdir -p "$HOME"
}

teardown() {
    rm -rf "$SANDBOX" # SAFE: exact mktemp-created fixture, never the real input method
}

check_stalled_input_method_removal() {
    local backend="$1"
    run env TIMEOUT_BACKEND="$backend" /bin/bash --noprofile --norc << 'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/bin/uninstall.sh"
source "$PROJECT_ROOT/tests/helpers/uninstall.bash"
mole_test_isolate_uninstall_inventory
if [[ "$TIMEOUT_BACKEND" == perl ]]; then
    MO_TIMEOUT_BIN=""
    MO_TIMEOUT_PERL_BIN=/usr/bin/perl
fi
export MOLE_CURRENT_COMMAND=uninstall
log_operation_session_start uninstall
first="$HOME/Library/Application Support/app.msime.macos"
stalled="$HOME/Library/HTTPStorages/app.msime.inputmethod.MetasequoiaIME"
app="$HOME/Library/Input Methods/水杉输入法.app"
mkdir -p "$first" "$stalled" "$app" "$MOLE_TEST_TRASH_DIR"
# Model the observed partial Trash move, then a helper ignoring TERM. Only
# the platform Trash helper is replaced; timeout, cancellation propagation,
# completed-path accounting, and the command's EXIT cleanup stay real.
validate_path_for_deletion() { return 0; }
_mole_move_to_trash_batch() {
    printf '%s\n' "$@" > "$SANDBOX/batch-inputs"
    mv "$1" "$MOLE_TEST_TRASH_DIR/completed"
    _MOLE_TRASH_BATCH_MOVED_PATHS=("$1")
    local rc=0
    run_with_timeout 1 /usr/bin/perl -e '
        $SIG{TERM} = "IGNORE";
        open my $ready, ">", "$ENV{SANDBOX}/helper-started" or die $!;
        close $ready;
        sleep 10;
    ' || rc=$?
    return "$rc"
}
mole_delete() { printf 'unexpected fallback\n' > "$SANDBOX/fallback"; return 99; }
rc=0
remove_file_list "$first"$'\n'"$stalled"$'\n'"$app" false || rc=$?
printf '%s\n' "$rc" > "$SANDBOX/status"
exit "$rc"
SCRIPT
    local timeout_rc="$status"
    # Use the shared status predicate rather than duplicating its reason code.
    source "$PROJECT_ROOT/lib/core/timeout.sh"
    mole_rc_timeout "$timeout_rc" || {
        echo "$output"
        return 1
    }
    [ -f "$SANDBOX/helper-started" ] || return 1
    [ -d "$MOLE_TEST_TRASH_DIR/completed" ] || return 1
    [ -d "$HOME/Library/HTTPStorages/app.msime.inputmethod.MetasequoiaIME" ] || return 1
    [ -d "$HOME/Library/Input Methods/水杉输入法.app" ] || return 1
    [ ! -e "$SANDBOX/fallback" ] || return 1
    grep -Fxq "$HOME/Library/HTTPStorages/app.msime.inputmethod.MetasequoiaIME" "$SANDBOX/batch-inputs" || return 1
    grep -Fq "$HOME/Library/Application Support/app.msime.macos" "$MOLE_DELETE_LOG" || return 1
    local log="$HOME/Library/Logs/mole/operations.log"
    grep -q 'uninstall .*session started' "$log" || return 1
    grep -q 'uninstall .*session ended' "$log"
}

# Keep the production batch, direct mover and timeout wrapper. Only the
# external mv executable and the live-owner probes are fixture seams.
check_direct_trash_deadline() {
    run env TIMEOUT_BACKEND="$1" MOLE_TIMEOUT_DISK_VERIFY_SEC=1 /bin/bash --noprofile --norc <<'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/bin/uninstall.sh"
source "$PROJECT_ROOT/tests/helpers/uninstall.bash"
mole_test_isolate_uninstall_inventory
if [[ "$TIMEOUT_BACKEND" == perl ]]; then
    MO_TIMEOUT_BIN=""
    MO_TIMEOUT_PERL_BIN=/usr/bin/perl
fi
mkdir -p "$HOME/.Trash" "$SANDBOX/bin" "$HOME/first" "$HOME/stalled" "$HOME/later"
chmod 700 "$HOME/.Trash"
cat > "$SANDBOX/bin/mv" <<'MOCK'
#!/bin/bash
[[ "$1" == -n && "$2" == "$HOME/"* && "$3" == "$HOME/.Trash/"* ]] || exit 97
printf '%s\n' "$2" >> "$SANDBOX/direct-moves"
if [[ "$2" == "$HOME/stalled" ]]; then
    /usr/bin/perl -e '$SIG{TERM} = "IGNORE"; sleep 5;'
fi
exec /bin/mv "$@"
MOCK
chmod +x "$SANDBOX/bin/mv"
export PATH="$SANDBOX/bin:$PATH"
# All targets, destination and executable are owned by this fixture. Never
# let the test-only shortcut bypass the real direct mover being exercised.
unset MOLE_TEST_NO_AUTH MOLE_TEST_MODE MOLE_TEST_TRASH_DIR
export MOLE_CURRENT_COMMAND=uninstall MOLE_DELETE_MODE=trash
validate_path_for_deletion() { [[ "$1" == "$HOME/"* ]]; }
_mole_trash_target_still_safe() { [[ "$1" == "$HOME/"* ]]; }
_mole_owned_path_still_valid() { [[ "$1" == "$HOME/"* ]]; }
rc=0
remove_file_list "$HOME/first"$'\n'"$HOME/stalled"$'\n'"$HOME/later" false || rc=$?
printf 'MOVE_STATUS=%s\n' "$rc"
grep -Fxq "$HOME/stalled" "$SANDBOX/direct-moves" || exit 1
mole_rc_timeout "$rc" || exit 1
[[ -d "$HOME/.Trash/first" && -d "$HOME/stalled" && -d "$HOME/later" ]] || exit 1
[[ ${#_MOLE_TRASH_BATCH_MOVED_PATHS[@]} -eq 1 && "${_MOLE_TRASH_BATCH_MOVED_PATHS[0]}" == "$HOME/first" ]] || exit 1
! grep -Fxq "$HOME/later" "$SANDBOX/direct-moves" || exit 1
grep -Fq "$HOME/first" "$MOLE_DELETE_LOG" || exit 1
printf 'bounded-direct-move completed-ledger later-preserved\n'
SCRIPT
    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    [[ "$output" == *bounded-direct-move* ]]
}

@test "input-method uninstall returns after a TERM-resistant Trash helper with coreutils (#1787)" {
    if ! command -v gtimeout > /dev/null 2>&1 && ! command -v timeout > /dev/null 2>&1; then
        skip "coreutils timeout not available"
    fi
    local started=$SECONDS
    check_stalled_input_method_removal coreutils || return 1
    [ "$((SECONDS - started))" -lt 7 ]
}

@test "input-method uninstall returns after a TERM-resistant Trash helper with Perl (#1787)" {
    [ -x /usr/bin/perl ] || skip "macOS Perl required"
    local started=$SECONDS
    check_stalled_input_method_removal perl || return 1
    [ "$((SECONDS - started))" -lt 7 ]
}

@test "real direct Trash sink times out and preserves the completed ledger with coreutils" {
    if ! command -v gtimeout > /dev/null 2>&1 && ! command -v timeout > /dev/null 2>&1; then
        skip "coreutils timeout not available"
    fi
    check_direct_trash_deadline coreutils
}

@test "real direct Trash sink times out and preserves the completed ledger with Perl" {
    [ -x /usr/bin/perl ] || skip "macOS Perl required"
    check_direct_trash_deadline perl
}
