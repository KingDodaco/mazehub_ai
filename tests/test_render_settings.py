"""Render settings saved per person, per project (<project>/mazehub/users/<user>.json).
    uv run python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MAZE_CONFIG_DIR', str(Path(_TMP.name) / 'config'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'))

import settings  # noqa: E402


class RenderSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = Path(self.tmp.name) / 'ProjectA'
        self.b = Path(self.tmp.name) / 'ProjectB'
        self.a.mkdir()
        self.b.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_per_project_and_user(self):
        settings.set_render_setting('render_engine', 'cpu', root=self.a, user='s5720563')
        settings.set_render_setting('render_engine', 'usd', root=self.a, user='alice')
        settings.set_render_setting('render_engine', 'xpu', root=self.b, user='s5720563')
        self.assertEqual(settings.get_render_setting('render_engine', 'x', root=self.a, user='s5720563'), 'cpu')
        self.assertEqual(settings.get_render_setting('render_engine', 'x', root=self.a, user='alice'), 'usd')
        self.assertEqual(settings.get_render_setting('render_engine', 'x', root=self.b, user='s5720563'), 'xpu')
        path = self.a / 'mazehub' / 'users' / 's5720563.json'
        self.assertEqual(json.loads(path.read_text()), {'render_engine': 'cpu'})

    def test_falls_back_to_global(self):
        settings.set_setting('render_order', 'frame_major')
        self.assertEqual(settings.get_render_setting('render_order', 'pass_major', root=self.a, user='bob'),
                         'frame_major')
        settings.set_render_setting('render_order', 'pass_major', root=self.a, user='bob')
        self.assertEqual(settings.get_render_setting('render_order', None, root=self.a, user='bob'), 'pass_major')
        self.assertEqual(settings.get_render_setting('render_missing', 7, root=self.a, user='bob'), 7)

    def test_env_project_and_username(self):
        old = {k: os.environ.get(k) for k in ('MAZE_PROJECT_ROOT', 'USERNAME')}
        try:
            os.environ['MAZE_PROJECT_ROOT'] = str(self.b)
            os.environ['USERNAME'] = 'DOMAIN\\Jo Smith'
            settings.set_render_setting('render_mplay', True)
            self.assertTrue((self.b / 'mazehub' / 'users' / 'DOMAIN_Jo_Smith.json').is_file())
            self.assertTrue(settings.get_render_setting('render_mplay', False))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_corrupt_file_reads_empty(self):
        path = settings.user_settings_path(self.a, 'eve')
        path.parent.mkdir(parents=True)
        path.write_text('{not json')
        self.assertEqual(settings.get_render_setting('render_unset_key', 'dflt', root=self.a, user='eve'), 'dflt')
        settings.set_render_setting('render_engine', 'cpu', root=self.a, user='eve')
        self.assertEqual(json.loads(path.read_text()), {'render_engine': 'cpu'})


if __name__ == '__main__':
    unittest.main()
