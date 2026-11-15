"""Memory diagnostics during long renders, and closing MPlay periodically / before retries.
    uv run python -m unittest discover -s tests -v
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'))

import pipeline_app as pa  # noqa: E402

try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

GB = 1024 ** 3


class Parsers(unittest.TestCase):
    def test_meminfo(self):
        text = 'MemTotal:       65165000 kB\nMemFree:  1000 kB\nMemAvailable:   12000000 kB\n'
        self.assertEqual(pa._parse_meminfo(text), (12000000 * 1024, 65165000 * 1024))
        self.assertIsNone(pa._parse_meminfo('garbage'))

    def test_nvidia_smi(self):
        self.assertEqual(pa._parse_nvidia_smi('1502, 16376\n'), ((16376 - 1502) * 1024 ** 2, 16376 * 1024 ** 2))
        self.assertIsNone(pa._parse_nvidia_smi('NVIDIA-SMI has failed'))

    def test_tasklist_csv(self):
        text = ('"System Idle Process","0","Services","0","8 K"\n'
                '"mplay.exe","4242","Console","1","31,234,567 K"\n'
                '"MazeHub.exe","100","Console","1","612.345 K"\n')
        self.assertEqual(pa._parse_tasklist_csv(text), [
            (0, 'System Idle Process', 8 * 1024),
            (4242, 'mplay.exe', 31234567 * 1024),
            (100, 'MazeHub.exe', 612345 * 1024)])

    def test_snapshot_and_format(self):
        procs = [(1, 'mplay.exe', 30 * GB), (2, 'mplay-bin', 3 * GB), (7, 'MazeHub.exe', GB // 2),
                 (9, 'husk.exe', 5 * GB)]
        snap = pa.resource_snapshot(own_pid=7, procs=procs, ram=(4 * GB, 64 * GB), gpu=(14 * GB, 16 * GB))
        self.assertEqual(snap['mplay_pids'], [1, 2])
        self.assertEqual(pa.format_resources(snap),
                         '[resources] RAM free 4.0 / 64.0 GB · GPU free 14.0 / 16.0 GB · '
                         'MPlay 33.0 GB · MazeHub 0.5 GB')
        warnings = pa.resource_warnings(snap)
        self.assertEqual(len(warnings), 2)
        self.assertIn('Only 4.0 GB of 64.0 GB RAM is free', warnings[0])
        self.assertIn('MPlay is holding 33.0 GB', warnings[1])

    def test_missing_parts_left_out(self):
        snap = pa.resource_snapshot(own_pid=1, procs=[], ram=None, gpu=None)
        with mock.patch.object(pa, 'system_memory', return_value=None), \
                mock.patch.object(pa, 'gpu_memory', return_value=None):
            snap = pa.resource_snapshot(own_pid=1, procs=[])
        self.assertEqual(pa.format_resources(snap), '[resources] not available on this system')
        self.assertEqual(pa.resource_warnings(snap), [])
        healthy = pa.resource_snapshot(own_pid=1, procs=[(1, 'x', GB)], ram=(40 * GB, 64 * GB), gpu=None)
        self.assertEqual(pa.resource_warnings(healthy), [])

    def test_gpu_memory_without_nvidia_smi(self):
        with mock.patch('shutil.which', return_value=None), mock.patch.object(pa.os, 'name', 'posix'):
            self.assertIsNone(pa.gpu_memory())


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
print('rendering', flush=True)
if step == 'oom':
    print('KarmaXPU: critical error "cudaErrorMemoryAllocation"', flush=True)
    sys.exit(139)
sys.exit(0)
'''


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class MPlayRestarts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pipeline_gui
        cls.gui = pipeline_gui

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.script = self.dir / 'fake.py'
        self.script.write_text(FAKE_RENDERER)
        self.plan = self.dir / 'plan.json'
        # Process table: pid 1 is the user's own MPlay (open before the render); every
        # "frame" opens render MPlay pid 100+n until it is killed.
        self.alive = {1}
        self.killed = []

    def tearDown(self):
        self.tmp.cleanup()

    def _procs(self):
        return [(pid, 'mplay.exe', GB) for pid in sorted(self.alive)]

    def _kill(self, pids):
        self.killed.append(sorted(pids))
        self.alive.difference_update(pids)
        return pids

    def _run(self, plan, frames, every):
        self.plan.write_text(json.dumps({str(k): v for k, v in plan.items()}))
        commands = [[sys.executable, str(self.script), '--plan', str(self.plan), '--pass', '/R/beauty',
                     '-f', str(f), '--mplay-monitor', '-'] for f in frames]
        thread = self.gui.RenderThread(commands, working_dir=str(self.dir), mplay_restart_every=every)
        thread.RETRY_DELAY = 0.01
        out = []
        thread.output.connect(out.append)
        # Each finished frame leaves an MPlay window open (as husk --mplay-monitor does).
        thread.frame_finished.connect(lambda: self.alive.add(100 + len(self.alive)))
        snap = {'ram_free': 40 * GB, 'ram_total': 64 * GB, 'gpu_free': None, 'gpu_total': None,
                'mplay_bytes': GB, 'mplay_pids': [], 'own_bytes': GB}
        with mock.patch.object(self.gui, 'list_processes', side_effect=self._procs), \
                mock.patch.object(self.gui, 'kill_processes', side_effect=self._kill), \
                mock.patch.object(self.gui, 'resource_snapshot', return_value=snap):
            thread.run()
        return out

    def test_restart_every_two_frames(self):
        out = self._run({}, [1, 2, 3, 4, 5], every=2)
        self.assertEqual(len(self.killed), 2)          # after frames 2 and 4, not after the last
        self.assertTrue(all(1 not in k for k in self.killed))  # the user's own MPlay is never closed
        self.assertIn(1, self.alive)
        self.assertEqual(sum(1 for l in out if l.startswith('[resources]')), 5)
        self.assertTrue(any('Closed MPlay' in l and 'after 2 frames' in l for l in out))

    def test_never_restart(self):
        self._run({}, [1, 2, 3], every=0)
        self.assertEqual(self.killed, [])

    def test_closed_before_retry(self):
        out = self._run({2: ['oom', 'ok']}, [1, 2, 3], every=0)
        self.assertEqual(len(self.killed), 1)
        self.assertNotIn(1, self.killed[0])
        retry_at = next(i for i, l in enumerate(out) if 'retrying once' in l)
        self.assertIn('before the retry', out[retry_at + 1])
        self.assertTrue(out[retry_at + 2].startswith('[resources]'))

    def test_log_widget_capped(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        with mock.patch('pipeline_app.KeepAwake'):
            page = self.gui.RenderPage(self.dir, self.dir / 'pipeline')
        self.addCleanup(page.deleteLater)
        self.assertEqual(page.log_output.document().maximumBlockCount(), page.LOG_MAX_LINES)
        page.mplay_cb.setChecked(True)
        page.mplay_restart_spin.setValue(0)
        self.assertIn('MPlay never restarted', page.advanced.header.text())
        page.mplay_restart_spin.setValue(25)
        self.assertNotIn('MPlay', page.advanced.header.text())


if __name__ == '__main__':
    unittest.main()
