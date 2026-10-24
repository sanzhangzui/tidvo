#!/usr/bin/env bats

load helpers/common

# CFBundleExecutable is attacker-controlled. App protection hands the name to
# pgrep/pkill, which read their argument as an ERE, so a crafted `.*` that is
# not escaped matches nearly every process and turns the uninstall kill ladder
# into a machine-wide signal. These cases pin the literal-name contract for the
# kill ladder, the wait helper, the preview probe, and the rejection of names
# that cannot be probed safely.

setup_file() {
	mole_test_setup_home uninstall-process-pattern
}

teardown_file() {
	mole_test_teardown_home
}

setup() {
	if [[ "$HOME" != "${BATS_TEST_DIRNAME}/tmp-"* ]]; then
		printf 'FATAL: HOME is not a test temp dir: %s\n' "$HOME" >&2
		return 1
	fi
	export TERM="dumb"
	rm -rf "${HOME:?}"/*
	mkdir -p "$HOME"
}

# A bundle whose CFBundleExecutable holds the test-supplied value, with a real
# Info.plist so force_kill_app reads it exactly the way it reads a shipped app.
make_app_fixture() {
	local app_path="$1" exec_name="$2" bundle_id="$3"
	mkdir -p "$app_path/Contents"
	cat > "$app_path/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>${exec_name}</string>
  <key>CFBundleIdentifier</key><string>${bundle_id}</string>
</dict></plist>
PLIST
}

@test "force_kill_app probes and kills a crafted CFBundleExecutable as a literal" {
	local app="$HOME/Applications/Probe.app"
	make_app_fixture "$app" '.*' 'com.example.Probe'

	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" MOLE_TEST_NO_AUTH=1 /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"

# Emulate real pgrep -x: an unescaped `.*` matches, the literal `\.\*` does
# not. A probe that reaches the wildcard is the regression this case punishes.
pgrep() {
	printf 'PGREP:%s\n' "$*" >> "$HOME/process.log"
	case "$*" in
		*'.*'*) return 0 ;;
	esac
	return 1
}
# A real pkill would signal nearly every process on the Mac, so only this stub
# may ever be reached; it records the ladder instead of sending anything.
pkill() {
	printf 'PKILL:%s\n' "$*" >> "$HOME/process.log"
	return 0
}
sleep() { :; }

rc=0
force_kill_app "Probe" "$HOME/Applications/Probe.app" || rc=$?
printf 'force-kill-rc:%s\n' "$rc"
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"force-kill-rc:0"* ]] || {
		echo "force_kill_app treated the crafted name as a live wildcard: $output"
		cat "$HOME/process.log"
		return 1
	}
	grep -Fq 'PGREP:-x \.\*' "$HOME/process.log" || {
		echo "escaped literal probe missing"
		cat "$HOME/process.log"
		return 1
	}
	! grep -Fq 'PGREP:-x .*' "$HOME/process.log" || {
		echo "unescaped wildcard reached pgrep"
		cat "$HOME/process.log"
		return 1
	}
	! grep -q '^PKILL:' "$HOME/process.log" || {
		echo "kill ladder ran for a name no process matched"
		cat "$HOME/process.log"
		return 1
	}
}

@test "force_kill_app still matches a normal CFBundleExecutable exactly" {
	local app="$HOME/Applications/NormalApp.app"
	make_app_fixture "$app" 'NormalApp' 'com.example.NormalApp'

	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" MOLE_TEST_NO_AUTH=1 /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"

# Only the literal normalized name matches, and it stops matching once the
# SIGTERM rung lands so the ladder exits after one signal.
running=1
pgrep() {
	printf 'PGREP:%s\n' "$*" >> "$HOME/process.log"
	[[ "$running" == "1" && "$*" == "-x NormalApp" ]] && return 0
	return 1
}
pkill() {
	printf 'PKILL:%s\n' "$*" >> "$HOME/process.log"
	[[ "$*" == "-x NormalApp" ]] || return 97
	running=0
	return 0
}
sleep() { :; }

force_kill_app "NormalApp" "$HOME/Applications/NormalApp.app" || exit 1
printf 'normal-exit:%s\n' "$running"
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"normal-exit:0"* ]] || { echo "$output"; cat "$HOME/process.log"; return 1; }
	grep -Fq 'PGREP:-x NormalApp' "$HOME/process.log" || {
		echo "normal name was not probed as itself"
		cat "$HOME/process.log"
		return 1
	}
	grep -Fq 'PKILL:-x NormalApp' "$HOME/process.log" || {
		echo "normal name did not reach the SIGTERM rung"
		cat "$HOME/process.log"
		return 1
	}
	! grep -Fq 'PKILL:-9 -x NormalApp' "$HOME/process.log" || {
		echo "normal name escalated after SIGTERM landed"
		cat "$HOME/process.log"
		return 1
	}
}

@test "uninstall preview probes the executable name as a literal" {
	run env HOME="$HOME" PROJECT_ROOT="$PROJECT_ROOT" MOLE_TEST_NO_AUTH=1 /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"
source "$PROJECT_ROOT/lib/uninstall/batch.sh"

pgrep() {
	printf 'PGREP:%s\n' "$*" >> "$HOME/process.log"
	case "$*" in
		*'.*'*) return 0 ;;
		'-qx NormalApp') return 0 ;;
	esac
	return 1
}
pkill() { printf 'PKILL:%s\n' "$*" >> "$HOME/process.log"; return 97; }

# The wildcard must miss (no process is literally named `.*`) while the
# escaped literal is the pattern the preview hands pgrep.
attacker_rc=0
_uninstall_app_running_by_executable "Probe" '.*' || attacker_rc=$?
[[ "$attacker_rc" -eq 1 ]] || exit 1
grep -Fq 'PGREP:-qx \.\*' "$HOME/process.log" || exit 1
! grep -Fq 'PGREP:-qx .*' "$HOME/process.log" || exit 1
! grep -q '^PKILL:' "$HOME/process.log" || exit 1

# A normal name still matches through the same preview probe.
normal_rc=0
_uninstall_app_running_by_executable "NormalApp" 'NormalApp' || normal_rc=$?
[[ "$normal_rc" -eq 0 ]] || exit 1
grep -Fq 'PGREP:-qx NormalApp' "$HOME/process.log" || exit 1

printf 'preview-probe:literal\n'
EOF

	[ "$status" -eq 0 ] || { echo "$output"; cat "$HOME/process.log"; return 1; }
	[[ "$output" == *"preview-probe:literal"* ]] || { echo "$output"; cat "$HOME/process.log"; return 1; }
}

@test "process pattern helper rejects empty and control-byte names" {
	run env PROJECT_ROOT="$PROJECT_ROOT" /bin/bash --noprofile --norc << 'EOF'
set -euo pipefail
source "$PROJECT_ROOT/lib/core/common.sh"

[[ "$(_mole_process_pattern_literal '.*')" == '\.\*' ]] || exit 1
[[ "$(_mole_process_pattern_literal 'NormalApp')" == 'NormalApp' ]] || exit 1

empty_rc=0
_mole_process_pattern_literal "" > /dev/null || empty_rc=$?
[[ "$empty_rc" -ne 0 ]] || exit 1

tab_rc=0
_mole_process_pattern_literal $'bad\tname' > /dev/null || tab_rc=$?
[[ "$tab_rc" -ne 0 ]] || exit 1

newline_rc=0
_mole_process_pattern_literal $'bad\nname' > /dev/null || newline_rc=$?
[[ "$newline_rc" -ne 0 ]] || exit 1

printf 'pattern-helper:guarded\n'
EOF

	[ "$status" -eq 0 ] || { echo "$output"; return 1; }
	[[ "$output" == *"pattern-helper:guarded"* ]] || { echo "$output"; return 1; }
}
