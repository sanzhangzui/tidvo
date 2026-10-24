import contextlib
import copy
import json
import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from macdev.engine import InterruptedMove, MoleBackend, apply, make_plan, prepare_trash, rename_exclusive, restore
from macdev.probes import NativeProbe
from macdev.safety import Refused, deduplicate, ordinary_path, tree_snapshot
from macdev.scanner import Scanner
from macdev.state import State


class FakeProbe:
    def __init__(self):
        self.active = False
        self.referenced = False
        self.open_state = "idle"
        self.reference_status = "complete"

    def refresh(self):
        pass

    def owner_cache_paths(self):
        return []

    def include_project_configs(self, root):
        pass

    def evidence(self, path, owner="", packages=()):
        return {"activity": "active" if self.active else "idle", "configured_reference": self.referenced,
                "reference_scan_status": self.reference_status, "matched_pids": []}

    def idle(self, path, *, rule_id=None):
        return self.open_state


class FixtureBackend:
    def move(self, source, destination, snapshot):
        rename_exclusive(source, destination)

    def restore(self, source, destination):
        rename_exclusive(source, destination)


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="macdev-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.home = (Path(self.temp.name).resolve() / "home")
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.project = self.home / "unusual-workspace/demo"
        self.write(self.project / "package.json", {"name": "fixture", "scripts": {"build": "fixture-only"}})
        self.artifact = self.project / ".next"
        self.write(self.artifact / "fixture/index.js", "module.exports = 1")
        self.probe = FakeProbe()
        self.backend = FixtureBackend()

    def write(self, p, value):
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value) if isinstance(value, (dict, list)) else value)
        return p

    def scan(self, **kwargs):
        return Scanner(home=self.home, roots=[self.project], probe=self.probe, **kwargs).scan()

    def planned(self):
        report = self.scan()
        item = next(x for x in report["candidates"] if x["path"] == str(self.artifact))
        state = State(self.home)
        plan = make_plan(report, [item["id"]], state, probe=self.probe)
        return state, plan

    def execute(self, state, plan, backend=None):
        return apply(plan["id"], state, confirmed=True, probe=self.probe, backend=backend or self.backend)

    def test_read_only_scan_discovers_nonstandard_project_without_state(self):
        before = tree_snapshot(self.home)
        report = self.scan()
        self.assertEqual(report["scan_status"], "complete")
        self.assertEqual(report["candidates"][0]["rule_id"], "project.next")
        self.assertEqual(before, tree_snapshot(self.home))
        self.assertFalse((self.home / ".local").exists())

    def test_scan_reports_volume_capacity_separately_from_cleanup_candidates(self):
        before = tree_snapshot(self.home)
        with patch("macdev.scanner.shutil.disk_usage", return_value=SimpleNamespace(total=1000000, used=800000, free=200000)) as measure:
            report = self.scan()
        measure.assert_called_once_with(self.home)
        self.assertEqual(report["disk_usage"], {"path": str(self.home), "scope": "filesystem_containing_home",
                                             "status": "available", "total_bytes": 1000000, "used_bytes": 800000, "free_bytes": 200000})
        self.assertNotEqual(report["candidate_allocated_bytes"], report["disk_usage"]["used_bytes"])
        self.assertEqual(before, tree_snapshot(self.home))

    def test_volume_capacity_failure_is_unknown_while_candidates_remain_reported(self):
        with patch("macdev.scanner.shutil.disk_usage", side_effect=PermissionError("fixture")):
            report = self.scan()
        self.assertEqual(report["disk_usage"]["status"], "unavailable")
        self.assertIsNone(report["disk_usage"]["free_bytes"])
        self.assertEqual(report["scan_status"], "partial")
        self.assertTrue(any(x["reason"] == "disk_capacity_unavailable" for x in report["issues"]))
        self.assertTrue(report["candidates"])
        self.assertFalse((self.home / ".local").exists())

    def test_excluded_path_not_candidate(self):
        self.assertEqual(self.scan(excludes=[self.artifact])["candidates"], [])

    def test_no_follow_symlink_project(self):
        link = self.home / "linked"
        link.symlink_to(self.project)
        self.assertEqual(Scanner(home=self.home, roots=[link], probe=self.probe).scan()["candidates"], [])

    def test_special_filename_rejected(self):
        bad = self.project / "bad\nname"
        self.write(bad, "safe")
        with self.assertRaises(Refused):
            ordinary_path(bad, self.home)

    def test_shared_root_and_external_path_refused(self):
        for p in [self.home, self.home / "Library", self.home / ".npm", self.home.parent]:
            p.mkdir(exist_ok=True)
            with self.assertRaises(Refused):
                ordinary_path(p, self.home)

    def test_payload_symlink_is_not_followed(self):
        external = self.write(self.home.parent / "precious", "keep")
        (self.artifact / "outside").symlink_to(external)
        state, plan = self.planned()
        self.execute(state, plan)
        self.assertEqual(external.read_text(), "keep")

    def test_sensitive_payload_report_only(self):
        self.write(self.artifact / ".env", "TOKEN=not-a-real-token")
        self.assertEqual(self.scan()["candidates"][0]["action"], "report_only")

    def test_nested_git_report_only(self):
        (self.artifact / "fixture/.git").mkdir()
        self.assertEqual(self.scan()["candidates"][0]["action"], "report_only")

    def test_unknown_process_is_not_idle(self):
        with patch("macdev.probes.command", return_value=None):
            probe = NativeProbe(self.home)
            self.assertEqual(probe.evidence(self.artifact)["activity"], "unknown")
            self.assertEqual(probe.idle(self.artifact), "unknown")

    def test_git_failure_is_not_treated_as_no_repository(self):
        from macdev.probes import git_evidence
        denied = subprocess.CompletedProcess([], 128, "", "fatal: permission denied")
        with patch("macdev.probes.command", return_value=denied):
            self.assertEqual(git_evidence(self.artifact), "unknown")

    def test_malformed_package_is_report_only_not_a_crash(self):
        folder = self.home / ".npm/_npx/invalid"
        self.write(folder / "package.json", ["not an object"])
        item = next(x for x in self.scan()["candidates"] if x["path"] == str(folder))
        self.assertEqual(item["action"], "report_only")

    def test_root_visibility_required_for_lsof(self):
        r = subprocess.CompletedProcess([], 1, "", "")
        with patch("macdev.probes.command", return_value=r):
            self.assertEqual(NativeProbe(self.home).idle(self.artifact), "unknown")

    def test_lsof_output_even_nonzero_means_active(self):
        root = subprocess.CompletedProcess([], 0, "p1\nu0\n", "")
        opened = subprocess.CompletedProcess([], 1, "p99\nnfile\n", "")
        with patch("macdev.probes.command", side_effect=[root, root, opened]):
            probe = NativeProbe(self.home)
            self.assertEqual(probe.idle(self.artifact), "active")

    def test_configuration_reference_is_private_and_blocks_npx(self):
        folder = self.home / ".npm/_npx/abc"
        self.write(folder / "package.json", {"dependencies": {"example-mcp": "1"}})
        self.write(self.home / ".cursor/mcp.json", {"mcpServers": {"fixture": {"command": "npx", "args": ["example-mcp"], "env": {"TOKEN": "do-not-export"}}}})
        idle = subprocess.CompletedProcess([], 0, "999 /bin/sleep 1", "")
        with patch("macdev.probes.command", return_value=idle):
            probe = NativeProbe(self.home)
            self.assertNotIn("do-not-export", str(probe.references))
            self.assertTrue(probe.evidence(folder, packages=["example-mcp"])["configured_reference"])

    def test_partial_config_blocks_npx_recommendation(self):
        folder = self.home / ".npm/_npx/abc"
        self.write(folder / "package.json", {"dependencies": {"example-mcp": "1"}})
        self.probe.reference_status = "partial"
        item = next(x for x in self.scan()["candidates"] if x["path"] == str(folder))
        self.assertEqual(item["action"], "report_only")

    def test_reference_evidence_becomes_partial_after_plan_preserves_npx(self):
        folder = self.home / ".npm/_npx/abc"
        self.write(folder / "package.json", {"dependencies": {"example-mcp": "1"}})
        report = self.scan()
        item = next(x for x in report["candidates"] if x["path"] == str(folder))
        state = State(self.home)
        plan = make_plan(report, [item["id"]], state, probe=self.probe)
        self.probe.reference_status = "partial"
        run = self.execute(state, plan)
        self.assertTrue(folder.exists())
        self.assertEqual(run["entries"][0]["reason"], "reference_evidence_incomplete")

    def test_snapshot_budget_is_not_zero_size_success(self):
        with self.assertRaises(Refused):
            tree_snapshot(self.artifact, limit=1)
        report = self.scan(budget=-1)
        self.assertEqual(report["scan_status"], "partial")

    def test_duplicate_nested_candidates_count_once(self):
        items = [{"path": str(self.artifact), "rule_id": "a"}, {"path": str(self.artifact / "fixture"), "rule_id": "b"}]
        self.assertEqual(len(deduplicate(items)), 1)

    def test_hard_link_blocks_not_double_counted(self):
        p = self.artifact / "fixture/index.js"
        before = tree_snapshot(self.artifact)
        os.link(p, p.with_name("linked.js"))
        after = tree_snapshot(self.artifact)
        self.assertLess(after["allocated_bytes"] - before["allocated_bytes"], p.stat().st_blocks * 512 or 4096)

    def test_malformed_config_is_partial(self):
        self.write(self.home / ".cursor/mcp.json", "{")
        with patch("macdev.probes.command", return_value=subprocess.CompletedProcess([], 0, "", "")):
            self.assertEqual(NativeProbe(self.home).reference_status, "partial")

    def test_plan_requires_explicit_selection(self):
        with self.assertRaises(Refused):
            make_plan(self.scan(), [], State(self.home), probe=self.probe)

    def test_changed_between_scan_and_plan_refused(self):
        report = self.scan()
        self.write(self.artifact / "new.js", "new")
        with self.assertRaises(Refused):
            make_plan(report, [report["candidates"][0]["id"]], State(self.home), probe=self.probe)

    def test_fabricated_scan_not_execution_authority(self):
        report = self.scan()
        p = self.write(self.home / "precious.txt", "keep")
        report["candidates"][0]["path"] = str(p)
        report["candidates"][0]["snapshot"] = tree_snapshot(p)
        with self.assertRaises(Refused):
            make_plan(report, [report["candidates"][0]["id"]], State(self.home), probe=self.probe)
        self.assertEqual(p.read_text(), "keep")

    def test_plan_tampering_rejected(self):
        state, plan = self.planned()
        p = state.path("plans", plan["id"])
        d = json.loads(p.read_text())
        d["candidates"][0]["path"] = str(self.home / "precious")
        p.write_text(json.dumps(d))
        with self.assertRaises(Refused):
            self.execute(state, plan)
        self.assertTrue(self.artifact.exists())

    def test_confirmation_required(self):
        state, plan = self.planned()
        with self.assertRaises(Refused):
            apply(plan["id"], state, probe=self.probe, backend=self.backend)

    def test_signed_plan_old_policy_refused(self):
        state, plan = self.planned()
        plan["policy_version"] = "different"
        state.write("plans", plan)
        with self.assertRaises(Refused):
            self.execute(state, plan)

    def test_changed_candidate_after_confirmation_skipped(self):
        state, plan = self.planned()
        self.write(self.artifact / "new.js", "new")
        result = self.execute(state, plan)
        self.assertEqual(result["entries"][0]["status"], "skipped")
        self.assertTrue(self.artifact.exists())

    def test_parent_replacement_skipped(self):
        state, plan = self.planned()
        self.project.rename(self.project.with_name("old"))
        self.write(self.artifact / "new.js", "new")
        self.assertEqual(self.execute(state, plan)["entries"][0]["status"], "skipped")

    def test_symlink_replacement_skipped(self):
        state, plan = self.planned()
        self.artifact.rename(self.project / "old_modules")
        self.artifact.symlink_to(self.project / "old_modules")
        self.assertEqual(self.execute(state, plan)["entries"][0]["status"], "skipped")

    def test_new_persistent_exclusion_skipped(self):
        state, plan = self.planned()
        self.write(self.home / ".config/mac-dev-cleanup/config.json", {"excludes": [str(self.artifact)]})
        self.assertEqual(self.execute(state, plan)["entries"][0]["reason"], "newly_excluded")

    def test_newly_active_skipped(self):
        state, plan = self.planned()
        self.probe.active = True
        self.assertEqual(self.execute(state, plan)["entries"][0]["status"], "skipped")

    def test_incomplete_occupancy_skipped(self):
        state, plan = self.planned()
        self.probe.open_state = "unknown"
        self.assertEqual(self.execute(state, plan)["entries"][0]["status"], "skipped")

    def test_git_tracked_after_plan_is_protected(self):
        state, plan = self.planned()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        subprocess.run(["git", "-C", str(self.project), "add", ".next"], check=True)
        self.assertEqual(self.execute(state, plan)["entries"][0]["reason"], "project_now_tracked_or_git_state_unknown")

    def test_trash_only_and_round_trip(self):
        state, plan = self.planned()
        fingerprint = tree_snapshot(self.artifact)["fingerprint"]
        result = self.execute(state, plan)
        entry = result["entries"][0]
        self.assertEqual(entry["status"], "trashed")
        self.assertFalse(self.artifact.exists())
        self.assertTrue(Path(entry["destination"]).is_dir())
        self.assertGreater(result["moved_allocated_bytes"], 0)
        restored = restore(result["id"], state, confirmed=True, backend=self.backend, probe=self.probe)
        self.assertEqual(restored["results"][0]["status"], "restored")
        self.assertEqual(tree_snapshot(self.artifact)["fingerprint"], fingerprint)

    def test_same_plan_is_not_replayed(self):
        state, plan = self.planned()
        self.execute(state, plan)
        with self.assertRaises(Refused):
            self.execute(state, plan)

    def test_trash_failure_never_deletes_source(self):
        state, plan = self.planned()
        class Broken(FixtureBackend):
            def move(self, *args):
                raise OSError("fixture failure")
        result = self.execute(state, plan, Broken())
        self.assertTrue(self.artifact.exists())
        self.assertEqual(result["entries"][0]["status"], "skipped")

    def test_unsafe_trash_mode_is_not_repaired(self):
        trash = self.home / ".Trash"
        trash.mkdir(mode=0o500)
        with self.assertRaises(Refused):
            prepare_trash(self.home)
        self.assertEqual(trash.stat().st_mode & 0o777, 0o500)

    def test_backend_drops_inherited_privilege_and_shell_overrides(self):
        state = State(self.home)
        backend = MoleBackend(state)
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict(os.environ, {"_MOLE_COMPLETE_LSOF_MODE": "sudo", "SUDO_UID": "0", "BASH_ENV": "/untrusted/startup"}):
            with patch("macdev.engine.subprocess.run", return_value=result) as run:
                backend.move(self.artifact, self.home / ".Trash/mac-dev-cleanup-test", tree_snapshot(self.artifact))
                env = run.call_args.kwargs["env"]
                self.assertNotIn("_MOLE_COMPLETE_LSOF_MODE", env)
                self.assertNotIn("SUDO_UID", env)
                self.assertNotIn("BASH_ENV", env)

    @unittest.skipUnless(platform.system() == "Darwin", "upstream Bash probe requires macOS")
    def test_product_flag_never_uses_cached_sudo_probe(self):
        root = Path(__file__).resolve().parent.parent
        marker = self.home / "sudo-was-called"
        shell = '''set -euo pipefail
source "$1/vendor/mole/lib/core/common.sh"
MACDEV_NO_SUDO=1
_mole_lsof_records_include_root_process() { return 1; }
run_with_timeout() { shift; "$@"; }
lsof() { return 1; }
sudo() { : > "$2"; return 0; }
probe_status=0
_mole_complete_lsof_mode || probe_status=$?
[[ $probe_status -eq 2 && ! -e "$2" ]] || exit 1
'''
        # sudo is a fixture function only; invoking it would expose a regression.
        shell = shell.replace('sudo() { : > "$2"; return 0; }', 'sudo() { : > "$marker"; return 0; }')
        env = dict(os.environ, HOME=str(self.home), marker=str(marker))
        for key in list(env):
            if key.startswith(("MOLE_", "MO_", "MACDEV_")):
                env.pop(key)
        result = subprocess.run(["/bin/bash", "-c", shell, "fixture", str(root), str(marker)], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_interrupted_move_recoverable_from_write_ahead_receipt(self):
        state, plan = self.planned()
        class Interrupted(FixtureBackend):
            def move(self, *args):
                super().move(*args)
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.execute(state, plan, Interrupted())
        run = state.history()[0]
        self.assertEqual(run["entries"][0]["status"], "moving")
        result = restore(run["id"], state, confirmed=True, backend=self.backend, probe=self.probe)
        self.assertEqual(result["results"][0]["status"], "restored")

    def test_mutation_timeout_stops_following_candidates(self):
        second = self.project / "dist"
        self.write(second / "output.js", "keep")
        report = self.scan()
        ids = [next(x["id"] for x in report["candidates"] if x["path"] == str(p)) for p in [self.artifact, second]]
        state = State(self.home)
        plan = make_plan(report, ids, state, probe=self.probe)
        class Timeout(FixtureBackend):
            def move(self, *args): raise InterruptedMove("fixture_timeout")
        run = self.execute(state, plan, Timeout())
        self.assertEqual(run["status"], "interrupted")
        self.assertEqual(len(run["entries"]), 1)
        self.assertTrue(second.exists())

    def test_completed_move_then_timeout_can_be_restored(self):
        state, plan = self.planned()
        class TimeoutAfterMove(FixtureBackend):
            def move(self, *args):
                super().move(*args)
                raise InterruptedMove("fixture_timeout")
        run = self.execute(state, plan, TimeoutAfterMove())
        self.assertEqual(run["entries"][0]["status"], "recovery_required")
        result = restore(run["id"], state, confirmed=True, backend=self.backend, probe=self.probe)
        self.assertEqual(result["results"][0]["status"], "restored")

    def test_restore_does_not_overwrite_recreated_path(self):
        state, plan = self.planned()
        run = self.execute(state, plan)
        self.write(self.artifact / "precious", "new data")
        result = restore(run["id"], state, confirmed=True, backend=self.backend, probe=self.probe)
        self.assertEqual(result["results"][0]["reason"], "restore_destination_exists")
        self.assertEqual((self.artifact / "precious").read_text(), "new data")

    def test_restore_missing_payload_reports_without_recreating(self):
        state, plan = self.planned()
        run = self.execute(state, plan)
        dest = Path(run["entries"][0]["destination"])
        dest.rename(dest.with_name("elsewhere"))
        result = restore(run["id"], state, confirmed=True, backend=self.backend, probe=self.probe)
        self.assertEqual(result["results"][0]["status"], "skipped")
        self.assertFalse(self.artifact.exists())

    def test_exclusive_rename_never_replaces(self):
        one = self.write(self.home / "one", "one")
        two = self.write(self.home / "two", "two")
        with self.assertRaises(Refused):
            rename_exclusive(one, two)
        self.assertEqual(one.read_text(), "one")
        self.assertEqual(two.read_text(), "two")

    def test_state_redirect_refused(self):
        other = self.home / "other"
        other.mkdir()
        link = self.home / "state-link"
        link.symlink_to(other)
        with self.assertRaises(Refused):
            State(self.home, link)

    def test_world_readable_state_refused(self):
        state = self.home / "state"
        state.mkdir(mode=0o755)
        with self.assertRaises(Refused):
            State(self.home, state)

    def test_concurrent_operation_refused(self):
        state, plan = self.planned()
        with state.locked():
            with self.assertRaises(Refused):
                self.execute(state, plan)

    def test_browser_origin_and_extension_separated(self):
        base = self.home / "Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage"
        for name, origin in [("website", "https://example.test"), ("extension", "chrome-extension://fixture")]:
            self.write(base / name / "index.txt", origin)
            self.write(base / name / "cache/data", "content")
        report = self.scan()
        items = [x for x in report["candidates"] if x["rule_id"] == "browser.site_cache"]
        self.assertEqual(len(items), 2)
        self.assertEqual(next(x for x in items if "/website/" in x["path"])["action"], "trash")
        self.assertEqual(next(x for x in items if "/extension/" in x["path"])["action"], "report_only")

    def test_managed_cache_never_executed(self):
        self.write(self.home / ".cache/uv/payload", "cache")
        item = next(x for x in self.scan()["candidates"] if x["rule_id"] == "owner.managed_cache")
        self.assertEqual(item["action"], "report_only")

    def test_npx_version_and_purpose_without_credential_url(self):
        folder = self.home / ".npm/_npx/fixture"
        self.write(folder / "package.json", {"dependencies": {"n8n": "https://user:secret@example.test/archive"}})
        self.write(folder / "node_modules/n8n/package.json", {"version": "1.2.3", "description": "ignored untrusted text"})
        item = next(x for x in self.scan()["candidates"] if x["rule_id"] == "developer.npx")
        self.assertEqual(item["package_details"][0]["installed_version"], "1.2.3")
        self.assertEqual(item["package_details"][0]["purpose"], "workflow automation")
        self.assertNotIn("secret", json.dumps(item))

    def test_virtualenv_without_rebuild_manifest_is_report_only(self):
        folder = self.project / ".venv"
        self.write(folder / "pyvenv.cfg", "version = 3.11")
        item = next(x for x in self.scan()["candidates"] if x["rule_id"] == "project.venv")
        self.assertEqual(item["action"], "report_only")

    def test_virtualenv_with_manifest_cannot_enter_cleanup_plan(self):
        folder = self.project / ".venv"
        self.write(folder / "pyvenv.cfg", "version = 3.11")
        self.write(self.project / "requirements.txt", "fixture==1.0")
        report = self.scan()
        item = next(x for x in report["candidates"] if x["rule_id"] == "project.venv")
        state = State(self.home)
        self.assertEqual(item["action"], "report_only")
        with self.assertRaises(Refused):
            make_plan(report, [item["id"]], state, probe=self.probe)
        self.assertTrue(folder.exists())

    def test_project_node_modules_is_preserved_even_when_idle_and_untracked(self):
        folder = self.project / "node_modules"
        self.write(folder / "fixture/index.js", "module.exports = 1")
        item = next(x for x in self.scan()["candidates"] if x["path"] == str(folder))
        self.assertEqual(item["action"], "report_only")
        self.assertIn("project_dependency_environment_preserved", item["evidence"])
        state = State(self.home)
        with self.assertRaises(Refused):
            make_plan(self.scan(), [item["id"]], state, probe=self.probe)
        self.assertTrue(folder.exists())

    def test_dependency_entry_in_preexisting_plan_is_refused_during_apply(self):
        state, plan = self.planned()
        folder = self.project / "node_modules"
        self.write(folder / "fixture/index.js", "module.exports = 1")
        plan["candidates"][0].update(path=str(folder), rule_id="project.node_modules", snapshot=tree_snapshot(folder))
        state.write("plans", plan)
        result = self.execute(state, plan)
        self.assertEqual(result["entries"][0]["reason"], "project_dependency_environment_preserved")
        self.assertTrue(folder.exists())

    def test_project_mcp_added_after_plan_is_respected(self):
        class ConfigProbe(NativeProbe):
            def refresh(inner):
                inner.rows = []
                inner.references = set()
                inner.reference_status = "complete"
                inner._references()
            def owner_cache_paths(inner): return []
            def idle(inner, path, *, rule_id=None): return "idle"
        folder = self.home / ".npm/_npx/reference-fixture"
        self.write(folder / "package.json", {"dependencies": {"fixture-mcp": "1.0"}})
        probe = ConfigProbe(self.home)
        report = Scanner(home=self.home, roots=[self.project], probe=probe).scan()
        item = next(x for x in report["candidates"] if x["path"] == str(folder))
        state = State(self.home)
        plan = make_plan(report, [item["id"]], state, probe=probe)
        self.write(self.project / ".mcp.json", {"mcpServers": {"new": {"command": "npx", "args": ["fixture-mcp"]}}})
        result = apply(plan["id"], state, confirmed=True, probe=ConfigProbe(self.home), backend=self.backend)
        self.assertEqual(result["entries"][0]["reason"], "active_or_referenced_or_unknown")
        self.assertTrue(folder.exists())

    def test_directory_name_alone_does_not_prove_artifact_type(self):
        self.write(self.project / "target/precious", "not a Rust or Maven project")
        item = next(x for x in self.scan()["candidates"] if x["path"] == str(self.project / "target"))
        self.assertEqual(item["action"], "report_only")

    def test_current_codex_release_and_pending_marker_preserved(self):
        root = self.home / ".codex/packages/app-server-daemon"
        for version in ["1.0.0", "1.1.0", "1.2.0"]:
            self.write(root / "releases" / version / "bin/codex", "fixture")
        (root / "current").symlink_to(root / "releases/1.1.0")
        self.write(root / "auto-update-version", "1.2.0")
        self.write(root / "install.lock", "")
        items = [x for x in self.scan()["candidates"] if x["rule_id"] == "agent.codex_old_release"]
        self.assertEqual([Path(x["path"]).name for x in items], ["1.0.0"])
        state = State(self.home)
        plan = make_plan(self.scan(), [items[0]["id"]], state, probe=self.probe)
        import fcntl
        with (root / "install.lock").open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.execute(state, plan)["entries"][0]["reason"], "daemon_install_lock_busy")

    def test_local_history_and_sqlite_payload_preserved(self):
        self.write(self.artifact / "LocalHistory/record", "history")
        self.write(self.artifact / "user.sqlite", "not-a-real-db")
        self.assertEqual(self.scan()["candidates"][0]["action"], "report_only")

    def test_browser_origin_strips_embedded_credentials(self):
        base = self.home / "Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage/origin"
        self.write(base / "index.txt", "https://user:password@example.test:443")
        self.write(base / "cache/data", "content")
        item = next(x for x in self.scan()["candidates"] if x["rule_id"] == "browser.site_cache")
        self.assertEqual(item["evidence"], ["origins: https://example.test:443"])

    def test_browser_index_symlink_not_followed(self):
        base = self.home / "Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage/origin"
        self.write(base / "cache/data", "content")
        external = self.write(self.home.parent / "private", "https://private.example.test")
        (base / "index.txt").symlink_to(external)
        item = next(x for x in self.scan()["candidates"] if x["rule_id"] == "browser.site_cache")
        self.assertEqual(item["action"], "report_only")
        self.assertNotIn("private.example", str(item))

    def test_extension_becoming_current_is_protected(self):
        base = self.home / ".vscode/extensions"
        folder = base / "fixture.extension-1.0"
        self.write(folder / "package.json", {"name": "fixture"})
        self.write(base / ".obsolete", {folder.name: True})
        self.write(base / "extensions.json", [])
        report = self.scan()
        item = next(x for x in report["candidates"] if x["rule_id"] == "editor.obsolete_extension")
        state = State(self.home)
        plan = make_plan(report, [item["id"]], state, probe=self.probe)
        self.write(base / "extensions.json", [{"relativeLocation": folder.name}])
        self.assertEqual(self.execute(state, plan)["entries"][0]["reason"], "extension_no_longer_obsolete")

    @unittest.skipUnless(platform.system() == "Darwin", "pinned Bash integration requires macOS")
    def test_pinned_mole_bridge_moves_only_fixture(self):
        state = State(self.home)
        trash = self.home / ".Trash"
        trash.mkdir(mode=0o700)
        dest = trash / "mac-dev-cleanup-fixture"
        backend = MoleBackend(state)
        backend.move(self.artifact, dest, tree_snapshot(self.artifact))
        self.assertFalse(self.artifact.exists())
        self.assertTrue((dest / "fixture/index.js").is_file())


if __name__ == "__main__":
    unittest.main()
