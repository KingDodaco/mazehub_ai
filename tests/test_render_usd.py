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
        self.assertEqual(info, {'passes': ['/only'], 'layer_refs': []})

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
            self.assertEqual(info['passes'], ['/Render/passes/beauty', '/Render/passes/utility'])
            self.assertEqual(set(info['layer_refs']),
                             {'./lighting.usda', '../env/set.usdc', './char.usd', 'big payload.usdc'})


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
        ]
        for p in self.patches:
            p.start()
        self.husk_calls = []
        self.page = self.gui.RenderPage(root, root / 'pipeline')
        self.page._ask_full_scan_fallback = lambda *a: False

    def tearDown(self):
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

    def _render_commands(self, name):
        class FakeSync:
            report = {}
            cancel_render = False

            def __init__(self, *a, **k):
                pass

            def start(self):
                pass

            def exec(self):
                return self_gui.QDialog.Accepted

            def elapsed(self):
                return 0.0

            def _format_duration(self, s):
                return '0s'
        self_gui = self.gui
        launched = []
        self.page._launch_render = lambda commands, *a, **k: launched.append(commands)
        self.page.render_name_combo.setCurrentText(name)
        self.page.version_combo.setCurrentIndex(self.page.version_combo.count() - 1)
        self.page.render_engine_combo.setCurrentIndex(0)
        self.page.start_frame_spin.setValue(1001)
        self.page.end_frame_spin.setValue(1001)
        with mock.patch.object(self.gui, 'SyncProgressDialog', FakeSync):
            self.page._do_render()
        self.assertEqual(len(launched), 1)
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


if __name__ == '__main__':
    unittest.main()
