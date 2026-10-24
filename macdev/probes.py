"""Bounded, read-only process and configuration evidence. Never expose argv."""
import os
import re
import subprocess
from pathlib import Path

from .agent_catalog import config_sources
from .agent_inspection import read_config
from .occupancy import check_occupancy


def command(args, timeout=10):
    try:
        env = dict(os.environ, COREPACK_ENABLE_DOWNLOAD_PROMPT="0", COREPACK_ENABLE_NETWORK="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
        if args and args[0] == "git":
            for name in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"]:
                env.pop(name, None)
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None


class NativeProbe:
    def __init__(self, home):
        self.home = Path(home)
        self.rows = None
        self.references = set()
        self.reference_status = "complete"
        self.config_paths = set()
        self.last_occupancy_evidence = {}
        self.refresh()

    def refresh(self):
        r = command(["/bin/ps", "-axo", "pid=,command="], 5)
        self.rows = r.stdout.splitlines() if r is not None and r.returncode == 0 and not r.stderr.strip() else None
        self.references = set()
        self.reference_status = "complete"
        self._references()

    def owner_cache_paths(self):
        found = []
        for args in [["uv", "cache", "dir"], ["pnpm", "store", "path"], ["npm", "config", "get", "cache"]]:
            r = command(args, 3)
            if r is not None and r.returncode == 0 and "\n" not in r.stdout.strip():
                value = Path(r.stdout.strip())
                if value.is_absolute() and value.is_relative_to(self.home) and value.exists():
                    found.append((args[0], value / "_cacache" if args[0] == "npm" else value))
        return found

    def _references(self):
        files = config_sources(self.home)
        files += sorted(self.config_paths)
        def visit(value, key=""):
            if isinstance(value, dict):
                for k, v in value.items():
                    if k.lower() not in ["env", "headers", "token", "apikey", "api_key", "password", "secret"]:
                        visit(v, k.lower())
            elif isinstance(value, list):
                for v in value:
                    visit(v, key)
            elif isinstance(value, str) and key in ["command", "args", "cwd", "path", "workspace", "workspaces", "projects"]:
                self.references.add(value)
        for f in files:
            if not f.exists():
                continue
            try:
                if f.resolve() != f or f.stat().st_size > 1024 * 1024:
                    raise ValueError("unsupported_config")
                value = read_config(f)
                visit(value)
            except (OSError, ValueError):
                self.reference_status = "partial"

    def include_project_configs(self, root):
        self.config_paths.update([Path(root) / x for x in [".mcp.json", ".vscode/mcp.json", ".pi/mcp.json", ".pi/settings.json", ".cursor/mcp.json", ".gemini/settings.json", ".qwen/settings.json"]])
        self._references()

    def evidence(self, path, owner="", packages=()):
        if self.rows is None:
            activity = "unknown"
            pids = []
        else:
            tokens = [str(path)]
            if owner:
                tokens.append("/" + owner + ".app/")
                if owner in ["Feishu", "Lark"]:
                    tokens += ["/Feishu.app/", "/Lark.app/"]
                if owner == "idea":
                    tokens += ["/IntelliJ IDEA.app/", "/PyCharm.app/"]
            package_tokens = [re.compile(r"(?<![\w.-])" + re.escape(x) + r"(?:@[\w.^~-]+)?(?=$|[\s/])") for x in packages]
            rows = [line for line in self.rows if any(t.lower() in line.lower() for t in tokens)
                    or any(t.search(line) for t in package_tokens)]
            # The crash reporter alone is not an active editor/browser session.
            rows = [line for line in rows if "chrome_crashpad_handler" not in line]
            pids = [line.strip().split()[0] for line in rows]
            activity = "active" if rows else "idle"
        referenced = any(str(path) in ref or any(p == ref.split("@", 1)[0] or p in ref for p in packages)
                         for ref in self.references)
        return {"activity": activity, "matched_pids": pids, "configured_reference": referenced,
                "reference_scan_status": self.reference_status,
                "reference_note": "known configuration adapters only; no match does not prove future non-use"}

    def idle(self, path, *, rule_id=None):
        self.last_occupancy_evidence = check_occupancy(path, self.home, command, rule_id)
        return self.last_occupancy_evidence["status"]


def git_evidence(path):
    p = Path(path)
    r = command(["git", "-C", str(p.parent), "rev-parse", "--show-toplevel"], 5)
    if r is None:
        return "unknown"
    if r.returncode != 0:
        return "not_a_repository" if "not a git repository" in r.stderr else "unknown"
    repo = Path(r.stdout.strip()).resolve()
    if not p.is_relative_to(repo):
        return "unknown"
    # Git index only, not status: no index refresh writes during discovery.
    r = command(["git", "-C", str(repo), "ls-files", "--", str(p.relative_to(repo))], 10)
    if r is None or r.returncode:
        return "unknown"
    return "tracked" if r.stdout.strip() else "untracked"
