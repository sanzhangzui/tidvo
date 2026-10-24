#!/usr/bin/env bats

load helpers/common

# Tests for get_path_size_kb in lib/core/file_ops.sh.
# Exercises the allocated-block stat fast-path for regular files / symlinks
# and the du fallback for directories, plus error and edge cases. Values are
# compared with `du -skP` so every path type keeps one physical disk-occupancy
# basis.

setup_file() {
    mole_test_setup_project_root
}

setup() {
    SANDBOX="$(mktemp -d "${BATS_TEST_DIRNAME}/tmp-fileops-size.XXXXXX")"
    export SANDBOX
    export MOLE_TEST_NO_AUTH=1
}

teardown() {
    rm -rf "$SANDBOX"
}

prelude() {
    cat << EOF
set -euo pipefail
export MOLE_TEST_NO_AUTH=1
source "$PROJECT_ROOT/lib/core/common.sh"
EOF
}

@test "clone preview keeps unknown bytes through both removal routes (#1698)" {
    mkdir -p "$SANDBOX/clone" "$SANDBOX/ordinary"
    for mutable in yes no; do
        run env PROJECT_ROOT="$PROJECT_ROOT" HOME="$SANDBOX" MUTABLE="$mutable" \
            MOLE_DRY_RUN=1 MO_DEBUG=1 /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
validate_path_for_deletion() { return 0; }
is_path_whitelisted() { return 1; }
holds_compiled_model_cache() { return 1; }
_mole_privileged_path_has_mutable_ancestor() { [[ "$MUTABLE" == yes ]]; }
get_path_size_kb() { echo UNEXPECTED_SIZE_PROBE >&2; echo 999999; }
record_dry_run_cleanup_target() {
    printf 'RECORD:%s:%s:%s\n' "${1##*/}" "$2" "$4"
    printf 'PREVALIDATED:%s:%s\n' "${1##*/}" "${_MOLE_DRY_RUN_TARGET_PREVALIDATED:-}"
}
safe_sudo_remove "$HOME/clone" unknown
safe_sudo_remove "$HOME/ordinary" 42
EOF
        [ "$status" -eq 0 ] || { echo "$output"; return 1; }
        [[ "$output" == *"RECORD:clone:0:false"* ]] || return 1
        [[ "$output" == *"RECORD:ordinary:42:true"* ]] || return 1
        [[ "$output" == *"PREVALIDATED:clone:false"* ]] || return 1
        [[ "$output" != *"UNEXPECTED_SIZE_PROBE"* ]] || return 1
        [[ "$output" != *"976.56MB"* ]] || return 1
    done
}

@test "unknown clone preview renders a partial total beside measured bytes (#1698)" {
    mkdir -p "$SANDBOX/clone" "$SANDBOX/ordinary"
    run env PROJECT_ROOT="$PROJECT_ROOT" HOME="$SANDBOX" MOLE_DRY_RUN=1 \
        /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/bin/clean.sh"
DRY_RUN=true
CLEAN_PREVIEW_FINAL_FILE="$HOME/preview.txt"
prepare_clean_preview_file
CURRENT_SECTION=System
get_path_size_kb() { echo 999999; }
_record_file_ops_dry_run_target "$HOME/clone" unknown
_record_file_ops_dry_run_target "$HOME/ordinary" 42
render_clean_preview_from_ledger
printf 'PARTIAL=%s TOTAL=%s ITEMS=%s\n' "$DRY_RUN_TOTAL_PARTIAL" "$total_size_cleaned" "$files_cleaned"
cat "$EXPORT_LIST_FILE"
EOF
    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    [[ "$output" == *"PARTIAL=true TOTAL=42 ITEMS=2"* ]] || return 1
    [[ "$output" == *"clone  # size unknown"* ]] || return 1
    [[ "$output" == *"ordinary  # 43KB"* ]] || { echo "$output"; return 1; }
}

@test "unknown clone removal does not log allocated bytes as freed (#1698)" {
    mkdir -p "$SANDBOX/clone"
    touch "$SANDBOX/clone/fixture"
    run env PROJECT_ROOT="$PROJECT_ROOT" HOME="$SANDBOX" MOLE_DRY_RUN=0 \
        /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
get_path_size_kb() { echo 999999; }
oplog_enabled() { return 0; }
log_operation() { printf 'OP:%s:%s:%s\n' "$2" "${3##*/}" "$4"; }
safe_remove "$HOME/clone" true unknown
[[ ! -e "$HOME/clone" ]] || exit 1
echo FIXTURE_REMOVED
EOF
    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    [[ "$output" == *"FIXTURE_REMOVED"* ]] || return 1
    [[ "$output" == *"OP:REMOVED:clone:"* ]] || return 1
    [[ "$output" != *"MB"* && "$output" != *"GB"* ]]
}

@test "get_path_size_kb returns 0 for empty path" {
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb ""
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "0" ]
}

@test "get_path_size_kb returns 0 for non-existent path" {
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/does-not-exist"
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "0" ]
}

@test "get_path_size_kb returns 0 for empty file" {
    : > "$SANDBOX/empty"
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/empty"
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "0" ]
}

