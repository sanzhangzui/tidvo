#!/usr/bin/env bats

load helpers/common

setup() {
    mole_test_setup_project_root
    export HOME="$BATS_TEST_TMPDIR/home"
    mkdir -p "$HOME"
    export KEYS_FILE="$BATS_TEST_TMPDIR/keys"
    export KEY_STATE="$BATS_TEST_TMPDIR/key-state"
    export MENU_OUTPUT="$BATS_TEST_TMPDIR/menu-output"
}

run_selector() {
    printf '%s\n' "$@" > "$KEYS_FILE"
    run env TERM=xterm-256color MOLE_TEST_NO_AUTH=1 COLUMNS="${COLUMNS:-80}" \
        /bin/bash "$PROJECT_ROOT/tests/fixtures/uninstall_menu.sh"
    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "uninstall name sorting works in both directions without metadata" {
    run_selector CHAR:s ENTER
    [[ "$output" == *"SELECTED=/fixture/Alpha.app"* ]] || return 1
    [[ "$output" == *"SORT=name REVERSE=false"* ]] || return 1

    : > "$KEY_STATE"
    run_selector CHAR:o ENTER
    [[ "$output" == *"SELECTED=/fixture/Zebra.app"* ]] || return 1
    [[ "$output" == *"SORT=name REVERSE=true"* ]] || return 1
}

@test "uninstall sorts full app names when their displayed prefixes match" {
    export WITH_METADATA=1 COLUMNS=40
    run_selector CHAR:s DOWN ENTER
    [[ "$output" == *"SELECTED=/fixture/LongAlpha.app"* ]] || return 1
}

@test "uninstall search applies multiword names before confirming selection" {
    run_selector CHAR:/ CHAR:v CHAR:I CHAR:s CHAR:u CHAR:a CHAR:l SPACE CHAR:s CHAR:t CHAR:u CHAR:d CHAR:i CHAR:o ENTER ENTER
    [[ "$output" == *"KEYS=16"* ]] || return 1
    [[ "$output" == *"SELECTED=/fixture/Studio.app"* ]] || return 1
}

@test "uninstall search treats punctuation literally and renders percent signs safely" {
    run_selector CHAR:/ 'CHAR:[' CHAR:1 CHAR:0 CHAR:0 CHAR:% 'CHAR:]' ENTER ENTER
    [[ "$output" == *"SELECTED=/fixture/Alpha.app"* ]] || return 1
    [[ "$output" == *"KEYS=9"* ]] || return 1
    run cat "$MENU_OUTPUT"
    [[ "$output" == *'/ Search: [100%]'* ]] || return 1
    [[ "$output" != *'invalid format'* ]] || return 1
}

@test "uninstall search header keeps the end of a long query visible" {
    COLUMNS=40 run_selector CHAR:/ CHAR:a CHAR:b CHAR:c CHAR:d CHAR:e CHAR:f CHAR:g CHAR:h CHAR:i \
        CHAR:j CHAR:k CHAR:l CHAR:m CHAR:n CHAR:o CHAR:p CHAR:q ENTER
    run cat "$MENU_OUTPUT"
    # 40 columns leave 11 for "(0/5; 0 selected)" plus the query: "..." and 8 characters.
    [[ "$output" == *'/ Search: ...jklmnopq'$'\033'* ]] || return 1
    [[ "$output" != *'/ Search: abcdefgh...'* ]] || return 1
}

@test "uninstall preserves selected app identities across sorting and searching" {
    run_selector CHAR:s SPACE CHAR:o CHAR:/ CHAR:v CHAR:i CHAR:s ENTER SPACE QUIT ENTER
    [[ "$output" == *"SELECTED=/fixture/Alpha.app"* ]] || return 1
    [[ "$output" == *"SELECTED=/fixture/Studio.app"* ]] || return 1
    [[ "$output" != *"SELECTED=/fixture/Zebra.app"* ]] || return 1
    [[ "$output" == *"KEYS=11"* ]] || return 1
}

@test "uninstall can sort applied search results without adding to the query" {
    run_selector CHAR:/ CHAR:s CHAR:a CHAR:m CHAR:e ENTER CHAR:o ENTER
    [[ "$output" == *"SELECTED=/fixture/LongZulu.app"* ]] || return 1
    [[ "$output" == *"KEYS=8"* ]] || return 1
}

@test "uninstall search can recover from no matches and backspace to an empty query" {
    run_selector CHAR:/ CHAR:~ ENTER QUIT CHAR:/ CHAR:z DELETE CHAR:v CHAR:i ENTER ENTER
    [[ "$output" == *"SELECTED=/fixture/Studio.app"* ]] || return 1
    [[ "$output" == *"KEYS=11"* ]] || return 1
    run cat "$MENU_OUTPUT"
    [[ "$output" == *"No matches"* ]] || return 1
}

@test "uninstall cannot submit hidden selections from an empty search result" {
    run_selector CHAR:s SPACE CHAR:/ CHAR:~ ENTER ENTER ENTER
    [[ "$output" == *"SELECTED=/fixture/Alpha.app"* ]] || return 1
    [[ "$output" == *"KEYS=7"* ]] || return 1
}

@test "uninstall Enter clears a search that hides selections instead of submitting" {
    # Alpha is selected, then hidden by a search that still shows Studio.
    run_selector CHAR:s SPACE CHAR:/ CHAR:v CHAR:i CHAR:s ENTER ENTER ENTER
    [[ "$output" == *"KEYS=9"* ]] || return 1
    [[ "$output" == *"SELECTED=/fixture/Alpha.app"* ]] || return 1
    [[ "$output" != *"SELECTED=/fixture/Studio.app"* ]] || return 1
}

@test "uninstall footer does not offer Q Cancel while a search is applied" {
    run_selector CHAR:/ CHAR:v CHAR:i CHAR:s ENTER
    run cat "$MENU_OUTPUT"
    # Q clears an applied search, so its frame must not label Q as Cancel.
    # Typing frames draw "vis_"; only the applied frame has a color reset here.
    local applied="${output##*Search: vis$'\033'}"
    [[ "$applied" != "$output" ]] || return 1
    applied="${applied%%$'\033[H'*}"
    [[ "$applied" == *"Esc Clear"* ]] || return 1
    [[ "$applied" != *"Q Cancel"* ]] || return 1
}

@test "uninstall footer prioritizes core actions before optional hints" {
    for COLUMNS in 40 54 60 80 120; do
        export COLUMNS
        : > "$KEY_STATE"
        run_selector CHAR:s QUIT
        run cat "$MENU_OUTPUT"
        [[ "$output" == *"Space Select"* ]] || return 1
        [[ "$output" == *"Enter Save"* ]] || return 1
        [[ "$output" == *"Q Cancel"* ]] || return 1
        if ((COLUMNS >= 47)); then
            [[ "$output" == *"/ Search"* ]] || return 1
        else
            [[ "$output" != *"/ Search"* ]] || return 1
        fi
        if ((COLUMNS >= 56)); then
            [[ "$output" == *"S Name"* ]] || return 1
        else
            [[ "$output" != *"S Name"* ]] || return 1
        fi
        if ((COLUMNS >= 80)); then
            [[ "$output" == *"O A-Z"* ]] || return 1
        else
            [[ "$output" != *"O A-Z"* ]] || return 1
        fi
    done
}

@test "uninstall keyboard input and narrow layouts work in a real terminal" {
    command -v python3 > /dev/null 2>&1 || skip "python3 is required for the PTY fixture"
    run python3 "$PROJECT_ROOT/tests/uninstall_menu_pty.py"
    [ "$status" -eq 0 ] || { echo "$output"; return 1; }
    [[ "$output" == *"PASS: A-Z/Z-A"* ]] || return 1
}

@test "leaving the uninstall screen stops the Preparing app list spinner" {
    if ! /usr/bin/script -q /dev/null /usr/bin/true < /dev/null > /dev/null 2>&1; then
        skip "script cannot allocate a TTY in this environment"
    fi
    local stop_fn="$BATS_TEST_TMPDIR/stop_screen.sh"
    sed -n '/^stop_uninstall_interactive_screen() {$/,/^}$/p' "$PROJECT_ROOT/bin/uninstall.sh" > "$stop_fn"
    [ -s "$stop_fn" ] || return 1

    local raw="$BATS_TEST_TMPDIR/spinner-stop.raw"
    # shellcheck disable=SC2016  # inner bash expands these from its environment
    PROJECT_ROOT="$PROJECT_ROOT" HOME="$HOME" TERM=xterm-256color STOP_FN="$stop_fn" \
        /usr/bin/script -q "$raw" /bin/bash --noprofile --norc -c '
            source "$PROJECT_ROOT/lib/core/common.sh"
            source "$STOP_FN"
            MOLE_SPINNER_PREFIX="" start_inline_spinner "Preparing app list..."
            pid="$INLINE_SPINNER_PID"
            [[ -n "$pid" ]] && echo "SPINNER_STARTED"
            /bin/sleep 0.2
            stop_uninstall_interactive_screen
            /bin/sleep 0.1
            if kill -0 "$pid" 2> /dev/null; then
                echo "SPINNER_LEFT_RUNNING"
                kill "$pid" 2> /dev/null
            else
                echo "SPINNER_STOPPED"
            fi
        ' < /dev/null > /dev/null 2>&1 || true

    run cat "$raw"
    [[ "$output" == *"SPINNER_STARTED"* ]] || return 1
    [[ "$output" == *"SPINNER_STOPPED"* ]] || return 1
    [[ "$output" != *"SPINNER_LEFT_RUNNING"* ]]
}
