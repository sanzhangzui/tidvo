#!/usr/bin/env python3
"""Build a self-contained GPLv3 skill archive; never upload or install it."""
import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from macdev import __version__


def build(output=None):
    output = Path(output or ROOT / "dist")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ("tidvo-" + __version__ + ".tar.gz")
    allowed = ["SKILL.md", "README.md", "README.zh-CN.md", "INSTALL.md", "UPSTREAM.md", "LICENSE", "macdev", "scripts", "references", "agents", "tests", "vendor/mole"]
    members = set()
    for relative in allowed:
        p = ROOT / relative
        members.add(p)
        if p.is_dir():
            members.update(p.rglob("*"))
    with tarfile.open(archive, "w:gz") as tar:
        for p in sorted(members):
            relative = p.relative_to(ROOT)
            upstream_fixture = relative.parts[:3] == ("vendor", "mole", "tests") and len(relative.parts) > 3 and relative.parts[3].startswith("tmp-")
            upstream_agent_files = relative.parts[:2] == ("vendor", "mole") and len(relative.parts) > 2 and relative.parts[2] in {".agents", ".claude", ".claude-plugin", "plugins", "skills", "AGENTS.md", "CLAUDE.md"}
            if upstream_agent_files or upstream_fixture or "__pycache__" in relative.parts or p.suffix in [".pyc", ".pyo"] or "docs/img" in str(relative) or ".git" in relative.parts:
                continue
            if p.is_symlink() and not p.resolve().is_relative_to(ROOT):
                raise RuntimeError("external symlink cannot be packaged")
            info = tar.gettarinfo(str(p), arcname="tidvo/" + str(relative))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if p.is_file() and not p.is_symlink():
                with p.open("rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(digest + "  " + archive.name + "\n")
    return {"archive": str(archive), "sha256": digest, "bytes": archive.stat().st_size,
            "note": "local package only; no upload or installation performed"}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
