import json
import os
import platform
from pathlib import Path


def _get_project_root():
    """Find the project root from MAZE_PROJECT_ROOT env var."""
    root = os.environ.get('MAZE_PROJECT_ROOT')
    if root:
        return Path(root)
    return None


def _get_shared_settings_path():
    """Lazy getter for shared settings path."""
    root = _get_project_root()
    if root:
        return root / 'pipeline' / 'mazehub' / 'shared_settings.json'
    return None
USER_SETTINGS_PATH = Path.home() / '.config' / 'mazehub' / 'user_settings.json'

# Keys that should be shared globally (project-level)
SHARED_KEYS = {
    'teams_webhook_url',
    'dailies_webhook_url',
    'production_webhook_url',
    'husk_path',
    'yt_screensaver_url',
}


def _ensure_dir(path):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)


def _load_json(path):
    if path and path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_json(path, data):
    if path:
        _ensure_dir(path)
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


def _merge_settings(shared, user):
    """Merge shared and user settings (shared takes precedence for shared keys)."""
    result = {}
    result.update(user)
    result.update(shared)
    return result


def load_settings():
    """Load all settings (shared + user)."""
    shared = _load_json(_get_shared_settings_path())
    user = _load_json(USER_SETTINGS_PATH)
    return _merge_settings(shared, user)


def save_settings(settings):
    """Save settings, splitting into shared and user files."""
    shared = {k: v for k, v in settings.items() if k in SHARED_KEYS}
    user = {k: v for k, v in settings.items() if k not in SHARED_KEYS}
    existing_shared = _load_json(_get_shared_settings_path())
    existing_shared.update(shared)
    existing_user = _load_json(USER_SETTINGS_PATH)
    existing_user.update(user)
    _save_json(_get_shared_settings_path(), existing_shared)
    _save_json(USER_SETTINGS_PATH, existing_user)


def get_setting(key, default=None):
    settings = load_settings()
    return settings.get(key, default)


def set_setting(key, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


def _default_husk_candidates():
    system = platform.system()
    candidates = []

    hfs = os.environ.get('HFS')
    if hfs:
        hfs_path = Path(hfs)
        if system == 'Windows':
            candidates.append(hfs_path / 'bin' / 'husk.exe')
        else:
            candidates.append(hfs_path / 'bin' / 'husk')

    if system == 'Windows':
        for base in [
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')),
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')),
        ]:
            sidefx = base / 'Side Effects Software'
            if sidefx.exists():
                for d in sorted(sidefx.iterdir(), reverse=True):
                    if d.is_dir() and d.name.lower().startswith('houdini'):
                        candidates.append(d / 'bin' / 'husk.exe')
    elif system == 'Darwin':
        for d in sorted(Path('/Applications').glob('Houdini*'), reverse=True):
            candidates.append(d / 'Frameworks' / 'Houdini.framework' / 'Versions' / 'Current' / 'Resources' / 'bin' / 'husk')
    else:
        for parent in [Path('/opt'), Path('/usr/local')]:
            for d in sorted(parent.glob('houdini*'), reverse=True):
                if d.is_dir():
                    candidates.append(d / 'bin' / 'husk')
            hfs_home = Path.home() / 'houdini'
            if hfs_home.exists():
                for d in sorted(hfs_home.glob('houdini*'), reverse=True):
                    if d.is_dir():
                        candidates.append(d / 'bin' / 'husk')

    return candidates


def find_husk():
    configured = get_setting('husk_path')
    if configured:
        p = Path(configured)
        if p.exists():
            return str(p)

    for candidate in _default_husk_candidates():
        if candidate.exists():
            return str(candidate)

    return ''
