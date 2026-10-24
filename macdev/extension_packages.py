"""An obsolete Agent program package needs positive replacement/scope evidence."""
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

from .safety import Refused, tree_snapshot

STATE_NAMES = {"sessions", "session", "memory", "memories", "history", "conversations", "checkpoints",
               "workspaces", "userdata", "user-data", "globalstorage", "workspacestorage"}


def metadata(path):
    p = Path(path)
    if p.resolve() != p:
        raise Refused("extension_metadata_redirected")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_size > 1024 * 1024:
            raise Refused("extension_metadata_unavailable")
        raw = f.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise Refused("extension_metadata_budget_exceeded")
    return json.loads(raw), {"path": str(p), "identity": [s.st_dev, s.st_ino], "sha256": hashlib.sha256(raw).hexdigest()}


def identifier(manifest):
    publisher, name = manifest.get("publisher"), manifest.get("name")
    if not all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in (publisher, name)):
        raise Refused("extension_identity_invalid")
    return (publisher + "." + name).lower()


def version(manifest):
    value = manifest.get("version", "")
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise Refused("extension_version_not_comparable")
    return tuple(map(int, value.split(".")))


def obsolete_context(path, home):
    p, home = Path(path), Path(home)
    base = home / ".vscode/extensions"
    if p.parent != base or p.resolve() != p or not p.is_dir():
        raise Refused("extension_package_path_invalid")
    obsolete, obsolete_meta = metadata(base / ".obsolete")
    registry, registry_meta = metadata(base / "extensions.json")
    manifest, manifest_meta = metadata(p / "package.json")
    if not isinstance(obsolete, dict) or not isinstance(registry, list) or not isinstance(manifest, dict):
        raise Refused("extension_inventory_invalid")
    if obsolete.get(p.name) is not True:
        raise Refused("extension_not_obsolete")
    identity, old_version = identifier(manifest), version(manifest)
    replacement = None
    for item in registry:
        if not isinstance(item, dict):
            raise Refused("extension_registry_invalid")
        name = item.get("relativeLocation")
        if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
            raise Refused("extension_registry_path_invalid")
        if name == p.name:
            raise Refused("extension_still_registered")
        # Only matching identities matter; never execute extension/owner code.
        declared = item.get("identifier", {})
        declared_id = declared.get("id", "") if isinstance(declared, dict) else ""
        if declared_id and str(declared_id).lower() != identity:
            continue
        try:
            current, current_meta = metadata(base / name / "package.json")
            if not isinstance(current, dict) or identifier(current) != identity or version(current) <= old_version:
                continue
            if item.get("version") is not None and item["version"] != current.get("version"):
                raise Refused("extension_replacement_version_mismatch")
            replacement = {"directory": name, "version": current["version"], "manifest": current_meta}
            break
        except FileNotFoundError:
            continue
    if replacement is None:
        raise Refused("extension_newer_registered_replacement_missing")
    snapshot = tree_snapshot(p)
    if snapshot["sensitive"]:
        raise Refused("extension_payload_contains_sensitive_state")
    # Look only at names/metadata, never session/credential contents.
    deadline, visited = time.monotonic() + 5, 0
    for parent, dirs, files in os.walk(p, followlinks=False):
        visited += len(dirs) + len(files)
        if visited > 250000 or time.monotonic() > deadline:
            raise Refused("extension_state_check_incomplete")
        if any(name.lower() in STATE_NAMES or name.lower().endswith((".jsonl", ".history")) for name in dirs + files):
            raise Refused("extension_payload_contains_persistent_state")
    return {"identity": identity, "old_version": manifest["version"], "replacement": replacement,
            "obsolete": obsolete_meta, "registry": registry_meta, "manifest": manifest_meta,
            "package_fingerprint": snapshot["fingerprint"], "scope": "obsolete_program_package_without_known_user_state"}


def unchanged_extension(candidate, home):
    context = candidate.get("extension_context")
    if context and obsolete_context(candidate["path"], home) != context:
        raise Refused("extension_replacement_or_package_changed")
