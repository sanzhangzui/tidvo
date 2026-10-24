"""Capacity partitions, newly covered caches and safe retired Agent programs."""
import json
import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from macdev.agent_inspection import AgentPolicy
from macdev.cache_rules import CACHE_LOCATIONS
from macdev.cleanup_summary import summarize, disposition
from macdev.display import render
from macdev.engine import MoleBackend, apply, make_plan, restore
from macdev.native_previews import brew_preview
from macdev.safety import Refused, observe_usage, tree_snapshot
from macdev.scanner import Scanner
from macdev.state import State
from test_product import FakeProbe, FixtureBackend


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tidvo-expansion-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir()
        env = patch.dict(os.environ, {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.probe = FakeProbe()

    def write(self, relative, data="fixture cache"):
        p = self.home / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data) if not isinstance(data, str) else data)
        return p

    def scan(self, **kwargs):
        return Scanner(home=self.home, probe=self.probe, **kwargs).scan(audit_agents=False)


class CacheCoverageTests(Fixture):
    def populate(self):
        paths = []
        for rule, relative, *_ in CACHE_LOCATIONS:
            p = Path(relative)
            paths.append(self.write(p if p.suffix == '.pbd' else p / 'fixture.bin'))
        for p in ['Library/Caches/Homebrew/downloads/'+'a'*64+'--package.tar.gz',
                  'Library/Caches/Homebrew/api/formula.json',
                  '.cargo/registry/cache/index.crates.io-abc/package-1.0.crate',
                  'Library/Application Support/pyinstaller/bincache00py31264bit/module.so',
                  'Library/Caches/com.apple.AppleMediaServices/Metrics/resource.bin',
                  'Library/Caches/com.apple.parsecd/bag.plist']:
            paths.append(self.write(p))
        return paths

    def test_all_added_families_are_sized_and_have_cleanup_impact(self):
        paths = self.populate()
        report = self.scan()
        for p in paths:
            rows = [c for c in report['candidates'] if p == Path(c['path']) or p.is_relative_to(Path(c['path']))]
            self.assertTrue(rows, str(p))
            self.assertTrue(all(c['action'] == 'trash' and c['allocated_bytes'] > 0 for c in rows), rows)
            self.assertTrue(all('known_regenerable_cache' in c['evidence'] for c in rows))

    def test_installed_environments_models_sdk_avd_archives_and_cargo_sources_stay_out(self):
        self.populate()
        kept = [self.write(p) for p in ['.cargo/registry/src/index/package/source.rs', '.cargo/bin/tool',
            '.gem/ruby/3.3/gems/installed/lib.rb', '.bundle/cache/git/repo/source.rb',
            'Library/Android/sdk/platform-tools/adb', '.android/avd/phone.avd/disk.img',
            'Library/Developer/Xcode/Archives/release.xcarchive/binary', '.ollama/models/model.bin']]
        for c in self.scan()['candidates']:
            self.assertFalse(any(p == Path(c['path']) or p.is_relative_to(Path(c['path'])) for p in kept), c)
        self.assertTrue(all(p.exists() for p in kept))

    def test_active_package_owner_prevents_download_cache_cleanup(self):
        self.populate()
        self.probe.active = True
        rows = [c for c in self.scan()['candidates'] if c['rule_id'].startswith('developer.')]
        self.assertTrue(rows)
        self.assertTrue(all(c['action'] == 'report_only' for c in rows))

    def test_homebrew_partial_downloads_and_lockfiles_are_not_swept_with_archives(self):
        parent='Library/Caches/Homebrew/downloads/'
        completed=self.write(parent+'b'*64+'--package.tar.gz')
        partial=self.write(parent+'c'*64+'--package.tar.gz.incomplete')
        lock=self.write(parent+'d'*64+'--package.tar.gz.lock')
        rows={c['path']:c for c in self.scan()['candidates']}
        self.assertEqual(rows[str(completed)]['action'],'trash')
        for p in [partial,lock]:
            self.assertEqual(rows[str(p)]['action'],'report_only')
            self.assertEqual(rows[str(p)]['disposition'],'unverified')

    def test_databases_inside_new_cache_roots_remain_protected(self):
        self.write('Library/Caches/GeoServices/Resources/history.db')
        row = self.scan()['candidates'][0]
        self.assertEqual(row['action'], 'report_only')
        self.assertIn('nested_repository_or_sensitive_file', row['evidence'])

    def test_symlinked_cache_root_never_grants_cleanup_of_external_payload(self):
        external = self.write('keep/precious.bin')
        p = self.home/'.bundle/cache/compact_index'
        p.parent.mkdir(parents=True)
        p.symlink_to(external.parent)
        rows = self.scan()['candidates']
        self.assertTrue(all(c['action'] == 'report_only' for c in rows))
        self.assertTrue(external.exists())

    def test_unknown_application_caches_are_visible_without_deletion_authority(self):
        p = self.write('Library/Application Support/unknown-app/Code Cache/js/fixture')
        row = next(c for c in self.scan()['candidates'] if p.is_relative_to(Path(c['path'])))
        self.assertEqual(row['rule_id'], 'app.unattributed_cache')
        self.assertEqual(row['action'], 'report_only')
        self.assertEqual(row['disposition'], 'unverified')

    def test_unknown_discovery_respects_explicit_agent_protection(self):
        folder = self.home/'Library/Application Support/my-agent'
        self.write(folder/'Code Cache/fixture')
        self.write('.config/mac-dev-cleanup/config.json', {'agent_roots': {'custom': [str(folder)]}})
        self.assertFalse(self.scan()['candidates'])

    def test_excluded_new_cache_is_not_a_candidate(self):
        p = self.write('.gem/specs/registry/spec.gz')
        self.assertFalse(self.scan(excludes=[p.parent.parent])['candidates'])

    @unittest.skipUnless(platform.system() == 'Darwin', 'pinned macOS backend')
    def test_new_cache_families_complete_actual_pinned_trash_and_restore(self):
        try:
            process_view=subprocess.run(['/bin/ps','-axo','pid=,comm='],capture_output=True,text=True,timeout=5)
        except (OSError,subprocess.TimeoutExpired):
            self.skipTest('Native backend process visibility unavailable in sandbox; fixture also tested outside it')
        if process_view.returncode != 0 or process_view.stderr.strip():
            self.skipTest('Native backend process visibility unavailable in sandbox; fixture also tested outside it')
        paths = self.populate()
        report = self.scan()
        state = State(self.home)
        plan = make_plan(report, [c['id'] for c in report['candidates'] if c['action'] == 'trash'], state, probe=self.probe)
        run = apply(plan['id'], state, confirmed=True, probe=self.probe, backend=MoleBackend(state))
        self.assertTrue(all(e['status'] == 'trashed' for e in run['entries']), run)
        result = restore(run['id'], state, confirmed=True, probe=self.probe, backend=MoleBackend(state))
        self.assertTrue(all(e['status'] == 'restored' for e in result['results']), result)
        self.assertTrue(all(p.exists() for p in paths))