@test "get_path_size_kb matches disk occupancy for sub-KB files" {
    dd if=/dev/zero of="$SANDBOX/small" bs=500 count=1 2> /dev/null
    expected=$(du -skP "$SANDBOX/small" | awk '{print $1}')
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/small"
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "$expected" ]
}

@test "get_path_size_kb matches disk occupancy for 1024-byte file" {
    dd if=/dev/zero of="$SANDBOX/onek" bs=1024 count=1 2> /dev/null
    expected=$(du -skP "$SANDBOX/onek" | awk '{print $1}')
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/onek"
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "$expected" ]
}

@test "get_path_size_kb matches disk occupancy for odd byte counts" {
    dd if=/dev/zero of="$SANDBOX/odd" bs=50000 count=1 2> /dev/null
    expected=$(du -skP "$SANDBOX/odd" | awk '{print $1}')
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/odd"
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "$expected" ]
}

@test "get_path_size_kb does not follow symlinks" {
    # 100 KB target, symlink should report its own (tiny) size, not 100 KB.
    dd if=/dev/zero of="$SANDBOX/target" bs=1024 count=100 2> /dev/null
    ln -s "$SANDBOX/target" "$SANDBOX/link"

    target_kb=$(/bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/target"
EOF
)
    link_kb=$(/bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/link"
EOF
)

    expected_target=$(du -skP "$SANDBOX/target" | awk '{print $1}')
    [ "$target_kb" = "$expected_target" ]
    # Symlink path strings are short, so link size rounds to 1 KB or 0.
    # Either is acceptable; what must NOT happen is the link reporting the
    # 100 KB target size.
    [ "$link_kb" -lt 10 ]
}

@test "get_path_size_kb still returns 0 for broken symlinks" {
    ln -s "$SANDBOX/missing" "$SANDBOX/broken"
    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/broken"
EOF
    [ "$status" -eq 0 ]
    # -e on a broken symlink returns false, so the early return triggers.
    [ "$output" = "0" ]
}

@test "get_path_size_kb sums directory contents recursively" {
    mkdir -p "$SANDBOX/dir/sub"
    dd if=/dev/zero of="$SANDBOX/dir/a" bs=1024 count=10 2> /dev/null
    dd if=/dev/zero of="$SANDBOX/dir/sub/b" bs=1024 count=20 2> /dev/null

    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$SANDBOX/dir"
EOF
    [ "$status" -eq 0 ]
    # Should be at least the sum of the two files (30 KB). Filesystem
    # overhead may push it slightly higher, so use >= rather than ==.
    [ "$output" -ge 30 ]
}

@test "get_path_size_kb handles whitespace in paths" {
    local quirky="$SANDBOX/dir with spaces"
    mkdir -p "$quirky"
    dd if=/dev/zero of="$quirky/payload" bs=1024 count=5 2> /dev/null
    expected=$(du -skP "$quirky/payload" | awk '{print $1}')

    run /bin/bash --noprofile --norc << EOF
$(prelude)
get_path_size_kb "$quirky/payload"
EOF
    [ "$status" -eq 0 ]
    [ "$output" = "$expected" ]
}

@test "get_path_size_kb propagates metadata stat and du timeouts" {
    mkdir -p "$SANDBOX/Stalled.app" "$SANDBOX/stalled-dir"
    printf 'x\n' > "$SANDBOX/stalled-file"

    run env PROJECT_ROOT="$PROJECT_ROOT" SANDBOX="$SANDBOX" \
        /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
run_with_timeout() { return 124; }

for target in "$SANDBOX/Stalled.app" "$SANDBOX/stalled-file" "$SANDBOX/stalled-dir"; do
    size=""
    rc=0
    size=$(get_path_size_kb "$target") || rc=$?
    printf 'RC=%s SIZE=%s TARGET=%s\n' "$rc" "$size" "${target##*/}"
    [[ $rc -eq 124 && -z "$size" ]] || exit 1
done
EOF

    [ "$status" -eq 0 ] || {
        echo "$output"
        return 1
    }
    [[ "$output" == *"RC=124 SIZE= TARGET=Stalled.app"* ]] || return 1
    [[ "$output" == *"RC=124 SIZE= TARGET=stalled-file"* ]] || return 1
    [[ "$output" == *"RC=124 SIZE= TARGET=stalled-dir"* ]]
}

@test "get_path_size_kb uses physical metadata for app bundles" {
    mkdir -p "$SANDBOX/Sized.app"

    run env PROJECT_ROOT="$PROJECT_ROOT" SANDBOX="$SANDBOX" \
        /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
run_with_timeout() {
    shift
    if [[ "$1" == "mdls" && "$*" == *"kMDItemPhysicalSize"* ]]; then
        printf '4096\n'
        return 0
    fi
    if [[ "$1" == "mdls" && "$*" == *"kMDItemLogicalSize"* ]]; then
        printf '8192\n'
        return 0
    fi
    return 1
}

get_path_size_kb "$SANDBOX/Sized.app"
EOF

    [ "$status" -eq 0 ] || return 1
    [ "$output" = "4" ]
}

