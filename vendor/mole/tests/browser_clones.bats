#!/usr/bin/env bats

load helpers/common

setup() {
    mole_test_setup_home browser-clones
    export MOLE_TEST_MODE=1 MOLE_TEST_NO_AUTH=1
    source "$PROJECT_ROOT/lib/core/common.sh"
    CLONE_ROOT="$HOME/Library/Caches/clone-fixture/X"
    CLONE="$CLONE_ROOT/com.google.Chrome.code_sign_clone/code_sign_clone.A123bc"
    BUNDLE="$CLONE/Google Chrome.app"
    mkdir -p "$BUNDLE/Contents/MacOS"
    printf 'fixture executable' >"$BUNDLE/Contents/MacOS/Google Chrome"
    /usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string com.google.Chrome' "$BUNDLE/Contents/Info.plist" >/dev/null
    /usr/libexec/PlistBuddy -c 'Add :CFBundleExecutable string Google Chrome' "$BUNDLE/Contents/Info.plist"
    # shellcheck disable=SC2329 # Called indirectly by the sourced cleanup implementation.
    _mole_browser_clone_root() { printf '%s\n' "$CLONE_ROOT"; }
    # No host browser, lsof, sudo, or deletion is used by these fixtures.
    # shellcheck disable=SC2329 # Called indirectly by the sourced cleanup implementation.
    run_with_timeout() {
        shift
        case "$1" in
        /bin/ps)
            printf '%s\n' "${PROCESS_TABLE:-/sbin/launchd}"
            return "${PROCESS_RC:-0}"
            ;;
        /usr/sbin/lsof)
            printf '%s' "${HANDLE_OUTPUT:-}"
            return "${HANDLE_RC:-1}"
            ;;
        *) "$@" ;;
        esac
    }
    # shellcheck disable=SC2329 # Called indirectly by the sourced cleanup implementation.
    system_cleanup_budget_reached() { return 1; }
    CALLS="$HOME/calls"
    : >"$CALLS"
    code_sign_cleaned=0
    # shellcheck disable=SC2329 # Called indirectly by the sourced cleanup implementation.
    safe_remove() {
        [[ "$2" == true && "$3" == unknown ]] || return 1
        [[ "$5" == "${1%/*}" && -n "$6" && -n "$7" ]] || return 1
        "$_MOLE_SAFE_REMOVE_FINAL_GUARD" "$1" || return 1
        printf '%s\n' "$1" >>"$CALLS"
        return "${REMOVE_RC:-0}"
    }
}

teardown() { mole_test_teardown_home; }

@test "browser clone cleanup offers individual reviewed children with unknown bytes" {
    clean_browser_code_sign_clones
    [ "$code_sign_cleaned" -eq 1 ]
    [ "$(cat "$CALLS")" = "$CLONE" ]
    [ -d "$CLONE" ]
}

@test "browser clone cleanup reaches Helium and retains it while Helium runs" {
    local helium="$CLONE_ROOT/net.imput.helium.code_sign_clone/code_sign_clone.2VaD4t"
    mkdir -p "$helium/Helium.app.bundle/Contents/MacOS"
    printf 'fixture executable' >"$helium/Helium.app.bundle/Contents/MacOS/Helium"
    /usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string net.imput.helium' "$helium/Helium.app.bundle/Contents/Info.plist" >/dev/null
    /usr/libexec/PlistBuddy -c 'Add :CFBundleExecutable string Helium' "$helium/Helium.app.bundle/Contents/Info.plist"
    for PROCESS_TABLE in '/sbin/launchd
/Applications/Helium.app/Contents/MacOS/Helium' '/sbin/launchd
Helium Helper (Renderer)'; do
        clean_browser_code_sign_clones
    done
    [ ! -s "$CALLS" ]
    PROCESS_TABLE=/sbin/launchd clean_browser_code_sign_clones
    grep -qx "$helium" "$CALLS"
    [ "$code_sign_cleaned" -eq 2 ]
}

@test "browser clone cleanup retains running browser helpers and unknown process probes" {
    for PROCESS_TABLE in '/sbin/launchd
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' '/sbin/launchd
Google Chrome Helper (Renderer)' '/sbin/launchd
/Applications/Chromium.app/Contents/MacOS/Chromium' 'permission denied'; do
        clean_browser_code_sign_clones
    done
    PROCESS_TABLE=/sbin/launchd PROCESS_RC=124 clean_browser_code_sign_clones
    [ ! -s "$CALLS" ]
    [ "$code_sign_cleaned" -eq 0 ]
}

