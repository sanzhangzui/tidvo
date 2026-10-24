#!/usr/bin/env bats

load helpers/common

setup_file() {
	mole_test_setup_home optimize-db
}

teardown_file() {
	mole_test_teardown_home
}

create_logical_file() {
	local path="$1"
	local size="$2"

	if command -v mkfile > /dev/null 2>&1; then
		mkfile -n "$size" "$path"
	else
		truncate -s "$size" "$path"
	fi
}

@test "opt_notification_cleanup reports healthy when db is small" {
	local tmp_dir nc_db_dir
	tmp_dir=$(mktemp -d)
	# Legacy Darwin-user-dir layout (pre-Sequoia fallback).
	nc_db_dir="$tmp_dir/com.apple.notificationcenter/db2"
	mkdir -p "$nc_db_dir"
	create_logical_file "$nc_db_dir/db" 1k

	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<EOF
set -euo pipefail
source "\$PROJECT_ROOT/lib/core/common.sh"
source "\$PROJECT_ROOT/lib/optimize/tasks.sh"
getconf() { echo "$tmp_dir"; }
execute_optimization notification_cleanup
EOF

	rm -rf "$tmp_dir"
	[ "$status" -eq 0 ]
	[[ "$output" == *"healthy"* ]]
}

@test "opt_notification_cleanup prefers the usernoted group-container database" {
	# macOS 15+ live path (issue #1368). When both exist, prefer group container.
	# Isolated HOME so leftover group-container dbs do not poison sibling tests.
	local case_home group_dir legacy_root legacy_dir
	case_home=$(mktemp -d "${BATS_TEST_DIRNAME}/tmp-nc-group.XXXXXX")
	group_dir="$case_home/Library/Group Containers/group.com.apple.usernoted/db2"
	legacy_root=$(mktemp -d "${BATS_TEST_DIRNAME}/tmp-nc-legacy.XXXXXX")
	legacy_dir="$legacy_root/com.apple.notificationcenter/db2"
	mkdir -p "$group_dir" "$legacy_dir"
	create_logical_file "$group_dir/db" 1k
	create_logical_file "$legacy_dir/db" 1k

	run env HOME="$case_home" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<EOF
set -euo pipefail
source "\$PROJECT_ROOT/lib/core/common.sh"
source "\$PROJECT_ROOT/lib/optimize/tasks.sh"
getconf() { echo "$legacy_root"; }
debug_log() { printf 'DEBUG:%s\n' "\$*"; }
execute_optimization notification_cleanup
EOF

	rm -rf "$case_home" "$legacy_root"
	[ "$status" -eq 0 ] || {
		echo "$output"
		return 1
	}
	[[ "$output" == *"healthy"* ]] || return 1
	[[ "$output" == *"DEBUG:Notification Center database: $group_dir/db"* ]] || return 1
}

@test "opt_notification_cleanup reports unavailable when no supported path exists" {
	run env HOME="$HOME/nc-missing" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
getconf() { echo "/nonexistent-darwin-user-dir"; }
execute_optimization notification_cleanup
[[ "$(optimize_outcome_count unavailable)" == "1" ]] || exit 1
EOF

	[ "$status" -eq 0 ] || {
		echo "$output"
		return 1
	}
	[[ "$output" == *"unavailable"* ]] || return 1
	[[ "$output" != *"not found"* ]] || return 1
	[[ "$output" != *"already optimized"* ]] || return 1
}

@test "opt_notification_cleanup warns when sqlite3 fails" {
	local tmp_dir nc_db_dir
	tmp_dir=$(mktemp -d)
	nc_db_dir="$tmp_dir/com.apple.notificationcenter/db2"
	mkdir -p "$nc_db_dir"
	create_logical_file "$nc_db_dir/db" 60m

	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<EOF
set -euo pipefail
source "\$PROJECT_ROOT/lib/core/common.sh"
source "\$PROJECT_ROOT/lib/optimize/tasks.sh"
getconf() { echo "$tmp_dir"; }
sqlite3() { return 1; }
execute_optimization notification_cleanup
EOF

	rm -rf "$tmp_dir"
	[ "$status" -eq 0 ]
	[[ "$output" == *"busy or locked"* ]]
}

