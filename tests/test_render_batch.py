"""Render batches: one render split over several machines, finished when every machine is done,
failed frames collected into a retry batch.
    uv run python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MAZE_CONFIG_DIR', str(Path(_TMP.name) / 'config'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline_app as pa  # noqa: E402

try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

NOW = time.mktime((2026, 11, 15, 12, 0, 0, 0, 0, -1))


def settings(frames=range(1, 11), passes=('/Render/beauty', '/Render/spec'), **kw):
    base = {'context': {'type': 'shot', 'name': 'SH010', 'rel_path': 'sequence/SH010', 'category': None},
            'mode': 'husk', 'usd_file': 'SH010_v001.usda', 'hip_file': None, 'render_name': '',
            'version': 3, 'houdini_version': '22.0', 'engine': 'xpu', 'render_order': 'pass_major',
            'resolution': {'mode': 'usd', 'width': 1920, 'height': 1080, 'percent': 50},
            'skip_sync_confirm': True, 'mplay': False, 'mplay_restart': 25, 'keep_awake': True,
            'keep_screen_on': True, 'save_log': True,
            'jobs': {p: list(frames) for p in passes}, 'rop_jobs': {}}
    base.update(kw)
    return base


class Split(unittest.TestCase):
    def test_machine_share_covers_everything_once(self):
        for count in range(1, 6):
            for frames in (range(1, 11), range(1001, 1012, 3), [5]):
                b = dict(settings(frames), machine_count=count)
                if len(list(frames)) < count:
                    continue
                seen = []
                for n in range(1, count + 1):
                    share = pa.machine_share(b, n)
                    self.assertEqual(share['/Render/beauty'], share['/Render/spec'])
                    seen += share['/Render/beauty']
                self.assertEqual(sorted(seen), list(frames))
                self.assertEqual(len(seen), len(set(seen)))

    def test_interleaved(self):
        b = dict(settings(range(1, 11)), machine_count=3)
        self.assertEqual(pa.machine_share(b, 1)['/Render/beauty'], [1, 4, 7, 10])
        self.assertEqual(pa.machine_share(b, 2)['/Render/beauty'], [2, 5, 8])
        with self.assertRaises(ValueError):
            pa.machine_share(b, 4)

    def test_uneven_retry_jobs(self):
        b = {'machine_count': 2, 'mode': 'husk', 'jobs': {'/a': [3, 9, 20], '/b': [9]}}
        self.assertEqual(pa.machine_share(b, 1), {'/a': [3, 20], '/b': []})
        self.assertEqual(pa.machine_share(b, 2), {'/a': [9], '/b': [9]})

    def test_frame_runs(self):
        self.assertEqual(pa.frame_runs([1, 4, 7, 10]), [(1, 10, 3)])
        self.assertEqual(pa.frame_runs([1, 5, 9, 10, 11, 12, 20]), [(1, 9, 4), (10, 12, 1), (20, 20, 1)])
        self.assertEqual(pa.frame_runs([7]), [(7, 7, 1)])
        self.assertEqual(pa.frame_runs([]), [])


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'proj'

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        b = pa.create_render_batch(self.root, settings(), 3, now=NOW)
        self.assertEqual(b['id'], 'SH010_render_v003_20261115-120000')
        self.assertTrue((Path(b['_dir']) / 'logs').is_dir())
        loaded = pa.load_render_batch(b['_dir'])
        self.assertEqual(loaded['machine_count'], 3)
        self.assertEqual(loaded['jobs'], settings()['jobs'])
        self.assertNotIn('_dir', json.loads((Path(b['_dir']) / 'batch.json').read_text()))
        # The same project synced somewhere else resolves the context there.
        other = Path(self.tmp.name) / 'elsewhere'
        self.assertEqual(pa.batch_context_path(other, loaded), other / 'sequence' / 'SH010')
        again = pa.create_render_batch(self.root, settings(), 2, now=NOW)
        self.assertNotEqual(again['id'], b['id'])

    def test_validation(self):
        with self.assertRaises(ValueError):
            pa.create_render_batch(self.root, settings(frames=[]), 2)
        with self.assertRaises(ValueError):
            pa.create_render_batch(self.root, settings(), 0)
        bad = dict(settings(), schema=99, id='x', machine_count=2)
        with self.assertRaisesRegex(ValueError, 'update MazeHub'):
            pa.validate_batch(bad)
        d = self.root / 'mazehub' / 'render_batches' / 'broken'
        d.mkdir(parents=True)
        (d / 'batch.json').write_text('{oops')
        with self.assertRaises(ValueError):
            pa.load_render_batch(d)
        self.assertEqual(pa.list_render_batches(self.root), [])

    def test_slots_and_finishing(self):
        b = pa.create_render_batch(self.root, settings(), 2, now=NOW)
        self.assertEqual([s['state'] for s in pa.batch_slots(b, NOW)], ['free', 'free'])
        self.assertEqual(pa.next_free_machine(b, NOW), 1)
        with mock.patch.object(pa, 'machine_host', return_value='PC-A'):
            pa.write_machine_status(b, 1, now=NOW, state='running', frames_done=0, frames_total=10)
        self.assertEqual(pa.batch_slots(b, NOW + 60)[0]['state'], 'running')
        self.assertEqual(pa.next_free_machine(b, NOW + 60), 2)
        self.assertEqual(pa.batch_slots(b, NOW + 3600)[0]['state'], 'stale')
        self.assertIn('running on PC-A', pa.describe_slot(pa.batch_slots(b, NOW + 120)[0], NOW + 120))
        with mock.patch.object(pa, 'machine_host', return_value='PC-B'):
            pa.write_machine_status(b, 2, now=NOW, state='cancelled', frames_done=2)
        self.assertEqual(pa.batch_slots(b, NOW)[1]['state'], 'free')
        self.assertEqual(pa.batch_state(b, NOW), 'active')
        pa.write_machine_status(b, 1, now=NOW, state='done', frames_done=10,
                                failed=[{'key': '/Render/beauty', 'frame': 3, 'reason': 'GPU out of memory'}])
        pa.write_machine_status(b, 2, now=NOW, state='done', frames_done=10,
                                failed=[{'key': '/Render/spec', 'frame': 4, 'reason': 'exit code 1'},
                                        {'key': '/Render/beauty', 'frame': 4, 'reason': 'exit code 1'}])
        self.assertEqual(pa.batch_state(b, NOW), 'finished')
        self.assertIsNone(pa.next_free_machine(b, NOW))
        failed, details = pa.batch_failed_frames(b)
        self.assertEqual(failed, {'/Render/beauty': [3, 4], '/Render/spec': [4]})
        self.assertEqual(len(details), 3)
        retry = pa.retry_batch_settings(b)
        self.assertEqual(retry['jobs'], {'/Render/beauty': [3, 4], '/Render/spec': [4]})
        self.assertEqual(retry['version'], 3)
        rb = pa.create_render_batch(self.root, retry, 2, retry_of=b['id'], now=NOW)
        self.assertEqual(rb['id'], b['id'] + '_retry1')
        self.assertEqual(rb['retry_of'], b['id'])
        listed = pa.list_render_batches(self.root, now=NOW)
        self.assertEqual({x['id']: x['_state'] for x in listed},
                         {b['id']: 'finished', rb['id']: 'active'})

    def test_hrender_retry(self):
        s = settings(jobs={}, mode='hrender', usd_file=None, hip_file='shot.hip',
                     rop_jobs={'/out/karma|/Render/beauty': {'rop': '/out/karma', 'pass': '/Render/beauty',
                                                             'type': 'karma', 'frames': list(range(1, 9))}})
        b = pa.create_render_batch(self.root, s, 2, now=NOW)
        self.assertEqual(pa.machine_share(b, 2), {'/out/karma|/Render/beauty': [2, 4, 6, 8]})
        pa.write_machine_status(b, 2, state='done',
                                failed=[{'key': '/out/karma|/Render/beauty', 'frames': [2, 4], 'reason': 'x'}])
        retry = pa.retry_batch_settings(b)
        self.assertEqual(retry['rop_jobs']['/out/karma|/Render/beauty']['frames'], [2, 4])

    def test_cleanup_and_delete(self):
        b = pa.create_render_batch(self.root, settings(), 1, now=NOW)
        pa.write_machine_status(b, 1, now=NOW, state='done')
        old = time.time() - 20 * 86400
        os.utime(Path(b['_dir']) / 'batch.json', (old, old))
        with mock.patch.object(pa, '_now_ts', side_effect=lambda now=None: NOW + 20 * 86400 if now is None else now):
            listed = pa.list_render_batches(self.root, now=NOW + 20 * 86400)
        self.assertEqual(listed, [])
        root = pa.render_batches_dir(self.root)
        self.assertTrue((root / f'.deleted-{b["id"]}' / 'batch.json').is_file())  # soft delete
        b2 = pa.create_render_batch(self.root, settings(), 2)
        dest = pa.delete_render_batch(b2)
        self.assertTrue(dest.name.startswith('.deleted-'))
        self.assertTrue((dest / 'batch.json').is_file())

    def test_teams_card_batch(self):
        card = pa.build_render_card('SH010', 'a.usd', ['/R/beauty'], 1, 9, 1, 3, 'xpu', 0, '1:00:00',
                                    batch='SH010_render_v003_x · machine 2 of 4', total_frames=5)
        facts = {f['name']: f['value'] for f in card['sections'][0]['facts']}
        self.assertEqual(facts['Batch'], 'SH010_render_v003_x')
        self.assertEqual(facts['Machine'], 'Machine 2 of 4')
        details = {f['name']: f['value'] for f in card['sections'][1]['facts']}
        self.assertEqual(details['Total Frames'], '5')


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class BatchGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import pipeline_gui
        cls.gui = pipeline_gui
        from test_render_usd import FakeKeepAwake, FakeSync, MAIN_USDA
        cls.FakeKeepAwake, cls.FakeSync, cls.MAIN_USDA = FakeKeepAwake, FakeSync, MAIN_USDA

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'proj'
        self.shot = self.root / 'sequence' / 'SH010'
        (self.shot / 'houdini' / 'USD').mkdir(parents=True)
        (self.shot / 'houdini' / 'render' / 'SH010_v002').mkdir(parents=True)
        (self.shot / 'houdini' / 'USD' / 'SH010_v001.usda').write_text(self.MAIN_USDA)
        self.husk = Path(self.tmp.name) / 'husk'
        self.husk.write_text('')
        os.environ['MAZE_PROJECT_ROOT'] = str(self.root)
        self.FakeKeepAwake.instances = []
        self.FakeSync.cancel = False
        self.FakeSync.created = []
        self.patches = [
            mock.patch('settings.find_husk', return_value=str(self.husk)),
            mock.patch('pipeline_app.KeepAwake', self.FakeKeepAwake),
            mock.patch.object(self.gui, 'SyncProgressDialog', self.FakeSync),
        ]
        for p in self.patches:
            p.start()
        self.page = self._new_page()
        self.launched = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        os.environ.pop('MAZE_PROJECT_ROOT', None)
        self.tmp.cleanup()

    def _new_page(self):
        page = self.gui.RenderPage(self.root, self.root / 'pipeline')
        self.addCleanup(page.deleteLater)
        page._ask_scan_references = lambda *a: False
        page._ask_full_scan_fallback = lambda *a: False
        page._batch_error = lambda msg: self.errors.append(msg)
        self.errors = getattr(self, 'errors', [])

        def fake_launch(commands, *a, **k):
            self.launched.append(commands)
            page._render_launched = True
        page._launch_render = fake_launch
        return page

    def _wait(self, cond, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if cond():
                return True
            time.sleep(0.01)
        return False

    def _setup_render(self, page=None):
        page = page or self.page
        page.ctx_tabs.setCurrentIndex(0)
        page.shot_combo.setCurrentText('SH010')
        page.usd_combo.setCurrentText('SH010_v001.usda')
        self.assertTrue(self._wait(lambda: len(page._listed_passes()) == 2))
        page.frame_source_combo.setCurrentIndex(page.frame_source_combo.findData('custom'))
        page._set_frames(1, 9)
        page.version_combo.setCurrentIndex(page.version_combo.count() - 1)  # v003 (new)
        page.mplay_cb.setChecked(True)
        page.mplay_restart_spin.setValue(10)

    def _finish(self, page, failures=(), cancelled=False):
        page._render_meta = dict(getattr(page, '_render_meta', {}) or {}, cancelled=cancelled)
        page._render_thread = mock.Mock(failures=list(failures), skipped=[], commands=[])
        page._render_dialog = None
        page._on_render_finished(1 if failures else 0)

    def test_create_render_finish_and_retry(self):
        self._setup_render()
        page = self.page
        page._ask_machine_count = lambda settings, **kw: 3
        page._ask_render_first_slot = lambda batch: True
        page._create_batch_clicked()
        batches = pa.list_render_batches(self.root)
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertEqual(batch['version'], 3)
        self.assertTrue(batch['mplay'])
        self.assertEqual(batch['mplay_restart'], 10)
        # Machine 1 started here: frames 1, 4, 7 for both passes, into the shared version folder.
        cmds = self.launched[-1]
        self.assertEqual(sorted({int(c[c.index('-f') + 1]) for c in cmds}), [1, 4, 7])
        self.assertEqual(len(cmds), 6)
        self.assertIn('--mplay-monitor', cmds[0])
        out = Path(cmds[0][cmds[0].index('-o') + 1])
        self.assertEqual(out.parent.parent.name, 'SH010_v003')
        self.assertIsNotNone(page._batch)
        self.assertFalse(page.batch_banner.isHidden())
        self.assertFalse(page.mplay_cb.isEnabled())
        self.assertFalse(page.keep_awake_cb.isEnabled())
        self.assertFalse(page.usd_combo.isEnabled())
        self.assertEqual(page.render_btn.text(), 'Render Machine 1 of 3')
        logs = list((Path(batch['_dir']) / 'logs').glob('machine_1_*.log'))
        self.assertEqual(len(logs), 1)
        self.assertFalse(list((self.shot / 'houdini' / 'render').rglob('*.log')))
        self.assertEqual(pa.read_machine_status(batch, 1)['state'], 'running')
        page._close_render_log()
        self._finish(page, failures=[{'pass': '/Render/passes/beauty', 'frame': 4, 'code': 139,
                                      'reason': 'GPU out of memory', 'index': 2}])
        self.assertIsNone(page._batch)
        self.assertTrue(page.batch_banner.isHidden())
        self.assertTrue(page.usd_combo.isEnabled())
        self.assertEqual(page.render_btn.text(), 'Render Selected Passes')
        status = pa.read_machine_status(batch, 1)
        self.assertEqual(status['state'], 'done')
        self.assertEqual(status['failed'], [{'key': '/Render/passes/beauty', 'frame': 4,
                                             'reason': 'GPU out of memory'}])
        # A second PC takes the next free machine through the Batches window.
        page2 = self._new_page()
        dlg = self.gui.BatchesDialog(page2)
        self.assertEqual(dlg._current['id'], batch['id'])  # the only active batch is preselected
        with mock.patch.object(pa, 'machine_host', return_value='PC-2'), \
                mock.patch.object(self.gui, 'machine_host', return_value='PC-2'):
            dlg._render_next()
            self.assertEqual(dlg.choice[1], 2)
            page2._render_batch_slot(*dlg.choice)
            self.assertEqual(sorted({int(c[c.index('-f') + 1]) for c in self.launched[-1]}), [2, 5, 8])
            self._finish(page2)
        page3 = self._new_page()
        page3._render_batch_slot(pa.load_render_batch(batch['_dir']), 3)
        self._finish(page3)
        listed = pa.list_render_batches(self.root)
        self.assertEqual(listed[0]['_state'], 'finished')
        # Re-render the failed frames as a new batch.
        page._ask_machine_count = lambda settings, **kw: kw['default']
        retry = page._create_retry_batch(listed[0])
        self.assertEqual(retry['jobs'], {'/Render/passes/beauty': [4]})
        self.assertEqual(retry['machine_count'], 1)

    def test_running_slot_on_other_pc_asks(self):
        self._setup_render()
        batch = pa.create_render_batch(self.root, self.page._collect_render_settings(), 2)
        with mock.patch.object(pa, 'machine_host', return_value='OTHER-PC'):
            pa.write_machine_status(batch, 1, state='running', frames_done=0)
        asked = []
        self.page._confirm_take_slot = lambda b, n, st: asked.append(st['host']) or False
        self.page._render_batch_slot(batch, 1)
        self.assertEqual(asked, ['OTHER-PC'])
        self.assertEqual(self.launched, [])
        self.assertIsNone(self.page._batch)

    def test_settings_restored_and_not_saved(self):
        self._setup_render()
        page = self.page
        engine_before = page.render_engine_combo.currentData()
        s = page._collect_render_settings()
        s['engine'] = 'cpu'
        s['mplay'] = False
        batch = pa.create_render_batch(self.root, s, 2)
        self.FakeSync.cancel = True  # sync cancelled: slot given back, batch mode left
        page._render_batch_slot(batch, 2)
        self.assertIsNone(page._batch)
        self.assertEqual(pa.read_machine_status(batch, 2)['state'], 'cancelled')
        self.assertEqual(page.render_engine_combo.currentData(), engine_before)
        self.assertTrue(page.mplay_cb.isChecked())
        self.assertEqual(self._new_page().render_engine_combo.currentData(), engine_before)

    def test_missing_usd_refused(self):
        self._setup_render()
        s = self.page._collect_render_settings()
        s['usd_file'] = 'not_synced_yet.usd'
        batch = pa.create_render_batch(self.root, s, 2)
        self.page._render_batch_slot(batch, 1)
        self.assertTrue(any('not_synced_yet.usd' in e for e in self.errors))
        self.assertIsNone(pa.read_machine_status(batch, 1))
        self.assertIsNone(self.page._batch)


if __name__ == '__main__':
    unittest.main()
