"""Private, signed documents and durable write-ahead receipts."""
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import uuid
from pathlib import Path

from .safety import Refused, canonical_json


def private_directory(p):
    p = Path(p)
    if p.resolve() != p:
        raise Refused("state_directory_redirect")
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = p.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise Refused("state_directory_not_private")


class State:
    def __init__(self, home, root=None):
        self.home = Path(home).resolve()
        self.root = Path(root or self.home / ".local/state/mac-dev-cleanup").absolute()
        if not self.root.is_relative_to(self.home):
            raise Refused("state_outside_home")
        private_directory(self.root)
        for name in ["plans", "runs", "upstream-logs"]:
            private_directory(self.root / name)
        key = self.root / "key"
        try:
            fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(os.urandom(32))
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            pass
        self.key = self.read_private(key, binary=True)
        if len(self.key) != 32:
            raise Refused("invalid_state_key")

    def read_private(self, p, binary=False):
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            s = os.fstat(f.fileno())
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077 or s.st_size > 64 * 1024 * 1024:
                raise Refused("untrusted_state_file")
            content = f.read()
        return content if binary else json.loads(content)

    def path(self, kind, identifier):
        if kind not in ["plans", "runs"] or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise Refused("invalid_document_id")
        return self.root / kind / (identifier + ".json")

    def write(self, kind, document):
        p = self.path(kind, document["id"])
        private_directory(p.parent)
        payload = {k: v for k, v in document.items() if k != "signature"}
        payload["signature"] = hmac.new(self.key, canonical_json(payload), hashlib.sha256).hexdigest()
        temp = p.with_name("." + uuid.uuid4().hex)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(canonical_json(payload))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, p)
        directory = os.open(p.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return p

    def load(self, kind, identifier):
        p = self.path(kind, identifier)
        private_directory(p.parent)
        d = self.read_private(p)
        signature = d.pop("signature", "")
        expected = hmac.new(self.key, canonical_json(d), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or d.get("id") != identifier or d.get("home") != str(self.home):
            raise Refused("document_tampered_or_wrong_home")
        return d

    @contextlib.contextmanager
    def locked(self):
        private_directory(self.root)
        fd = os.open(self.root / "operation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            s = os.fstat(fd)
            if s.st_uid != os.getuid() or s.st_mode & 0o077:
                raise Refused("untrusted_lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused("another_operation_in_progress") from None
            yield
        finally:
            os.close(fd)

    def history(self):
        result = []
        for p in sorted((self.root / "runs").glob("*.json"), reverse=True):
            result.append(self.load("runs", p.stem))
        return sorted(result, key=lambda x: x.get("started_at", ""), reverse=True)
