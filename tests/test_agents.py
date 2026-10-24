"""Agent inventory never reads persistent bodies or grants deletion authority."""
import json
import io
import os
import plistlib
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

from macdev.agent_catalog import CATALOG, catalog_report, config_sources, expand_path
from macdev.agent_inspection import AgentPolicy, data_category
from macdev.cli import main
from macdev.engine import apply, make_plan
from macdev.probes import NativeProbe
from macdev.scanner import Scanner
from macdev.safety import Refused, tree_snapshot
from macdev.state import State
import test_coverage as coverage_fixtures
from test_coverage import FixtureBackend, FixtureProbe


class AgentInventoryTests(unittest.TestCase):
    write = coverage_fixtures.CoverageTests.write
    scan = coverage_fixtures.CoverageTests.scan
    item = coverage_fixtures.CoverageTests.item
    plan = coverage_fixtures.CoverageTests.plan

    def setUp(self):
        coverage_fixtures.CoverageTests.setUp(self)
        env = patch.dict(os.environ, {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def policy(self, **kwargs):
        return AgentPolicy(self.home, **kwargs)

    def config(self, data):
        return self.write(self.home / ".config/mac-dev-cleanup/config.json", json.dumps(data))

    def cache(self):
        project = self.home / "Projects/demo"
        self.write(project / "package.json", '{}')
        folder = project / ".next"
        self.write(folder / "cache/data")
        return folder

    def test_catalog_declares_read_only_capabilities_and_scope(self):
        report = catalog_report()
        self.assertGreaterEqual(len(report["entries"]), 30)
        self.assertEqual(len({x["id"] for x in CATALOG}), len(CATALOG))
        for item in report["entries"]:
            self.assertEqual(set(item["capabilities"]), {"read_only_inventory", "protect_data"})
            self.assertIn(item["layout_evidence"], {"documented_defaults", "conservative_location_hints"})
        self.assertIn("not exhaustive", report["scope_note"])

    def test_each_registered_root_has_a_protection_rule(self):
        policy = self.policy(environ={})
        for tool in CATALOG:
            for template in tool["roots"]:
                p, _ = expand_path(template, self.home, {})
                with self.subTest(tool=tool["id"], path=p):
                    reason = policy.protection_for(p / "nested-cache" if not p.suffix else p, "project.dist")
                    self.assertIsNotNone(reason)
                    self.assertIn(tool["id"], reason["tool_ids"])

    def test_all_project_markers_are_protected_without_claiming_installation(self):
        project = self.home / "Projects/demo"
        for tool in CATALOG:
            for relative in tool["project"]:
                path = project / relative
                if relative.startswith('.') and '.' not in path.name[1:] and path.name not in {".clinerules", ".roorules", ".kilocoderules", ".cursorrules", ".windsurfrules"}:
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    self.write(path, '{}')
        policy = self.policy()
        policy.inspect_project(project)
        for tool in CATALOG:
            for relative in tool["project"]:
                with self.subTest(tool=tool["id"], relative=relative):
                    self.assertIsNotNone(policy.protection_for(project / relative, "project.dist"))

    def test_inventory_reads_only_metadata_of_auth_sessions_and_database(self):
        root = self.home / ".codex"
        protected = {self.write(root / "auth.json", '{"token":"secret-token"}'),
                     self.write(root / "sessions/s1.jsonl", 'secret-conversation'),
                     self.write(root / "memories/MEMORY.md", 'secret-memory'),
                     self.write(root / "state.db", 'secret-db'),
                     self.write(root / "state.db-wal", 'secret-wal')}
        before = tree_snapshot(self.home)
        original = os.open
        def guard(path, *args, **kwargs):
            self.assertNotIn(Path(path), protected)
            return original(path, *args, **kwargs)
        with patch("os.open", side_effect=guard):
            result = self.policy().audit(include_apps=False)
        self.assertEqual(result["action"], "report_only")
        self.assertNotIn("candidates", result)
        self.assertNotIn("secret-", json.dumps(result))
        self.assertEqual(before, tree_snapshot(self.home))
        categories = next(x for x in result["detected_tools"] if x["id"] == "codex")["roots"][0]["categories"]
        for category in ["credentials", "sessions_and_tasks", "memory", "databases"]:
            self.assertIn(category, categories)

    def test_database_wal_and_shm_are_persistent_data(self):
        for name in ["state.db", "state.db-wal", "state.db-shm", "state.sqlite-wal", "state.sqlite3-shm", "state.sqlite-journal", "state.sqlite3-journal"]:
            with self.subTest(name=name):
                self.assertEqual(data_category(name), "databases")
                p = self.write(self.home / "files" / name)
                self.assertTrue(tree_snapshot(p)["sensitive"])

    def test_every_project_marker_and_known_credential_name_is_sensitive_inside_artifacts(self):
        names = {Path(relative).name for tool in CATALOG for relative in tool["project"]}
        names.update({"auth.json", ".credentials.json", "oauth_creds.json"})
        for name in names:
            with self.subTest(name=name):
                p = self.write(self.home / "files" / name)
                self.assertTrue(tree_snapshot(p)["sensitive"])

    def test_data_named_tmp_or_cache_is_never_cleanup_authority(self):
        self.write(self.home / ".gemini/tmp/project/chats/session.json", '{}')
        self.write(self.home / ".workbuddy/cache/MEMORY.md", 'keep')
        policy = self.policy()
        for p in [self.home / ".gemini/tmp", self.home / ".workbuddy/cache"]:
            self.assertIsNotNone(policy.protection_for(p, "app.page_cache"))
        result = policy.audit(include_apps=False)
        self.assertTrue(all(root["action"] == "report_only" for t in result["detected_tools"] for root in t["roots"]))

    def test_agent_data_inside_build_artifact_prevents_whole_move(self):
        folder = self.cache()
        self.write(folder / "nested/.pi/sessions/history.jsonl", 'keep')
        item = self.item(self.scan(), folder)
        self.assertEqual(item["action"], "report_only")
        state = State(self.home)
        with self.assertRaises(Refused):
            make_plan(self.scan(), [item["id"]], state, probe=self.probe)

    def test_custom_roots_are_reported_and_protected(self):
        folder = self.cache()
        self.config({"agent_roots": {"future_agent": [str(folder)]}})
        item = self.item(self.scan(), folder)
        self.assertEqual(item["action"], "report_only")
        self.assertEqual(item["agent_protection"]["reason"], "agent_data_protected")
        result = self.policy().audit(include_apps=False)
        self.assertTrue(any(x["id"] == "future_agent" for x in result["detected_tools"]))

    def test_new_custom_protection_after_plan_blocks_apply(self):
        folder = self.cache()
        state, plan = self.plan(folder)
        self.config({"agent_roots": {"future_agent": [str(folder)]}})
        result = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(result["entries"][0]["reason"], "agent_data_protected")
        self.assertTrue(folder.exists())

    def test_another_project_declaring_resource_after_plan_blocks_apply(self):
        folder = self.cache()
        other = self.home / "Projects/other"
        self.write(other / "package.json", '{}')
        state, plan = self.plan(folder)
        self.write(other / ".pi/settings.json", json.dumps({"sessionDir": str(folder)}))
        result = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(result["entries"][0]["reason"], "agent_data_protected")
        self.assertTrue(folder.exists())

    def test_project_skill_link_protects_its_shared_source(self):
        folder = self.cache()
        state, plan = self.plan(folder)
        resource = folder.parent / ".pi"
        resource.mkdir()
        (resource / "skills").symlink_to(folder)
        result = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(result["entries"][0]["reason"], "agent_data_protected")
        self.assertTrue(folder.exists())

    def test_protection_added_during_occupancy_probe_blocks_final_move(self):
        folder = self.cache()
        state, plan = self.plan(folder)
        def idle(path):
            self.config({"agent_roots": {"new_agent": [str(folder)]}})
            return "idle"
        with patch.object(self.probe, "idle", side_effect=idle):
            result = apply(plan["id"], state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(result["entries"][0]["reason"], "agent_data_protected")
        self.assertTrue(folder.exists())

    def test_malformed_or_overbroad_custom_roots_fail_closed(self):
        for value in [{"bad": "~/data"}, {"bad": [str(self.home)]}, {"bad": [str(self.home / ".config")]}, {"bad": ["https://secret@example.test"]}]:
            with self.subTest(value=value):
                self.config({"agent_roots": value})
                policy = self.policy()
                self.assertTrue(policy.fail_closed)
                self.assertEqual(policy.protection_for(self.home / "cache", "app.page_cache")["reason"], "agent_protection_configuration_incomplete")

    def test_directory_overrides_and_config_sources_are_honored(self):
        env = {"CODEX_HOME": str(self.home / "custom/codex"), "CLAUDE_CONFIG_DIR": str(self.home / "custom/claude"),
               "PI_CODING_AGENT_DIR": str(self.home / "custom/pi"), "OPENCLAW_STATE_DIR": str(self.home / "custom/claw"),
               "XDG_DATA_HOME": str(self.home / "custom/data"), "OPENCODE_DB": str(self.home / "custom/state.db")}
        policy = self.policy(environ=env)
        for key, value in env.items():
            p = str(Path(value) / "opencode") if key == "XDG_DATA_HOME" else value
            self.assertIsNotNone(policy.protection_for(Path(p) / "cache", "app.page_cache"))
        files = config_sources(self.home, env)
        self.assertIn(Path(env["CODEX_HOME"]) / "config.toml", files)
        self.assertIn(Path(env["PI_CODING_AGENT_DIR"]) / "mcp.json", files)
        self.assertIn(Path(env["OPENCLAW_STATE_DIR"]) / "openclaw.json", files)

    def test_invalid_directory_override_does_not_expose_secret(self):
        policy = self.policy(environ={"CODEX_HOME": "https://user:secret@example.test"})
        self.assertTrue(policy.fail_closed)
        self.assertNotIn("secret", json.dumps(policy.issues))

    def test_unknown_marker_detection_is_labeled_and_preserved(self):
        root = self.home / ".future-agent"
        self.write(root / "SOUL.md", 'keep')
        self.write(root / "memory/daily.md", 'keep')
        policy = self.policy()
        policy.discover()
        self.assertIsNotNone(policy.protection_for(root / "cache", "app.page_cache"))
        result = policy.audit(include_apps=False)
        roots = [r for x in result["detected_tools"] for r in x["roots"] if r["path"] == str(root)]
        self.assertEqual(roots[0]["basis"], "unknown_agent_marker_match")

    def test_plain_hidden_directory_is_not_claimed_as_an_agent(self):
        self.write(self.home / ".photos/README.md", 'ordinary files')
        result = self.policy().audit(include_apps=False)
        self.assertFalse(any(r["path"] == str(self.home / ".photos") for t in result["detected_tools"] for r in t["roots"]))

    def test_shared_skill_symlinks_protect_the_actual_source_and_deduplicate(self):
        source = self.home / "personal-skills"
        self.write(source / "demo/SKILL.md", 'user skill')
        for parent in [self.home / ".pi/agent", self.home / ".agents"]:
            parent.mkdir(parents=True)
            (parent / "skills").symlink_to(source)
        policy = self.policy()
        self.assertIsNotNone(policy.protection_for(source / "demo", "project.dist"))
        result = policy.audit(include_apps=False)
        aliases = [r for t in result["detected_tools"] for r in t["roots"] if r.get("resolved_path") == str(source)]
        self.assertEqual(len(aliases), 2)
        self.assertTrue(any(r.get("shared_measurement") for r in aliases))
        self.assertLess(result["total_unique_allocated_bytes"], sum(r.get("allocated_bytes") or 0 for t in result["detected_tools"] for r in t["roots"]))

    def test_symlink_outside_home_is_not_measured(self):
        external = self.home.parent / "outside"
        self.write(external / "secret", 'keep')
        (self.home / ".codex").symlink_to(external)
        result = self.policy().audit(include_apps=False)
        row = next(t for t in result["detected_tools"] if t["id"] == "codex")["roots"][0]
        self.assertEqual(row["scan_status"], "unavailable")
        self.assertIsNone(row["allocated_bytes"])
        self.assertEqual(result["total_unique_allocated_bytes"], 0)

    def test_permission_failure_is_unknown_not_missing_or_zero(self):
        root = self.home / ".codex"
        self.write(root / "sessions/history.jsonl")
        policy = self.policy()
        policy.load_resource_paths()
        policy.discover()
        original = Path.lstat
        def guard(path, *args, **kwargs):
            if path == root:
                raise PermissionError("fixture")
            return original(path, *args, **kwargs)
        with patch.object(Path, "lstat", guard):
            result = policy.audit(include_apps=False)
        row = next(t for t in result["detected_tools"] if t["id"] == "codex")["roots"][0]
        self.assertEqual(row["scan_status"], "unavailable")
        self.assertIsNone(row["allocated_bytes"])
        self.assertEqual(result["scan_status"], "partial")

    def test_app_version_comes_from_bounded_metadata_without_exporting_other_fields(self):
        p = self.home / "Applications/Cursor.app/Contents/Info.plist"
        p.parent.mkdir(parents=True)
        p.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.2.3", "private": "secret-token"}))
        bad = self.home / "Applications/Claude.app/Contents/Info.plist"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(plistlib.dumps(["malformed bundle metadata"]))
        result = self.policy().app_versions()
        row = next(row for row in result["cursor"] if row["path"] == str(p.parent.parent))
        self.assertEqual(row["version"], "1.2.3")
        self.assertNotIn("secret-token", json.dumps(result))

    def test_shared_parent_redirect_does_not_trigger_unknown_scan_outside_home(self):
        external = self.home.parent / "outside"
        self.write(external / "future/SOUL.md", 'private')
        (self.home / ".config").symlink_to(external)
        policy = self.policy()
        policy.inspect_unknown(self.home / ".config")
        self.assertTrue(any(x["reason"] == "unknown_agent_discovery_redirected" for x in policy.issues))
        self.assertFalse(any(str(external) in r["path"] for r in policy.roots.values()))

    def test_resource_path_in_pi_settings_protects_external_session_store(self):
        folder = self.cache()
        self.write(self.home / ".pi/agent/settings.json", json.dumps({"sessionDir": str(folder), "env": {"API_KEY": "secret-token"}}))
        report = self.scan()
        self.assertEqual(self.item(report, folder)["action"], "report_only")
        self.assertNotIn("secret-token", json.dumps(report))

    def test_claude_custom_memory_directory_is_protected(self):
        folder = self.cache()
        self.write(self.home / ".claude/settings.json", json.dumps({"autoMemoryDirectory": str(folder)}))
        self.assertEqual(self.item(self.scan(), folder)["action"], "report_only")

    def test_overbroad_declared_resource_blocks_first_protection_check(self):
        self.write(self.home / ".pi/agent/settings.json", json.dumps({"sessionDir": str(self.home)}))
        self.assertEqual(self.policy().protection_for(self.home / "cache", "app.page_cache")["reason"],
                         "agent_protection_configuration_incomplete")

    def test_inventory_honors_subtree_exclusions(self):
        excluded = self.home / ".codex/sessions"
        self.write(excluded / "session.jsonl", 'private')
        result = self.policy(excludes=[excluded]).audit(include_apps=False)
        row = next(t for t in result["detected_tools"] if t["id"] == "codex")["roots"][0]
        self.assertNotIn("sessions_and_tasks", row["categories"])
        self.assertIsNotNone(self.policy(excludes=[excluded]).protection_for(excluded, "project.dist"))

    def test_truncated_unknown_discovery_is_reported(self):
        self.write(self.home / ".future-agent/SOUL.md")
        policy = self.policy()
        policy.inspect_unknown(self.home, limit=0)
        self.assertTrue(any(x["reason"] == "unknown_agent_discovery_partial" for x in policy.issues))

    def test_agents_catalog_does_not_scan_or_create_state(self):
        out = io.StringIO()
        before = tree_snapshot(self.home)
        with patch("macdev.cli.Scanner", side_effect=AssertionError("catalog must not scan")), redirect_stdout(out):
            self.assertEqual(main(["agents", "--catalog", "--json"]), 0)
        self.assertIn("entries", json.loads(out.getvalue()))
        self.assertEqual(before, tree_snapshot(self.home))

    def test_agents_command_is_metadata_only_and_report_is_private(self):
        self.write(self.home / ".gemini/tmp/project/chats/session.json", 'secret-history')
        project = self.home / "Projects/demo"
        self.write(project / "package.json", '{}')
        self.write(project / "node_modules/large.js", 'keep')
        before = tree_snapshot(self.home)
        output = self.home.parent / "agent-report.json"
        out, calls = io.StringIO(), []
        def fake_command(args, *rest, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("macdev.probes.command", side_effect=fake_command), redirect_stdout(out):
            self.assertEqual(main(["agents", "--root", str(project), "--json", "--output", str(output)]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result, json.loads(output.read_text()))
        self.assertEqual(result["action"], "report_only")
        self.assertNotIn("candidates", result)
        self.assertNotIn("secret-history", out.getvalue())
        self.assertTrue(calls)
        self.assertTrue(all(args[0] == "/bin/ps" for args in calls), calls)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(before, tree_snapshot(self.home))
        self.assertFalse((self.home / ".local/state/mac-dev-cleanup").exists())

    def test_agents_human_report_explains_no_cleanup_and_next_step(self):
        self.write(self.home / ".codex/config.toml", '')
        out = io.StringIO()
        with patch("macdev.probes.command", return_value=None), redirect_stdout(out):
            self.assertEqual(main(["agents"]), 0)
        self.assertIn("本次没有清理", out.getvalue())
        self.assertIn("下一步", out.getvalue())
        self.assertIn("unknown", out.getvalue())

    def test_local_pi_package_is_installed_resource_not_a_download_cache(self):
        source = self.home / "packages/my-plugin"
        self.write(source / "package.json", '{}')
        self.write(self.home / ".pi/agent/settings.json", json.dumps({"packages": [{"source": str(source)}]}))
        self.assertIsNotNone(self.policy().protection_for(source, "project.dist"))

    def test_pi_mcp_and_project_mcp_references_preserve_npx(self):
        folder = self.home / ".npm/_npx/fixture"
        self.write(folder / "package.json", json.dumps({"dependencies": {"fixture-mcp": "1"}}))
        self.write(self.home / ".pi/agent/mcp.json", json.dumps({"mcpServers": {"a": {"command": "npx", "args": ["fixture-mcp"], "env": {"API_KEY": "secret-token"}}}}))
        self.probe = FixtureProbe(self.home)
        self.assertEqual(self.item(self.scan(), folder)["action"], "report_only")
        self.assertNotIn("secret-token", json.dumps(self.scan()))

    def test_metadata_budget_is_partial_not_zero_or_reclaimable(self):
        self.write(self.home / ".codex/sessions/session.jsonl", 'data')
        result = self.policy().audit(include_apps=False, limit=1)
        self.assertEqual(result["scan_status"], "partial")
        roots = [r for t in result["detected_tools"] for r in t["roots"]]
        self.assertTrue(any(r.get("bytes_are_lower_bound") for r in roots))
        self.assertNotIn("reclaimable_bytes", result)

    def test_expired_budget_still_reports_protected_roots(self):
        self.write(self.home / ".codex/sessions/session.jsonl")
        result = self.policy().audit(include_apps=False, deadline=time.monotonic() - 1)
        self.assertEqual(result["scan_status"], "partial")
        self.assertEqual(result["detected_tools"][0]["roots"][0]["action"], "report_only")

    def test_agent_process_reporting_exports_only_pid(self):
        self.write(self.home / ".codex/config.toml", '')
        self.probe.process_rows = ["42 /usr/local/bin/codex --api-key secret-token"]
        self.probe.refresh()
        result = self.policy().audit(include_apps=False, probe=self.probe)
        codex = next(t for t in result["detected_tools"] if t["id"] == "codex")
        self.assertEqual(codex["activity"], "observed_process")
        self.assertEqual(codex["matched_pids"], ["42"])
        self.assertNotIn("secret-token", json.dumps(result))

    def test_scan_contains_inventory_without_converting_it_to_candidates(self):
        self.write(self.home / ".openclaw/agents/main/agent/openclaw-agent.sqlite", 'state')
        report = self.scan()
        self.assertIn("agent_audit", report)
        self.assertTrue(any(t["id"] == "openclaw" for t in report["agent_audit"]["detected_tools"]))
        self.assertFalse(any(".openclaw" in x["path"] for x in report["candidates"]))

    def test_standard_worktree_cache_is_separate_from_source_and_build_outputs(self):
        project = self.home / ".codex/worktrees/demo"
        self.write(project / "pyproject.toml", '[project]\nname="fixture"')
        self.write(project / "__pycache__/fixture.pyc")
        self.write(project / "dist/output")
        report = self.scan()
        self.assertEqual(self.item(report, project / "__pycache__")["action"], "trash")
        self.assertEqual(self.item(report, project / "dist")["action"], "report_only")

    def test_explicit_protection_and_shared_resources_override_worktree_cache_exception(self):
        folders = []
        for name in ["custom", "shared"]:
            project = self.home / ".codex/worktrees" / name
            self.write(project / "pyproject.toml", '[project]\nname="fixture"')
            folders.append(self.write(project / "__pycache__/data").parent)
        self.config({"agent_roots": {"future_agent": [str(folders[0])]}})
        shared = self.home / ".pi/agent/skills"
        shared.parent.mkdir(parents=True)
        shared.symlink_to(folders[1])
        report = self.scan()
        for folder in folders:
            self.assertEqual(self.item(report, folder)["action"], "report_only")

    def test_explicit_protection_cannot_enable_existing_codex_release_exception(self):
        folder = self.home / ".codex/packages/app-server-daemon/releases/0.1"
        self.write(folder / "program")
        self.assertIsNone(self.policy().protection_for(folder, "agent.codex_old_release"))
        self.config({"agent_roots": {"codex": [str(folder)]}})
        self.assertIsNotNone(self.policy().protection_for(folder, "agent.codex_old_release"))

    def test_known_and_manifest_discovered_agent_extensions_are_protected(self):
        base = self.home / ".vscode/extensions"
        known = base / "anthropic.claude-code-1.0"
        unknown = base / "example.future-1.0"
        self.write(known / "package.json", json.dumps({"publisher": "anthropic", "name": "claude-code"}))
        self.write(unknown / "package.json", json.dumps({"publisher": "example", "name": "future", "contributes": {"languageModelTools": []}}))
        self.write(base / ".obsolete", json.dumps({known.name: True, unknown.name: True}))
        self.write(base / "extensions.json", '[]')
        report = self.scan()
        for p in [known, unknown]:
            self.assertEqual(self.item(report, p)["action"], "report_only")
            self.assertIn("agent_protection", self.item(report, p))


if __name__ == "__main__":
    unittest.main()
