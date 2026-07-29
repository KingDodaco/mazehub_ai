import json
import os
import time
from pathlib import Path


RECENT_FILES_PATH = Path.home() / '.config' / 'mazehub' / 'recent_files.json'
MAX_RECENT = 100


def _ensure_dir():
    RECENT_FILES_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_recent_files():
    _ensure_dir()
    if RECENT_FILES_PATH.exists():
        try:
            with open(RECENT_FILES_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_recent_files(files):
    _ensure_dir()
    try:
        with open(RECENT_FILES_PATH, 'w') as f:
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