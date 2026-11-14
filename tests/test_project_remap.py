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

settings._REGISTRY_SYNC_ROOTS = []  # no real OneDrive registry in tests

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


class StaleCopy(unittest.TestCase):
    def test_old_profile_onedrive_is_stale(self):
        self.assertEqual(settings.stale_copy(OLD, ENV), NEW)

    def test_onedrive_moved_to_other_drive(self):
        env = dict(ENV, OneDriveCommercial='D:\\OneDrive - Maze', OneDrive='D:\\OneDrive - Maze')
        cur = NEW_PROFILE + '\\OneDrive - Maze\\Projects\\Film'
        self.assertEqual(settings.stale_copy(cur, env), 'D:\\OneDrive - Maze\\Projects\\Film')

    def test_sharepoint_library_needs_mount_point(self):
        old = 'C:\\Users\\dominic\\Maze Ltd\\Studio - Projects\\Film'
        new = NEW_PROFILE + '\\Maze Ltd\\Studio - Projects\\Film'
        mounts = settings._sync_roots(ENV) + [NEW_PROFILE + '\\Maze Ltd\\Studio - Projects']
        self.assertEqual(settings.stale_copy(old, ENV, mounts), new)
        self.assertIsNone(settings.stale_copy(old, ENV))

    def test_local_documents_in_old_profile_not_stale(self):
        self.assertIsNone(settings.stale_copy('C:\\Users\\dominic\\Documents\\Film', ENV))

    def test_current_profile_not_stale(self):
        self.assertIsNone(settings.stale_copy(NEW, ENV))

    def test_no_env_not_stale(self):
        self.assertIsNone(settings.stale_copy(OLD, {}))
        self.assertIsNone(settings.stale_copy('/home/dominic/Film', ENV))


