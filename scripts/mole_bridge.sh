#!/bin/bash
# GPL-3.0-only. A narrow adapter, not an entry to upstream's broad clean command.
set -euo pipefail
[[ $# -eq 5 ]] || exit 64
[[ $(uname -s) == Darwin && ${EUID:-0} -ne 0 ]] || exit 65
source_path="$1"
destination="$2"
export MACDEV_MOLE_LOG_DIR="$3"
parent_id="$4"
target_id="$5"
[[ "$source_path" == "$HOME/"* && "$source_path" != "$HOME" ]] || exit 66
[[ "${destination%/*}" == "$HOME/.Trash" && "${destination##*/}" == mac-dev-cleanup-* ]] || exit 66
export MACDEV_TRASH_DEST="$destination"
export MACDEV_NO_SUDO=1
export MACDEV_NO_PERMISSION_REPAIR=1
export MOLE_DELETE_MODE=trash
export DRY_RUN=false
product_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# Prevent environment-imported shell functions from shadowing system commands.
# shellcheck disable=SC1091 # Bundled runtime path; libraries are reviewed and tested separately.
source "$product_root/vendor/mole/lib/core/common.sh"
# shellcheck disable=SC2034 # Consumed by upstream protection helpers after sourcing.
WHITELIST_PATTERNS=("${DEFAULT_WHITELIST_PATTERNS[@]}" "${SAFETY_WHITELIST_PATTERNS[@]}")
refuse() {
    log_operation "mac-dev-cleanup" "SKIPPED" "$source_path" "$1"
    printf 'MACDEV_REFUSAL:%s\n' "$1" >&2
    exit "$2"
}
validate_path_for_deletion "$source_path" || refuse upstream_path_policy_refused 67
_mole_path_matches_identity "$source_path" "${source_path%/*}" "$parent_id" "$target_id" || refuse upstream_identity_changed 68
# All product targets are invoking-user-owned. Use the upstream guarded direct
# Trash mover so a journaled, same-volume destination is known before moving.
move_status=0
_mole_move_path_to_user_trash "$source_path" false "${source_path%/*}" "$parent_id" "$target_id" || move_status=$?
if [[ $move_status -ne 0 ]]; then
    case "$move_status" in
        14) refuse trash_privacy_denied "$move_status" ;;
        15) refuse mutable_parent_refused "$move_status" ;;
        16) refuse owner_unverified "$move_status" ;;
        17) refuse application_reappeared "$move_status" ;;
        *) refuse trash_move_failed_or_interrupted "$move_status" ;;
    esac
fi
log_operation "mac-dev-cleanup" "TRASHED" "$source_path" "journaled recoverable move"