class SummaryTests(unittest.TestCase):
    def item(self, rule, action='trash', activity='idle', size=4096, **kwargs):
        return dict(rule_id=rule, path='/fixture/'+rule, id='a'*24, action=action, allocated_bytes=size,
                    scan_status='complete', activity={'activity':activity,'configured_reference':False,'reference_scan_status':'complete'}, **kwargs)

    def test_capacity_is_partitioned_without_counting_protected_data_as_reclaimable(self):
        rows = [self.item('project.__pycache__'), self.item('editor.vsix','report_only','active',900000000),
                self.item('project.dist',size=20000000),self.item('project.node_modules','report_only',size=8000000000,
                evidence=['project_dependency_environment_preserved'])]
        summary = summarize(rows)
        groups = {g['id']:g for g in summary['buckets']}
        self.assertEqual(groups['ready_caches']['measured_allocated_bytes'],4096)
        self.assertEqual(groups['quit_app']['measured_allocated_bytes'],900000000)
        self.assertEqual(groups['protected']['measured_allocated_bytes'],8000000000)
        self.assertEqual(groups['separate_review']['measured_allocated_bytes'],20000000)
        self.assertEqual(sum(g['count'] for g in summary['buckets']),len(rows))
        self.assertEqual(sum(g['measured_allocated_bytes'] for g in summary['buckets']),summary['measured_allocated_bytes'])

    def test_uncertainty_and_lower_bounds_are_preserved(self):
        row=self.item('developer.npm_download','report_only',size=None)
        row['scan_status']='unavailable'
        other=self.item('developer.npm_download','report_only',size=100000)
        other.update(scan_status='unavailable',size_observation={'lower_bound':True})
        group=next(g for g in summarize([row,other])['buckets'] if g['id']=='unverified')
        self.assertEqual(group['unknown_size_count'],1)
        self.assertEqual(group['lower_bound_count'],1)
        self.assertEqual(group['measured_allocated_bytes'],100000)

    def test_running_npx_is_a_retained_runtime_not_an_app_quit_recommendation(self):
        self.assertEqual(disposition(self.item('developer.npx','report_only','active')),'protected')

    def test_independent_protection_overrides_quit_application_suggestion(self):
        self.assertEqual(disposition(self.item('editor.obsolete_extension','report_only','active',agent_protection={'reason':'agent_data_protected'})),'protected')

    def test_human_report_surfaces_large_deferred_capacity_and_simple_next_action(self):
        row=self.item('editor.vsix','report_only','active',900000000)
        result={'scan_status':'complete','candidate_allocated_bytes':900000000,'actionable_allocated_bytes':0,
                'candidates':[row],'issues':[]}
        text=render('scan',result,report_path='/fixture/scan.json')
        self.assertIn('需退出应用后复查',text)
        self.assertIn('900.0 MB',text)
        self.assertIn('清理建议的缓存',text)
        self.assertIn('不是释放量',text)


