import json
import os
import shutil
import time
import getpass
from pathlib import Path


MAX_RECENT = 100


def _config_path(filename):
    return Path.home() / '.config' / 'mazehub' / filename


def _migrate_once(path, legacy):
    if path.exists() or not legacy or not legacy.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(legacy, path)
    except Exception:
        pass


def _get_recent_files_path():
    filename = f'recent_files_{getpass.getuser()}.json'
    try:
        from settings import CONFIG_DIR, _get_project_root
        project_root = _get_project_root()
        if project_root:
            path = project_root / 'mazehub' / filename
            legacy = project_root / 'pipeline' / 'mazehub' / filename
            _migrate_once(path, legacy)
            return path
        path = CONFIG_DIR / filename
        _migrate_once(path, _config_path('recent_files.json'))
        return path
    except Exception:
        pass
    return _config_path(filename)


def _ensure_dir(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def load_recent_files():
    path = _get_recent_files_path()
    _ensure_dir(path)
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_recent_files(files):
    path = _get_recent_files_path()
    _ensure_dir(path)
    tmp = path.with_name(path.name + '.tmp')
    try:
        with open(tmp, 'w') as f:
            json.dump(files, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def add_recent_file(path, app_name='', context_type='', context_name='', context_category='', app_key=''):
    if not path:
        return
    files = load_recent_files()
    display_name = os.path.basename(path)
    entry = {
        'path': str(path),
        'display_name': display_name,
        'app_name': app_name,
        'app_key': app_key,
        'context_type': context_type,
        'context_name': context_name,
        'context_category': context_category,
        'timestamp': time.time(),
    }
    files = [f for f in files if f.get('path') != str(path)]
    files.insert(0, entry)
    if len(files) > MAX_RECENT:
        files = files[:MAX_RECENT]
    save_recent_files(files)


def get_recent_files(limit=None):
    files = load_recent_files()
    if limit:
        files = files[:limit]
    return files


def remove_recent_file(path):
    files = load_recent_files()
    files = [f for f in files if f.get('path') != str(path)]
    save_recent_files(files)


def clear_recent_files():
    save_recent_files([])


def _get_app_versions_path():
    path = _config_path('app_versions.json')
    legacy = None
    try:
        from settings import _get_project_root
        project_root = _get_project_root()
        if project_root:
            legacy = (project_root / 'pipeline' / 'mazehub' /
                      f'app_versions_{getpass.getuser()}.json')
    except Exception:
        legacy = None
    _migrate_once(path, legacy)
    return path


def load_app_versions():
    path = _get_app_versions_path()
    _ensure_dir(path)
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_app_versions(versions):
    path = _get_app_versions_path()
    _ensure_dir(path)
    try:
        with open(path, 'w') as f:
            json.dump(versions, f, indent=2)
    except Exception:
        pass


def get_last_app_version(app_key):
    versions = load_app_versions()
    return versions.get(app_key, '')


def set_last_app_version(app_key, version):
    versions = load_app_versions()
    versions[app_key] = version
    save_app_versions(versions)