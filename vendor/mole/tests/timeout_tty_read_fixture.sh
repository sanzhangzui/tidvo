#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$1"
MODE="${2:-read}"

# shellcheck source=lib/core/timeout.sh
source "$PROJECT_ROOT/lib/core/timeout.sh"

MO_TIMEOUT_BIN=""
MO_TIMEOUT_PERL_BIN="/usr/bin/perl"

if [[ "$MODE" == "brew" ]]; then
    MO_TIMEOUT_BIN="${3:?timeout binary required}"
    # shellcheck source=lib/uninstall/brew.sh
    source "$PROJECT_ROOT/lib/uninstall/brew.sh"

    # shellcheck disable=SC2329 # Called by the sourced Homebrew uninstall helper.
    debug_log() { :; }
    # shellcheck disable=SC2329 # Called by the sourced Homebrew uninstall helper.
    log_operation() { :; }
    # shellcheck disable=SC2329 # Called by the sourced Homebrew uninstall helper.
    is_brew_cask_installed() { return 1; }

    brew_uninstall_cask tty-probe "" nozap
    [[ "$MO_TIMEOUT_BIN" == "$3" ]] || exit 1
    printf 'BACKEND-RESTORED\n'
    exit 0
fi

if [[ "$MODE" == "timeout" ]]; then
    set +e
    run_with_timeout 1 /bin/sleep 8
    rc=$?
    set -e

    printf 'TIMEOUT:%s\n' "$rc"
    printf 'READY-AFTER\n'
    read -r value
    printf 'READ-AFTER:%s\n' "$value"
    exit 0
fi

# shellcheck disable=SC2016  # The inner bash expands value after reading the tty.
run_with_timeout 2 /bin/bash --noprofile --norc -c '
    printf "READY\n"
    read -r value
    printf "READ:%s\n" "$value"
'
