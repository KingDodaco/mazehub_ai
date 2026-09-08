import json
import os
import time
import getpass
from pathlib import Path


MAX_RECENT = 100


def _get_recent_files_path():
    """Get the recent files path - per-user in project folder, or fallback to home."""
    try:
        from settings import _get_project_root
        project_root = _get_project_root()
        if project_root:
            username = getpass.getuser()
            return project_root / 'pipeline' / 'mazehub' / f'recent_files_{username}.json'
    except Exception:
        pass
    return Path.home() / '.config' / 'mazehub' / 'recent_files.json'


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
    try:
        with open(path, 'w') as f:
            json.dump(files, f, indent=2)
    except Exception:
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