class RegistryRemap(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ENV}
        os.environ.update(ENV)
        self.reachable = {NEW}
        self._orig_reachable = settings._reachable
        settings._reachable = lambda root: root in self.reachable
        settings._SESSION_PATHS.clear()
        for path in (settings.PROJECTS_PATH, settings.PROJECTS_BACKUP_PATH, settings.LOCAL_STATE_PATH):
            if path.exists():
                path.unlink()
        self.use_registered(OLD)

    def tearDown(self):
        settings._reachable = self._orig_reachable
        settings._SESSION_PATHS.clear()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def use_registered(self, *roots, active=None):
        settings._save_json(settings.PROJECTS_PATH, {
            'projects': [{'name': 'Film', 'root': r} for r in roots],
            'active': active or roots[0]})
        self.registry_bytes = settings.PROJECTS_PATH.read_bytes()

    def registry(self):
        return json.loads(settings.PROJECTS_PATH.read_text())

    def local_state(self):
        if not settings.LOCAL_STATE_PATH.exists():
            return {}
        return json.loads(settings.LOCAL_STATE_PATH.read_text())

    def test_resolve_finds_moved_project_and_saves_nothing(self):
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), NEW)
        self.assertEqual(settings.PROJECTS_PATH.read_bytes(), self.registry_bytes)
        state = self.local_state()
        self.assertNotIn('remapped', state)
        self.assertEqual(state['last_project'], OLD)
        [entry] = settings.list_projects()
        self.assertEqual(entry['root'], NEW)
        self.assertEqual(entry['registered_root'], OLD)

    def test_next_session_works_it_out_again(self):
        settings.resolve_project_root(wait=0.5)
        settings._SESSION_PATHS.clear()
        self.assertEqual(settings.list_projects()[0]['root'], NEW)  # synced: no probe needed
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), NEW)

    def test_old_saved_remaps_are_dropped(self):
        settings._save_json(settings.LOCAL_STATE_PATH, {'remapped': {OLD: 'C:\\elsewhere'}})
        settings.resolve_project_root(wait=0.5)
        self.assertNotIn('remapped', self.local_state())

    def test_switching_and_adding_moved_folder_adds_no_duplicate(self):
        settings.resolve_project_root(wait=0.5)
        settings.set_active_project(NEW)
        settings.add_project(NEW)
        reg = self.registry()
        self.assertEqual(reg['projects'], [{'name': 'Film', 'root': OLD}])
        self.assertEqual(reg['active'], OLD)
        self.assertEqual(self.local_state()['last_project'], OLD)

    def test_adding_moved_folder_before_any_resolve(self):
        settings.add_project(NEW)
        self.assertEqual(len(self.registry()['projects']), 1)

    def test_stale_old_copy_never_opened_even_if_present(self):
        self.reachable = {OLD, NEW}
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), NEW)
        self.assertEqual(settings.PROJECTS_PATH.read_bytes(), self.registry_bytes)

    def test_only_stale_copy_present_is_unreachable(self):
        self.reachable = {OLD}
        self.assertIsNone(settings.resolve_project_root(wait=0.5))
        self.assertIsNone(settings.locate_project(OLD, timeout=0.5))

    def test_local_old_profile_project_still_opens(self):
        old_local = 'C:\\Users\\dominic\\Documents\\Film'
        self.use_registered(old_local)
        self.reachable = {old_local}
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), old_local)

    def test_original_back(self):
        # Without OneDrive on this login the old path isn't a stale copy.
        for k in ('OneDriveCommercial', 'OneDrive', 'OneDriveConsumer'):
            os.environ.pop(k, None)
        old_local = 'C:\\Users\\dominic\\Documents\\Film'
        new_local = NEW_PROFILE + '\\Documents\\Film'
        self.use_registered(old_local)
        self.reachable = {new_local}
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), new_local)
        self.reachable = {old_local, new_local}
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), old_local)
        self.assertEqual(settings._SESSION_PATHS, {})

    def test_locate_project(self):
        self.assertEqual(str(settings.locate_project(OLD, timeout=0.5)), NEW)
        self.assertEqual(settings.list_projects()[0]['root'], NEW)

    def test_remove_by_local_path(self):
        settings.resolve_project_root(wait=0.5)
        settings.remove_project(NEW)
        self.assertEqual(self.registry()['projects'], [])


B_PROFILE = 'C:\\Users\\user'
A_PATH = 'C:\\Users\\user.STUDENT.000\\OneDrive - Uni\\Projects\\Film'
B_PATH = B_PROFILE + '\\OneDrive - Uni\\Projects\\Film'
B_ENV = {'USERPROFILE': B_PROFILE, 'USERNAME': 'user',
         'OneDriveCommercial': B_PROFILE + '\\OneDrive - Uni',
         'OneDrive': B_PROFILE + '\\OneDrive - Uni', 'OneDriveConsumer': ''}


