"""Installation evidence, exclusive residual scope and reinstallation races."""
import json
import os
import platform
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from macdev.app_installation import PROFILES, RESIDUAL_RULE, inspect_installation, residual_paths
from macdev.engine import MoleBackend, apply, make_plan, restore
from macdev.safety import Refused
from macdev.scanner import Scanner
from macdev.state import State
from test_product import FakeProbe, FixtureBackend


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tidvo-installation-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.apps = self.home / "Applications"
        self.apps.mkdir()
        self.response = subprocess.CompletedProcess([], 0, "", "")
        patcher = patch("macdev.app_installation.platform", SimpleNamespace(system=lambda: "Darwin"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def bundle(self, name="Dia", identifier="company.thebrowser.dia", parent=None):
        app = (parent or self.apps) / (name + ".app")
        (app / "Contents").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": identifier}))
        return app

    def inspect(self):
        return inspect_installation("Dia", self.home, lambda *args: self.response, app_roots=[self.apps])

    def test_empty_inventory_is_scoped_not_found_not_uninstall_proof(self):
        evidence = self.inspect()
        self.assertEqual(evidence["status"], "not_found")
        self.assertTrue(evidence["absence_is_not_uninstall_proof"])

    def test_named_bundle_blocks_even_when_bundle_metadata_is_damaged(self):
        (self.apps / "Dia.app").mkdir()
        self.assertEqual(self.inspect()["status"], "installed")

    def test_renamed_bundle_is_detected_by_identifier(self):
        app = self.bundle("My Browser")
        self.assertIn(str(app), self.inspect()["paths"])

    def test_nested_second_copy_prevents_uninstalled_classification(self):
        self.bundle("Renamed", parent=self.apps / "Tools/Browsers")
        self.assertEqual(self.inspect()["status"], "installed")

    def test_spotlight_finds_portable_copy_outside_application_folders(self):
        app = self.bundle("Portable", parent=self.home / "Portable")
        self.response = subprocess.CompletedProcess([], 0, str(app) + "\n", "")
        self.assertEqual(self.inspect()["status"], "installed")

    def test_failed_or_malformed_spotlight_does_not_authorize_residual_cleanup(self):
        for response in [None, subprocess.CompletedProcess([], 1, "", ""),
                         subprocess.CompletedProcess([], 0, "relative.app\n", ""),
                         subprocess.CompletedProcess([], 0, "", "permission denied")]:
            self.response = response
            self.assertEqual(self.inspect()["status"], "unknown")

    def test_unverified_spotlight_identity_stays_unknown(self):
        app = self.bundle("Other", "other.application", self.home / "Portable")
        self.response = subprocess.CompletedProcess([], 0, str(app) + "\n", "")
        self.assertEqual(self.inspect()["status"], "unknown")

    def test_redirected_application_folder_stays_unknown(self):
        alias = self.home / "redirect"
        alias.symlink_to(self.apps)
        evidence = inspect_installation("Dia", self.home, lambda *args: self.response, app_roots=[alias])
        self.assertEqual(evidence["status"], "unknown")

    def test_unknown_owner_or_non_macos_cannot_establish_absence(self):
        self.assertEqual(inspect_installation("unknown", self.home, lambda *args: self.response, app_roots=[])['status'], "unknown")
        with patch("macdev.app_installation.platform", SimpleNamespace(system=lambda: "Linux")):
            self.assertEqual(self.inspect()["status"], "unknown")


class ResidualProbe(FakeProbe):
    def __init__(self):
        super().__init__()
        self.install_status = "not_found"
        self.after_occupancy = None

    def installation(self, owner, *, refresh=False):
        return {"status": self.install_status, "paths": [], "bundle_ids": PROFILES.get(owner, {}).get("bundles", [])}

    def idle(self, path, *, rule_id=None):
        if self.after_occupancy:
            self.after_occupancy()
        return super().idle(path, rule_id=rule_id)


class ResidualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tidvo-residual-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.data = self.home / "Library/Application Support/Dia"
        self.data.mkdir(parents=True)
        (self.data / "memory.db").write_bytes(b"fixture private data")
        (self.data / "memory.db-wal").write_bytes(b"fixture wal")
        self.project = self.home / "project"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text('[project]\nname="fixture"')
        env = patch.dict(os.environ, {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.probe = ResidualProbe()
        self.state = State(self.home)

    def scan(self, asserted=True, **kwargs):
        return Scanner(home=self.home, roots=[self.project], probe=self.probe,
                       uninstalled_apps=["Dia"] if asserted else [], **kwargs).scan(audit_agents=False)

    def item(self, report):
        return next(x for x in report["candidates"] if x['path'] == str(self.data))

    def plan(self):
        report = self.scan()
        return make_plan(report, [self.item(report)["id"]], self.state, probe=self.probe)

    def test_absence_without_user_uninstall_confirmation_is_report_only(self):
        report = self.scan(asserted=False)
        item = next(c for c in report['uninstalled_residual_inventory'] if c['path'] == str(self.data))
        self.assertEqual(item["action"], "report_only")
        self.assertNotIn(item, report['candidates'])
        with self.assertRaises(Refused):
            make_plan(report, [item["id"]], self.state, probe=self.probe)

    def test_confirmed_uninstalled_exclusive_database_root_is_eligible(self):
        item = self.item(self.scan())
        self.assertEqual(item["action"], "trash")
        self.assertEqual(item["rule_id"], RESIDUAL_RULE)
        self.assertTrue(item["residual_context"]["user_confirmed_uninstalled"])
        self.assertIn("memory.db", item["snapshot"]["sensitive"])

    def test_installed_or_unknown_is_not_upgraded_by_user_assertion(self):
        for status in ["installed", "unknown"]:
            self.probe.install_status = status
            report = self.scan()
            self.assertFalse(any(c['action'] == 'trash' and c['rule_id'] == RESIDUAL_RULE for c in report['candidates']))

    def test_active_referenced_and_incomplete_reference_evidence_are_retained(self):
        for flag, value in [("active", True), ("referenced", True), ("reference_status", "partial")]:
            self.probe = ResidualProbe()
            setattr(self.probe, flag, value)
            self.assertEqual(self.item(self.scan())["action"], "report_only")

    def test_exact_paths_do_not_include_shared_vendor_roots_or_user_vaults(self):
        for owner in PROFILES:
            for path in residual_paths(self.home, owner):
                self.assertTrue(path.is_relative_to(self.home / "Library"))
                self.assertNotIn(path.name, ["Google", "Application Support", "Caches", "Group Containers", "Containers"])
        (self.home / 'notes').mkdir()
        self.assertFalse(any(c['path'] == str(self.home/'notes') for c in self.scan()['candidates']))

    def test_exclusions_and_nested_agent_resources_remain_protected(self):
        self.assertFalse(self.scan(excludes=[self.data])['candidates'])
        (self.data / 'AGENTS.md').write_text('fixture agent instructions')
        self.assertEqual(self.item(self.scan())["action"], "report_only")

    def test_user_declared_agent_root_overrides_uninstall_confirmation(self):
        config = self.home / '.config/mac-dev-cleanup/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'agent_roots': {'custom_agent': [str(self.data)]}}))
        self.assertEqual(self.item(self.scan())["action"], "report_only")

    def test_uninstalled_parent_deduplicates_nested_cache_candidates(self):
        p = self.data / 'User Data/Default/GPUCache'
        p.mkdir(parents=True)
        (p/'fixture').write_text('cache')
        candidates = self.scan()['candidates']
        self.assertEqual([c['path'] for c in candidates], [str(self.data)])

    def test_unconfirmed_parent_does_not_hide_independent_cache_candidates(self):
        p = self.data / 'User Data/Default/GPUCache'
        p.mkdir(parents=True)
        (p/'fixture').write_text('cache')
        report = self.scan(asserted=False)
        self.assertTrue(any(c['path'] == str(p) and c['action'] == 'trash' for c in report['candidates']))
        self.assertTrue(report['uninstalled_residual_inventory'])

    def test_signed_but_forged_shared_path_is_refused_at_apply(self):
        plan = self.plan()
        plan['candidates'][0]['path'] = str(self.home / 'Library/Application Support')
        self.state.write('plans', plan)
        run = apply(plan['id'], self.state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'], 'skipped')
        self.assertTrue(self.data.exists())

    def test_residual_referenced_during_occupancy_is_preserved(self):
        plan = self.plan()
        self.probe.after_occupancy = lambda: setattr(self.probe, 'referenced', True)
        run = apply(plan['id'], self.state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'], 'skipped')
        self.assertTrue(self.data.exists())

    def test_reinstallation_between_scan_and_plan_refuses(self):
        report = self.scan()
        self.probe.install_status = 'installed'
        with self.assertRaises(Refused):
            make_plan(report, [self.item(report)['id']], self.state, probe=self.probe)

    def test_reinstallation_before_apply_or_during_occupancy_preserves_data(self):
        for during in [False, True]:
            self.probe = ResidualProbe()
            plan = self.plan()
            if during:
                self.probe.after_occupancy = lambda: setattr(self.probe, 'install_status', 'installed')
            else:
                self.probe.install_status = 'installed'
            run = apply(plan['id'], self.state, confirmed=True, probe=self.probe, backend=FixtureBackend())
            self.assertEqual(run['entries'][0]['status'], 'skipped')
            self.assertTrue((self.data/'memory.db').exists())

    def test_fabricated_residual_context_is_rejected(self):
        report = self.scan()
        self.item(report)['residual_context']['bundle_ids'] = ['other.app']
        with self.assertRaises(Refused):
            make_plan(report, [self.item(report)['id']], self.state, probe=self.probe)

    def test_unknown_app_identifier_is_refused(self):
        with self.assertRaises(Refused):
            Scanner(home=self.home, probe=self.probe, uninstalled_apps=['unknown'])

    def test_receipt_preserves_uninstall_scope_and_roundtrip_contents(self):
        plan = self.plan()
        run = apply(plan['id'], self.state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'], 'trashed')
        self.assertEqual(run['entries'][0]['residual_context']['app'], 'Dia')
        result = restore(run['id'], self.state, confirmed=True, probe=self.probe, backend=FixtureBackend())
        self.assertEqual(result['results'][0]['status'], 'restored')
        self.assertEqual((self.data/'memory.db').read_bytes(), b'fixture private data')

    @unittest.skipUnless(platform.system() == 'Darwin', 'pinned macOS backend fixture')
    def test_pinned_backend_moves_and_restores_exclusive_app_data_with_databases(self):
        plan = self.plan()
        backend = MoleBackend(self.state)
        run = apply(plan['id'], self.state, confirmed=True, probe=self.probe, backend=backend)
        self.assertEqual(run['entries'][0]['status'], 'trashed', run)
        result = restore(run['id'], self.state, confirmed=True, probe=self.probe, backend=backend)
        self.assertEqual(result['results'][0]['status'], 'restored', result)
        self.assertEqual((self.data/'memory.db-wal').read_bytes(), b'fixture wal')
