"""Bounded occupancy observations; cache-only compatibility when PID 1 is hidden."""
import os
import platform
import re
import stat
import tempfile
from pathlib import Path
from .app_installation import RESIDUAL_RULE
from .cache_rules import REGENERABLE_RULES

# Only these reviewed, regenerable cache rules may use current-user evidence.
# Logs, offline site stores, installed tools and build/delivery outputs stay strict.
USER_CACHE_RULES = frozenset({"browser.resource_cache", "browser.component_download",
    "editor.vsix", "editor.compiled_cache", "app.page_cache", "developer.npm_prebuild",
    "project.__pycache__", "project.pytest_cache", "project.mypy_cache", "project.ruff_cache"}) | REGENERABLE_RULES


def response_status(result):
    if result is None or result.stderr.strip():
        return "unknown"
    if result.stdout.strip():
        return "active" if any(line.startswith("p") and line[1:].isdigit() for line in result.stdout.splitlines()) else "unknown"
    return "idle" if result.returncode == 1 else "unknown"


def cache_target(path, home):
    """Engine independently verifies every descendant's owner and fingerprint."""
    p, home = Path(path), Path(home)
    shared = {home, home / "Library", home / "Library/Caches", home / "Library/Application Support",
              home / ".npm", home / ".Trash", home / ".config", home / ".local"}
    try:
        s = p.lstat()
        return (p.is_absolute() and ".." not in p.parts and p.is_relative_to(home) and p not in shared
                and p.resolve(strict=True) == p and s.st_uid == os.getuid()
                and (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)))
    except (OSError, RuntimeError):
        return False


def visible_user_pids(output, uid):
    """A PID counts only when both its UID and a real descriptor were observed."""
    observed = set()
    pid, owner, descriptor = None, None, False
    for line in output.splitlines() + ["p0"]:
        if not line:
            continue
        if line.startswith("p"):
            if not line[1:].isdigit():
                return None
            if pid is not None and owner == uid and descriptor:
                observed.add(pid)
            pid, owner, descriptor = int(line[1:]), None, False
        elif line.startswith("u") and line[1:].isdigit() and pid is not None:
            if owner is not None:
                return None
            owner = int(line[1:])
        elif line.startswith("f") and pid is not None:
            descriptor |= bool(re.fullmatch(r"(?:[0-9]+[rwu]?|cwd|rtd|txt|mem|mmap)", line[1:]))
        else:
            return None
    return observed


def census_user_pids(output, uid):
    pids = set()
    for line in output.splitlines():
        parts = line.split(None, 4)
        if len(parts) != 5 or any(not x.isdigit() for x in parts[:3]) or not parts[3]:
            return None
        pid, parent, owner = map(int, parts[:3])
        if owner != uid or parts[3].startswith("Z"):
            continue
        # Only the census subprocess itself is exempt from the prior observation.
        if parent == os.getpid() and parts[4] == "/bin/ps":
            continue
        pids.add(pid)
    return pids


def user_visibility(command):
    uid, pid = os.getuid(), os.getpid()
    if uid == 0:
        return False, "root_user_scope_not_supported", 0
    try:
        with tempfile.NamedTemporaryFile(prefix="tidvo-open-file-", mode="w+b") as held:
            canary = str(Path(held.name).resolve(strict=True))
            result = command(["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid), "-Fpun"], 5)
            records = result.stdout.splitlines() if result is not None else []
            if (result is None or result.returncode != 0 or result.stderr.strip()
                    or not {"p" + str(pid), "u" + str(uid), "n" + canary}.issubset(records)):
                return False, "open_file_calibration_incomplete", 0
    except (OSError, RuntimeError):
        return False, "open_file_calibration_unavailable", 0
    result = command(["/usr/sbin/lsof", "-nP", "-u", str(uid), "-Fpuf"], 10)
    if result is None or result.returncode != 0 or result.stderr.strip():
        return False, "user_process_visibility_incomplete", 0
    observed = visible_user_pids(result.stdout, uid)
    census = command(["/bin/ps", "-axo", "pid=,ppid=,uid=,stat=,comm="], 5)
    if census is None or census.returncode != 0 or census.stderr.strip():
        return False, "user_process_census_incomplete", 0
    current = census_user_pids(census.stdout, uid)
    if not current or observed is None or pid not in current or not current.issubset(observed):
        return False, "user_process_visibility_incomplete", len(current or ())
    return True, "current_user_visibility_verified", len(current)


def check_occupancy(path, home, command, rule_id=None):
    evidence = {"status": "unknown", "scope": "unverified", "reason": "system_process_visibility_incomplete"}
    root = command(["/usr/sbin/lsof", "-Fpu", "-p", "1"], 5)
    complete = root is not None and root.returncode == 0 and not root.stderr.strip() and {"p1", "u0"}.issubset(root.stdout.splitlines())
    if complete:
        evidence.update(scope="root_visible_probe", reason="root_process_visible")
    elif platform.system() == "Darwin" and (rule_id in USER_CACHE_RULES or rule_id in {RESIDUAL_RULE, "editor.obsolete_extension"}) and cache_target(path, home):
        valid, reason, count = user_visibility(command)
        scope = "current_user_uninstalled_residual" if rule_id == RESIDUAL_RULE else "current_user_obsolete_extension" if rule_id == "editor.obsolete_extension" else "current_user_cache"
        evidence.update(scope=scope, uid=os.getuid(), reason=reason,
                        observed_user_processes=count, other_users_certified=False)
        if not valid:
            return evidence
    else:
        return evidence
    args = ["/usr/sbin/lsof", "-nP", "-Fpn"]
    args += ["+D", str(path)] if Path(path).is_dir() else [str(path)]
    evidence["status"] = response_status(command(args, 15))
    if evidence["status"] == "unknown":
        evidence["reason"] = "target_occupancy_incomplete"
    return evidence
