"""RenderThread retries a failed frame once with the same command, then moves on, and
reports frames that failed twice (log summary, Teams card).
    uv run python -m unittest discover -s tests -v
Uses a fake renderer script instead of husk. Skips if PySide6 is missing.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MAZE_CONFIG_DIR', str(Path(_TMP.name) / 'config'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
MAZEHUB_DIR = Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'
sys.path.insert(0, str(MAZEHUB_DIR))

import pipeline_app as pa  # noqa: E402

try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

# Lines from a real Karma XPU out-of-GPU-memory crash.
OOM_LINES = [
    '[11:35:09] Invalid shader wire specularTexture -> SurfaceShader: invalid destination sockets r->specular',
    '[11:35:09] Error wiring nodes for surface shader graph SurfaceShader',
    '[11:35:21] KarmaXPU: device Type:Optix ID:0 Name:"NVIDIA GeForce RTX 4080" has registered a critical '
    'error "cudaErrorMemoryAllocation", so will now stop functioning.  Future error messages will be suppressed',
    '00:00:26 16005MB WARNING | signal caught: error C0000005 -- access violation',
    '25924: Fatal error: Segmentation fault',
]

# Fake renderer. Argv like husk: --engine E --pass P -f N ... ; the behaviour per frame is read
# from a JSON plan {"<frame>": ["ok" | "oom" | "fail" | "spam", ...]}, one entry per attempt.
FAKE_RENDERER = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
plan_file = Path(args[args.index('--plan') + 1])
frame = args[args.index('-f') + 1]
plan = json.loads(plan_file.read_text())
counts_file = plan_file.with_suffix('.counts')
counts = json.loads(counts_file.read_text()) if counts_file.exists() else {}
attempt = counts.get(frame, 0)
counts[frame] = attempt + 1
counts_file.write_text(json.dumps(counts))
steps = plan.get(frame, ['ok'])
step = steps[min(attempt, len(steps) - 1)]
print('[11:35:04] Loading scene.usd', flush=True)
if step == 'ok':
    sys.exit(0)
if step == 'spam':
    for _ in range(200):
        print('[11:35:09] Invalid shader wire specularTexture -> SurfaceShader')
    sys.exit(0)
if step == 'oom':
    print('[11:35:21] KarmaXPU: device registered a critical error "cudaErrorMemoryAllocation"')
    print('25924: Fatal error: Segmentation fault', flush=True)
    sys.exit(139)
if step == 'crash':
    print('* CRASHED in 0x00007ffd5b271a8a', flush=True)
    sys.exit(139)
sys.exit(1)
'''


class FailureHelpers(unittest.TestCase):
    def test_classify_real_log(self):
        self.assertEqual(pa.classify_render_failure(139, OOM_LINES), 'GPU out of memory')

    def test_classify_others(self):
        self.assertEqual(pa.classify_render_failure(139, ['* CRASHED in 0x0']),
                         'Renderer crashed (access violation)')
        self.assertEqual(pa.classify_render_failure(3221225477, ['loading']),
                         'Renderer crashed (access violation)')
        self.assertEqual(pa.classify_render_failure(1, ['terminate: std::bad_alloc']), 'Out of memory')
        self.assertEqual(pa.classify_render_failure(1, ['Karma: no licenses available']), 'Licence error')
        self.assertTrue(pa.classify_render_failure(
            1, ['[12:00:00] Unable to open file C:/tex/wood.rat']).startswith('Missing file: Unable to open'))
        self.assertEqual(pa.classify_render_failure(
            1, ['[12:00:00] Invalid shader wire a -> b', 'Error wiring nodes for surface shader graph',
                'Render failed: bad camera']), 'exit code 1: Render failed: bad camera')
        self.assertEqual(pa.classify_render_failure(2, ['all good', '']), 'exit code 2')

    def test_compact_frames(self):
        self.assertEqual(pa.compact_frames([72, 56, 58, 70, 71, 56]), '56, 58, 70-72')
        self.assertEqual(pa.compact_frames([]), '')
        self.assertEqual(pa.compact_frames([1001]), '1001')

    def test_failed_frames_by_pass(self):
        failures = [{'pass': '/Render/Passes/Lightning', 'frame': 56},
                    {'pass': '/Render/Passes/Lightning', 'frame': 58},
                    {'pass': '/Render/Passes/Beauty', 'frame': 70},
                    {'pass': '/Render/Passes/Beauty', 'frame': 71},
                    {'pass': 'karma1', 'frame': None}]
        self.assertEqual(pa.failed_frames_by_pass(failures),
                         'Lightning 56, 58  |  Beauty 70-71  |  karma1 (whole job)')


class TeamsCard(unittest.TestCase):
    def _card(self, **kw):
        args = dict(shot='portal_0010', usd_file='portal_0010_renderscene_v003.usd',
                    passes=['/Render/Passes/Lightning'], start_frame=1, end_frame=100, interval=1,
                    version=6, render_engine='xpu', exit_code=139, render_time='18:34:04')
        args.update(kw)
        return pa.build_render_card(**args)

    def test_partial_failure(self):
        failures = [{'pass': '/Render/Passes/Lightning', 'frame': 56, 'code': 139,
                     'reason': 'GPU out of memory; retry: Renderer crashed (access violation)'}]
        card = self._card(failures=failures, total_jobs=100)
        facts = {f['name']: f['value'] for f in card['sections'][0]['facts']}
        self.assertEqual(facts['Status'], 'Finished with 1 failed frame')
        self.assertEqual(facts['Failed Frames'], 'Lightning 56')
        self.assertEqual(card['themeColor'], 'F39C12')
        section = card['sections'][-1]
        self.assertIn('Failed Frames', section['title'])
        self.assertEqual(section['facts'], [{'name': 'Lightning 56', 'value': failures[0]['reason']}])
        json.dumps(card)

    def test_all_failed_and_cap(self):
        failures = [{'pass': '/R/beauty', 'frame': f, 'code': 1, 'reason': 'exit code 1'}
                    for f in range(1, 21)]
        card = self._card(failures=failures, total_jobs=20)
        facts = {f['name']: f['value'] for f in card['sections'][0]['facts']}
        self.assertEqual(facts['Status'], 'Failed')
        self.assertEqual(facts['Failed Frames'], 'beauty 1-20')
        rows = card['sections'][-1]['facts']
        self.assertEqual(len(rows), pa.TEAMS_MAX_FAILURE_ROWS + 1)
        self.assertIn('5 more', rows[-1]['value'])

    def test_success_unchanged(self):
        card = self._card(exit_code=0)
        self.assertEqual(len(card['sections']), 2)
        facts = {f['name']: f['value'] for f in card['sections'][0]['facts']}
        self.assertEqual(facts['Status'], 'Succeeded')
        self.assertNotIn('Failed Frames', facts)

    def test_engine_labels(self):
        for engine, label in (('usd', 'From USD render settings'), ('xpu', 'Karma XPU'),
                              ('cpu', 'Karma CPU'), ('karma', 'karma')):
            facts = {f['name']: f['value'] for f in self._card(render_engine=engine)['sections'][1]['facts']}
            self.assertEqual(facts['Engine'], label)

    def test_send_posts_card(self):
        sent = []
        with mock.patch.object(pa.urllib.request, 'urlopen', side_effect=lambda req, timeout: sent.append(req)):
            ok = pa.send_teams_notification(
                'https://example.invalid/hook', 'SH010', 'a.usd', ['/R/beauty'], 1, 2, 1, 1, 'cpu', 1,
                '0:01:00', failures=[{'pass': '/R/beauty', 'frame': 2, 'code': 1, 'reason': 'exit code 1'}],
                total_jobs=2)
        self.assertTrue(ok)
        body = json.loads(sent[0].data)
        self.assertEqual(body['sections'][-1]['facts'][0], {'name': 'beauty 2', 'value': 'exit code 1'})


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class RetryRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pipeline_gui
        cls.gui = pipeline_gui

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.script = self.dir / 'fake_renderer.py'
        self.script.write_text(FAKE_RENDERER)
        self.plan = self.dir / 'plan.json'

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, plan, frames, engine='xpu', render_pass='/Render/Passes/Lightning', cancel_after=None):
        self.plan.write_text(json.dumps({str(k): v for k, v in plan.items()}))
        commands = [[sys.executable, str(self.script), '--plan', str(self.plan), '--engine', engine,
                     '--pass', render_pass, '-f', str(f), '-n', '1'] for f in frames]
        thread = self.gui.RenderThread(commands, working_dir=str(self.dir))
        thread.RETRY_DELAY = 0.01
        out, started, progress, finished = [], [], [], []
        thread.output.connect(out.append)
        thread.frame_started.connect(lambda *a: started.append(a))
        thread.progress.connect(lambda *a: progress.append(a))
        thread.finished.connect(finished.append)
        if cancel_after:
            thread.output.connect(lambda line: thread.cancel() if cancel_after in line else None)
        thread.run()
        counts_file = self.plan.with_suffix('.counts')
        counts = json.loads(counts_file.read_text()) if counts_file.exists() else {}
        return thread, out, started, progress, finished, counts

    def test_fail_then_ok_retries_once(self):
        for engine in ('xpu', 'cpu'):
            with self.subTest(engine=engine):
                cf = self.plan.with_suffix('.counts')
                if cf.exists():
                    cf.unlink()
                thread, out, started, progress, finished, counts = self._run(
                    {56: ['fail', 'ok']}, [55, 56, 57], engine=engine)
                self.assertEqual(counts, {'55': 1, '56': 2, '57': 1})
                self.assertEqual(thread.failures, [])
                self.assertEqual(len(started), 3)  # the retried frame is counted once
                self.assertEqual(progress[-1], (3, 3))
                self.assertTrue(any('retrying once' in l for l in out))
                self.assertTrue(any('rendered on the retry' in l for l in out))
                self.assertFalse(any(l.startswith('[summary]') for l in out))

    def test_oom_twice_listed_then_moves_on(self):
        thread, out, *_rest, finished, counts = self._run({56: ['oom', 'crash']}, [56, 57])
        self.assertEqual(counts, {'56': 2, '57': 1})
        self.assertEqual(thread.failures, [{
            'pass': '/Render/Passes/Lightning', 'frame': 56, 'code': 139,
            'reason': 'GPU out of memory; retry: Renderer crashed (access violation)', 'index': 0}])
        self.assertEqual(finished, [139])
        self.assertIn('[summary] 1 frame failed after a retry:', out)
        self.assertIn('[summary] Frames to re-render: Lightning 56', out)

    def test_plain_failure(self):
        thread, *_rest, counts = self._run({1: ['fail']}, [1, 2])
        self.assertEqual(counts, {'1': 2, '2': 1})
        self.assertEqual(thread.failures[0]['reason'], 'exit code 1')

    def test_cancel_does_not_retry(self):
        thread, out, *_rest, counts = self._run({1: ['fail']}, [1, 2], cancel_after='Loading scene')
        self.assertEqual(counts, {'1': 1})
        self.assertEqual(thread.failures, [])
        self.assertIn('[cancelled]', out)

    def test_skip_does_not_retry(self):
        self.plan.write_text(json.dumps({'1': ['fail']}))
        commands = [[sys.executable, str(self.script), '--plan', str(self.plan), '--pass', '/R/beauty',
                     '-f', str(f)] for f in (1, 2)]
        thread = self.gui.RenderThread(commands, working_dir=str(self.dir))
        thread.RETRY_DELAY = 0.01
        out = []
        thread.output.connect(out.append)
        thread.output.connect(lambda line: thread.skip_current()
                              if 'Loading scene' in line and thread.current_label.endswith('frame 1')
                              and not thread.skipped else None)
        thread.run()
        counts = json.loads(self.plan.with_suffix('.counts').read_text())
        self.assertEqual(counts, {'1': 1, '2': 1})
        self.assertEqual(thread.skipped, [{'pass': '/R/beauty', 'frame': 1}])
        self.assertEqual(thread.failures, [])
        self.assertIn('[summary] Skipped: beauty 1', out)

    def test_repeats_hidden(self):
        thread, out, *_rest = self._run({1: ['spam']}, [1])
        shown = [l for l in out if 'Invalid shader wire' in l and not l.startswith('[info]')]
        self.assertEqual(len(shown), 3)
        self.assertIn('[info] Hid 197 more repeats of: Invalid shader wire specularTexture -> SurfaceShader', out)


if __name__ == '__main__':
    unittest.main()