@test "get_path_size_kb rejects partial du output on scan failure" {
    mkdir -p "$SANDBOX/partial-dir"

    run env PROJECT_ROOT="$PROJECT_ROOT" SANDBOX="$SANDBOX" \
        /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
run_with_timeout() {
    shift
    if [[ "$1" == "du" ]]; then
        printf '777\t%s\n' "$SANDBOX/partial-dir"
        return 1
    fi
    command "$@"
}

size=""
rc=0
size=$(get_path_size_kb "$SANDBOX/partial-dir") || rc=$?
printf 'RC=%s SIZE=%s\n' "$rc" "$size"
[[ $rc -eq 1 && -z "$size" ]] || exit 1
EOF

    [ "$status" -eq 0 ] || return 1
    [ "$output" = "RC=1 SIZE=" ]
}

@test "mole_item_size_continues keeps an item through a failed size and stops on a signal" {
    run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc << 'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
MOLE_CURRENT_COMMAND=clean
for rc in 0 1 124 130; do
    MOLE_CLEAN_CANCEL_STATUS=0
    MOLE_CLEAN_SIZING_TIMEOUTS=0
    result=0
    mole_item_size_continues "$rc" || result=$?
    printf '%s:%s:%s:%s ' "$rc" "$result" "$MOLE_CLEAN_SIZING_TIMEOUTS" "$MOLE_CLEAN_CANCEL_STATUS"
done
SCRIPT

    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    # Only a timeout marks the total partial; a vanished item (1) does not.
    [[ "$output" == "0:0:0:0 1:0:0:0 124:0:1:0 130:130:0:130 " ]]
}

@test "mole_add_cleaned_row adds one category and ignores non-numeric input" {
    run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc << 'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
files_cleaned=2
total_size_cleaned=10
total_items=1
removed=3
mole_add_cleaned_row 4 "$removed"
mole_add_cleaned_row "removed" "12KB"
mole_add_cleaned_row "" ""
printf 'FILES=%s KB=%s ITEMS=%s\n' "$files_cleaned" "$total_size_cleaned" "$total_items"
SCRIPT

    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    [[ "$output" == "FILES=6 KB=13 ITEMS=4" ]]
}

@test "cleanup sizing counts the readable bytes of a folder with an unlistable child" {
    local root="$SANDBOX/partly-readable"
    mkdir -p "$root/locked"
    head -c 409600 /dev/zero > "$root/data.bin"
    chmod 000 "$root/locked"
    local expected
    expected=$(du -skP "$root" 2> /dev/null | awk '{print $1}' || true)

    run /bin/bash --noprofile --norc <<EOF
$(prelude)
strict_rc=0
strict=\$(get_path_size_kb "$root") || strict_rc=\$?
echo "STRICT=[\$strict] rc=\$strict_rc"
readable_rc=0
readable=\$(get_path_size_kb "$root" "" readable) || readable_rc=\$?
echo "READABLE=\$readable rc=\$readable_rc"
source "$PROJECT_ROOT/bin/clean.sh"
echo "CLEANUP=\$(get_cleanup_path_size_kb "$root")"
EOF
    chmod 755 "$root/locked"

    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    # Uninstall keeps the strict contract (#1404).
    [[ "$output" == *"STRICT=[] rc=1"* ]] || { echo "$output"; return 1; }
    # A folder Mole cannot list cannot be removed either, so the readable
    # bytes are what a cleanup frees; dropping them counted the item as 0.
    [[ "$output" == *"READABLE=$expected rc=0"* ]] || { echo "$output"; return 1; }
    [[ "$output" == *"CLEANUP=$expected"* ]] || { echo "$output"; return 1; }
    [ "$expected" -ge 400 ]
}

@test "only a sizing timeout marks the cleanup total as a lower bound" {
    run /bin/bash --noprofile --norc <<EOF
$(prelude)
MOLE_CLEAN_SIZING_TIMEOUTS=0
mole_item_size_continues 1
echo "AFTER_FAILURE=\$MOLE_CLEAN_SIZING_TIMEOUTS"
mole_item_size_continues 124
echo "AFTER_TIMEOUT=\$MOLE_CLEAN_SIZING_TIMEOUTS"
EOF

    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    # A vanished item leaves nothing to free and must not add a lower-bound mark.
    [[ "$output" == *"AFTER_FAILURE=0"* ]] || { echo "$output"; return 1; }
    [[ "$output" == *"AFTER_TIMEOUT=1"* ]]
}

@test "a sizing timeout names the item in the debug log" {
    mkdir -p "$SANDBOX/slow-dir"
    run /bin/bash --noprofile --norc <<EOF
$(prelude)
run_with_timeout() { return 124; }
debug_log() { echo "DEBUG: \$*"; }
rc=0
get_path_size_kb "$SANDBOX/slow-dir" 7 readable || rc=\$?
echo "RC=\$rc"
EOF

    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    [[ "$output" == *"RC=124"* ]] || { echo "$output"; return 1; }
    [[ "$output" == *"DEBUG: Size check timed out after 7s: $SANDBOX/slow-dir"* ]] || { echo "$output"; return 1; }
}