class MeasurementTests(Fixture):
    def test_foreign_metadata_can_be_measured_without_granting_move_authority(self):
        root=self.write('.npm/_cacache/content-v2/archive.bin').parent.parent
        with patch('macdev.safety.os.getuid',return_value=os.getuid()+1):
            with self.assertRaises(Refused):tree_snapshot(root)
            observed=observe_usage(root)
        self.assertEqual(observed['status'],'complete')
        self.assertGreater(observed['allocated_bytes'],0)
        self.assertGreater(observed['foreign_owned_entries'],0)

    def test_usage_measurement_never_opens_payload_bodies(self):
        p=self.write('cache/file.bin')
        with patch.object(Path,'open',side_effect=AssertionError('no bodies')):
            result=observe_usage(p.parent)
        self.assertEqual(result['status'],'complete')

    def test_measurement_deduplicates_hardlinks(self):
        p=self.write('cache/file.bin')
        os.link(p,p.with_name('copy.bin'))
        self.assertEqual(observe_usage(p.parent)['allocated_bytes'],tree_snapshot(p.parent)['allocated_bytes'])

    def test_budget_exhaustion_is_not_complete_zero_capacity(self):
        p=self.write('cache/file.bin')
        result=observe_usage(p.parent,limit=0)
        self.assertEqual(result['status'],'partial')
        self.assertIsNone(result['allocated_bytes'])

    def test_unreadable_child_keeps_readable_capacity_as_a_lower_bound(self):
        p=self.write('cache/readable.bin');blocked=self.home/'cache/blocked';blocked.mkdir()
        original=os.scandir
        def scandir(path):
            if Path(path)==blocked:raise PermissionError('fixture')
            return original(path)
        with patch('macdev.safety.os.scandir',side_effect=scandir):
            row=observe_usage(p.parent)
        self.assertEqual(row['status'],'partial');self.assertTrue(row['lower_bound'])
        self.assertGreaterEqual(row['allocated_bytes'],p.stat().st_blocks*512)

    def test_symlinked_root_is_not_followed_for_capacity(self):
        p=self.write('valuable/file.bin');link=self.home/'alias';link.symlink_to(p.parent)
        self.assertEqual(observe_usage(link)['status'],'unavailable')

    def test_scanner_shows_foreign_owned_size_but_keeps_it_unavailable_for_plans(self):
        p=self.write('.npm/_cacache/content-v2/archive.bin')
        # Model the mutation snapshot refusing ownership while metadata remains readable.
        from macdev.scanner import tree_snapshot as real_snapshot
        def snapshot(path,**kwargs):
            if Path(path)==p.parent.parent:raise Refused('foreign_owner_or_nested_mount')
            return real_snapshot(path,**kwargs)
        with patch('macdev.scanner.tree_snapshot',side_effect=snapshot):
            report=self.scan()
            row=next(c for c in report['candidates'] if c['rule_id']=='developer.npm_download')
            self.assertEqual(row['action'],'report_only')
            self.assertGreater(row['allocated_bytes'],0)
            self.assertEqual(row['disposition'],'unverified')
            with self.assertRaises(Refused):make_plan(report,[row['id']],State(self.home),probe=self.probe)


