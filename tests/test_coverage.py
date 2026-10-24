"""Coverage additions tested only in synthetic homes, including refusal paths."""
import json
import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from macdev.cache_context import cache_index
from macdev.engine import MoleBackend, apply, make_plan, rename_exclusive, restore
from macdev.probes import NativeProbe
from macdev.safety import Refused, tree_snapshot
from macdev.scanner import Scanner
from macdev.state import State


CACHE_ID = "f5f30a50-c16f-47c8-b043-0790d96a4fad"


class FixtureProbe(NativeProbe):
    def __init__(self, home):
        self.process_rows = []
        super().__init__(home)

    def refresh(self):
        self.rows = list(self.process_rows)
        self.references = set()
        self.reference_status = "complete"
        self._references()

    def owner_cache_paths(self):
        return []

    def installation(self, owner, *, refresh=False):
        return {"status": "not_found", "reason": "isolated_fixture_has_no_installed_apps"}

    def idle(self, path, *, rule_id=None):
        return "idle"


class FixtureBackend:
    def move(self, source, destination, snapshot):
        rename_exclusive(source, destination)

    def restore(self, source, destination):
        rename_exclusive(source, destination)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="macdev-coverage-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.support = self.home / "Library/Application Support"
        self.probe = FixtureProbe(self.home)

    def write(self, path, text="fixture"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def scan(self, **kwargs):
        return Scanner(home=self.home, probe=self.probe, **kwargs).scan()

    def item(self, report, path):
        return next(x for x in report["candidates"] if x["path"] == str(path))

    def plan(self, path):
        report = self.scan()
        state = State(self.home)
        plan = make_plan(report, [self.item(report, path)["id"]], state, probe=self.probe)
        return state, plan

    def worker(self, profile, origin="https://docs.example.test"):
        bucket = profile / "Service Worker/CacheStorage" / ("a" * 40)
        self.write(bucket / "index.txt", origin)
        payload = bucket / CACHE_ID
        self.write(payload / "data", "cached resources")
        return payload

    def webview(self, index=True, partition="11"):
        root = self.support / "Code/WebStorage" / partition / "CacheStorage"
        if index:
            self.write(root / "index.txt", "vscode-webview://fixture")
        payload = root / CACHE_ID
        self.write(payload / "data", "cached resources")
        return payload

    def test_vscode_known_cache_leaves_exclude_user_state(self):
        logs = self.support / "Code/logs/20261023T123456"
        compiled = self.support / "Code/CachedData" / ("a" * 40)
        payload = self.webview()
        self.write(logs / "main.log")
        self.write(compiled / "code.cache")
        keep = [self.write(self.support / "Code/User/History/record"),
                self.write(self.support / "Code/User/globalStorage/state.vscdb"),
                self.write(payload.parent.parent / "IndexedDB/database"),
                self.write(payload.parent.parent / "Local Storage/state"),
                self.write(self.support / "Code/CachedData/custom/precious")]
        before = tree_snapshot(self.home)
        report = self.scan()
        for p in [logs, compiled, payload]:
            self.assertEqual(self.item(report, p)["action"], "trash")
        paths = [Path(x["path"]) for x in report["candidates"] if x["action"] == "trash"]
        self.assertTrue(all(not any(p == x or p.is_relative_to(x) for x in paths) for p in keep))
        self.assertEqual(before, tree_snapshot(self.home))

    def test_vscode_running_keeps_logs_and_webviews(self):
        payload = self.webview()
        logs = self.support / "Code/logs/20261023T123456"
        self.write(logs / "main.log")
        self.probe.process_rows = ["42 /Applications/Visual Studio Code.app/Contents/MacOS/Electron"]
        self.probe.refresh()
        report = self.scan()
        for p in [payload, logs]:
            self.assertEqual(self.item(report, p)["action"], "report_only")

    def test_vscode_unrecognized_partition_and_cache_entries_are_retained(self):
        payload = self.webview(partition="custom")
        odd = self.support / "Code/WebStorage/11/CacheStorage/notes"
        self.write(odd / "source")
        report = self.scan()
        self.assertEqual(self.item(report, payload)["action"], "report_only")
        self.assertEqual(self.item(report, odd)["action"], "report_only")

    def test_vscode_index_metadata_changes_after_plan_block_move(self):
        payload = self.webview()
        state, plan = self.plan(payload)
        self.write(payload.parent / "index.txt", "changed mapping")
        run = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run["entries"][0]["reason"], "cache_index_changed")
        self.assertTrue(payload.exists())

    def test_previously_absent_index_appearing_after_plan_blocks_move(self):
        payload = self.webview(index=False)
        state, plan = self.plan(payload)
        self.write(payload.parent / "index.txt", "new mapping")
        run = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run["entries"][0]["reason"], "cache_index_changed")
        self.assertTrue(payload.exists())

    def test_dia_resource_download_and_http_caches_exclude_profile_data(self):
        base = self.support / "Dia/User Data"
        paths = [base / "GraphiteDawnCache", base / "component_crx_cache", base / "extensions_crx_cache",
                 base / "Default/GPUCache", self.home / "Library/Caches/Dia/User Data/Default/Code Cache"]
        for p in paths:
            self.write(p / "data")
        self.write(base / "Default/Cookies")
        self.write(base / "Default/IndexedDB/database")
        self.write(base / "Default/Local Storage/state")
        report = self.scan()
        self.assertEqual({x["path"] for x in report["candidates"]}, {str(p) for p in paths})
        self.assertTrue(all(self.item(report, p)["action"] == "trash" for p in paths))

    def test_dia_worker_origin_attribution_redacts_userinfo(self):
        payload = self.worker(self.support / "Dia/User Data/Default", "https://user:secret@example.test:443/path")
        item = self.item(self.scan(), payload)
        self.assertEqual(item["action"], "trash")
        self.assertEqual(item["cache_context"]["origins"], ["https://example.test:443"])
        self.assertNotIn("secret", json.dumps(item))

    def test_unknown_mixed_or_extension_worker_origins_are_retained(self):
        for owner, profile in [("Dia", self.support / "Dia/User Data/Default"),
                               ("Chrome", self.support / "Google/Chrome/Default")]:
            for origin in ["chrome-extension://fixture", "https://a.test https://b.test", "https://a.test chrome-extension://fixture", "unknown"]:
                with self.subTest(owner=owner, origin=origin):
                    payload = self.worker(profile, origin)
                    self.assertEqual(self.item(self.scan(), payload)["action"], "report_only")

    def test_dia_running_protects_component_and_site_caches(self):
        payload = self.worker(self.support / "Dia/User Data/Default")
        download = self.support / "Dia/User Data/component_crx_cache"
        self.write(download / "archive")
        self.probe.process_rows = ["42 /Applications/Dia.app/Contents/MacOS/Dia"]
        self.probe.refresh()
        report = self.scan()
        self.assertTrue(all(self.item(report, p)["action"] == "report_only" for p in [payload, download]))

    def test_feishu_six_known_profile_layouts_preserve_account_data(self):
        roots = [self.support / "LarkShell", self.support / "LarkInternational",
                 self.home / "Library/Containers/com.bytedance.macos.feishu/Data/Library/Application Support/LarkShell"]
        payloads = []
        for root in roots:
            for engine, name in [("aha", "profile_explorer"), ("iron", "profile_main")]:
                profile = root / engine / "users/fixture-user" / name
                payloads.append(self.worker(profile))
                self.write(profile / "Cookies")
                self.write(profile / "IndexedDB/documents")
                self.write(profile / "Local Storage/session")
        report = self.scan()
        self.assertEqual({x["path"] for x in report["candidates"]}, {str(p) for p in payloads})
        self.assertTrue(all(x["action"] == "trash" for x in report["candidates"]))

    def test_feishu_and_lark_running_guard_all_profile_variants(self):
        payload = self.worker(self.support / "LarkShell/iron/users/fixture-user/profile_main")
        for owner in ["Feishu", "Lark"]:
            with self.subTest(owner=owner):
                self.probe.process_rows = [f"42 /Applications/{owner}.app/Contents/MacOS/{owner}"]
                self.probe.refresh()
                self.assertEqual(self.item(self.scan(), payload)["action"], "report_only")

    def test_app_starting_after_plan_is_retained(self):
        payload = self.worker(self.support / "LarkShell/aha/users/fixture-user/profile_explorer")
        state, plan = self.plan(payload)
        self.probe.process_rows = ["42 /Applications/Lark.app/Contents/MacOS/Lark"]
        run = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run["entries"][0]["status"], "skipped")
        self.assertTrue(payload.exists())

    def test_worker_index_change_after_plan_is_retained(self):
        payload = self.worker(self.support / "Dia/User Data/Default")
        state, plan = self.plan(payload)
        self.write(payload.parent / "index.txt", "chrome-extension://new-owner")
        run = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run["entries"][0]["reason"], "cache_index_changed")
        self.assertTrue(payload.exists())

    def test_origin_change_between_scan_and_plan_requires_rescan(self):
        payload = self.worker(self.support / "Dia/User Data/Default")
        report = self.scan()
        self.write(payload.parent / "index.txt", "https://other-owner.test")
        state = State(self.home)
        with self.assertRaises(Refused):
            make_plan(report, [self.item(report, payload)["id"]], state, probe=self.probe)
        self.assertTrue(payload.exists())

    def test_redirected_index_is_not_read_and_never_enters_plan(self):
        payload = self.webview(index=False)
        external = self.write(self.home.parent / "private", "https://private.test")
        (payload.parent / "index.txt").symlink_to(external)
        item = self.item(self.scan(), payload)
        self.assertEqual(item["action"], "report_only")
        self.assertNotIn("private.test", json.dumps(item))

    def test_fifo_index_is_refused_without_blocking(self):
        p = self.home / "index.txt"
        os.mkfifo(p)
        with self.assertRaises(Refused):
            cache_index(p)

    def test_redirected_feishu_profile_root_is_not_followed(self):
        external = self.home.parent / "external-profile"
        self.worker(external)
        target = self.support / "LarkShell/aha/users/u/profile_explorer"
        target.parent.mkdir(parents=True)
        target.symlink_to(external)
        report = self.scan()
        self.assertEqual(report["candidates"], [])
        self.assertTrue(any(x["reason"] == "symlink_not_followed" for x in report["issues"]))

    def test_prebuild_archives_are_downloads_and_unknown_entries_are_retained(self):
        base = self.home / ".npm/_prebuilds"
        archive = self.write(base / "a68de9-frida-v17.23.2-napi-v8-darwin-arm64.tar.gz")
        unknown = self.write(base / "precious.txt", "keep")
        directory = base / "installed-tool"
        self.write(directory / "runtime")
        report = self.scan()
        self.assertEqual(self.item(report, archive)["action"], "trash")
        for p in [unknown, directory]:
            self.assertEqual(self.item(report, p)["action"], "report_only")

    def test_npm_activity_keeps_prebuild_archives(self):
        archive = self.write(self.home / ".npm/_prebuilds/abcdef-package-v1.tar.gz")
        self.probe.process_rows = ["42 npm install fixture"]
        self.probe.refresh()
        self.assertEqual(self.item(self.scan(), archive)["action"], "report_only")

    def test_default_discovery_reaches_nested_projects_without_entering_dependencies(self):
        projects = [self.home / "Documents/software/MCP/zen-mcp-server",
                    self.home / "ideaprojects/team/client/tool/project"]
        for project in projects:
            self.write(project / "pyproject.toml", '[project]\nname="fixture"\nversion="1"')
            self.write(project / "tools/__pycache__/fixture.pyc")
        package = self.home / "Documents/node_modules/dependency"
        self.write(package / "package.json", '{}')
        self.write(package / "__pycache__/precious")
        self.write(self.home / "node_modules/stray/package.json", '{}')
        before = tree_snapshot(self.home)
        report = self.scan()
        self.assertTrue(all(str(p) in report["projects"] for p in projects))
        self.assertTrue(all(self.item(report, p / "tools/__pycache__")["action"] == "trash" for p in projects))
        self.assertFalse(any("node_modules" in x["path"] for x in report["candidates"]))
        self.assertEqual(before, tree_snapshot(self.home))

    def test_explicit_roots_inside_dependencies_are_refused(self):
        package = self.home / "Projects/demo/node_modules/dependency"
        self.write(package / "package.json", '{}')
        self.write(package / "dist/precious")
        report = self.scan(roots=[package])
        self.assertEqual(report["candidates"], [])
        self.assertTrue(any(x["reason"] == "project_root_inside_dependency_environment" for x in report["issues"]))

    def test_nested_project_mcp_reference_blocks_npx_candidate(self):
        project = self.home / "Documents/software/MCP/zen-mcp-server"
        self.write(project / "pyproject.toml", '[project]\nname="fixture"')
        self.write(project / ".mcp.json", json.dumps({"mcpServers": {"fixture": {"command": "npx", "args": ["fixture-mcp"]}}}))
        folder = self.home / ".npm/_npx/fixture"
        self.write(folder / "package.json", json.dumps({"dependencies": {"fixture-mcp": "1"}}))
        self.assertEqual(self.item(self.scan(), folder)["action"], "report_only")

    def test_discovery_depth_limit_does_not_scan_unbounded_containers(self):
        project = self.home / "Documents/a/b/c/d/e/f/g/deeper"
        self.write(project / "pyproject.toml", '[project]\nname="fixture"')
        self.write(project / "__pycache__/keep.pyc")
        report = self.scan()
        self.assertNotIn(str(project), report["projects"])
        self.assertFalse(any(x["path"].startswith(str(project)) for x in report["candidates"]))

    def test_excluded_nested_project_remains_out_of_scope(self):
        project = self.home / "Documents/software/MCP/zen-mcp-server"
        self.write(project / "pyproject.toml", '[project]\nname="fixture"')
        self.write(project / "__pycache__/keep.pyc")
        report = self.scan(excludes=[project])
        self.assertNotIn(str(project), report["projects"])
        self.assertFalse(any(x["path"].startswith(str(project)) for x in report["candidates"]))

    def test_discovery_directory_budget_yields_partial_evidence(self):
        self.write(self.home / "Projects/a/b/c/d/e/pyproject.toml", '[project]\nname="fixture"')
        with patch("macdev.scanner.PROJECT_DISCOVERY_LIMIT", 2):
            report = self.scan()
        self.assertEqual(report["scan_status"], "partial")
        self.assertTrue(any(x["reason"] == "project_directory_budget_exceeded" for x in report["issues"]))

    @unittest.skipUnless(platform.system() == "Darwin", "pinned Bash backend requires macOS")
    def test_new_cache_paths_move_and_restore_through_pinned_backend(self):
        webview = self.webview()
        dia = self.worker(self.support / "Dia/User Data/Default")
        feishu = self.worker(self.support / "LarkShell/aha/users/u/profile_explorer")
        archive = self.write(self.home / ".npm/_prebuilds/abcdef-fixture-v1.tar.gz")
        logs = self.support / "Code/logs/20261023T123456"
        compiled = self.support / "Code/CachedData" / ("a" * 40)
        components = self.support / "Dia/User Data/component_crx_cache"
        for p in [logs, compiled, components]:
            self.write(p / "fixture.cache")
        report = self.scan()
        state = State(self.home)
        paths = [webview, dia, feishu, archive, logs, compiled, components]
        plan = make_plan(report, [self.item(report, p)["id"] for p in paths], state, probe=self.probe)
        run = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=MoleBackend(state))
        self.assertEqual([x["status"] for x in run["entries"]], ["trashed"] * len(paths), run)
        self.assertTrue((webview.parent / "index.txt").is_file())
        self.assertTrue((dia.parent / "index.txt").is_file())
        result = restore(run["id"], state, confirmed=True, probe=self.probe, backend=MoleBackend(state))
        self.assertEqual([x["status"] for x in result["results"]], ["restored"] * len(paths))
        self.assertTrue(all(p.exists() for p in paths))