@test "browser clone snapshot retains open handles and lsof failures" {
    for HANDLE_RC in 0 2 124; do
        run _mole_browser_clone_snapshot "$CLONE"
        [ "$status" -ne 0 ]
    done
    HANDLE_RC=1 HANDLE_OUTPUT='warning: permission denied'
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot refuses parent unknown vendor extra files and symlinks" {
    run _mole_browser_clone_snapshot "${CLONE%/*}"
    [ "$status" -ne 0 ]
    # Sorts before the bundle, so the bundle is still the last entry listed
    # and only the entry count refuses the clone.
    touch "$CLONE/AAA-personal.txt"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
    /bin/rm "$CLONE/AAA-personal.txt" # SAFE: test-owned fixture
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    mv "$BUNDLE" "$HOME/saved-bundle"
    ln -s "$HOME/saved-bundle" "$BUNDLE"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot refuses an unknown vendor clone shaped like Chrome" {
    local other="$CLONE_ROOT/com.crowdstrike.falcon.code_sign_clone/code_sign_clone.A123bc"
    # The same shape under an allowlisted id is accepted.
    cp -R "$CLONE" "${CLONE%/*}/code_sign_clone.B234cd"
    run _mole_browser_clone_snapshot "${CLONE%/*}/code_sign_clone.B234cd"
    [ "$status" -eq 0 ]
    mkdir -p "${other%/*}"
    cp -R "$CLONE" "$other"
    /usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier com.crowdstrike.falcon' "$other/Google Chrome.app/Contents/Info.plist"
    # Only the id allowlist is left to refuse it.
    run _mole_browser_clone_snapshot "$other"
    [ "$status" -ne 0 ]
}

@test "browser clone cleanup retains a clone reached through a symlinked directory" {
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    mv "${CLONE%/*}" "$HOME/real-id-dir"
    ln -s "$HOME/real-id-dir" "${CLONE%/*}"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
    clean_browser_code_sign_clones
    [ ! -s "$CALLS" ]
    [ "$code_sign_cleaned" -eq 0 ]
    [ -d "$HOME/real-id-dir/code_sign_clone.A123bc" ]
}

@test "browser clone snapshot refuses a clone name that is not six characters" {
    cp -R "$CLONE" "${CLONE%?}d"
    run _mole_browser_clone_snapshot "${CLONE%?}d"
    [ "$status" -eq 0 ]
    cp -R "$CLONE" "${CLONE}x"
    run _mole_browser_clone_snapshot "${CLONE}x"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot refuses a clone nested below the clone directory" {
    local nested="${CLONE%/*}/nest/${CLONE##*/}"
    mkdir -p "${nested%/*}"
    cp -R "$CLONE" "$nested"
    run _mole_browser_clone_snapshot "$nested"
    [ "$status" -ne 0 ]
    # Positive control: the same clone at the allowed depth is accepted.
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
}

@test "browser clone snapshot refuses a bundle that is not named for its vendor app" {
    mv "$BUNDLE" "$CLONE/Other.app"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot refuses a plist whose executable is another app" {
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    /usr/libexec/PlistBuddy -c 'Set :CFBundleExecutable Other' "$BUNDLE/Contents/Info.plist"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot refuses an oversized plist" {
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    /usr/libexec/PlistBuddy -c "Add :Filler string $(head -c 70000 /dev/zero | tr '\0' a)" "$BUNDLE/Contents/Info.plist"
    [ "$(/usr/bin/stat -f %z "$BUNDLE/Contents/Info.plist")" -gt 65536 ]
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot refuses an executable that is not a regular file" {
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    /bin/rm "$BUNDLE/Contents/MacOS/Google Chrome" # SAFE: test-owned fixture
    mkdir "$BUNDLE/Contents/MacOS/Google Chrome"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser clone snapshot validates identity and supports app.bundle layout" {
    mv "$BUNDLE" "$BUNDLE.bundle"
    BUNDLE="$BUNDLE.bundle"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    /usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier other' "$BUNDLE/Contents/Info.plist"
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -ne 0 ]
}

@test "browser starting at final removal guard retains the clone" {
    # shellcheck disable=SC2329 # Called indirectly by the sourced cleanup implementation.
    safe_remove() {
        PROCESS_TABLE='/sbin/launchd
Google Chrome Helper'
        "$_MOLE_SAFE_REMOVE_FINAL_GUARD" "$1" || return 1
        printf 'unexpected\n' >>"$CALLS"
    }
    clean_browser_code_sign_clones
    [ ! -s "$CALLS" ]
    [ "$code_sign_cleaned" -eq 0 ]
}