class RetiredAgentPackageTests(Fixture):
    def setUp(self):
        super().setUp()
        self.base=self.home/'.vscode/extensions'
        self.old=self.base/'openai.chatgpt-1.0.0'
        self.new=self.base/'openai.chatgpt-2.0.0'
        self.write(self.old/'package.json',{'publisher':'openai','name':'chatgpt','version':'1.0.0'})
        self.write(self.old/'bin/codex','fixture executable bytes')
        self.write(self.new/'package.json',{'publisher':'openai','name':'chatgpt','version':'2.0.0'})
        self.write(self.base/'.obsolete',{self.old.name:True})
        self.register(self.new)

    def register(self,path):
        self.write(self.base/'extensions.json',[{'identifier':{'id':'openai.chatgpt'},'version':'2.0.0','relativeLocation':path.name}])

    def row(self,report=None):
        return next(c for c in (report or self.scan())['candidates'] if c['path']==str(self.old))

    def plan(self):
        report=self.scan();state=State(self.home)
        return state,make_plan(report,[self.row(report)['id']],state,probe=self.probe)

    def test_verified_retired_program_is_separate_review_and_not_blanket_agent_data(self):
        row=self.row()
        self.assertEqual(row['action'],'trash')
        self.assertEqual(row['extension_context']['replacement']['version'],'2.0.0')
        self.assertEqual(row['disposition'],'separate_review')
        self.assertNotIn('agent_protection',row)

    def test_active_old_binary_or_editor_is_retained(self):
        self.probe.active=True
        row=self.row();self.assertEqual(row['action'],'report_only');self.assertEqual(row['disposition'],'quit_app')

    def test_referenced_or_incompletely_checked_extension_is_retained(self):
        for field,value in [('referenced',True),('reference_status','partial')]:
            self.probe=FakeProbe();setattr(self.probe,field,value)
            self.assertEqual(self.row()['action'],'report_only')

    def test_missing_or_not_newer_replacement_keeps_agent_protection(self):
        for manifest in [{}, {'publisher':'openai','name':'chatgpt','version':'1.0.0'}]:
            self.write(self.new/'package.json',manifest)
            self.assertEqual(self.row()['action'],'report_only')

    def test_persistent_databases_and_session_names_keep_entire_package(self):
        for relative in ['memory.db','sessions/task.jsonl','auth.json','globalStorage/state.json']:
            p=self.write(self.old/relative)
            row=self.row();self.assertEqual(row['action'],'report_only',relative)
            p.unlink()

    def test_explicit_agent_root_for_same_known_tool_cannot_be_overwritten_by_manifest_detection(self):
        self.write('.config/mac-dev-cleanup/config.json',{'agent_roots':{'codex':[str(self.old)]}})
        self.assertEqual(self.row()['action'],'report_only')

    def test_user_state_and_shared_editor_history_are_never_targeted_by_package_exception(self):
        state=self.write('Library/Application Support/Code/User/globalStorage/openai.chatgpt/memory.db')
        before=tree_snapshot(state)
        row=self.row();self.assertEqual(row['action'],'trash')
        policy=AgentPolicy(self.home)
        self.assertIsNotNone(policy.protection_for(state,'editor.obsolete_extension',extension_context=row['extension_context']))
        self.assertEqual(tree_snapshot(state),before)

    def test_fabricated_extension_evidence_cannot_override_known_agent_protection(self):
        report=self.scan();row=self.row(report);row['extension_context']['replacement']['version']='99.0.0'
        with self.assertRaises(Refused):make_plan(report,[row['id']],State(self.home),probe=self.probe)

    def test_reference_check_becoming_partial_after_plan_stops_move(self):
        state,plan=self.plan();self.probe.reference_status='partial'
        run=apply(plan['id'],state,confirmed=True,probe=self.probe,backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'],'skipped');self.assertTrue(self.old.exists())

    def test_persistent_state_created_during_occupancy_stops_move(self):
        state,plan=self.plan()
        def idle(path,*,rule_id=None):
            self.write(self.old/'sessions/task.jsonl','fixture persistent state')
            return 'idle'
        self.probe.idle=idle
        run=apply(plan['id'],state,confirmed=True,probe=self.probe,backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'],'skipped');self.assertTrue(self.old.exists())

    def test_unproven_nonagent_package_does_not_get_current_user_occupancy_scope(self):
        self.write(self.old/'package.json',{'name':'fixture'})
        seen=[]
        self.probe.idle=lambda path,*,rule_id=None: seen.append(rule_id) or 'idle'
        state,plan=self.plan()
        run=apply(plan['id'],state,confirmed=True,probe=self.probe,backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'],'trashed')
        self.assertEqual(seen,[None])

    def test_shared_skill_link_to_old_package_keeps_package(self):
        link=self.home/'.codex/skills';link.parent.mkdir();link.symlink_to(self.old)
        self.assertEqual(self.row()['action'],'report_only')

    def test_replacement_change_after_scan_requires_fresh_plan(self):
        report=self.scan()
        self.write(self.new/'package.json',{'publisher':'openai','name':'chatgpt','version':'3.0.0'})
        with self.assertRaises(Refused):make_plan(report,[self.row(report)['id']],State(self.home),probe=self.probe)

    def test_registration_change_before_apply_stops_move(self):
        state,plan=self.plan();self.register(self.old)
        run=apply(plan['id'],state,confirmed=True,probe=self.probe,backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'],'skipped');self.assertTrue(self.old.exists())

    def test_replacement_change_during_occupancy_stops_move(self):
        state,plan=self.plan()
        def idle(path,*,rule_id=None):
            self.register(self.old)
            return 'idle'
        self.probe.idle=idle
        run=apply(plan['id'],state,confirmed=True,probe=self.probe,backend=FixtureBackend())
        self.assertEqual(run['entries'][0]['status'],'skipped');self.assertTrue(self.old.exists())

    def test_unknown_agent_extension_stays_protected_despite_obsolete_registry(self):
        for folder,ver in [(self.old,'1.0.0'),(self.new,'2.0.0')]:
            self.write(folder/'package.json',{'publisher':'future','name':'agent','version':ver,'contributes':{'languageModelTools':[]}})
        self.write(self.base/'extensions.json',[{'identifier':{'id':'future.agent'},'relativeLocation':self.new.name}])
        self.assertEqual(self.row()['action'],'report_only')

    @unittest.skipUnless(platform.system()=='Darwin','pinned macOS backend')
    def test_retired_agent_package_actual_trash_and_restore_preserves_current_version(self):
        current=tree_snapshot(self.new);state,plan=self.plan();backend=MoleBackend(state)
        run=apply(plan['id'],state,confirmed=True,probe=self.probe,backend=backend)
        self.assertEqual(run['entries'][0]['status'],'trashed',run)
        result=restore(run['id'],state,confirmed=True,probe=self.probe,backend=backend)
        self.assertEqual(result['results'][0]['status'],'restored',result)
        self.assertEqual(tree_snapshot(self.new),current)


class NativePreviewTests(unittest.TestCase):
    def test_native_preview_is_separate_and_never_executes_cleanup(self):
        calls=[]
        def command(args,timeout):
            calls.append(args)
            return subprocess.CompletedProcess(args,0,'Would remove: /fixture/old (7MB)\nThis operation would free approximately 49MB of disk space.','')
        row=brew_preview(command,'/fixture/brew')
        self.assertEqual(calls,[['/fixture/brew','cleanup','--dry-run']])
        self.assertEqual(row['reported_estimate'],'49MB')
        self.assertFalse(row['included_in_candidate_totals'])
        self.assertIsNone(row['estimated_bytes'])
        self.assertEqual(row['action'],'manual_review')

    def test_failed_and_warning_native_preview_are_not_certified_complete(self):
        row=brew_preview(lambda *args:None,'/fixture/brew');self.assertEqual(row['status'],'unavailable')
        row=brew_preview(lambda *args:subprocess.CompletedProcess([],0,'','warning'),'/fixture/brew')
        self.assertEqual(row['status'],'partial')

    def test_native_probe_disables_auto_update_analytics_and_install_cleanup(self):
        from macdev.probes import command
        with patch('macdev.probes.subprocess.run',return_value=subprocess.CompletedProcess([],0,'','')) as call:
            command(['/opt/homebrew/bin/brew','cleanup','--dry-run'])
        env=call.call_args.kwargs['env']
        self.assertEqual(env['HOMEBREW_NO_AUTO_UPDATE'],'1')
        self.assertEqual(env['HOMEBREW_NO_ANALYTICS'],'1')
        self.assertEqual(env['HOMEBREW_NO_INSTALL_CLEANUP'],'1')
        self.assertEqual(env['HOMEBREW_NO_BOOTSNAP'],'1')

    def test_unbootstrapped_homebrew_is_not_invoked(self):
        from macdev.probes import NativeProbe
        p=object.__new__(NativeProbe)
        with patch('macdev.probes.shutil.which',return_value='/opt/homebrew/bin/brew'), \
             patch('macdev.probes.homebrew_runtime_ready',return_value=False), \
             patch('macdev.probes.command') as call:
            row=p.native_previews()[0]
        call.assert_not_called()
        self.assertEqual(row['reason'],'homebrew_runtime_not_ready_no_bootstrap')


class NativeRuntimeReadinessTests(Fixture):
    def setUp(self):
        super().setUp()
        self.executable=self.write('brew-repo/bin/brew')
        self.vendor=self.home/'brew-repo/Library/Homebrew/vendor'
        self.write(self.vendor/'portable-ruby-version','4.0.7_1\n')
        self.runtime=self.vendor/'portable-ruby/4.0.7_1'
        self.write(self.runtime/'bin/ruby').chmod(0o700)
        self.bundle=self.write(self.runtime/'bin/bundle')
        self.current=self.vendor/'portable-ruby/current';self.current.symlink_to(self.runtime)

    def test_existing_matching_ruby_and_bundler_are_required(self):
        from macdev.native_previews import homebrew_runtime_ready
        self.assertTrue(homebrew_runtime_ready(self.executable))
        self.bundle.unlink()
        self.assertFalse(homebrew_runtime_ready(self.executable))

    def test_stale_runtime_pointer_is_not_allowed_to_trigger_upgrade(self):
        from macdev.native_previews import homebrew_runtime_ready
        self.write(self.vendor/'portable-ruby-version','4.0.8\n')
        self.assertFalse(homebrew_runtime_ready(self.executable))


class RenamedApplicationEvidenceTests(unittest.TestCase):
    def probe(self,status='installed'):
        from macdev.probes import NativeProbe
        p=object.__new__(NativeProbe)
        p.rows=['123 /fixture/Coding.app/Contents/MacOS/Electron']
        p.references=set();p.reference_status='complete'
        p.installation=lambda owner:{'status':status,'paths':['/fixture/Coding.app'] if status=='installed' else []}
        return p

    def test_bundle_identified_renamed_editor_remains_active(self):
        evidence=self.probe().evidence('/fixture/cache','Visual Studio Code')
        self.assertEqual(evidence['activity'],'active')
        self.assertEqual(evidence['matched_pids'],['123'])

    def test_incomplete_install_evidence_does_not_assert_idle_from_fixed_name_silence(self):
        evidence=self.probe('unknown').evidence('/fixture/cache','Visual Studio Code')
        self.assertEqual(evidence['activity'],'unknown')