@test "notification refresh targets only its current-user launchd service" {
	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
resolve_notification_center_db() { printf '%s\n' "$HOME/nc.db"; }
opt_existing_file_size_kb_strict() { echo 60000; }
sqlite3() { :; }
trace="$HOME/notification-refresh.trace"
run_with_timeout() { printf '%s\n' "$*" > "$trace"; }
# A name-based kill would also reach an unrelated program named NotificationCenter.
killall() { echo "UNSAFE_NAME_KILL" > "$trace"; }
execute_optimization notification_cleanup
[[ "$(cat "$trace")" == "$MOLE_TIMEOUT_MEDIUM_PROBE_SEC /bin/launchctl kill SIGTERM gui/$UID/com.apple.notificationcenterui.agent" ]] || exit 1
[[ "$(optimize_outcome_count applied)" == "1" ]] || exit 1
EOF
	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "notification refresh never falls back to name killing after launchd refusal" {
	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
resolve_notification_center_db() { printf '%s\n' "$HOME/nc.db"; }
opt_existing_file_size_kb_strict() { echo 60000; }
sqlite3() { :; }
trace="$HOME/notification-refused.trace"
run_with_timeout() { printf '%s\n' "$*" >> "$trace"; return 3; }
killall() { echo "UNSAFE_NAME_KILL" >> "$trace"; }
execute_optimization notification_cleanup
[[ "$(cat "$trace")" == "$MOLE_TIMEOUT_MEDIUM_PROBE_SEC /bin/launchctl kill SIGTERM gui/$UID/com.apple.notificationcenterui.agent" ]] || exit 1
# SQL succeeded: a missing/not-running service does not undo database maintenance.
[[ "$(optimize_outcome_count applied)" == "1" ]] || exit 1
EOF
	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "notification cleanup dry run never refreshes the service" {
	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" MOLE_DRY_RUN=1 /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
resolve_notification_center_db() { printf '%s\n' "$HOME/nc.db"; }
opt_existing_file_size_kb_strict() { echo 60000; }
trace="$HOME/notification-dry.trace"
sqlite3() { echo SQL >> "$trace"; }
run_with_timeout() { echo LAUNCHCTL >> "$trace"; }
killall() { echo KILL >> "$trace"; }
execute_optimization notification_cleanup
[[ ! -e "$trace" ]] || exit 1
EOF
	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "opt_coreduet_cleanup reports healthy when db is small" {
	local tmp_dir
	tmp_dir=$(mktemp -d)
	mkdir -p "$tmp_dir/Library/Application Support/Knowledge"
	local knowledge_db="$tmp_dir/Library/Application Support/Knowledge/knowledgeC.db"
	create_logical_file "$knowledge_db" 1k

	run env HOME="$tmp_dir" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<EOF
set -euo pipefail
source "\$PROJECT_ROOT/lib/core/common.sh"
source "\$PROJECT_ROOT/lib/optimize/tasks.sh"
execute_optimization coreduet_cleanup
EOF

	rm -rf "$tmp_dir"
	[ "$status" -eq 0 ]
	[[ "$output" == *"healthy"* ]]
}

@test "opt_coreduet_cleanup warns when sqlite3 fails" {
	local tmp_dir fake_bin
	tmp_dir=$(mktemp -d)
	fake_bin="$tmp_dir/bin"
	mkdir -p "$tmp_dir/Library/Application Support/Knowledge" "$fake_bin"
	local knowledge_db="$tmp_dir/Library/Application Support/Knowledge/knowledgeC.db"
	create_logical_file "$knowledge_db" 1k

	cat > "$fake_bin/du" <<'EOF'
#!/bin/bash
echo "112640 total"
EOF
	chmod +x "$fake_bin/du"

	run env HOME="$tmp_dir" PROJECT_ROOT="$PROJECT_ROOT" PATH="$fake_bin:$PATH" /bin/bash --noprofile --norc <<EOF
set -euo pipefail
source "\$PROJECT_ROOT/lib/core/common.sh"
source "\$PROJECT_ROOT/lib/optimize/tasks.sh"
sqlite3() { return 1; }
execute_optimization coreduet_cleanup
EOF

	rm -rf "$tmp_dir"
	[ "$status" -eq 0 ]
	[[ "$output" == *"busy or locked"* ]]
}

@test "SQLite optimization is unavailable when pgrep is missing" {
	run env HOME="$HOME/sqlite-no-pgrep" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
sqlite3() { echo "UNEXPECTED_SQLITE"; return 0; }
PATH=/nonexistent

execute_optimization sqlite_vacuum
[[ "$(optimize_outcome_count unavailable)" == "1" ]] || exit 1
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"process probe unavailable"* ]] || return 1
	[[ "$output" != *"UNEXPECTED_SQLITE"* ]]
}

@test "SQLite optimization fails closed when pgrep errors" {
	run env HOME="$HOME/sqlite-pgrep-error" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
pgrep() { return 2; }
sqlite3() { echo "UNEXPECTED_SQLITE"; return 0; }

execute_optimization sqlite_vacuum
[[ "$(optimize_outcome_count failed)" == "1" ]] || exit 1
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"Failed to inspect active apps"* ]] || return 1
	[[ "$output" != *"UNEXPECTED_SQLITE"* ]]
}

