import importlib.util
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from macdev import __version__


def script_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="macdev-interface-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "COREPACK_ENABLE_NETWORK": "0"}

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/tidvo.py"), *args], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_empty_history_does_not_create_state(self):
        r = self.cli("history", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"runs": []})
        self.assertEqual(list(self.home.iterdir()), [])

    def test_renamed_and_legacy_entrypoints_preserve_existing_signed_history(self):
        from macdev.state import State
        state = State(self.home)
        run = {"id": "a" * 32, "home": str(self.home), "started_at": "2026-10-23T00:00:00Z", "entries": [], "status": "finished"}
        state.write("runs", run)
        current = self.cli("history", "--json")
        legacy = subprocess.run([sys.executable, str(ROOT / "scripts/mac_cleanup.py"), "history", "--json"],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(json.loads(current.stdout), {"runs": [run]})
        self.assertEqual(json.loads(legacy.stdout), json.loads(current.stdout))
        self.assertFalse((self.home / ".local/state/tidvo").exists())

    def test_cli_scan_missing_root_is_partial_and_read_only(self):
        r = self.cli("scan", "--root", str(self.home / "missing"), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["scan_status"], "partial")
        self.assertFalse((self.home / ".local").exists())

    def test_cli_rejects_bad_config_without_traceback(self):
        p = self.home / ".config/mac-dev-cleanup/config.json"
        p.parent.mkdir(parents=True)
        p.write_text('[]')
        r = self.cli("scan")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_cli_output_never_overwrites(self):
        p = self.home / "existing.json"
        p.write_text('keep')
        r = self.cli("scan", "--root", str(self.home / "missing"), "--output", str(p))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(p.read_text(), "keep")

    def test_baseline_comparison_is_not_an_extra_space_claim(self):
        compare = script_module("compare_baseline").compare
        report = {"scan_status": "partial", "candidates": [
            {"path": "/fixture/cache/child", "action": "trash"},
            {"path": "/fixture/other", "action": "report_only"}]}
        value = compare(report, '/fixture/cache  # 12MB\n/fixture/mole-only  # size unknown\n')
        self.assertEqual(value["overlapping_product_candidates"], 1)
        self.assertEqual(value["product_scan_status"], "partial")
        self.assertEqual(value["product_only"][0]["path"], "/fixture/other")
        self.assertNotIn("extra_reclaimable_bytes", value)

    def test_release_is_self_contained_and_has_corresponding_source(self):
        result = script_module("build_release").build(Path(self.temp.name) / "release")
        extract = Path(self.temp.name) / "unpacked"
        extract.mkdir()
        with tarfile.open(result["archive"]) as tar:
            names = tar.getnames()
            self.assertTrue(all(not n.startswith('/') and '..' not in Path(n).parts for n in names))
            self.assertFalse(any('__pycache__' in n or 'docs/img' in n for n in names))
            self.assertFalse(any('/vendor/mole/tests/tmp-' in n for n in names))
            self.assertEqual([n for n in names if n.endswith('/SKILL.md')], ['tidvo/SKILL.md'])
            tar.extractall(extract, filter='data')
        skill = extract / "tidvo"
        for name in ["SKILL.md", "README.zh-CN.md", "INSTALL.md", "LICENSE", "UPSTREAM.md", "macdev/engine.py", "macdev/agent_catalog.py", "macdev/agent_inspection.py", "references/agent-adapters.md", "scripts/tidvo.py", "scripts/mac_cleanup.py", "scripts/mole_bridge.sh", "vendor/mole/lib/core/file_ops.sh", "tests/test_product.py", "tests/test_agents.py"]:
            self.assertTrue((skill / name).is_file(), name)
        r = subprocess.run([sys.executable, str(skill / "scripts/tidvo.py"), "--version"],
                           env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), __version__)
        r = subprocess.run([sys.executable, str(skill / "scripts/tidvo.py"), "scan", "--root", str(self.home / "missing"), "--json"],
                           cwd=extract, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["scan_status"], "partial")

    def test_terminal_summary_saves_json_and_shows_how_to_plan(self):
        report = self.home / "scan.json"
        r = self.cli("scan", "--root", str(self.home / "missing"), "--output", str(report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("本次只扫描，没有清理文件", r.stdout)
        self.assertIn("plan --scan", r.stdout)
        self.assertIn(str(report), r.stdout)
        self.assertEqual(json.loads(report.read_text())["scan_status"], "partial")
        self.assertFalse((self.home / ".local").exists())

    def test_unsaved_summary_explains_report_is_needed_for_plan(self):
        r = self.cli("scan", "--root", str(self.home / "missing"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--output scan.json", r.stdout)
        self.assertFalse((self.home / ".local").exists())

    def test_terminal_summary_escapes_control_characters_in_untrusted_paths(self):
        project = self.home / "project-\x1b[2J\nspoof"
        cache = project / "__pycache__"
        cache.mkdir(parents=True)
        (project / "package.json").write_text('{}')
        (cache / "fixture.pyc").write_text('fixture')
        r = self.cli("scan", "--root", str(project))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("\x1b", r.stdout)
        self.assertNotIn("\nspoof", r.stdout)
        self.assertIn("\\x1b", r.stdout)

    def test_plan_summary_names_exact_selection_and_confirmation_command(self):
        from macdev.display import render
        selected = {"id": "a" * 24, "path": "/fixture/selected-cache", "action": "trash", "allocated_bytes": 4096}
        plan = {"id": "b" * 32, "selected_allocated_bytes": 4096, "candidates": [selected]}
        text = render("plan", plan)
        self.assertIn(selected["path"], text)
        self.assertIn("apply --plan " + plan["id"] + " --confirmed", text)
        self.assertIn("没有清理文件", text)

    def test_terminal_summary_retains_dependency_reason_and_unknown_size(self):
        from macdev.display import candidates
        item = {"id": "a" * 24, "path": "/fixture/node_modules", "action": "report_only", "allocated_bytes": None,
                "evidence": ["project_dependency_environment_preserved"]}
        text = "\n".join(candidates([item]))
        self.assertIn("保留开发环境", text)
        self.assertIn("未知", text)


if __name__ == "__main__":
    unittest.main()
