"""Only signed, revalidated candidate plans may cross the mutation boundary."""
import contextlib
import ctypes
import datetime
import errno
import fcntl
import os
import platform
import shutil
import subprocess
import uuid
from pathlib import Path

from .probes import NativeProbe
from .cache_context import unchanged_cache_context
from .agent_inspection import AgentPolicy
from .probes import git_evidence
from . import __version__
from .safety import Refused, identity, ordinary_path, tree_snapshot, unchanged
from .scanner import DEPENDENCY_RULES, Scanner, read_json
from .state import State, private_directory


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class InterruptedMove(Refused):
    """A mutation may be unresolved: preserve intent and stop later moves."""


def rename_exclusive(source, destination):
    """Atomic same-volume rename with no replacement, anchored to directory FDs."""
    src, dst = Path(source), Path(destination)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    sfd, dfd = os.open(src.parent, flags), os.open(dst.parent, flags)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if platform.system() == "Darwin":
            fn = libc.renameatx_np
            option = 0x00000004  # RENAME_EXCL, Darwin stdio.h
        elif platform.system() == "Linux":
            # Used by the isolated fixture suite; production CLI remains macOS-only.
            fn = libc.renameat2
            option = 1  # RENAME_NOREPLACE
        else:
            raise Refused("exclusive_rename_unavailable")
        fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        fn.restype = ctypes.c_int
        if fn(sfd, os.fsencode(src.name), dfd, os.fsencode(dst.name), option) != 0:
            code = ctypes.get_errno()
            if code == errno.EEXIST:
                raise Refused("restore_or_trash_destination_conflict")
            raise OSError(code, os.strerror(code))
    finally:
        os.close(sfd)
        os.close(dfd)


class MoleBackend:
    def __init__(self, state):
        self.state = state
        self.bridge = Path(__file__).resolve().parent.parent / "scripts/mole_bridge.sh"

    def move(self, source, destination, snapshot):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("MOLE_", "_MOLE_", "MO_", "MACDEV_", "SUDO_", "BASH_FUNC_")) and k not in ["BASH_ENV", "ENV", "CDPATH"]}
        env.update(HOME=str(self.state.home), NO_COLOR="1", MOLE_CURRENT_COMMAND="mac-dev-cleanup", PATH="/usr/bin:/bin:/usr/sbin:/sbin")
        args = ["/bin/bash", str(self.bridge), str(source), str(destination), str(self.state.root / "upstream-logs"),
                ":".join(map(str, snapshot["parent_identity"][:2])), ":".join(map(str, snapshot["identity"][:2]))]
        try:
            r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise InterruptedMove("trash_operation_interrupted_check_receipt") from None
        if r.returncode != 0:
            if r.returncode in [124, 130, 137, 143] or r.returncode < 0:
                raise InterruptedMove("trash_operation_interrupted_check_receipt")
            for line in r.stderr.splitlines():
                if line.startswith("MACDEV_REFUSAL:"):
                    reason = line.split(":", 1)[1]
                    if reason and all(c.islower() or c == "_" for c in reason):
                        raise Refused(reason)
            raise Refused("upstream_policy_or_trash_refusal_" + str(r.returncode))

    def restore(self, source, destination):
        rename_exclusive(source, destination)


def make_plan(report, selected, state, *, probe=None, scanner_factory=Scanner):
    if not selected or len(selected) != len(set(selected)):
        raise Refused("explicit_nonduplicate_selection_required")
    if report.get("schema_version") != 1 or report.get("home") != str(state.home):
        raise Refused("scan_schema_or_home_mismatch")
    # Reports are untrusted input: recompute rules and evidence, not commands from JSON.
    fresh = scanner_factory(home=state.home, roots=report["roots"], excludes=report["excludes"], probe=probe).scan()
    before = {x["id"]: x for x in report["candidates"]}
    current = {x["id"]: x for x in fresh["candidates"]}
    candidates = []
    for identifier in selected:
        if identifier not in before or identifier not in current:
            raise Refused("candidate_missing_rescan_required")
        old, item = before[identifier], current[identifier]
        if item["action"] != "trash" or old.get("snapshot") != item.get("snapshot") or old.get("cache_context") != item.get("cache_context"):
            raise Refused("candidate_changed_or_report_only")
        candidates.append(item)
    plan = {"schema_version": 1, "policy_version": __version__, "id": uuid.uuid4().hex, "home": str(state.home), "created_at": now(),
            "mode": "trash", "roots": report["roots"], "projects": fresh["projects"], "excludes": report["excludes"], "candidates": candidates,
            "selected_allocated_bytes": sum(x["allocated_bytes"] for x in candidates),
            "confirmation_note": "Review these exact candidates before apply --confirmed; the flag is an acknowledgement, not proof of human consent."}
    state.write("plans", plan)
    return plan


