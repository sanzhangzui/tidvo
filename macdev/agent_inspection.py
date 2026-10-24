"""Metadata-only Agent inventory plus a fail-closed filesystem protection policy."""
import json
import os
import plistlib
import re
import stat
import time
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from .agent_catalog import (CATALOG, CATALOG_VERSION, EDITOR_EXTENSION_ROOTS, EDITOR_SUPPORT_NAMES,
                            UNKNOWN_MARKERS, config_sources, expand_path)
from .safety import Refused

CACHE_RULES = {"project.__pycache__", "project.pytest_cache", "project.mypy_cache", "project.ruff_cache"}
RESOURCE_KEYS = {"sessiondir", "memorydirectory", "automemorydirectory", "workspace", "workspacedir", "worktreeroot", "skills", "extensions", "prompts"}
SECRET_KEYS = {"env", "headers", "token", "apikey", "api_key", "password", "secret", "credentials", "authorization"}


def read_config(path):
    """Only called for explicit configuration/extension manifests, never auth/db/history."""
    p = Path(path)
    if p.resolve() != p:
        raise ValueError("configuration_redirected")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_size > 1024 * 1024:
            raise ValueError("configuration_unavailable")
        raw = f.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("configuration_too_large")
    value = tomllib.loads(raw.decode()) if p.suffix == ".toml" else json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("configuration_not_object")
    return value


def data_category(relative):
    parts = [x.lower() for x in Path(relative).parts]
    name = parts[-1] if parts else ""
    if any(x in {"auth.json", ".credentials.json", "credentials", "tokens", "oauth_creds.json"} for x in parts) or name.endswith((".key", ".pem", ".p12", ".pfx")):
        return "credentials"
    if re.search(r"\.(?:db|sqlite|sqlite3)(?:-wal|-shm|-journal)?$", name):
        return "databases"
    if any(x in {"memory", "memories", "memory.md", "soul.md", "user.md", "identity.md", "heartbeat.md", "dreams.md"} for x in parts):
        return "memory"
    if any(x in {"sessions", "projects", "chats", "history", "history.jsonl", "tasks", "transcripts"} for x in parts) or name.endswith((".jsonl", ".history.md", ".history")):
        return "sessions_and_tasks"
    if any(x in {"file-history", "snapshot", "snapshots", "checkpoints", "backups"} for x in parts):
        return "checkpoints"
    if any(x in {"worktrees", "workspace", "workspaces"} for x in parts):
        return "workspaces"
    if any(x in {"browser", "browsers", "profiles", "cookies", "indexeddb", "local storage", "webstorage"} for x in parts):
        return "browser_state"
    if any(x in {"skills", "extensions", "plugins", "prompts", "npm", "git", "node_modules", ".venv", "venv", "models"} for x in parts):
        return "installed_resources"
    if any(x in {"log", "logs", "debug"} for x in parts) or name.endswith(".log"):
        return "diagnostics"
    if any(x in {"cache", "caches", ".cache", "cacheddata", "gpucache", "code cache"} for x in parts):
        return "cache_like_requires_review"
    if name.endswith((".json", ".jsonc", ".yaml", ".yml", ".toml")) or name in {"agents.md", "claude.md", "gemini.md", "qwen.md", "codebuddy.md"}:
        return "configuration"
    return "unclassified_protected"


