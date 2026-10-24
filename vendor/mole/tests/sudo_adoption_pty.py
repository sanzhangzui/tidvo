#!/usr/bin/env python3
"""Exercise sudo adoption with a mock that authorizes commands via /dev/tty."""
import fcntl
import os
import pty
import select
import signal
import subprocess
import termios
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
source "$TEST_ROOT/lib/core/common.sh"
unset MOLE_TEST_MODE MOLE_TEST_NO_AUTH
sudo() {
    case "$*" in
        '-n -v') echo VALIDATION_OK; return 0 ;;
        '-n true')
            echo COMMAND_PROBE
            [[ "$TEST_CASE" == cached ]] && return 0
            printf 'AUTH_REQUIRED flag=%s pid=%s\n' "$MOLE_SUDO_ESTABLISHED" "$MOLE_SUDO_KEEPALIVE_PID" > /dev/tty
            local answer
            IFS= read -r answer < /dev/tty || return 1
            [[ "$answer" == allow ]]
            ;;
        *) return 97 ;;
    esac
}
_start_sudo_keepalive() { echo KEEPALIVE > /dev/tty; echo mock-pid; }
_stop_sudo_keepalive() { :; }
sudo -n -v || exit 1
if adopt_sudo_session; then
    printf 'ADOPTED flag=%s pid=%s\n' "$MOLE_SUDO_ESTABLISHED" "$MOLE_SUDO_KEEPALIVE_PID"
    echo CLEANUP_READY
else
    printf 'DENIED flag=%s pid=%s\n' "$MOLE_SUDO_ESTABLISHED" "$MOLE_SUDO_KEEPALIVE_PID"
fi
'''


def own_terminal():
    os.setsid()
    fcntl.ioctl(1, termios.TIOCSCTTY, 0)


def check(case, redirected=False):
    master, slave = pty.openpty()
    process = None
    output = b''
    answered = False
    try:
        process = subprocess.Popen(
            ['/bin/bash', '--noprofile', '--norc', '-c', SCRIPT],
            stdin=subprocess.DEVNULL if redirected else slave,
            stdout=slave, stderr=slave, preexec_fn=own_terminal,
            env=dict(os.environ, TEST_ROOT=str(ROOT), TEST_CASE=case),
        )
        deadline = time.monotonic() + 10
        while True:
            assert time.monotonic() < deadline, output.decode(errors='replace')
            if select.select([master], [], [], .05)[0]:
                output += os.read(master, 4096)
            if b'AUTH_REQUIRED' in output and not answered:
                assert not redirected, 'redirected stdin unexpectedly prompted'
                assert b'AUTH_REQUIRED flag=false pid=\r\n' in output, output
                assert b'KEEPALIVE' not in output, output
                assert b'CLEANUP_READY' not in output, output
                os.write(master, b'allow\n' if case == 'allow' else b'deny\n')
                answered = True
            if process.poll() is not None:
                # A closed pty can stay readable and return b'' (macOS) or
                # raise EIO (Linux); stop draining at end of output.
                while select.select([master], [], [], .05)[0]:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
                break
        text = output.decode(errors='replace').replace('\r', '')
        assert process.returncode == 0, text
        assert 'VALIDATION_OK' in text, text
        if redirected:
            assert 'COMMAND_PROBE' not in text, text
        else:
            assert 'COMMAND_PROBE' in text, text
            assert answered == (case != 'cached'), text
        if case == 'deny' and not redirected:
            assert 'DENIED flag=false pid=\n' in text, text
            assert 'KEEPALIVE' not in text, text
            assert 'CLEANUP_READY' not in text, text
        else:
            assert 'ADOPTED flag=true pid=mock-pid' in text, text
            assert text.index('KEEPALIVE') < text.index('CLEANUP_READY'), text
        print(f'PASS: {case}, redirected={redirected}')
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        os.close(master)
        os.close(slave)


for scenario in ('allow', 'cached', 'deny'):
    check(scenario)
check('allow', redirected=True)
