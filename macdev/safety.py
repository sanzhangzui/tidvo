"""Filesystem policy shared by discovery, planning, execution and restore."""
import hashlib
import json
import os
import stat
import time
from pathlib import Path

from .agent_catalog import PROTECTED_AGENT_NAMES


class Refused(RuntimeError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def identity(path):
    s = Path(path).lstat()
    return [s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode), s.st_uid]


def ordinary_path(path, home):
    p = Path(path)
    home = Path(home)
    if not p.is_absolute() or ".." in p.parts or any(ord(c) < 32 or ord(c) == 127 for c in str(p)):
        raise Refused("invalid_path")
    if not p.is_relative_to(home) or p == home:
        raise Refused("outside_home")
    if p.resolve() != p:
        raise Refused("symlink_or_ancestor_redirect")
    if p in [home / "Library", home / "Library/Caches", home / "Library/Application Support", home / ".npm"]:
        raise Refused("shared_root")
    relative = p.relative_to(home)
    if relative.parts[0] in [".ssh", ".aws", ".gnupg", ".Trash"]:
        raise Refused("protected_root")
    if p.lstat().st_uid != os.getuid():
        raise Refused("foreign_owner")
    if not (p.is_dir() or p.is_file()):
        raise Refused("unsupported_file_type")
    return p


def tree_snapshot(path, *, limit=250000, deadline=None):
    """Do not follow payload symlinks; include their identity and link text.

    Metadata fingerprints detect ordinary intervening changes, not adversarial
    writes by another process with the same UID. Hard-linked blocks count once;
    APFS clone sharing cannot be established with this portable traversal.
    """
    root = Path(path)
    deadline = deadline or time.monotonic() + 30
    digest = hashlib.sha256()
    stack = [root]
    seen = set()
    size = 0
    logical = 0
    count = 0
    sensitive = []
    while stack:
        if time.monotonic() > deadline or count >= limit:
            raise Refused("snapshot_budget_exceeded")
        p = stack.pop()
        s = p.lstat()
        count += 1
        if s.st_uid != os.getuid() or s.st_dev != root.lstat().st_dev:
            raise Refused("foreign_owner_or_nested_mount")
        rel = str(p.relative_to(root))
        link = os.readlink(p) if stat.S_ISLNK(s.st_mode) else ""
        digest.update(canonical_json([rel, s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_size, s.st_mtime_ns, link]))
        key = (s.st_dev, s.st_ino)
        if key not in seen:
            size += getattr(s, "st_blocks", 0) * 512
            logical += s.st_size
            seen.add(key)
        database = any(p.name.lower().endswith(suffix) for suffix in [".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".db-journal", ".sqlite-wal", ".sqlite-shm", ".sqlite-journal", ".sqlite3-wal", ".sqlite3-shm", ".sqlite3-journal"])
        if p.name in PROTECTED_AGENT_NAMES | {".git", ".env", "LocalHistory", "shelf"} or p.name.startswith(".env.") or p.suffix in [".key", ".pem", ".p12", ".pfx"] or database:
            sensitive.append(rel)
        if stat.S_ISDIR(s.st_mode):
            with os.scandir(p) as entries:
                stack.extend(sorted((Path(e.path) for e in entries), key=str, reverse=True))
        elif not (stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode)):
            raise Refused("special_payload_file")
    return {"identity": identity(root), "parent_identity": identity(root.parent), "fingerprint": digest.hexdigest(),
            "allocated_bytes": size, "logical_bytes": logical, "entries": count, "sensitive": sensitive,
            "size_note": "allocated estimate; hard links deduplicated per candidate; APFS clones may share blocks"}


def unchanged(path, snapshot):
    p = Path(path)
    if identity(p.parent) != snapshot["parent_identity"]:
        raise Refused("parent_identity_changed")
    current = tree_snapshot(p)
    if current["identity"] != snapshot["identity"] or current["fingerprint"] != snapshot["fingerprint"]:
        raise Refused("target_changed")
    return current


def observe_usage(path, *, limit=50000, deadline=None):
    """Metadata-only measurement, independent of permission to move the tree.

    Foreign-owned readable metadata may contribute size; it never authorizes
    mutation. Do not follow symlinks or nested mounts, or read file bodies.
    """
    root = Path(path)
    deadline = deadline or time.monotonic() + 3
    stack, seen, count, total, foreign, gaps = [root], set(), 0, 0, 0, set()
    try:
        if root.resolve() != root:
            raise Refused("redirected_measurement_root")
        device = root.lstat().st_dev
    except (OSError, Refused):
        return {"status": "unavailable", "allocated_bytes": None, "lower_bound": False, "issues": ["measurement_root_unavailable"]}
    while stack:
        if count >= limit or time.monotonic() > deadline:
            gaps.add("measurement_budget_exceeded")
            break
        p = stack.pop()
        try:
            s = p.lstat()
            count += 1
            if s.st_dev != device:
                gaps.add("nested_mount_not_measured")
                continue
            key = s.st_dev, s.st_ino
            if key not in seen:
                total += getattr(s, "st_blocks", 0) * 512
                foreign += s.st_uid != os.getuid()
                seen.add(key)
            if stat.S_ISDIR(s.st_mode):
                with os.scandir(p) as entries:
                    stack.extend(Path(e.path) for e in entries)
        except OSError:
            gaps.add("metadata_unreadable")
    known = total if count and (total or not gaps) else None
    return {"status": "partial" if gaps else "complete", "allocated_bytes": known,
            "lower_bound": bool(gaps) and known is not None, "foreign_owned_entries": foreign,
            "metadata_entries": count, "issues": sorted(gaps)}


def deduplicate(items):
    ordered = sorted(items, key=lambda x: (len(Path(x["path"]).parts), x["path"], x["rule_id"]))
    selected = []
    for item in ordered:
        p = Path(item["path"])
        if any(p == Path(x["path"]) or p.is_relative_to(Path(x["path"])) for x in selected):
            continue
        selected.append(item)
    return sorted(selected, key=lambda x: x["path"])
