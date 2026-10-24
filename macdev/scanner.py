"""Declarative discovery with explicit uncertainty; no cleanup commands."""
import hashlib
import json
import os
import re
import time
import tomllib
from collections import deque
from pathlib import Path

from .cache_context import cache_index
from .agent_inspection import AgentPolicy
from .probes import NativeProbe, git_evidence
from .safety import Refused, canonical_json, deduplicate, ordinary_path, tree_snapshot

PROJECT_MARKERS = {"package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Package.swift", ".git"}
ARTIFACTS = {"node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".nuxt", ".turbo", "dist", "build", "target", ".gradle", ".build", ".cxx", ".expo"}
DEPENDENCY_ARTIFACTS = {"node_modules", ".venv", "venv"}
DEPENDENCY_RULES = {"project." + name.lstrip(".") for name in DEPENDENCY_ARTIFACTS}
PROJECT_DISCOVERY_DEPTH = 6
PROJECT_DISCOVERY_LIMIT = 20000
CACHE_NAMES = {"Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache", "GrShaderCache", "GraphiteDawnCache"}
APPS = {"Code": "Visual Studio Code", "obsidian": "Obsidian", "baidunetdisk": "BaiduNetdisk_mac", "Juzhenyun": "Juzhenyun", "juzhenyun-desktop": "Electron", "electron-adb-tool": "Electron", "pgAdmin 4": "pgAdmin 4", "GitHub Desktop": "GitHub Desktop", "Postman": "Postman"}
TOOL_PURPOSES = {"n8n": "workflow automation", "react-native": "mobile development", "electron-builder": "desktop app packaging", "hyperframes": "HTML video rendering", "rea-agents": "reverse engineering CLI/MCP", "chrome-devtools-mcp": "browser developer tools MCP", "@playwright/mcp": "browser automation MCP", "@modelcontextprotocol/server-puppeteer": "browser automation MCP", "@modelcontextprotocol/server-memory": "MCP memory service", "@modelcontextprotocol/server-filesystem": "MCP filesystem service", "@upstash/context7-mcp": "documentation MCP"}


def read_json(path):
    p = Path(path)
    if p.resolve() != p or p.stat().st_size > 1024 * 1024:
        raise ValueError("metadata_not_regular_or_too_large")
    return json.loads(p.read_text())


class Scanner:
    def __init__(self, home=None, roots=None, excludes=(), probe=None, budget=120):
        self.started = time.monotonic()
        self.home = Path(home or Path.home()).resolve()
        self.roots = [Path(x).expanduser().absolute() for x in (roots or [])]
        self.excludes = [Path(x).expanduser().absolute() for x in excludes]
        self.probe = probe or NativeProbe(self.home)
        self.deadline = time.monotonic() + budget
        self.items = []
        self.issues = []
        self.project_roots = []
        self.agent_policy = AgentPolicy(self.home, excludes=self.excludes)
        self.agent_policy.discover(deadline=self.deadline)

    def children(self, p):
        if time.monotonic() > self.deadline:
            raise Refused("scan_budget_exceeded")
        try:
            p.lstat()
        except FileNotFoundError:
            return []
        except OSError:
            self.issues.append({"path": str(p), "reason": "unreadable"})
            return []
        if p.resolve() != p:
            self.issues.append({"path": str(p), "reason": "symlink_not_followed"})
            return []
        try:
            return sorted(p.iterdir(), key=str)
        except OSError:
            self.issues.append({"path": str(p), "reason": "unreadable"})
            return []

    def excluded(self, p):
        return any(p == x or p.is_relative_to(x) for x in self.excludes)

    def add(self, p, rule, group, *, owner="", packages=(), notes=(), report_only=False, project=False, package_details=(), cache_context=None):
        if not p.exists() or self.excluded(p):
            return
        item = {"id": hashlib.sha256(canonical_json([rule, str(p)])).hexdigest()[:24], "path": str(p),
                "rule_id": rule, "group": group, "owner": owner, "packages": list(packages),
                "package_details": list(package_details),
                "evidence": list(notes), "scan_status": "complete", "action": "trash", "recommendation": "review"}
        if cache_context:
            item["cache_context"] = cache_context
        protection = self.agent_policy.protection_for(p, rule, cache_context)
        if protection:
            report_only = True
            item["agent_protection"] = protection
            item["evidence"].append(protection["reason"])
        try:
            ordinary_path(p, self.home)
            item["snapshot"] = tree_snapshot(p, deadline=min(self.deadline, time.monotonic() + 30))
            item["allocated_bytes"] = item["snapshot"]["allocated_bytes"]
            item["activity"] = self.probe.evidence(p, owner, packages)
            if project:
                item["git_status"] = git_evidence(p)
                if item["git_status"] in ["tracked", "unknown"]:
                    report_only = True
                    item["evidence"].append("git_tracked_or_index_unavailable")
            if item["snapshot"]["sensitive"]:
                report_only = True
                item["evidence"].append("nested_repository_or_sensitive_file")
            if item["activity"]["activity"] != "idle" or item["activity"]["configured_reference"]:
                report_only = True
            if packages and item["activity"]["reference_scan_status"] != "complete":
                report_only = True
            if report_only:
                item["action"] = "report_only"
        except (OSError, ValueError, Refused) as exc:
            item.update(scan_status="unavailable", action="report_only", allocated_bytes=None,
                        evidence=item["evidence"] + [str(exc) if isinstance(exc, Refused) else type(exc).__name__])
            self.issues.append({"path": str(p), "reason": item["evidence"][-1]})
        self.items.append(item)

    def projects(self, *, discover_only=False):
        for p in self.roots:
            if not p.exists():
                self.issues.append({"path": str(p), "reason": "configured_root_missing_or_unreadable"})
        starts = self.roots or [p for p in self.children(self.home) if p.is_dir() and not p.name.startswith(".") and p.name not in ARTIFACTS | {"Library", "Applications", "Pictures", "Movies", "Music", "Public"}]
        if not self.roots:
            starts += self.agent_policy.worktree_roots()
        queue = deque((p, 0, set()) for p in starts if p.exists())
        seen = set()
        while queue:
            if len(seen) >= PROJECT_DISCOVERY_LIMIT:
                raise Refused("project_directory_budget_exceeded")
            p, depth, inherited = queue.popleft()
            if p in seen or self.excluded(p) or p.is_symlink():
                continue
            seen.add(p)
            if not p.is_relative_to(self.home) or p == self.home or p.is_relative_to(self.home / "Library"):
                self.issues.append({"path": str(p), "reason": "project_root_outside_allowed_scope"})
                continue
            if any(part in DEPENDENCY_ARTIFACTS for part in p.relative_to(self.home).parts):
                self.issues.append({"path": str(p), "reason": "project_root_inside_dependency_environment"})
                continue
            children = self.children(p)
            names = {x.name for x in children}
            self.agent_policy.inspect_project(p, names)
            project = bool(names & PROJECT_MARKERS)
            markers = inherited | (names & PROJECT_MARKERS)
            if project:
                self.project_roots.append(str(p))
                self.probe.include_project_configs(p)
            for child in children:
                if not child.is_dir() or child.is_symlink():
                    continue
                if child.name in ARTIFACTS:
                    if inherited or project:
                        marker = "recognized_project_artifact"
                        report = False
                        supported = {
                            "node_modules": {"package.json"}, ".next": {"package.json"}, ".nuxt": {"package.json"},
                            ".turbo": {"package.json"}, ".expo": {"package.json"}, ".cxx": {"package.json", "build.gradle", "build.gradle.kts"},
                            "target": {"Cargo.toml", "pom.xml"}, ".gradle": {"build.gradle", "build.gradle.kts"},
                            ".build": {"Package.swift"}, "dist": {"package.json", "pyproject.toml"},
                            "build": {"package.json", "pyproject.toml", "build.gradle", "build.gradle.kts"},
                        }
                        if child.name in supported and not markers & supported[child.name]:
                            report = True
                            marker = "artifact_type_not_confirmed_by_project"
                        if child.name in [".venv", "venv"]:
                            report = not (child / "pyvenv.cfg").is_file() or not bool(names & {"uv.lock", "poetry.lock", "requirements.txt", "Pipfile.lock"})
                            marker = "virtualenv_with_rebuild_manifest" if not report else "virtualenv_rebuild_not_proven"
                        notes = [marker]
                        if child.name in DEPENDENCY_ARTIFACTS:
                            report = True
                            notes.append("project_dependency_environment_preserved")
                        if not discover_only:
                            self.add(child, "project." + child.name.lstrip("."), "projects", notes=notes, report_only=report, project=True)
                    continue
                if depth < PROJECT_DISCOVERY_DEPTH and child.name not in {".git", ".ssh", ".aws", "Library"} and (not child.name.startswith(".") or child.name == ".agents"):
                    queue.append((child, depth + 1, markers))

    def developer(self):
        for p in self.children(self.home / ".npm/_prebuilds"):
            archive = p.is_file() and not p.is_symlink() and re.fullmatch(r"[a-fA-F0-9]{6,64}-.+\.(?:tar\.gz|tgz|tar\.xz|zip)", p.name)
            self.add(p, "developer.npm_prebuild", "package_managers", packages=["npm"],
                     notes=["downloaded_native_module_archive", "may_need_download_for_next_native_install"] if archive else ["unrecognized_prebuild_entry"],
                     report_only=not archive)
        for p in self.children(self.home / ".npm/_npx"):
            if not p.is_dir():
                continue
            try:
                d = read_json(p / "package.json")
                if not isinstance(d, dict):
                    raise ValueError("invalid_package_metadata")
                declared = d.get("dependencies", {})
                if not isinstance(declared, dict):
                    raise ValueError("invalid_dependencies")
                packages = [x for x in declared if re.fullmatch(r"(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+", x)]
                details = []
                for name in packages:
                    try:
                        metadata = read_json(p / "node_modules" / name / "package.json")
                        installed = metadata.get("version", "unknown") if isinstance(metadata, dict) else "unknown"
                    except (OSError, ValueError):
                        installed = "unknown"
                    spec = declared[name]
                    details.append({"name": name, "installed_version": installed if isinstance(installed, str) and re.fullmatch(r"[A-Za-z0-9.+_-]{1,80}", installed) else "unknown",
                                    "declared_version": spec if isinstance(spec, str) and re.fullmatch(r"[0-9^~*<>=| .+_-]{1,80}", spec) else "non-semver spec redacted",
                                    "purpose": TOOL_PURPOSES.get(name, "npm tool or dependency; inspect before cleanup")})
            except (OSError, ValueError):
                packages = []
                details = []
            self.add(p, "developer.npx", "agent_tools", packages=packages, package_details=details, notes=["npx_installation_not_download_cache"], report_only=not packages)
        vsix = self.home / "Library/Application Support/Code/CachedExtensionVSIXs"
        for p in self.children(vsix):
            self.add(p, "editor.vsix", "editors", owner="Visual Studio Code", notes=["downloaded_extension_installer"])
        extensions = self.home / ".vscode/extensions"
        try:
            obsolete = read_json(extensions / ".obsolete")
            registered = read_json(extensions / "extensions.json")
            current = {x.get("relativeLocation") for x in registered}
            for p in self.children(extensions):
                if obsolete.get(p.name) is True and p.name not in current and (p / "package.json").is_file():
                    read_json(p / "package.json")
                    self.add(p, "editor.obsolete_extension", "editors", owner="Visual Studio Code", notes=["obsolete_and_not_registered"])
        except (OSError, ValueError, AttributeError):
            if extensions.exists():
                self.issues.append({"path": str(extensions), "reason": "extension_inventory_unavailable"})
        daemon = self.home / ".codex/packages/app-server-daemon"
        if (daemon / "releases").exists():
            try:
                current = (daemon / "current").resolve(strict=True)
                if not current.parent == daemon / "releases":
                    raise ValueError("invalid_daemon_current")
                marker = (daemon / "auto-update-version").read_text().strip()
                if not re.fullmatch(r"[\w.-]+", marker) or not (daemon / "install.lock").is_file():
                    raise ValueError("invalid_daemon_marker_or_lock")
                for p in self.children(daemon / "releases"):
                    if p.is_dir() and p != current and p.name != marker and re.fullmatch(r"\d+\.\d+\.\d+[\w.-]*", p.name):
                        self.add(p, "agent.codex_old_release", "agent_tools", notes=["not_current_or_pending_update", "install_lock_required"])
            except (OSError, ValueError):
                self.issues.append({"path": str(daemon), "reason": "daemon_inventory_unavailable"})
        for family in ["ms-playwright", "puppeteer"]:
            base = self.home / ("Library/Caches/" + family if family == "ms-playwright" else ".cache/puppeteer")
            for p in self.children(base):
                self.add(p, "automation.browser_inventory", "agent_tools", notes=["browser_version_references_require_review"], report_only=True)
        for relative, hint in [(".cache/uv", "uv cache prune"), ("Library/pnpm/store", "pnpm store prune")]:
            p = self.home / relative
            self.add(p, "owner.managed_cache", "package_managers", notes=["owner_managed_cache", "manual_suggestion: " + hint], report_only=True)
        self.add(self.home / ".npm/_cacache", "developer.npm_download", "package_managers", packages=["npm"], notes=["npm_content_addressed_download_cache"])
        # Actual custom owner paths are read only; never execute prune or install.
        for owner, value in self.probe.owner_cache_paths():
            if any(x["path"] == str(value) for x in self.items):
                continue
            self.add(value, "owner.configured_cache", "package_managers", notes=["owner_reported_cache_path", owner + "_owner_cleanup_manual"], report_only=True)

    def service_worker(self, base, owner, group="browsers", rule="browser.site_cache"):
        for bucket in self.children(base):
            if not bucket.is_dir() or bucket.is_symlink():
                continue
            context = None
            try:
                context = cache_index(bucket / "index.txt")
            except (OSError, Refused):
                pass
            origins = context["origins"] if context else []
            notes = ["origins: " + ", ".join(origins)]
            if not context or not context["attributed"]:
                notes.append("cache_origin_unverified")
            if owner != "Google Chrome":
                notes += ["service_worker_resources", "offline_resources_may_need_download"]
            for p in self.children(bucket):
                if p.is_dir() and not p.is_symlink():
                    self.add(p, rule, group, owner=owner, notes=notes, cache_context=context,
                             report_only=not context or not context["attributed"])

    def browser_caches(self, base, owner, *, downloads=False):
        for p in self.children(base):
            if p.name in CACHE_NAMES:
                self.add(p, "browser.resource_cache", "browsers", owner=owner, notes=["browser_resource_cache"])
            elif downloads and p.name in {"component_crx_cache", "extensions_crx_cache"}:
                self.add(p, "browser.component_download", "browsers", owner=owner,
                         notes=["downloaded_browser_component_archive", "may_need_component_download"], report_only=not p.is_dir())
            elif p.name == "GPUPersistentCache":
                for cache in self.children(p):
                    if cache.name in CACHE_NAMES:
                        self.add(cache, "browser.resource_cache", "browsers", owner=owner, notes=["browser_resource_cache"])
            elif p.is_dir() and not p.is_symlink():
                for cache in self.children(p):
                    if cache.name in CACHE_NAMES:
                        self.add(cache, "browser.resource_cache", "browsers", owner=owner, notes=["browser_resource_cache"])
                self.service_worker(p / "Service Worker/CacheStorage", owner)

    def editor_caches(self, support):
        code = support / "Code"
        for p in self.children(code / "logs"):
            known = p.is_dir() and re.fullmatch(r"\d{8}T\d{6}", p.name)
            self.add(p, "app.historical_logs", "logs", owner="Visual Studio Code", report_only=not known,
                     notes=["editor_diagnostic_logs", "historical_debugging_records_will_be_lost"] + ([] if known else ["unrecognized_cache_layout"]))
        for p in self.children(code / "CachedData"):
            known = p.is_dir() and re.fullmatch(r"[a-fA-F0-9]{32,64}", p.name)
            self.add(p, "editor.compiled_cache", "editors", owner="Visual Studio Code", report_only=not known,
                     notes=["versioned_editor_compiled_cache", "regenerated_on_editor_launch"] + ([] if known else ["unrecognized_cache_layout"]))
        for partition in self.children(code / "WebStorage"):
            if not partition.is_dir() or partition.is_symlink():
                continue
            base = partition / "CacheStorage"
            context = None
            metadata_safe = True
            payloads = self.children(base)
            if payloads:
                try:
                    context = cache_index(base / "index.txt", missing_ok=True)
                except (OSError, Refused):
                    metadata_safe = False
            for p in payloads:
                if not p.is_dir() or p.is_symlink():
                    continue
                known = re.fullmatch(r"(?:[a-fA-F0-9]{32,64}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})", p.name)
                self.add(p, "editor.webview_cache", "editors", owner="Visual Studio Code", cache_context=context,
                         notes=["extension_webview_resources", "offline_resources_may_need_download"] +
                               ([] if known and partition.name.isdecimal() else ["unrecognized_cache_layout"]) +
                               ([] if metadata_safe else ["cache_index_unavailable"]),
                         report_only=not known or not metadata_safe or not partition.name.isdecimal())

    def feishu_caches(self, support):
        roots = [support / "LarkShell", support / "LarkInternational",
                 self.home / "Library/Containers/com.bytedance.macos.feishu/Data/Library/Application Support/LarkShell"]
        for root in roots:
            for engine, profile in [("aha", "profile_explorer"), ("iron", "profile_main")]:
                for user in self.children(root / engine / "users"):
                    if user.is_dir() and not user.is_symlink():
                        self.service_worker(user / profile / "Service Worker/CacheStorage", "Feishu", "app_caches", "app.site_cache")

    def applications(self):
        support = self.home / "Library/Application Support"
        for app, owner in APPS.items():
            for p in self.children(support / app):
                if p.name in CACHE_NAMES:
                    self.add(p, "app.page_cache", "app_caches", owner=owner, notes=["known_application_cache_child"])
        self.editor_caches(support)
        self.browser_caches(support / "Google/Chrome", "Google Chrome")
        self.browser_caches(self.home / "Library/Caches/Google/Chrome", "Google Chrome")
        self.browser_caches(support / "Dia/User Data", "Dia", downloads=True)
        self.browser_caches(self.home / "Library/Caches/Dia/User Data", "Dia")
        self.feishu_caches(support)
        for owner in ["Code", "JetBrains"]:
            for p in self.children(self.home / "Library/Logs" / owner):
                self.add(p, "app.historical_logs", "logs", owner="Visual Studio Code" if owner == "Code" else "idea", notes=["logs_not_local_history"])
        for relative, owner in [("Library/Caches/com.apple.helpd", "helpd"), ("Library/Containers/com.apple.geod/Data/tmp", "com.apple.geod")]:
            for p in self.children(self.home / relative):
                self.add(p, "app.user_temporary", "app_caches", owner=owner, notes=["specific_user_cache_or_temporary_child"])

    def scan(self, *, audit_agents=True):
        for function in [self.projects, self.developer, self.applications]:
            try:
                function()
            except (OSError, Refused) as exc:
                self.issues.append({"path": str(self.home), "reason": str(exc) if isinstance(exc, Refused) else type(exc).__name__})
        # Later-discovered project settings may point at an earlier candidate.
        for item in self.items:
            protection = self.agent_policy.protection_for(Path(item["path"]), item["rule_id"], item.get("cache_context"))
            if protection:
                item.update(action="report_only", agent_protection=protection)
                if protection["reason"] not in item["evidence"]:
                    item["evidence"].append(protection["reason"])
        items = deduplicate(self.items)
        result = {"schema_version": 1, "home": str(self.home), "roots": [str(x) for x in self.roots],
                "scan_duration_seconds": round(time.monotonic() - self.started, 3),
                "excludes": [str(x) for x in self.excludes], "scan_status": "partial" if self.issues else "complete",
                "issues": self.issues, "projects": sorted(set(self.project_roots)), "candidates": items,
                "candidate_allocated_bytes": sum(x.get("allocated_bytes") or 0 for x in items),
                "actionable_allocated_bytes": sum(x.get("allocated_bytes") or 0 for x in items if x["action"] == "trash"),
                "notes": ["allocated sizes are estimates, not guaranteed reclaimable bytes", "no process or reference match does not prove future non-use"]}
        if audit_agents:
            result["agent_audit"] = self.agent_policy.audit(deadline=min(self.deadline, time.monotonic() + 20), probe=self.probe)
        return result
