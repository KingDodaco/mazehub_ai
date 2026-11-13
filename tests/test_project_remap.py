"""Remapping registered project paths after a Windows profile / OneDrive
folder moves. Uses fake Windows paths, so it runs on any OS:
    uv run python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ['MAZE_CONFIG_DIR'] = str(Path(_TMP.name) / 'config')
os.environ['XDG_STATE_HOME'] = str(Path(_TMP.name) / 'state')
os.environ['LOCALAPPDATA'] = str(Path(_TMP.name) / 'state')
os.environ.pop('MAZE_PROJECT_ROOT', None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.pipeline_mirror' / 'pipeline' / 'mazehub'))

import settings  # noqa: E402

OLD = 'C:\\Users\\dominic\\OneDrive - Maze\\Projects\\Film'
NEW_PROFILE = 'C:\\Users\\dominic.000'
NEW = NEW_PROFILE + '\\OneDrive - Maze\\Projects\\Film'

ENV = {
    'USERPROFILE': NEW_PROFILE,
    'USERNAME': 'dominic',
    'OneDriveCommercial': NEW_PROFILE + '\\OneDrive - Maze',
    'OneDrive': NEW_PROFILE + '\\OneDrive - Maze',
    'OneDriveConsumer': NEW_PROFILE + '\\OneDrive',
}


class RemapCandidates(unittest.TestCase):
    def test_new_profile_suffix(self):
        self.assertEqual(settings.remap_candidates(OLD, ENV), [NEW])

    def test_machine_suffix_back_to_plain_profile(self):
        env = dict(ENV, USERPROFILE='C:\\Users\\dominic',
                   OneDriveCommercial='C:\\Users\\dominic\\OneDrive - Maze', OneDrive='',
                   OneDriveConsumer='')
        old = 'C:\\Users\\dominic.MAZE-PC03\\OneDrive - Maze\\Projects\\Film'
        self.assertEqual(settings.remap_candidates(old, env), [OLD])

    def test_case_insensitive_and_slashes(self):
        old = 'c:/users/DOMINIC/OneDrive - Maze/Projects/Film'
        cands = settings.remap_candidates(old, ENV)
        self.assertTrue(cands)
        self.assertTrue(settings._same_path(cands[0], NEW))

    def test_other_user_profile_not_remapped_but_onedrive_is(self):
        alice_desktop = 'C:\\Users\\alice\\Desktop\\Film'
        self.assertEqual(settings.remap_candidates(alice_desktop, ENV), [])
        alice_od = 'C:\\Users\\alice\\OneDrive - Maze\\Projects\\Film'
        self.assertEqual(settings.remap_candidates(alice_od, ENV), [NEW])

    def test_onedrive_moved_off_profile(self):
        env = dict(ENV, OneDriveCommercial='D:\\OneDrive - Maze', OneDrive='D:\\OneDrive - Maze')
        cands = settings.remap_candidates(OLD, env)
        self.assertEqual(cands, [NEW, 'D:\\OneDrive - Maze\\Projects\\Film'])

    def test_same_onedrive_account_only(self):
        old = 'E:\\OneDrive\\Film'
        self.assertEqual(settings.remap_candidates(old, ENV), [NEW_PROFILE + '\\OneDrive\\Film'])

    def test_renamed_org_falls_back_to_any_onedrive(self):
        old = 'E:\\OneDrive - Old Name\\Film'
        self.assertIn(NEW_PROFILE + '\\OneDrive - Maze\\Film', settings.remap_candidates(old, ENV))

    def test_non_profile_paths_untouched(self):
        for path in ('D:\\Projects\\Film', '\\\\server\\share\\Film', '/home/dominic/Film', ''):
            self.assertEqual(settings.remap_candidates(path, ENV), [], path)

    def test_no_env(self):
        self.assertEqual(settings.remap_candidates(OLD, {}), [])

    def test_unchanged_profile_gives_nothing(self):
        env = dict(ENV, USERPROFILE='C:\\Users\\dominic',
                   OneDriveCommercial='C:\\Users\\dominic\\OneDrive - Maze', OneDrive='',
                   OneDriveConsumer='')
        self.assertEqual(settings.remap_candidates(OLD, env), [])

    def test_remap_under(self):
        old_file = OLD + '\\sequence\\sh010\\houdini\\sh010_v003.hip'
        self.assertEqual(settings.remap_under(old_file, NEW, ENV),
                         NEW + '\\sequence\\sh010\\houdini\\sh010_v003.hip')
        self.assertIsNone(settings.remap_under(NEW + '\\a.hip', NEW, ENV))
        self.assertIsNone(settings.remap_under('D:\\elsewhere\\a.hip', NEW, ENV))


class RegistryRemap(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ENV}
        os.environ.update(ENV)
        self.reachable = {NEW}
        self._orig_reachable = settings._reachable
        settings._reachable = lambda root: root in self.reachable
        for path in (settings.PROJECTS_PATH, settings.PROJECTS_BACKUP_PATH, settings.LOCAL_STATE_PATH):
            if path.exists():
                path.unlink()
        settings._save_json(settings.PROJECTS_PATH, {
            'projects': [{'name': 'Film', 'root': OLD}], 'active': OLD})
        self.registry_bytes = settings.PROJECTS_PATH.read_bytes()

    def tearDown(self):
        settings._reachable = self._orig_reachable
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def local_state(self):
        return json.loads(settings.LOCAL_STATE_PATH.read_text())

    def test_resolve_finds_moved_project_without_touching_registry(self):
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), NEW)
        self.assertEqual(settings.PROJECTS_PATH.read_bytes(), self.registry_bytes)
        state = self.local_state()
        self.assertEqual(state['remapped'], {OLD: NEW})
        self.assertEqual(state['last_project'], OLD)
        [entry] = settings.list_projects()
        self.assertEqual(entry['root'], NEW)
        self.assertEqual(entry['registered_root'], OLD)

    def test_switching_and_adding_moved_folder_adds_no_duplicate(self):
        settings.resolve_project_root(wait=0.5)
        settings.set_active_project(NEW)
        settings.add_project(NEW)
        reg = json.loads(settings.PROJECTS_PATH.read_text())
        self.assertEqual(reg['projects'], [{'name': 'Film', 'root': OLD}])
        self.assertEqual(reg['active'], OLD)
        self.assertEqual(self.local_state()['last_project'], OLD)

    def test_adding_moved_folder_before_any_resolve(self):
        settings.add_project(NEW)
        reg = json.loads(settings.PROJECTS_PATH.read_text())
        self.assertEqual(len(reg['projects']), 1)
        self.assertEqual(self.local_state()['remapped'], {OLD: NEW})

    def test_original_back_drops_alias(self):
        settings.resolve_project_root(wait=0.5)
        self.reachable = {OLD, NEW}
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), OLD)
        self.assertEqual(self.local_state()['remapped'], {})

    def test_unreachable_stays_unreachable(self):
        self.reachable = set()
        self.assertIsNone(settings.resolve_project_root(wait=0.5))
        self.assertNotIn('remapped', self.local_state() if settings.LOCAL_STATE_PATH.exists() else {})

    def test_locate_project(self):
        self.assertEqual(str(settings.locate_project(OLD, timeout=0.5)), NEW)
        self.assertEqual(self.local_state()['remapped'], {OLD: NEW})

    def test_remove_by_local_path(self):
        settings.resolve_project_root(wait=0.5)
        settings.remove_project(NEW)
        reg = json.loads(settings.PROJECTS_PATH.read_text())
        self.assertEqual(reg['projects'], [])
        self.assertEqual(self.local_state()['remapped'], {})


if __name__ == '__main__':
    unittest.main()
