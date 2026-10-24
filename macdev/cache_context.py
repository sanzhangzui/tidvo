"""Read-only cache index evidence, bound to plans without exposing raw content."""
import hashlib
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from .safety import Refused, identity


def cache_index(path, *, missing_ok=False):
    p = Path(path)
    if p.resolve() != p:
        raise Refused("cache_index_redirected")
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if missing_ok:
            return {"path": str(p), "missing": True, "parent_identity": identity(p.parent)}
        raise
    with os.fdopen(fd, "rb") as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_size > 1024 * 1024:
            raise Refused("cache_index_unavailable")
        raw = f.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or identity(p) != [s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode), s.st_uid]:
            raise Refused("cache_index_changed")
    origins = set()
    unknown = False
    for value in re.findall(rb'[A-Za-z][A-Za-z0-9+.-]*://[^\x00-\x20\x7f-\xff<>"\x27]+', raw):
        try:
            u = urlsplit(value.decode())
            if u.scheme not in ["http", "https"] or not u.hostname:
                unknown = True
                continue
            host = "[" + u.hostname + "]" if ":" in u.hostname else u.hostname
            origins.add(u.scheme + "://" + host + (":" + str(u.port) if u.port else ""))
        except ValueError:
            unknown = True
    return {"path": str(p), "identity": [s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode), s.st_uid],
            "parent_identity": identity(p.parent), "sha256": hashlib.sha256(raw).hexdigest(),
            "origins": sorted(origins), "attributed": len(origins) == 1 and not unknown}


def unchanged_cache_context(candidate):
    context = candidate.get("cache_context")
    if context and cache_index(context["path"], missing_ok=context.get("missing", False)) != context:
        raise Refused("cache_index_changed")
