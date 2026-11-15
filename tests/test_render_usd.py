"""Render output naming (optional render name) and main-file-only pass discovery.
    uv run python -m unittest discover -s tests -v
The GUI tests run offscreen and skip if PySide6 is missing; the Sdf test skips without pxr.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.TemporaryDirectory()
os.environ['MAZE_CONFIG_DIR'] = str(Path(_TMP.name) / 'config')
os.environ['XDG_STATE_HOME'] = str(Path(_TMP.name) / 'state')
os.environ['LOCALAPPDATA'] = str(Path(_TMP.name) / 'state')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.pop('MAZE_PROJECT_ROOT', None)
MAZEHUB_DIR = Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'
sys.path.insert(0, str(MAZEHUB_DIR))

import pipeline_app as pa  # noqa: E402

try:
    import pxr  # noqa: F401
    HAVE_PXR = True
except ImportError:
    HAVE_PXR = False

try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


MAIN_USDA = '''#usda 1.0
(
    customLayerData = { string note = "braces { in a string" }
    subLayers = [ @./lighting.usda@, @../env/set.usdc@ ]
)

def Xform "World" (
    prepend references = @./char.usd@</Char>
    payload = @@@big payload.usdc@@@
    customData = { string def = "not a prim" }
)
{
    custom string note = "def RenderPass \\"fake\\" {"
    def Mesh "m" ( references = </World/other> ) {}
}

def Scope "Render"
{
    def Scope "passes"
    {
        def RenderPass "beauty"
        {
            custom string note = "}"
        }
        def RenderPass "utility" (
            customData = { int x = 1 }
        )
        {
        }
    }
}
'''


class RenderNaming(unittest.TestCase):
    def test_clean_render_name(self):
        self.assertEqual(pa.clean_render_name(''), ('', None))
        self.assertEqual(pa.clean_render_name('  '), ('', None))
        self.assertEqual(pa.clean_render_name('lighting'), ('lighting', None))
        self.assertEqual(pa.clean_render_name('key light/fx!'), ('key_light_fx', None))
        self.assertEqual(pa.clean_render_name('look-dev'), ('look-dev', None))
        for bad in ('v003', 'lit_v2', 'lit V12'):
            name, error = pa.clean_render_name(bad)
            self.assertEqual(name, '')
            self.assertTrue(error, bad)

    def test_no_name_is_old_layout(self):
        base = Path('/p/sequence/SH010/houdini/render')
        self.assertEqual(
            pa.render_output_path(base, 'SH010', '', 3, '/Render/passes/beauty', 1001),
            base / 'SH010_v003' / 'beauty' / 'SH010_beauty_v003_1001.exr')

    def test_names_do_not_collide(self):
        base = Path('/p/asset/prop/Chair/houdini/render')
        a = pa.render_output_path(base, 'Chair', 'lighting', 1, '/Render/beauty', 1001)
        b = pa.render_output_path(base, 'Chair', 'fx', 1, '/Render/beauty', 1001)
        self.assertNotEqual(a.parent, b.parent)
        self.assertNotEqual(a.name, b.name)
        self.assertEqual(a, base / 'Chair_lighting_v001' / 'beauty' / 'Chair_lighting_beauty_v001_1001.exr')
        self.assertEqual(pa.render_output_path(base, 'Chair', 'fx', 2, 'beauty', '$F4').name,
                         'Chair_fx_beauty_v002_$F4.exr')

    def test_versions_counted_per_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for d in ('SH010_v001', 'SH010_v004', 'SH010_lighting_v001', 'SH010_lighting_v002',
                      'SH010_fx_v007', 'SH0100_v009', 'notes'):
                (base / d).mkdir()
            self.assertEqual(pa.render_versions(base, 'SH010'), [1, 4])
            self.assertEqual(pa.render_versions(base, 'SH010', 'lighting'), [1, 2])
            self.assertEqual(pa.render_versions(base, 'SH010', 'comp'), [])
            self.assertEqual(pa.existing_render_names(base, 'SH010'), ['fx', 'lighting'])
            self.assertEqual(pa.render_versions(Path(tmp) / 'missing', 'SH010'), [])

    def test_preview_sees_named_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            shot = Path(tmp) / 'SH010'
            base = shot / 'houdini' / 'render'
            for name in ('', 'lighting'):
                for f in (1001, 1002):
                    out = pa.render_output_path(base, 'SH010', name, 2, '/Render/beauty', f)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(b'x')
            seqs = pa.discover_image_sequences(shot)
            self.assertEqual(len(seqs), 2)
            self.assertEqual({s['version'] for s in seqs}, {'v002'})
            self.assertEqual({s['prefix'] for s in seqs}, {'SH010_beauty', 'SH010_lighting_beauty'})
            self.assertEqual({s['count'] for s in seqs}, {2})


class MainLayerPasses(unittest.TestCase):
    def test_parse_usda_layer(self):
        info = pa.parse_usda_layer(MAIN_USDA)
        self.assertEqual(info['passes'], ['/Render/passes/beauty', '/Render/passes/utility'])
        self.assertEqual(info['layer_refs'],
                         ['./lighting.usda', '../env/set.usdc', './char.usd', 'big payload.usdc'])

    def test_no_refs(self):
        info = pa.parse_usda_layer('#usda 1.0\ndef RenderPass "only" {}\n')
        self.assertEqual(info, {'passes': ['/only'], 'layer_refs': [], 'start': None, 'end': None})

    def test_time_codes(self):
        text = '#usda 1.0\n(\n    endTimeCode = 1240\n    startTimeCode = 1001.0\n    timeCodesPerSecond = 24\n)\n'
        info = pa.parse_usda_layer(text)
        self.assertEqual((info['start'], info['end']), (1001, 1240))
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / 'shot.usda'
            main.write_text(text + MAIN_USDA.split('\n', 1)[1])
            result = pa.scan_main_layer_passes(main)
            self.assertEqual((result['start'], result['end']), (1001, 1240))
            self.assertEqual(len(result['passes']), 2)

    def test_scan_reads_only_main_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / 'SH010_v001.usda'
            main.write_text(MAIN_USDA)
            synced, opened = [], []
            real_open = open

            def spy_open(path, *a, **kw):
                opened.append(str(path))
                return real_open(path, *a, **kw)

            with mock.patch.object(pa, 'sync_file', side_effect=lambda p, *a, **k: synced.append(Path(p)) or True), \
                    mock.patch.object(pa.subprocess, 'run', side_effect=AssertionError('no subprocess')), \
                    mock.patch('builtins.open', spy_open):
                result = pa.scan_main_layer_passes(main, husk_path='/nowhere/husk')
            self.assertEqual(result['error'], '')
            self.assertEqual(result['passes'], ['/Render/passes/beauty', '/Render/passes/utility'])
            self.assertEqual(len(result['layer_refs']), 4)
            self.assertEqual(synced, [main])
            self.assertTrue(all(Path(p) == main for p in opened), opened)

    def test_scan_missing_file(self):
        result = pa.scan_main_layer_passes(Path(_TMP.name) / 'nope.usda')
        self.assertTrue(result['error'])
        self.assertEqual(result['passes'], [])

    @unittest.skipUnless(HAVE_PXR, 'pxr not installed')
    def test_sdf_layer_info(self):
        import maze_usd_deps
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / 'main.usda'
            main.write_text(MAIN_USDA)
            info = maze_usd_deps.layer_info(str(main))
            self.assertEqual((info['start'], info['end']), (None, None))
            timed = Path(tmp) / 'timed.usda'
            timed.write_text('#usda 1.0\n(\n    startTimeCode = 1001\n    endTimeCode = 1100\n)\n')
            t = maze_usd_deps.layer_info(str(timed))
            self.assertEqual((t['start'], t['end']), (1001, 1100))
            self.assertEqual(info['passes'], ['/Render/passes/beauty', '/Render/passes/utility'])
            self.assertEqual(set(info['layer_refs']),
                             {'./lighting.usda', '../env/set.usdc', './char.usd', 'big payload.usdc'})


class FakeKeepAwake:
    instances = []

    def __init__(self, screen_on=True):
        self.screen_on = screen_on
        self.active = False
        self.events = []
        FakeKeepAwake.instances.append(self)

    def start(self):
        self.active = True
        self.events.append('start')
        return ''

    def stop(self):
        self.active = False
        self.events.append('stop')


class FakeSync:
    """Stands in for SyncProgressDialog: accepts at once, or cancels the render."""
    cancel = False
    report = {}
    created = []

    def __init__(self, *a, auto_continue=False, **k):
        self.auto_continue = auto_continue
        self.cancel_render = FakeSync.cancel
        FakeSync.created.append(self)

    def start(self):
        pass

    def exec(self):
        from PySide6.QtWidgets import QDialog
        return QDialog.Rejected if self.cancel_render else QDialog.Accepted

    def elapsed(self):
        return 0.0

    def _format_duration(self, s):
        return '0s'


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class RenderPageGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import pipeline_gui
        cls.gui = pipeline_gui

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'proj'
        self.shot = root / 'sequence' / 'SH010'
        (self.shot / 'houdini' / 'USD').mkdir(parents=True)
        (self.shot / 'houdini' / 'render' / 'SH010_lighting_v001').mkdir(parents=True)
        (self.shot / 'houdini' / 'render' / 'SH010_v002').mkdir(parents=True)
        (self.shot / 'houdini' / 'USD' / 'SH010_v001.usda').write_text(MAIN_USDA)
        self.asset = root / 'asset' / 'prop' / 'Chair'
        (self.asset / 'houdini' / 'USD').mkdir(parents=True)
        (self.asset / 'houdini' / 'USD' / 'Chair_v001.usda').write_text(
            '#usda 1.0\ndef RenderPass "beauty" {}\n')
        self.husk = Path(self.tmp.name) / 'husk'
        self.husk.write_text('')
        self.patches = [
            mock.patch('settings.find_husk', return_value=str(self.husk)),
            mock.patch.object(self.gui, 'discover_husk_passes',
                              side_effect=self._fake_husk_passes),
            mock.patch('pipeline_app.KeepAwake', FakeKeepAwake),
        ]
        FakeKeepAwake.instances = []
        FakeSync.cancel = False
        FakeSync.created = []
        for p in self.patches:
            p.start()
        self.husk_calls = []
        self.root = root
        os.environ['MAZE_PROJECT_ROOT'] = str(root)
        self.page = self.gui.RenderPage(root, root / 'pipeline')
        self.page._ask_full_scan_fallback = lambda *a: False

    def tearDown(self):
        os.environ.pop('MAZE_PROJECT_ROOT', None)
        self.page.deleteLater()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _fake_husk_passes(self, husk_path, usd_file):
        self.husk_calls.append(usd_file)
        return ['/Render/passes/beauty', '/Render/passes/fromSublayer'], ''

    def _wait(self, cond, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if cond():
                return True
            time.sleep(0.01)
        return False

    def _pick_shot(self, answer):
        asked = []
        self.page._ask_scan_references = lambda usd, refs, found: asked.append((refs, found)) or answer
        self.page.ctx_tabs.setCurrentIndex(0)
        self.page.shot_combo.setCurrentText('SH010')
        self.page.usd_combo.setCurrentText('SH010_v001.usda')
        return asked

    def test_decline_uses_main_file_passes(self):
        asked = self._pick_shot(False)
        self.assertTrue(self._wait(lambda: asked))
        self._wait(lambda: False, timeout=0.3)
        self.assertEqual(asked[0][1], 2)
        self.assertEqual(len(asked[0][0]), 4)
        self.assertEqual(self.page._listed_passes(), ['/Render/passes/beauty', '/Render/passes/utility'])
        self.assertEqual(self.husk_calls, [])
        self.assertFalse(self.page.scan_refs_btn.isHidden())
        # Changing their mind later with the button runs the full husk scan once.
        self.page._scan_referenced_passes()
        self.assertTrue(self._wait(lambda: len(self.page._listed_passes()) == 3))
        self.assertEqual(len(self.husk_calls), 1)
        self.assertTrue(self.page.scan_refs_btn.isHidden())

    def test_accept_merges_referenced_passes(self):
        asked = self._pick_shot(True)
        self.assertTrue(self._wait(lambda: len(self.page._listed_passes()) == 3))
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.page._listed_passes(), [
            '/Render/passes/beauty', '/Render/passes/utility', '/Render/passes/fromSublayer'])
        self.assertEqual(len(self.husk_calls), 1)

    def test_no_refs_no_question(self):
        asked = []
        self.page._ask_scan_references = lambda *a: asked.append(a) or True
        self.page.ctx_tabs.setCurrentIndex(1)
        self.page.asset_cat_combo.setCurrentText('prop')
        self.page.asset_combo.setCurrentText('Chair')
        self.page.usd_combo.setCurrentText('Chair_v001.usda')
        self.assertTrue(self._wait(lambda: self.page._listed_passes() == ['/beauty']))
        self._wait(lambda: False, timeout=0.3)
        self.assertEqual(asked, [])
        self.assertEqual(self.husk_calls, [])

    def test_name_drives_versions(self):
        self._pick_shot(False)
        names = [self.page.render_name_combo.itemText(i) for i in range(self.page.render_name_combo.count())]
        self.assertEqual(names, ['(none)', 'lighting'])
        versions = lambda: [self.page.version_combo.itemData(i) for i in range(self.page.version_combo.count())]
        self.assertEqual(versions(), [2, 3])
        self.page.render_name_combo.setCurrentText('lighting')
        self.assertEqual(versions(), [1, 2])
        self.page.render_name_combo.setCurrentText('new look')
        self.assertEqual(versions(), [1])
        self.assertIn('new_look', self.page.render_name_hint.text())
        self.page.render_name_combo.setCurrentText('lit_v3')
        self.assertEqual(versions(), [])
        self.assertTrue(self.page.render_name_hint.text())

    def _render_commands(self, name, engine='xpu', full=False):
        launched = []

        def fake_launch(commands, *a, **k):
            launched.append(commands)
            self.page._render_launched = True  # what the real _launch_render does
        self.page._launch_render = fake_launch
        self.page.render_name_combo.setCurrentText(name)
        self.page.version_combo.setCurrentIndex(self.page.version_combo.count() - 1)
        self.page.render_engine_combo.setCurrentIndex(self.page.render_engine_combo.findData(engine))
        self.page.start_frame_spin.setValue(1001)
        self.page.end_frame_spin.setValue(1001)
        with mock.patch.object(self.gui, 'SyncProgressDialog', FakeSync):
            self.page._start_render()
        self.assertEqual(len(launched), 1)
        if full:
            return launched[0]
        return [Path(c[c.index('-o') + 1]) for c in launched[0]]

    def test_render_paths_shot(self):
        asked = self._pick_shot(False)
        self.assertTrue(self._wait(lambda: asked))
        render = self.shot / 'houdini' / 'render'
        self.assertEqual(self._render_commands(''), [
            render / 'SH010_v003' / 'beauty' / 'SH010_beauty_v003_1001.exr',
            render / 'SH010_v003' / 'utility' / 'SH010_utility_v003_1001.exr'])
        self.assertTrue((render / 'SH010_v003' / 'beauty').is_dir())
        self.assertEqual(self._render_commands('lighting')[0],
                         render / 'SH010_lighting_v002' / 'beauty' / 'SH010_lighting_beauty_v002_1001.exr')

    def test_render_paths_asset(self):
        self.page._ask_scan_references = lambda *a: False
        self.page.ctx_tabs.setCurrentIndex(1)
        self.page.asset_cat_combo.setCurrentText('prop')
        self.page.asset_combo.setCurrentText('Chair')
        self.page.usd_combo.setCurrentText('Chair_v001.usda')
        self.assertTrue(self._wait(lambda: self.page._listed_passes() == ['/beauty']))
        render = self.asset / 'houdini' / 'render'
        self.assertEqual(self._render_commands('fx'),
                         [render / 'Chair_fx_v001' / 'beauty' / 'Chair_fx_beauty_v001_1001.exr'])

    def test_engine_from_usd_render_settings(self):
        asked = self._pick_shot(False)
        self.assertTrue(self._wait(lambda: asked))
        usd = str(self.shot / 'houdini' / 'USD' / 'SH010_v001.usda')
        for cmd in self._render_commands('', engine='usd', full=True):
            self.assertNotIn('--engine', cmd)
            self.assertEqual(cmd[0], str(self.husk))
            self.assertEqual(cmd[-1], usd)
            self.assertIn('--pass', cmd)
            self.assertIn('-o', cmd)
        cpu = self._render_commands('', engine='cpu', full=True)[0]
        self.assertEqual(cpu[1:3], ['--engine', 'cpu'])

    def test_engine_choice_remembered(self):
        combo = self.page.render_engine_combo
        combo.setCurrentIndex(combo.findData('usd'))
        page = self.gui.RenderPage(self.page.project_root, self.page.pipeline_dir)
        self.assertEqual(page.render_engine_combo.currentData(), 'usd')
        combo.setCurrentIndex(combo.findData('xpu'))
        page.deleteLater()
        page = self.gui.RenderPage(self.page.project_root, self.page.pipeline_dir)
        self.assertEqual(page.render_engine_combo.currentData(), 'xpu')
        page.deleteLater()

    # ---- v0.14.0: Advanced section, resolution, keep awake, frame source, per-project ----
    def _new_page(self, root=None):
        page = self.gui.RenderPage(root or self.root, (root or self.root) / 'pipeline')
        self.addCleanup(page.deleteLater)
        return page

    def test_advanced_section(self):
        adv = self.page.advanced
        self.assertFalse(adv.is_expanded())
        self.assertTrue(adv.content.isHidden())
        adv.set_expanded(True)
        self.assertFalse(adv.content.isHidden())
        self.assertTrue(self._new_page().advanced.is_expanded())
        self.assertEqual(adv.header.text(), 'Advanced')
        self.page.res_mode_combo.setCurrentIndex(self.page.res_mode_combo.findData('percent'))
        self.page.res_pct_spin.setValue(50)
        self.assertEqual(adv.header.text(), 'Advanced (resolution 50%)')
        self.page.keep_awake_cb.setChecked(False)
        self.assertIn('may sleep', adv.header.text())
        self.assertFalse(self.page.keep_screen_on_cb.isEnabled())

    def test_resolution_args(self):
        asked = self._pick_shot(False)
        self.assertTrue(self._wait(lambda: asked))
        cmd = self._render_commands('', full=True)[0]
        self.assertNotIn('--res', cmd)
        self.assertNotIn('--res-scale', cmd)
        combo = self.page.res_mode_combo
        combo.setCurrentIndex(combo.findData('size'))
        self.page.res_w_spin.setValue(1280)
        self.page.res_h_spin.setValue(720)
        cmd = self._render_commands('', full=True)[0]
        self.assertEqual(cmd[cmd.index('--res') + 1:cmd.index('--res') + 3], ['1280', '720'])
        self.assertEqual(self.page._render_meta['resolution'], '1280 x 720 (override)')
        combo.setCurrentIndex(combo.findData('percent'))
        self.page.res_pct_buttons[0].click()
        cmd = self._render_commands('', full=True)[0]
        self.assertEqual(cmd[cmd.index('--res-scale') + 1], '25')
        self.assertNotIn('--res', cmd)
        page = self._new_page()
        self.assertEqual(page.res_mode_combo.currentData(), 'percent')
        self.assertEqual(page.res_pct_spin.value(), 25)
        self.assertEqual(page.res_w_spin.value(), 1280)

    def test_keep_awake_lifecycle(self):
        asked = self._pick_shot(False)
        self.assertTrue(self._wait(lambda: asked))
        self.page.keep_screen_on_cb.setChecked(False)
        self._render_commands('')
        ka = FakeKeepAwake.instances[-1]
        self.assertEqual(ka.events, ['start'])  # still rendering (launch is stubbed)
        self.assertFalse(ka.screen_on)
        self.page._render_thread = None
        self.page._render_dialog = None
        self.page._on_render_finished(0)
        self.assertEqual(ka.events, ['start', 'stop'])
        # Sync cancelled: started before the sync, stopped right after.
        FakeSync.cancel = True
        launched = []
        self.page._launch_render = lambda commands, *a, **k: launched.append(commands)
        with mock.patch.object(self.gui, 'SyncProgressDialog', FakeSync):
            self.page._start_render()
        self.assertEqual(launched, [])
        self.assertEqual(FakeKeepAwake.instances[-1].events, ['start', 'stop'])
        # Error during the render setup.
        FakeSync.cancel = False
        with mock.patch.object(self.gui, 'SyncProgressDialog', side_effect=RuntimeError('boom')):
            self.page._start_render()
        self.assertEqual(FakeKeepAwake.instances[-1].events, ['start', 'stop'])
        # Option off: never started.
        count = len(FakeKeepAwake.instances)
        self.page.keep_awake_cb.setChecked(False)
        self._render_commands('')
        self.assertEqual(len(FakeKeepAwake.instances), count)

    def test_skip_sync_confirmation_passed(self):
        asked = self._pick_shot(False)
        self.assertTrue(self._wait(lambda: asked))
        self._render_commands('')
        self.assertFalse(FakeSync.created[-1].auto_continue)
        self.page.skip_sync_confirm_cb.setChecked(True)
        self._render_commands('')
        self.assertTrue(FakeSync.created[-1].auto_continue)
        self.assertTrue(self._new_page().skip_sync_confirm_cb.isChecked())

    def test_sync_dialog_auto_continue(self):
        from PySide6.QtWidgets import QDialog
        report = {'refs': 3, 'synced': 1, 'total': 3, 'missing': ['/a.vdb'], 'missing_groups': []}
        dlg = self.gui.SyncProgressDialog(Path('/x.usd'), None, auto_continue=True)
        dlg._on_finished(dict(report))
        self.assertEqual(dlg.result(), QDialog.Accepted)
        self.assertFalse(dlg.cancel_render)
        dlg = self.gui.SyncProgressDialog(Path('/x.usd'), None)
        dlg._on_finished(dict(report))
        self.assertNotEqual(dlg.result(), QDialog.Accepted)
        self.assertFalse(dlg.continue_btn.isHidden())
        dlg = self.gui.SyncProgressDialog(Path('/x.usd'), None, auto_continue=True)
        dlg._on_finished({'cancelled': True})
        self.assertNotEqual(dlg.result(), QDialog.Accepted)
        self.assertEqual(pa.sync_problem_count(report), 1)
        self.assertEqual(pa.sync_problem_count({'error': 'x'}), 1)

    def test_frame_source(self):
        pa.write_shot_meta(self.shot, {**pa.read_shot_meta(self.shot), 'frame_range': '1001-1050'})
        usd = self.shot / 'houdini' / 'USD' / 'SH010_v002.usda'
        usd.write_text('#usda 1.0\n(\n    startTimeCode = 1\n    endTimeCode = 24\n)\n'
                       'def RenderPass "beauty" {}\n')
        page = self.page
        page._ask_scan_references = lambda *a: False
        page.ctx_tabs.setCurrentIndex(0)
        page.shot_combo.setCurrentText('SH010')
        spins = lambda: (page.start_frame_spin.value(), page.end_frame_spin.value())
        self.assertEqual(page.frame_source_combo.currentData(), 'shot')
        self.assertEqual(spins(), (1001, 1050))
        src = page.frame_source_combo
        src.setCurrentIndex(src.findData('usd'))
        page.usd_combo.setCurrentText('SH010_v002.usda')
        self.assertTrue(self._wait(lambda: spins() == (1, 24)))
        page.usd_combo.setCurrentText('SH010_v001.usda')  # no time codes
        self.assertTrue(self._wait(lambda: page.frame_source_hint.text() == 'USD file has no frame range'))
        self.assertEqual(spins(), (1, 24))
        # Typing switches to Custom; Custom survives a context change.
        page.start_frame_spin.setValue(5)
        self.assertEqual(src.currentData(), 'custom')
        page._on_context_changed()
        self.assertEqual(spins(), (5, 24))
        self.assertEqual(self._new_page().frame_source_combo.currentData(), 'custom')
        # hrender: USD source disabled, shot range used, choice kept.
        src.setCurrentIndex(src.findData('usd'))
        page.render_mode_combo.setCurrentIndex(page.render_mode_combo.findData('hrender'))
        self.assertFalse(src.model().item(1).isEnabled())
        self.assertEqual(spins(), (1001, 1050))
        self.assertEqual(src.currentData(), 'usd')
        self.assertEqual(self._new_page().render_mode_combo.currentData(), 'hrender')
        # Asset label.
        page.render_mode_combo.setCurrentIndex(0)
        page.ctx_tabs.setCurrentIndex(1)
        self.assertEqual(src.itemText(0), 'From asset')

    def test_settings_per_project(self):
        page = self.page
        page.render_engine_combo.setCurrentIndex(page.render_engine_combo.findData('cpu'))
        page.mplay_cb.setChecked(True)
        page.houdini_version_combo.setCurrentText('21.0')
        page.render_order_combo.setCurrentIndex(1)
        page.save_log_cb.setChecked(False)
        restored = self._new_page()
        self.assertEqual(restored.render_engine_combo.currentData(), 'cpu')
        self.assertTrue(restored.mplay_cb.isChecked())
        self.assertEqual(restored.houdini_version_combo.currentText(), '21.0')
        self.assertEqual(restored.render_order_combo.currentData(), 'frame_major')
        self.assertFalse(restored.save_log_cb.isChecked())
        self.assertTrue(list((self.root / 'mazehub' / 'users').glob('*.json')))
        other = Path(self.tmp.name) / 'other_proj'
        other.mkdir()
        os.environ['MAZE_PROJECT_ROOT'] = str(other)
        fresh = self._new_page(other)
        self.assertNotEqual(fresh.render_engine_combo.currentData(), 'cpu')
        self.assertFalse(fresh.mplay_cb.isChecked())
        os.environ['MAZE_PROJECT_ROOT'] = str(self.root)


if __name__ == '__main__':
    unittest.main()
