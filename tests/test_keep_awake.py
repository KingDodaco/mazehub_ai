"""KeepAwake: the exact Windows power request, and the macOS/Linux subprocess fallbacks.
    uv run python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MAZE_CONFIG_DIR', str(Path(_TMP.name) / 'config'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'))

import pipeline_app as pa  # noqa: E402


class FakeKernel32:
    def __init__(self, result=1):
        self.calls = []
        self.result = result

    def SetThreadExecutionState(self, flags):
        self.calls.append(flags)
        return self.result


def fake_ctypes(kernel32):
    return types.SimpleNamespace(windll=types.SimpleNamespace(kernel32=kernel32))


class WindowsKeepAwake(unittest.TestCase):
    def _run(self, screen_on, result=1):
        k32 = FakeKernel32(result)
        with mock.patch.object(pa.os, 'name', 'nt'), mock.patch.dict(sys.modules, {'ctypes': fake_ctypes(k32)}):
            ka = pa.KeepAwake(screen_on=screen_on)
            error = ka.start()
            again = ka.start()
            active = ka.active
            ka.stop()
            ka.stop()
        return k32.calls, error, again, active, ka.active

    def test_screen_on(self):
        calls, error, again, active, after = self._run(True)
        self.assertEqual(error, '')
        self.assertEqual(again, '')
        self.assertTrue(active)
        self.assertFalse(after)
        self.assertEqual(calls, [0x80000003, 0x80000000])  # CONTINUOUS|SYSTEM|DISPLAY, then CONTINUOUS

    def test_system_only(self):
        calls, *_ = self._run(False)
        self.assertEqual(calls, [0x80000001, 0x80000000])

    def test_failure_reported_not_raised(self):
        calls, error, _again, active, _after = self._run(True, result=0)
        self.assertIn('SetThreadExecutionState failed', error)
        self.assertFalse(active)


class SubprocessKeepAwake(unittest.TestCase):
    def test_linux_systemd_inhibit(self):
        procs = []

        class FakeProc:
            def __init__(self, cmd, **kw):
                self.cmd = cmd
                self.terminated = False
                procs.append(self)

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 0

        with mock.patch.object(pa.os, 'name', 'posix'), mock.patch.object(pa.sys, 'platform', 'linux'), \
                mock.patch('shutil.which', lambda name: f'/usr/bin/{name}' if name == 'systemd-inhibit' else None), \
                mock.patch.object(pa.subprocess, 'Popen', FakeProc):
            ka = pa.KeepAwake(screen_on=True)
            self.assertEqual(ka.start(), '')
            ka.stop()
        self.assertEqual(len(procs), 1)
        self.assertEqual(procs[0].cmd[:2], ['systemd-inhibit', '--what=sleep:idle'])
        self.assertTrue(procs[0].terminated)

    def test_macos_caffeinate(self):
        with mock.patch.object(pa.os, 'name', 'posix'), mock.patch.object(pa.sys, 'platform', 'darwin'), \
                mock.patch('shutil.which', lambda name: '/usr/bin/caffeinate' if name == 'caffeinate' else None):
            cmd = pa.KeepAwake(screen_on=False)._command()
        self.assertEqual(cmd[:2], ['caffeinate', '-i'])
        self.assertNotIn('-d', cmd)
        self.assertEqual(cmd[-2:], ['-w', str(os.getpid())])

    def test_no_tool(self):
        with mock.patch.object(pa.os, 'name', 'posix'), mock.patch('shutil.which', lambda name: None):
            ka = pa.KeepAwake()
            self.assertIn('no caffeinate', ka.start())
            self.assertFalse(ka.active)
            ka.stop()

    def test_stop_without_start(self):
        pa.KeepAwake().stop()


if __name__ == '__main__':
    unittest.main()
