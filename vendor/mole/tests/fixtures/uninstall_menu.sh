#!/bin/bash
# Exercise the real selector using synthetic app rows; never load removal code.
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/ui/menu_paginated.sh"
source "$PROJECT_ROOT/lib/ui/app_selector.sh"

if [[ "${1:-}" != --tty ]]; then
    enter_alt_screen() { :; }
    leave_alt_screen() { :; }
    stty() { :; }
    tput() {
        case "${1:-}" in
            cols) echo "${COLUMNS:-80}" ;;
            lines) echo 16 ;;
        esac
    }
    drain_pending_input() { :; }
fi
export MOLE_MANAGED_ALT_SCREEN=1
unset MOLE_MENU_SORT_MODE MOLE_MENU_SORT_REVERSE MOLE_READ_KEY_FORCE_CHAR

apps_data=(
    '0|/fixture/Zebra.app|Zebra|test.zebra|0|Never|0'
    '0|/fixture/Alpha.app|alpha App [100%]|test.alpha|0|Never|0'
    '0|/fixture/Studio.app|Visual Studio Code|test.studio|0|Never|0'
    '0|/fixture/LongZulu.app|Same very long application name with hidden suffix Zulu|test.longz|1MB|Never|0'
    '0|/fixture/LongAlpha.app|Same very long application name with hidden suffix Alpha|test.longa|9MB|Never|0'
)
if [[ "${WITH_METADATA:-0}" == 1 ]]; then
    apps_data[0]='100|/fixture/Zebra.app|Zebra|test.zebra|10MB|Today|10240'
fi

# read_key runs in command substitution, so persist the position in a file.
scripted_read_key() {
    local index
    index=$(cat "$KEY_STATE" 2> /dev/null || echo 0)
    index=$((index + 1))
    printf '%s\n' "$index" > "$KEY_STATE"
    local key
    key=$(sed -n "${index}p" "$KEYS_FILE")
    printf '%s\n' "${key:-QUIT}"
}
if [[ "${1:-}" != --tty ]]; then
    read_key() { scripted_read_key; }
fi

rc=0
selected_apps=()
if [[ "${1:-}" == --tty ]]; then
    select_apps_for_uninstall || rc=$?
else
    select_apps_for_uninstall > "$MENU_OUTPUT" 2>&1 || rc=$?
fi
printf 'RC=%s\n' "$rc"
[[ "${1:-}" == --tty ]] || printf 'KEYS=%s\n' "$(cat "$KEY_STATE")"
printf 'SORT=%s REVERSE=%s\n' "${MOLE_MENU_SORT_MODE:-}" "${MOLE_MENU_SORT_REVERSE:-}"
for row in ${selected_apps[@]+"${selected_apps[@]}"}; do
    IFS='|' read -r _ path _ <<< "$row"
    printf 'SELECTED=%s\n' "$path"
done