class BothDirections(RegistryRemap.__base__):
    """Machine B (C:\\Users\\user) reading a registry written on machine A
    (C:\\Users\\user.STUDENT.000), and the other way round."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in B_ENV}
        os.environ.update(B_ENV)
        self._orig_reachable = settings._reachable
        self.reachable = {B_PATH}
        settings._reachable = lambda root: root in self.reachable
        settings._SESSION_PATHS.clear()
        for path in (settings.PROJECTS_PATH, settings.PROJECTS_BACKUP_PATH, settings.LOCAL_STATE_PATH):
            if path.exists():
                path.unlink()

    tearDown = RegistryRemap.tearDown
    use_registered = RegistryRemap.use_registered
    registry = RegistryRemap.registry
    local_state = RegistryRemap.local_state

    def test_profile_variants_both_ways(self):
        for old in ('C:\\Users\\user.STUDENT.000\\x', 'C:\\Users\\user.STUDENT\\x'):
            self.assertEqual(settings.remap_candidates(old, B_ENV), [B_PROFILE + '\\x'])
        env_a = dict(B_ENV, USERPROFILE='C:\\Users\\user.STUDENT.000')
        for old in ('C:\\Users\\user\\x', 'C:\\Users\\user.STUDENT\\x'):
            self.assertEqual(settings.remap_candidates(old, env_a),
                             ['C:\\Users\\user.STUDENT.000\\x'])

    def test_list_shows_this_machines_path_without_probing(self):
        self.use_registered(A_PATH)
        [entry] = settings.list_projects()
        self.assertEqual(entry['root'], B_PATH)

    def test_local_project_mapped_after_startup_probe(self):
        other = 'D:\\Projects\\Other'
        a_local = 'C:\\Users\\user.STUDENT.000\\Documents\\Short'
        b_local = B_PROFILE + '\\Documents\\Short'
        self.use_registered(other, a_local, active=other)
        self.reachable = {other, b_local}
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), other)
        roots = {p['registered_root']: p['root'] for p in settings.list_projects()}
        self.assertEqual(roots[a_local], b_local)

    def test_duplicates_from_both_machines_show_once(self):
        self.use_registered(B_PATH, A_PATH)
        [entry] = settings.list_projects()
        self.assertEqual(entry['root'], B_PATH)
        self.assertEqual(entry['registered_root'], B_PATH)
        self.assertEqual(entry['aliases'], [A_PATH])

    def test_duplicates_local_unsynced(self):
        for k in ('OneDriveCommercial', 'OneDrive'):
            os.environ.pop(k, None)
        a = 'C:\\Users\\user.STUDENT.000\\Documents\\Short'
        b = 'C:\\Users\\user.STUDENT\\Documents\\Short'
        self.use_registered(a, b)
        self.assertEqual(len(settings.list_projects()), 1)

    def test_add_either_variant_adds_nothing(self):
        self.use_registered(A_PATH)
        settings.add_project(B_PATH)
        settings.add_project('C:\\Users\\user.STUDENT\\OneDrive - Uni\\Projects\\Film')
        self.assertEqual(self.registry()['projects'], [{'name': 'Film', 'root': A_PATH}])

    def test_remove_removes_duplicates(self):
        self.use_registered(B_PATH, A_PATH)
        settings.remove_project(B_PATH)
        self.assertEqual(self.registry()['projects'], [])
        self.assertEqual(self.registry()['active'], '')

    def test_resolve_backwards(self):
        self.use_registered(A_PATH)
        self.assertEqual(str(settings.resolve_project_root(wait=0.5)), B_PATH)
        self.assertEqual(settings.PROJECTS_PATH.read_bytes(), self.registry_bytes)


class RecentFilesKeepStoredPaths(unittest.TestCase):
    def test_save_keeps_other_machines_paths(self):
        import recent_files
        tmp = Path(_TMP.name) / 'recent.json'
        a_file = 'C:\\Users\\user.STUDENT.000\\OneDrive - Uni\\Projects\\Film\\a.hip'
        tmp.write_text(json.dumps([{'path': a_file, 'display_name': 'a.hip'}]))
        saved = {k: os.environ.get(k) for k in ('USERPROFILE', 'USERNAME', 'MAZE_PROJECT_ROOT')}
        orig = recent_files._get_recent_files_path
        try:
            os.environ.update(USERPROFILE=B_PROFILE, USERNAME='user', MAZE_PROJECT_ROOT=B_PATH)
            recent_files._get_recent_files_path = lambda: tmp
            [entry] = recent_files.load_recent_files()
            self.assertEqual(entry['path'], B_PATH + '\\a.hip')
            recent_files.add_recent_file(B_PATH + '\\b.hip', 'Houdini')
            stored = json.loads(tmp.read_text())
            self.assertEqual([e['path'] for e in stored], [B_PATH + '\\b.hip', a_file])
            self.assertFalse(any('_stored_path' in e for e in stored))
        finally:
            recent_files._get_recent_files_path = orig
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == '__main__':
    unittest.main()
