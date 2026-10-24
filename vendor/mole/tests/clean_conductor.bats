#!/usr/bin/env bats

load helpers/common

setup() {
    mole_test_setup_project_root
    SANDBOX=$(mktemp -d "${BATS_TEST_DIRNAME}/tmp-conductor.XXXXXX")
    export SANDBOX
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/Conductor/workspaces/repo/workspace" \
        "$HOME/Conductor/archived-contexts/repo/workspace"
}

teardown() {
    rm -rf "$SANDBOX"
}

@test "Conductor workspace and archived context usage is queued and report-only (#1800)" {
    run env MOLE_TEST_MODE=1 /bin/bash --noprofile --norc << 'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/clean/user.sh"
_large_prefetch_queue_rows
run_with_timeout() { shift; "$@"; }
du() { printf '2097152\t%s\n' "${!#}"; }
agent_worktree_containers() { :; }
start_section_spinner() { :; }
stop_section_spinner() { :; }
note_activity() { :; }
safe_clean() { echo UNEXPECTED_DELETE; return 99; }
check_large_file_candidates
SCRIPT
    [ "$status" -eq 0 ] || {
        echo "$output"
        return 1
    }
    [[ "$output" == *"$HOME/Conductor/workspaces"* ]] || return 1
    [[ "$output" == *"$HOME/Conductor/archived-contexts"* ]] || return 1
    [[ "$output" == *"Conductor workspaces"* ]] || return 1
    [[ "$output" == *"Conductor archived contexts"* ]] || return 1
    [[ "$output" != *UNEXPECTED_DELETE* ]] || return 1
    [ -d "$HOME/Conductor/workspaces/repo/workspace" ]
    [ -d "$HOME/Conductor/archived-contexts/repo/workspace" ]
}

@test "Conductor usage ignores linked roots and incomplete measurements (#1800)" {
    mv "$HOME/Conductor/workspaces" "$HOME/real-workspaces"
    ln -s "$HOME/real-workspaces" "$HOME/Conductor/workspaces"
    run env MOLE_TEST_MODE=1 /bin/bash --noprofile --norc << 'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/clean/user.sh"
_large_prefetch_queue_rows
run_with_timeout() { printf '2097152\tpartial\n'; return 124; }
agent_worktree_containers() { :; }
start_section_spinner() { :; }
stop_section_spinner() { :; }
note_activity() { :; }
check_large_file_candidates
SCRIPT
    [ "$status" -eq 0 ] || {
        echo "$output"
        return 1
    }
    [[ "$output" != *"Conductor workspaces"* ]] || return 1
    [[ "$output" != *"Conductor archived contexts"* ]] || return 1
    [ -d "$HOME/real-workspaces/repo/workspace" ]
}

@test "Conductor cache and logs use the existing cleanup while authored state stays (#1800)" {
    local mode
    for mode in preview clean whitelist; do
        local fixture="$SANDBOX/$mode"
        mkdir -p "$fixture/Library/Caches/com.conductor.app" \
            "$fixture/Library/Logs/com.conductor.app" \
            "$fixture/Library/Application Support/com.conductor.app/agent-binaries" \
            "$fixture/Library/Application Support/com.conductor.app/bin" \
            "$fixture/Conductor/workspaces/repo/workspace" \
            "$fixture/Conductor/archived-contexts/repo/workspace" \
            "$fixture/.conductor/projects/workspace" "$fixture/.config/mole"
        printf 'cache\n' > "$fixture/Library/Caches/com.conductor.app/data"
        printf 'diagnostic\n' > "$fixture/Library/Logs/com.conductor.app/app.log"
        local state
        local -a states=(
            'Library/Application Support/com.conductor.app/conductor.db'
            'Library/Application Support/com.conductor.app/conductor.db-wal'
            'Library/Application Support/com.conductor.app/conductor.db-shm'
            'Library/Application Support/com.conductor.app/conductor.db.bak'
            'Library/Application Support/com.conductor.app/agent-binaries/agent'
            'Library/Application Support/com.conductor.app/bin/tool'
            'Conductor/workspaces/repo/workspace/uncommitted.txt'
            'Conductor/archived-contexts/repo/workspace/chat.json'
            '.conductor/settings.toml'
        )
        for state in "${states[@]}"; do
            printf 'keep\n' > "$fixture/$state"
        done
        if [[ "$mode" == whitelist ]]; then
            printf '%s\n' "$fixture/Library/Caches/com.conductor.app" \
                "$fixture/Library/Logs/com.conductor.app" > "$fixture/.config/mole/whitelist"
        fi
        run env -u DENO_DIR HOME="$fixture" CONDUCTOR_MODE="$mode" \
            MOLE_TEST_MODE=1 MOLE_TEST_NO_AUTH=1 /bin/bash --noprofile --norc << 'SCRIPT'
set -euo pipefail
source "$PROJECT_ROOT/bin/clean.sh"
# Deterministic idle owner; retain the production cache policy and sink.
ps() { printf '  PID  PPID COMM ARGS\n'; }
[[ "$CONDUCTOR_MODE" == preview ]] && DRY_RUN=true
start_section_spinner() { :; }
stop_section_spinner() { :; }
clean_trash() { :; }
_clean_recent_items() { :; }
_clean_mail_downloads() { :; }
clean_user_essentials
SCRIPT
        [ "$status" -eq 0 ] || {
            echo "$mode: $output"
            return 1
        }
        for state in "${states[@]}"; do
            [ "$(cat "$fixture/$state")" = keep ] || return 1
        done
        [ -d "$fixture/.conductor/projects/workspace" ] || return 1
        if [[ "$mode" == clean ]]; then
            [ ! -e "$fixture/Library/Caches/com.conductor.app/data" ] || {
                echo "$output"
                return 1
            }
            [ ! -e "$fixture/Library/Logs/com.conductor.app/app.log" ] || return 1
        else
            [ -f "$fixture/Library/Caches/com.conductor.app/data" ] || return 1
            [ -f "$fixture/Library/Logs/com.conductor.app/app.log" ] || return 1
        fi
    done
}