@test "SQLite optimization skips while an owning app is running" {
	run env HOME="$HOME/sqlite-busy" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
pgrep() {
    [[ "$1" == "-x" && "$2" == "Mail" ]]
}
sqlite3() { echo "UNEXPECTED_SQLITE"; return 0; }

execute_optimization sqlite_vacuum
[[ "$(optimize_outcome_count skipped)" == "1" ]] || exit 1
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"Close these apps before database optimization: Mail"* ]] || return 1
	[[ "$output" != *"UNEXPECTED_SQLITE"* ]]
}

@test "SQLite optimization proceeds after reliable no-match process probes" {
	run env HOME="$HOME/sqlite-clear" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
db="$HOME/Library/Messages/chat.db"
mkdir -p "$(dirname "$db")"
touch "$db"
pgrep() { return 1; }
sqlite3() { :; }
file() { echo "SQLite 3.x database"; }
get_file_size() { echo 1024; }
should_protect_path() { return 1; }
run_with_timeout() {
    case "$4" in
        "PRAGMA page_count; PRAGMA freelist_count;") printf '100\n10\n' ;;
        "PRAGMA integrity_check;") echo "ok" ;;
        "VACUUM;") echo "VACUUM_CALLED" ;;
        *) return 64 ;;
    esac
}

execute_optimization sqlite_vacuum
[[ "$(optimize_outcome_count applied)" == "1" ]] || exit 1
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"VACUUM_CALLED"* ]] || return 1
	[[ "$output" == *"Optimized 1 databases"* ]]
}

@test "SQLite optimization does not claim all optimized when size policy skips" {
	# issue #1367: oversized skip must not share the "already optimized" headline.
	run env HOME="$HOME/sqlite-oversized" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
db="$HOME/Library/Messages/chat.db"
mkdir -p "$(dirname "$db")"
touch "$db"
pgrep() { return 1; }
file() { echo "SQLite 3.x database"; }
# 200 MiB > MOLE_SQLITE_MAX_SIZE (100 MiB).
get_file_size() { echo 209715200; }
should_protect_path() { return 1; }
bytes_to_human() { echo "200.0MB"; }
run_with_timeout() { echo "UNEXPECTED_SQLITE"; return 0; }

execute_optimization sqlite_vacuum
EOF

	[ "$status" -eq 0 ] || {
		echo "$output"
		return 1
	}
	[[ "$output" == *"No databases compacted"* ]] || return 1
	[[ "$output" == *"100 MB safety limit"* ]] || return 1
	[[ "$output" == *"Messages/chat.db"* ]] || return 1
	[[ "$output" != *"All databases already optimized"* ]] || return 1
	[[ "$output" != *"UNEXPECTED_SQLITE"* ]] || return 1
}

@test "CoreDuet cleanup recovers committed WAL before pruning old records" {
	local case_home="$BATS_TEST_TMPDIR/knowledge-recovery"
	local db="$case_home/Library/Application Support/Knowledge/knowledgeC.db"
	mkdir -p "$(dirname "$db")"
	# Leave committed transactions in WAL as an abruptly stopped owner does.
	python3 - "$db" <<'PYSQL'
import os
import sqlite3
import sys
import time

connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("PRAGMA wal_autocheckpoint=0")
connection.execute("CREATE TABLE ZOBJECT (ZCREATIONDATE REAL, value TEXT)")
connection.commit()
connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
now = time.time() - 978307200
connection.executemany("INSERT INTO ZOBJECT VALUES (?, ?)", [
    (now, "recent-committed"), (now - 120 * 86400, "expired")
])
connection.commit()
os._exit(0)
PYSQL
	[[ -s "$db-wal" ]] || return 1
	# Cross only the size threshold; all database operations remain real.
	mole_test_fake_command du "printf '112640 total\n'"
	run env HOME="$case_home" PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc <<'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/optimize/tasks.sh"
# The fixture writer exited. Supply its known idle state without host lsof/sudo.
_mole_paths_have_open_handle() { return 1; }
execute_optimization coreduet_cleanup
[[ "$(optimize_outcome_count applied)" == "1" ]] || exit 1
rows=$(sqlite3 "$HOME/Library/Application Support/Knowledge/knowledgeC.db" 'SELECT value FROM ZOBJECT ORDER BY value;')
[[ "$rows" == "recent-committed" ]] || { printf 'unexpected surviving rows: %s\n' "$rows"; exit 1; }
EOF
	[[ "$status" -eq 0 ]] || { echo "$output"; return 1; }
}