@contextlib.contextmanager
def version_lock(candidate):
    if candidate["rule_id"] != "agent.codex_old_release":
        yield
        return
    p = Path(candidate["path"])
    root = p.parent.parent
    if (root / "install.lock.d").exists():
        raise Refused("daemon_directory_lock_present")
    fd = os.open(root / "install.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise Refused("daemon_lock_foreign_owner")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused("daemon_install_lock_busy") from None
        if (root / "current").resolve(strict=True) == p or (root / "auto-update-version").read_text().strip() == p.name:
            raise Refused("daemon_release_became_current_or_pending")
        yield
    finally:
        os.close(fd)


def prepare_trash(home):
    p = home / ".Trash"
    if p.resolve() != p:
        raise Refused("trash_redirected")
    # Do not repair permissions or create a fallback on another volume.
    p.mkdir(mode=0o700, exist_ok=True)
    s = p.lstat()
    if s.st_uid != os.getuid() or s.st_mode & 0o777 != 0o700:
        raise Refused("trash_not_private")
    return p


def current_policy(candidate, state, projects=()):
    p = Path(candidate["path"])
    policy = AgentPolicy(state.home)
    for project in projects:
        policy.inspect_project(Path(project))
    protection = policy.protection_for(p, candidate["rule_id"], candidate.get("cache_context"))
    if protection:
        raise Refused(protection["reason"])
    if candidate["rule_id"] in DEPENDENCY_RULES:
        raise Refused("project_dependency_environment_preserved")
    config = state.home / ".config/mac-dev-cleanup/config.json"
    if config.exists():
        if config.resolve() != config:
            raise Refused("configuration_redirected")
        for exclude in read_json(config).get("excludes", []):
            excluded = Path(exclude).expanduser().absolute()
            if p == excluded or p.is_relative_to(excluded):
                raise Refused("newly_excluded")
    if candidate["rule_id"].startswith("project.") and git_evidence(p) not in ["untracked", "not_a_repository"]:
        raise Refused("project_now_tracked_or_git_state_unknown")
    if candidate["rule_id"] == "editor.obsolete_extension":
        base = p.parent
        current = {x.get("relativeLocation") for x in read_json(base / "extensions.json")}
        if read_json(base / ".obsolete").get(p.name) is not True or p.name in current:
            raise Refused("extension_no_longer_obsolete")


def apply(plan_id, state, *, confirmed=False, probe=None, backend=None):
    if not confirmed:
        raise Refused("confirmation_required")
    probe = probe or NativeProbe(state.home)
    backend = backend or MoleBackend(state)
    with state.locked():
        plan = state.load("plans", plan_id)
        if plan.get("mode") != "trash":
            raise Refused("only_trash_supported")
        if plan.get("policy_version") != __version__:
            raise Refused("plan_policy_version_changed_rescan_required")
        if any(x.get("plan_id") == plan_id for x in state.history()):
            raise Refused("plan_already_attempted_make_a_new_plan")
        for project in plan.get("projects", []):
            probe.include_project_configs(Path(project))
        trash = prepare_trash(state.home)
        free_before = shutil.disk_usage(state.home).free
        run = {"schema_version": 1, "id": uuid.uuid4().hex, "home": str(state.home), "plan_id": plan_id,
               "started_at": now(), "status": "running", "entries": [], "free_before_bytes": free_before}
        state.write("runs", run)
        try:
            for candidate in plan["candidates"]:
                p = Path(candidate["path"])
                dest = trash / ("mac-dev-cleanup-" + run["id"] + "-" + candidate["id"])
                entry = {"candidate_id": candidate["id"], "group": candidate["group"], "rule_id": candidate["rule_id"],
                         "source": str(p), "destination": str(dest), "snapshot": candidate["snapshot"], "status": "checking"}
                run["entries"].append(entry)
                state.write("runs", run)
                try:
                    ordinary_path(p, state.home)
                    current_policy(candidate, state, plan.get("projects", []))
                    with version_lock(candidate):
                        unchanged(p, candidate["snapshot"])
                        probe.refresh()
                        ev = probe.evidence(p, candidate.get("owner", ""), candidate.get("packages", ()))
                        if ev["activity"] != "idle" or ev["configured_reference"]:
                            raise Refused("active_or_referenced_or_unknown")
                        if candidate.get("packages") and ev["reference_scan_status"] != "complete":
                            raise Refused("reference_evidence_incomplete")
                        if probe.idle(p) != "idle":
                            raise Refused("open_file_check_active_or_incomplete")
                        unchanged(p, candidate["snapshot"])
                        if p.lstat().st_dev != trash.stat().st_dev:
                            raise Refused("cross_volume_trash_not_supported")
                        if dest.exists() or dest.is_symlink():
                            raise Refused("trash_destination_conflict")
                        unchanged_cache_context(candidate)
                        current_policy(candidate, state, plan.get("projects", []))
                        entry["status"] = "moving"
                        state.write("runs", run)  # durable intent before filesystem mutation
                        backend.move(p, dest, candidate["snapshot"])
                        if not dest.exists() or dest.is_symlink():
                            raise Refused("trash_result_unverified")
                        moved = tree_snapshot(dest)
                        if moved["identity"] != candidate["snapshot"]["identity"] or moved["fingerprint"] != candidate["snapshot"]["fingerprint"]:
                            raise Refused("trash_payload_changed_check_receipt")
                        entry["status"] = "trashed"
                        entry["source_recreated"] = p.exists()
                except (OSError, Refused) as exc:
                    # A completed move followed by an error is recoverable from the durable intent.
                    entry["status"] = "recovery_required" if dest.exists() else "skipped"
                    entry["reason"] = str(exc) if isinstance(exc, Refused) else type(exc).__name__
                    if isinstance(exc, InterruptedMove):
                        entry["status"] = "recovery_required"
                        run["status"] = "interrupted"
                        state.write("runs", run)
                        break
                state.write("runs", run)
            if run["status"] != "interrupted":
                run["status"] = "finished"
        except (KeyboardInterrupt, SystemExit):
            run["status"] = "interrupted"
            raise
        finally:
            run["ended_at"] = now()
            run["moved_allocated_bytes"] = sum(x["snapshot"]["allocated_bytes"] for x in run["entries"] if x["status"] == "trashed")
            run["free_after_bytes"] = shutil.disk_usage(state.home).free
            run["free_space_delta_bytes"] = run["free_after_bytes"] - free_before
            run["space_note"] = "Trash moves usually do not free blocks; free-space changes include unrelated system activity."
            state.write("runs", run)
        return run


def restore(run_id, state, *, confirmed=False, backend=None, probe=None):
    if not confirmed:
        raise Refused("confirmation_required")
    backend = backend or MoleBackend(state)
    probe = probe or NativeProbe(state.home)
    with state.locked():
        run = state.load("runs", run_id)
        trash = prepare_trash(state.home)
        result = []
        for entry in run["entries"]:
            if entry["status"] not in ["trashed", "moving", "recovery_required"]:
                continue
            src, dest = Path(entry["destination"]), Path(entry["source"])
            record = {"candidate_id": entry["candidate_id"], "status": "skipped"}
            try:
                if src.parent != trash or not src.name.startswith("mac-dev-cleanup-" + run_id + "-"):
                    raise Refused("invalid_receipt_destination")
                if src.resolve() != src or dest.resolve() != dest or not dest.is_relative_to(state.home):
                    raise Refused("restore_path_redirected")
                if dest.exists() or dest.is_symlink():
                    raise Refused("restore_destination_exists")
                if identity(dest.parent) != entry["snapshot"]["parent_identity"]:
                    raise Refused("original_parent_missing_or_changed")
                current = tree_snapshot(src)
                if current["identity"] != entry["snapshot"]["identity"] or current["fingerprint"] != entry["snapshot"]["fingerprint"]:
                    raise Refused("trash_payload_missing_or_changed")
                if probe.idle(src) != "idle":
                    raise Refused("restore_payload_in_use_or_unknown")
                entry["restore_status"] = "restoring"
                state.write("runs", run)
                backend.restore(src, dest)
                entry["status"] = "restored"
                entry["restored_at"] = now()
                record["status"] = "restored"
            except (OSError, Refused) as exc:
                record["reason"] = str(exc) if isinstance(exc, Refused) else type(exc).__name__
            entry["restore_result"] = record
            result.append(record)
            state.write("runs", run)
        return {"run_id": run_id, "results": result}