@test "replacing a reviewed clone with a valid copy before its identity is bound retains it" {
    # The sink binds whatever stands at the path when the identity is taken,
    # so a swap after the review snapshot is caught only by the snapshot
    # comparison in the final guard. The copy passes every structural check.
    eval "real_$(declare -f _mole_snapshot_path_identity)"
    # shellcheck disable=SC2329 # Called indirectly by the sourced cleanup implementation.
    _mole_snapshot_path_identity() {
        cp -R "$1" "$1.copy"
        mv "$1" "$1.replaced"
        mv "$1.copy" "$1"
        real__mole_snapshot_path_identity "$@"
    }
    clean_browser_code_sign_clones
    run _mole_browser_clone_snapshot "$CLONE"
    [ "$status" -eq 0 ]
    [ ! -s "$CALLS" ]
    [ "$code_sign_cleaned" -eq 0 ]
}

@test "browser clone failed removal does not report cleaned" {
    REMOVE_RC=1 clean_browser_code_sign_clones
    [ "$code_sign_cleaned" -eq 0 ]
}

@test "browser clone probe signals stop every later candidate and section" {
    local phase code failures=0
    cp -R "$CLONE" "${CLONE%?}d"
    for code in 130 143; do
        for phase in ps:1 ps:2 ps:3 ps:4 ps:5 identifier:1 identifier:2 identifier:3 executable:1 executable:2 executable:3 handles:1 handles:2 handles:3; do
            run env PROJECT_ROOT="$PROJECT_ROOT" CLONE_ROOT="$CLONE_ROOT" CLONE="$CLONE" PHASE="$phase" CODE="$code" HOME="$HOME" /bin/bash <<'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
_mole_browser_clone_root() { printf '%s\n' "$CLONE_ROOT"; }
system_cleanup_budget_reached() { return 1; }
trace="$HOME/probe-$CODE-${PHASE/:/-}"
mkdir -p "$trace"
run_with_timeout() {
    shift
    local kind=""
    case "$1" in
        /bin/ps) kind=ps ;;
        /usr/sbin/lsof) kind=handles ;;
        /usr/libexec/PlistBuddy)
            case "$3" in *CFBundleIdentifier) kind=identifier;; *) kind=executable;; esac ;;
        *) exit 90 ;;
    esac
    printf 'call\n' >> "$trace/$kind"
    local count
    count=$(wc -l < "$trace/$kind")
    count=$((count))
    if [[ "$kind:$count" == "$PHASE" ]]; then return "$CODE"; fi
    case "$kind" in
        ps) printf '/sbin/launchd\n' ;;
        handles) return 1 ;;
        *) "$@" ;;
    esac
}
safe_remove() {
    "$_MOLE_SAFE_REMOVE_FINAL_GUARD" "$1" || return $?
    printf '%s\n' "$1" >> "$trace/deleted"
}
code_sign_cleaned=0
rc=0
clean_browser_code_sign_clones && touch "$trace/later-section" || rc=$?
[[ "$rc" == "$CODE" ]] || { printf 'rc=%s expected=%s\n' "$rc" "$CODE"; exit 11; }
[[ ! -e "$trace/deleted" && ! -e "$trace/later-section" ]] || exit 12
[[ "$code_sign_cleaned" == 0 ]] || exit 13
SCRIPT
            [ "$status" -eq 0 ] || { echo "$phase/$code: $output"; failures=$((failures + 1)); }
        done
    done
    [ "$failures" -eq 0 ]
}

@test "browser clone interruption stops the next deep system cleanup stage" {
    run env PROJECT_ROOT="$PROJECT_ROOT" HOME="$HOME" /bin/bash <<'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/clean/system.sh"
_mole_browser_clone_root() { printf '/unused-fixture\n'; }
safe_sudo_find_delete() { MOLE_SAFE_SUDO_FIND_DELETE_COUNT=0; }
safe_sudo_remove() { :; }
safe_remove() { :; }
get_current_macos_major_version() { printf '26\n'; }
macos_installer_candidate_identity() { return 1; }
materialize_completed_system_scan() { : > "$1"; }
start_section_spinner() {
    if [[ "$1" == 'Cleaning rebuildable system service caches...' ]]; then touch "$HOME/later-stage"; fi
}
stop_section_spinner() { :; }
system_cleanup_budget_reached() { [[ -e "$HOME/later-stage" ]]; }
run_with_timeout() {
    shift
    case "$1" in
        /bin/ps) touch "$HOME/interrupted-probe"; return 130 ;;
        *) return 0 ;;
    esac
}
rc=0
clean_deep_system || rc=$?
[[ -e "$HOME/interrupted-probe" ]] || exit 10
[[ "$rc" == 130 && ! -e "$HOME/later-stage" ]] || exit 11
SCRIPT
    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}
