"""Cache-only occupancy compatibility, including loss of observation coverage."""
import json
import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from macdev.engine import MoleBackend, apply, make_plan, restore
from macdev.occupancy import USER_CACHE_RULES, check_occupancy, user_visibility
from macdev.probes import NativeProbe, command as native_command
from macdev.scanner import Scanner
from macdev.state import State


@unittest.skipIf(os.getuid() == 0, "current-user compatibility requires a non-root process")
class OccupancyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tidvo-occupancy-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.cache = self.home / "project/__pycache__"
        self.cache.mkdir(parents=True)
        (self.cache / "fixture.pyc").write_text("fixture bytecode")
        (self.cache.parent / "pyproject.toml").write_text('[project]\nname="fixture"')
        environment = patch.dict(os.environ, {"HOME": str(self.home),
                                 "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.pid, self.uid = os.getpid(), os.getuid()
        self.calls = []
        self.overrides = {}
        factory = tempfile.NamedTemporaryFile
        def canary(*args, **kwargs):
            kwargs["dir"] = self.temp.name
            held = factory(*args, **kwargs)
            self.canary = Path(held.name).resolve()
            return held
        for patcher in [patch("macdev.occupancy.platform", SimpleNamespace(system=lambda: "Darwin")),
                        patch("macdev.occupancy.tempfile.NamedTemporaryFile", side_effect=canary)]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def result(self, code=0, output="", error=""):
        return subprocess.CompletedProcess([], code, output, error)

    def command(self, args, timeout=10):
        self.calls.append(args)
        if args[0] == "git":
            return self.result(128, error="fatal: not a git repository")
        if args == ["/bin/ps", "-axo", "pid=,command="]:
            return self.result(output=f"{self.pid} /fixture/interpreter\n")
        if args[-2:] == ["-p", "1"]:
            label, default = "root", self.result(1)
        elif args[-1] == "-Fpun":
            label, default = "canary", self.result(output=f"p{self.pid}\nu{self.uid}\nn{self.canary}\n")
        elif args[-1] == "-Fpuf":
            label, default = "user", self.result(output=f"p{self.pid}\nu{self.uid}\nfcwd\nf3\n")
        elif args == ["/bin/ps", "-axo", "pid=,ppid=,uid=,stat=,comm="]:
            label, default = "census", self.result(output=f"{self.pid} 1 {self.uid} S /fixture/interpreter\n")
        else:
            label, default = "target", self.result(1)
        return self.overrides.get(label, default)

    def check(self, rule="project.__pycache__", path=None):
        return check_occupancy(path or self.cache, self.home, self.command, rule)

    def test_root_invisible_known_caches_use_calibrated_current_user_evidence(self):
        for rule in USER_CACHE_RULES:
            with self.subTest(rule=rule):
                evidence = self.check(rule)
                self.assertEqual(evidence["status"], "idle")
                self.assertEqual(evidence["scope"], "current_user_cache")
                self.assertFalse(evidence["other_users_certified"])
                self.assertNotIn(str(self.canary), json.dumps(evidence))

    def test_builds_logs_offline_data_and_unspecified_rules_stay_strict(self):
        for rule in [None, "project.dist", "project.next", "app.historical_logs", "browser.site_cache", "developer.npx", "agent.codex_old_release"]:
            with self.subTest(rule=rule):
                self.calls.clear()
                self.assertEqual(self.check(rule)["status"], "unknown")
                self.assertEqual(len(self.calls), 1)

    def test_open_target_is_active_even_with_nonzero_exit(self):
        self.overrides["target"] = self.result(1, "p99\nnfixture\n")
        self.assertEqual(self.check()["status"], "active")

    def test_target_warning_timeout_failure_and_empty_success_are_unknown(self):
        for result in [None, self.result(1, error="permission warning"), self.result(2), self.result(0), self.result(1, "unrecognized output")]:
            with self.subTest(result=result):
                self.overrides["target"] = result
                self.assertEqual(self.check()["status"], "unknown")

    def test_canary_must_show_the_open_file_and_owner(self):
        for result in [None, self.result(1), self.result(output=f"p{self.pid}\nu{self.uid}\n"), self.result(output=f"p{self.pid}\nnfixture\n"), self.result(error="partial")]:
            with self.subTest(result=result):
                self.overrides["canary"] = result
                self.assertEqual(self.check()["status"], "unknown")
                self.assertNotIn("-Fpuf", [args[-1] for args in self.calls[-2:]])

    def test_unobservable_user_process_blocks_negative_target_result(self):
        self.overrides["census"] = self.result(output=f"{self.pid} 1 {self.uid} S python\n999 1 {self.uid} S protected-app\n")
        self.assertEqual(self.check()["status"], "unknown")

    def test_pid_and_uid_without_file_descriptor_do_not_prove_visibility(self):
        self.overrides["user"] = self.result(output=f"p{self.pid}\nu{self.uid}\nfNOFD\n")
        self.assertEqual(self.check()["status"], "unknown")

    def test_bad_process_output_and_missing_self_fail_closed(self):
        for output in ["", "malformed", f"999 1 {self.uid} S other\n"]:
            self.overrides["census"] = self.result(output=output)
            self.assertEqual(self.check()["status"], "unknown")

    def test_user_census_and_lsof_failures_remain_unknown(self):
        for label in ["user", "census"]:
            for result in [None, self.result(1), self.result(error="permission warning")]:
                with self.subTest(label=label, result=result):
                    self.overrides = {label: result}
                    self.assertEqual(self.check()["status"], "unknown")

    def test_only_measurement_ps_and_zombies_are_exempt_from_census(self):
        self.overrides["census"] = self.result(output=f"{self.pid} 1 {self.uid} S python\n998 {self.pid} {self.uid} R /bin/ps\n999 1 {self.uid} Z zombie\n")
        self.assertEqual(self.check()["status"], "idle")
        self.overrides["census"] = self.result(output=f"{self.pid} 1 {self.uid} S python\n998 1 {self.uid} R /bin/ps\n")
        self.assertEqual(self.check()["status"], "unknown")

    def test_shared_roots_redirects_and_outside_home_do_not_get_cache_scope(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        link = self.home / "redirect"
        link.symlink_to(self.cache)
        for path in [self.home, outside, link]:
            with self.subTest(path=path):
                self.assertEqual(self.check(path=path)["status"], "unknown")

    def test_foreign_owner_does_not_get_current_user_cache_scope(self):
        with patch("macdev.occupancy.os.getuid", return_value=self.uid + 1):
            self.assertEqual(self.check()["status"], "unknown")

    def test_non_macos_does_not_get_compatibility_scope(self):
        with patch("macdev.occupancy.platform", SimpleNamespace(system=lambda: "Linux")):
            self.assertEqual(self.check()["status"], "unknown")

    def test_root_visible_keeps_original_target_check(self):
        self.overrides["root"] = self.result(output="p1\nu0\n")
        evidence = self.check("project.dist")
        self.assertEqual(evidence["status"], "idle")
        self.assertEqual(evidence["scope"], "root_visible_probe")
        self.assertEqual(len(self.calls), 2)

    def test_uninstalled_residual_uses_its_own_observation_scope(self):
        evidence = self.check("app.uninstalled_residual")
        self.assertEqual(evidence["status"], "idle")
        self.assertEqual(evidence["scope"], "current_user_uninstalled_residual")
        self.assertFalse(evidence["other_users_certified"])

    def test_verified_obsolete_program_uses_separate_observation_scope(self):
        evidence = self.check("editor.obsolete_extension")
        self.assertEqual(evidence["status"], "idle")
        self.assertEqual(evidence["scope"], "current_user_obsolete_extension")
        self.assertFalse(evidence["other_users_certified"])

    def test_receipts_record_scope_and_restore_uses_same_cache_contract(self):
        class Probe(NativeProbe):
            def owner_cache_paths(inner): return []
        with patch("macdev.probes.command", side_effect=self.command):
            probe = Probe(self.home)
            report = Scanner(home=self.home, roots=[self.cache.parent], probe=probe).scan(audit_agents=False)
            item = next(x for x in report["candidates"] if x["path"] == str(self.cache))
            state = State(self.home)
            plan = make_plan(report, [item["id"]], state, probe=probe)
            from test_product import FixtureBackend
            backend = FixtureBackend()
            run = apply(plan["id"], state, confirmed=True, probe=probe, backend=backend)
            self.assertEqual(run["entries"][0]["status"], "trashed")
            self.assertEqual(run["entries"][0]["occupancy"]["scope"], "current_user_cache")
            result = restore(run["id"], state, confirmed=True, probe=probe, backend=backend)
            self.assertEqual(result["results"][0]["status"], "restored")
            self.assertEqual(result["results"][0]["occupancy"]["scope"], "current_user_cache")


class ScopeBoundaryTests(unittest.TestCase):
    def test_root_process_never_enters_user_cache_visibility_mode(self):
        with patch("macdev.occupancy.os.getuid", return_value=0):
            valid, reason, count = user_visibility(lambda *args: self.fail("must not execute"))
        self.assertFalse(valid)
        self.assertEqual(count, 0)


@unittest.skipUnless(platform.system() == "Darwin" and os.getuid() != 0, "macOS fixture integration")
class NativeOccupancyIntegration(unittest.TestCase):
    def test_real_held_fixture_is_blocked_then_trashed_and_restored(self):
        with tempfile.TemporaryDirectory(prefix="tidvo-native-occupancy-") as directory:
            home = Path(directory).resolve() / "home"
            cache = home / "project/__pycache__"
            cache.mkdir(parents=True)
            (cache.parent / "pyproject.toml").write_text('[project]\nname="fixture"')
            payload = cache / "held.pyc"
            payload.write_text("fixture bytecode")
            def observed_command(args, timeout=10):
                if args == ["/usr/sbin/lsof", "-Fpu", "-p", "1"]:
                    return subprocess.CompletedProcess(args, 1, "", "")
                return native_command(args, timeout)
            class Probe(NativeProbe):
                def owner_cache_paths(self): return []
            environment = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1"}
            with patch.dict(os.environ, environment, clear=True), patch("macdev.probes.command", side_effect=observed_command):
                probe = Probe(home)
                with payload.open() as held:
                    state = probe.idle(cache, rule_id="project.__pycache__")
                    if state == "unknown":
                        self.skipTest("native process observation unavailable in this sandbox: " + probe.last_occupancy_evidence["reason"])
                    self.assertEqual(state, "active")
                    self.assertFalse(held.closed)
                state = probe.idle(cache, rule_id="project.__pycache__")
                if state == "unknown":
                    self.assertEqual(payload.read_text(), "fixture bytecode")
                    self.skipTest("native observation became incomplete after closing fixture: " + probe.last_occupancy_evidence["reason"])
                self.assertEqual(state, "idle")
                report = Scanner(home=home, roots=[cache.parent], probe=probe).scan(audit_agents=False)
                item = next(x for x in report["candidates"] if x["path"] == str(cache))
                state = State(home)
                plan = make_plan(report, [item["id"]], state, probe=probe)
                run = apply(plan["id"], state, confirmed=True, probe=probe, backend=MoleBackend(state))
                entry = run["entries"][0]
                if entry["status"] == "skipped" and entry.get("occupancy", {}).get("status") == "unknown":
                    self.assertEqual(entry["reason"], "open_file_check_active_or_incomplete")
                    self.assertEqual(payload.read_text(), "fixture bytecode")
                    self.assertFalse(Path(entry["destination"]).exists())
                    self.skipTest("native apply correctly retained fixture after observation loss: " + entry["occupancy"]["reason"])
                self.assertEqual(entry["status"], "trashed", entry)
                result = restore(run["id"], state, confirmed=True, probe=probe, backend=MoleBackend(state))
                record = result["results"][0]
                if record["status"] == "skipped" and record.get("occupancy", {}).get("status") == "unknown":
                    self.assertEqual(record["reason"], "restore_payload_in_use_or_unknown")
                    self.assertFalse(cache.exists())
                    self.assertEqual((Path(entry["destination"]) / "held.pyc").read_text(), "fixture bytecode")
                    self.skipTest("native restore correctly retained Trash fixture after observation loss: " + record["occupancy"]["reason"])
                self.assertEqual(record["status"], "restored", result)
                self.assertEqual(payload.read_text(), "fixture bytecode")