class AgentPolicy:
    def __init__(self, home, *, environ=None, excludes=()):
        self.home = Path(home).resolve()
        self.environ = os.environ if environ is None else environ
        self.excludes = [Path(x) for x in excludes]
        self.roots = {}
        self.issues = []
        self.fail_closed = False
        self._inspected_projects = set()
        self._pending_projects = set()
        self._resources_loaded = False
        self._discovered = False
        self.tools = {t["id"]: t for t in CATALOG}
        for t in CATALOG:
            for template in t["roots"]:
                try:
                    path, basis = expand_path(template, self.home, self.environ)
                    self.register(t["id"], path, basis)
                except (ValueError, KeyError):
                    self.issues.append({"tool_id": t["id"], "reason": "invalid_agent_directory_override"})
                    self.fail_closed = True
        for name in EDITOR_SUPPORT_NAMES:
            # Shared editor databases and user history are not ordinary page caches.
            self.register("shared_agent_resources", self.home / "Library/Application Support" / name / "User", "shared_editor_userdata")
        self.load_custom_roots()
        self.register_shared_links()

    def register_shared_links(self, paths=None):
        paths = [Path(root["path"]) for root in self.roots.values()] if paths is None else paths
        for path in paths:
            for child in ["skills", "skills/shared", "extensions", "plugins", "prompts"]:
                p = path / child
                if p.is_symlink():
                    self.register("shared_agent_resources", p, "shared_resource_symlink", "resource")

    def register(self, tool_id, path, basis, role="data"):
        path = Path(path)
        forbidden = {self.home, self.home / "Library", self.home / "Library/Application Support", self.home / "Library/Caches",
                     self.home / ".config", self.home / ".local", self.home / ".local/share", self.home / ".npm"}
        if not path.is_absolute() or ".." in path.parts or path in forbidden or not path.is_relative_to(self.home):
            self.issues.append({"tool_id": tool_id, "reason": "agent_root_outside_scoped_home"})
            if basis in {"user_configured", "environment_override", "declared_resource_path"}:
                self.fail_closed = True
            return
        key = (tool_id, str(path))
        self.roots[key] = {"tool_id": tool_id, "path": str(path), "basis": basis, "role": role}

    def load_custom_roots(self):
        config = self.home / ".config/mac-dev-cleanup/config.json"
        if not config.exists() and not config.is_symlink():
            return
        try:
            data = read_config(config).get("agent_roots", {})
            if not isinstance(data, dict):
                raise ValueError("invalid_agent_roots")
            for name, values in data.items():
                if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) or not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                    raise ValueError("invalid_agent_roots")
                if name not in self.tools:
                    self.tools[name] = {"id": name, "name": name, "kind": "user_configured", "source_urls": [],
                                        "layout_evidence": "user_declared", "capabilities": ["read_only_inventory", "protect_data"]}
                for value in values:
                    p, _ = expand_path(value, self.home, {})
                    if not p.is_relative_to(self.home) or p == self.home:
                        raise ValueError("invalid_agent_roots")
                    self.register(name, p, "user_configured")
        except (OSError, ValueError, KeyError):
            self.issues.append({"reason": "invalid_agent_roots_configuration"})
            self.fail_closed = True

    def inspect_project(self, path, names=None):
        p = Path(path)
        if p in self._inspected_projects or not p.is_relative_to(self.home):
            return
        if p.resolve() != p:
            return
        self._inspected_projects.add(p)
        try:
            names = names if names is not None else {x.name for x in p.iterdir()}
            if names & {".pi", ".claude"}:
                self._pending_projects.add(p)
                self._resources_loaded = False
            new_paths = []
            hits = names & UNKNOWN_MARKERS
            if hits and (p.name.startswith(".") or "agent" in p.name.lower() or len(hits) >= 2):
                if not any(p == Path(x["path"]) for x in self.roots.values()):
                    self.register("shared_agent_resources", p, "unknown_agent_marker_match", "unknown")
                    new_paths.append(p)
            for t in CATALOG:
                for relative in t["project"]:
                    if relative.split("/")[0] in names and ((p / relative).exists() or (p / relative).is_symlink()):
                        self.register(t["id"], p / relative, "project_resource")
                        new_paths.append(p / relative)
            self.register_shared_links(new_paths)
        except OSError:
            self.issues.append({"reason": "project_agent_resources_unavailable"})

    def load_resource_paths(self):
        if self._resources_loaded:
            return
        self._resources_loaded = True
        files = [(None, p) for p in config_sources(self.home, self.environ)]
        for project in self._pending_projects:
            files += [(None, project / p) for p in [".pi/settings.json", ".pi/mcp.json", ".claude/settings.json", ".claude/settings.local.json"]]
        self._pending_projects.clear()
        for _, path in files:
            if not path.exists() and not path.is_symlink():
                continue
            try:
                data = read_config(path)
            except (OSError, ValueError):
                self.issues.append({"reason": "agent_resource_config_unavailable", "path": str(path)})
                continue
            def visit(value, key=""):
                if isinstance(value, dict):
                    for k, v in value.items():
                        if k.lower() not in SECRET_KEYS:
                            visit(v, "package_path" if key == "packages" and k.lower() == "source" else k.lower())
                elif isinstance(value, list):
                    for item in value:
                        visit(item, key)
                elif isinstance(value, str) and key in RESOURCE_KEYS | {"packages", "package_path"}:
                    if "://" in value or any(ord(c) < 32 for c in value):
                        return
                    if key in {"packages", "package_path"} and not (value.startswith(("./", "../", "~/")) or Path(value).is_absolute()):
                        return
                    try:
                        if value.startswith("~/") or Path(value).is_absolute():
                            target, _ = expand_path(value, self.home, {})
                        else:
                            target = (path.parent / value).absolute()
                            if ".." in target.parts:
                                target = target.resolve()
                        self.register("shared_agent_resources", target, "declared_resource_path", role="workspace" if "workspace" in key or key == "worktreeroot" else "resource")
                    except (ValueError, OSError):
                        self.issues.append({"reason": "agent_resource_path_unavailable"})
            visit(data)

    def inspect_unknown(self, parent, *, limit=1000, deadline=None):
        try:
            if parent.resolve() != parent:
                self.issues.append({"reason": "unknown_agent_discovery_redirected", "path": str(parent)})
                return
            with os.scandir(parent) as children:
                for index, entry in enumerate(children):
                    if index >= limit or (deadline is not None and time.monotonic() > deadline):
                        self.issues.append({"reason": "unknown_agent_discovery_partial", "path": str(parent)})
                        break
                    p = Path(entry.path)
                    if entry.name in {".ssh", ".aws", ".gnupg", ".git", ".Trash", ".npm", ".config", ".local", ".cache", "Library"} or not entry.is_dir(follow_symlinks=False):
                        continue
                    with os.scandir(p) as items:
                        names = set()
                        for n, item in enumerate(items):
                            if n >= 500 or (deadline is not None and time.monotonic() > deadline):
                                self.issues.append({"reason": "unknown_agent_discovery_partial", "path": str(p)})
                                break
                            names.add(item.name)
                    hits = names & UNKNOWN_MARKERS
                    agent_name = "agent" in entry.name.lower() or entry.name.startswith(".")
                    if hits and (agent_name or len(hits) >= 2):
                        if not any(p == Path(x["path"]) for x in self.roots.values()):
                            self.register("shared_agent_resources", p, "unknown_agent_marker_match", "unknown")
        except FileNotFoundError:
            pass
        except OSError:
            self.issues.append({"reason": "unknown_agent_discovery_unavailable", "path": str(parent)})

    def inspect_extensions(self, *, deadline=None):
        known = {identifier.lower(): t["id"] for t in CATALOG for identifier in t["extensions"]}
        for relative in EDITOR_EXTENSION_ROOTS:
            base = self.home / relative
            if base.resolve() != base:
                continue
            try:
                with os.scandir(base) as entries:
                    for n, entry in enumerate(entries):
                        if n >= 1500 or (deadline is not None and time.monotonic() > deadline):
                            self.issues.append({"reason": "extension_discovery_partial", "path": str(base)})
                            break
                        p = Path(entry.path)
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        try:
                            manifest = read_config(p / "package.json")
                            publisher, name = manifest.get("publisher", ""), manifest.get("name", "")
                            identifier = publisher + "." + name if isinstance(publisher, str) and isinstance(name, str) else ""
                            contributes = manifest.get("contributes", {})
                            agent_capability = isinstance(contributes, dict) and any(k in contributes for k in ["chatParticipants", "languageModelTools", "languageModelToolSets", "mcpServerDefinitionProviders"])
                            owner = known.get(identifier.lower())
                            if owner or agent_capability:
                                self.register(owner or "shared_agent_resources", p, "known_extension_identity" if owner else "unknown_agent_extension_manifest", "installed_extension")
                        except (OSError, ValueError):
                            # Do not turn an unreadable extension into a claim of being unused.
                            continue
            except FileNotFoundError:
                pass
            except OSError:
                self.issues.append({"reason": "extension_discovery_unavailable", "path": str(base)})

    def discover(self, *, deadline=None):
        if self._discovered:
            return
        self._discovered = True
        for base in [self.home, self.home / ".config", self.home / ".local/share", self.home / "Library/Application Support"]:
            self.inspect_unknown(base, deadline=deadline)
        self.inspect_extensions(deadline=deadline)
        self.register_shared_links()

    def worktree_roots(self):
        roots = []
        for template in ["${CODEX_HOME}/worktrees", "${CLAUDE_CONFIG_DIR}/worktrees", "~/.cursor/worktrees"]:
            try:
                p, _ = expand_path(template, self.home, self.environ)
                if p.is_relative_to(self.home):
                    roots.append(p)
            except ValueError:
                continue
        return roots

    def protection_for(self, path, rule, cache_context=None):
        p = Path(path)
        if self.fail_closed:
            return {"reason": "agent_protection_configuration_incomplete", "tool_ids": []}
        # Discover newly added project markers at apply time, including unknown agents.
        parent = p.parent
        while parent != self.home and parent.is_relative_to(self.home):
            self.inspect_project(parent)
            parent = parent.parent
        self.load_resource_paths()
        if self.fail_closed:
            return {"reason": "agent_protection_configuration_incomplete", "tool_ids": []}
        matches = []
        for root in self.roots.values():
            original = Path(root["path"])
            try:
                physical = original.resolve()
            except (OSError, RuntimeError):
                physical = original
            overlap = any(p == r or p.is_relative_to(r) or r.is_relative_to(p) for r in {original, physical})
            if not overlap:
                continue
            builtin = root["basis"] in {"registered_location", "environment_override"} and root["role"] == "data"
            if builtin and root["tool_id"] == "codex" and rule == "agent.codex_old_release" and p.parent.name == "releases" and p.parent.parent.name == "app-server-daemon":
                continue  # Existing current/update/lock checks still apply; no new cleanup authority.
            if builtin and root["tool_id"] in {"codex", "claude_code", "cursor"} and rule in CACHE_RULES and any(p.is_relative_to(r) for r in self.worktree_roots()):
                continue
            if root["role"] == "workspace" and rule in CACHE_RULES and p.is_relative_to(original):
                continue
            if builtin and root["tool_id"] == "feishu" and rule == "app.site_cache" and cache_context and cache_context.get("attributed"):
                if p.is_relative_to(original) and p.parent.parent.name == "CacheStorage" and p.parent.parent.parent.name == "Service Worker":
                    continue  # The separately reviewed 0.1.2 cache-leaf rule remains available.
            matches.append(root["tool_id"])
        return {"reason": "agent_data_protected", "tool_ids": sorted(set(matches))} if matches else None

    def app_versions(self):
        found = defaultdict(list)
        for t in CATALOG:
            for app in t["apps"]:
                for parent in [self.home / "Applications", Path("/Applications")]:
                    p = parent / (app + ".app") / "Contents/Info.plist"
                    try:
                        if p.is_symlink() or not p.is_file() or p.stat().st_size > 1024 * 1024:
                            continue
                        with p.open("rb") as file:
                            raw = file.read(1024 * 1024 + 1)
                        if len(raw) > 1024 * 1024:
                            continue
                        data = plistlib.loads(raw)
                        if not isinstance(data, dict):
                            continue
                        version = data.get("CFBundleShortVersionString", "unknown")
                        if not isinstance(version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,79}", version):
                            version = "unknown"
                        found[t["id"]].append({"path": str(p.parent.parent), "version": version, "source": "Info.plist"})
                    except (OSError, ValueError, plistlib.InvalidFileException):
                        continue
        return found

    def audit(self, *, deadline=None, limit=100000, include_apps=True, probe=None):
        deadline = deadline or time.monotonic() + 30
        self.load_resource_paths()
        self.discover(deadline=deadline)
        versions = self.app_versions() if include_apps else {}
        observed = []
        measured_roots = {}
        globally_seen = set()
        unique_bytes = 0
        visited = 0
        for root in sorted(self.roots.values(), key=lambda x: (len(Path(x["path"]).parts), x["path"], x["tool_id"])):
            p = Path(root["path"])
            if any(p == x or p.is_relative_to(x) for x in self.excludes):
                continue
            try:
                p.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                observed.append(dict(root, action="report_only", protection="preserve_agent_data", scan_status="unavailable", allocated_bytes=None, reason="agent_metadata_unavailable"))
                continue
            try:
                physical = p.resolve(strict=True)
                row = dict(root, resolved_path=str(physical), via_symlink=physical != p, action="report_only", protection="preserve_agent_data")
                if not physical.is_relative_to(self.home):
                    row.update(scan_status="unavailable", allocated_bytes=None, reason="agent_root_outside_scoped_home")
                    observed.append(row)
                    continue
                if physical in measured_roots:
                    row.update(measured_roots[physical], shared_measurement=True)
                    observed.append(row)
                    continue
                stack = [physical]
                local_seen = set()
                categories = Counter()
                total = 0
                status = "complete"
                reason = None
                root_deadline = min(deadline, time.monotonic() + 5)
                device = physical.stat().st_dev
                while stack:
                    if time.monotonic() > root_deadline or visited >= limit:
                        status, reason = "partial", "agent_inventory_budget_exceeded"
                        break
                    q = stack.pop()
                    if any(q == x or q.is_relative_to(x) for x in self.excludes):
                        continue
                    try:
                        s = q.lstat()
                        visited += 1
                        if s.st_uid != os.getuid() or s.st_dev != device:
                            status, reason = "partial", "agent_metadata_unavailable"
                            continue
                        inode = (s.st_dev, s.st_ino)
                        if inode not in local_seen:
                            amount = getattr(s, "st_blocks", 0) * 512
                            total += amount
                            categories[data_category(Path(physical.name) / q.relative_to(physical))] += amount
                            local_seen.add(inode)
                            if inode not in globally_seen:
                                unique_bytes += amount
                                globally_seen.add(inode)
                        if stat.S_ISDIR(s.st_mode):
                            with os.scandir(q) as entries:
                                for entry in entries:
                                    if len(stack) + visited >= limit or time.monotonic() > root_deadline:
                                        status, reason = "partial", "agent_inventory_budget_exceeded"
                                        break
                                    stack.append(Path(entry.path))
                    except OSError:
                        status, reason = "partial", "agent_metadata_unavailable"
                measurement = {"scan_status": status, "allocated_bytes": total, "categories": dict(categories), "bytes_are_lower_bound": status != "complete"}
                if reason:
                    measurement["reason"] = reason
                measured_roots[physical] = measurement
                row.update(measurement)
                observed.append(row)
            except (OSError, RuntimeError):
                observed.append(dict(root, action="report_only", protection="preserve_agent_data", scan_status="unavailable", allocated_bytes=None, reason="agent_metadata_unavailable"))
        tools = []
        for identifier, t in self.tools.items():
            roots = [r for r in observed if r["tool_id"] == identifier]
            if roots or versions.get(identifier):
                aliases = {"claude_code": "claude", "gemini_cli": "gemini", "qwen_code": "qwen", "kimi": "kimi", "pi": "pi", "copilot": "copilot"}
                name = aliases.get(identifier, identifier)
                matched = []
                rows = getattr(probe, "rows", None)
                if rows is not None:
                    patterns = [r"(?:^|[/\s])" + re.escape(name) + r"(?:$|[\s])"] + [re.escape("/" + app + ".app/") for app in t.get("apps", [])]
                    matched = [line.strip().split()[0] for line in rows if any(re.search(pattern, line, re.I) for pattern in patterns) and line.strip().split()[0].isdigit()]
                tools.append({k: t.get(k) for k in ["id", "name", "kind", "layout_evidence", "source_urls", "capabilities"]} |
                             {"roots": roots, "app_bundles": versions.get(identifier, []), "installation_state": "data_or_app_observed_not_runtime_certification",
                              "activity": "observed_process" if matched else ("not_observed" if rows is not None else "unknown"), "matched_pids": sorted(set(matched))})
        return {"schema_version": 1, "home": str(self.home), "excludes": [str(p) for p in self.excludes], "catalog_version": CATALOG_VERSION, "catalog_entries": len(CATALOG),
                "detected_tools": tools, "scan_status": "partial" if self.issues or any(x["scan_status"] != "complete" for x in observed) else "complete",
                "issues": self.issues, "total_unique_allocated_bytes": unique_bytes, "metadata_entries_visited": visited,
                "action": "report_only", "notes": ["Inventory creates no cleanup candidates or deletion authority.",
                "Sizes are metadata estimates; shared inodes are counted once in the unique total. Partial sizes are lower bounds.",
                "No credentials, transcript bodies or database contents are read; no agent binary, hook, SQL connection or remote API is invoked.",
                "Name/location hints are conservative, not proof of installation, idleness, complete coverage, or supported cleanup.",
                "No matching process does not establish that background, scheduled or remote work has ended."]}
