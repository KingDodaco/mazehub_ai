import json
import os
import platform
from pathlib import Path

USER_SETTINGS_PATH = Path.home() / '.config' / 'mazehub' / 'user_settings.json'
PROJECTS_PATH = Path.home() / '.config' / 'mazehub' / 'projects.json'

# Keys that should be shared across machines within a project
SHARED_KEYS = {
    'teams_webhook_url',
    'dailies_webhook_url',
    'production_webhook_url',
    'husk_path',
    'yt_screensaver_url',
}


def _get_project_root():
    root = os.environ.get('MAZE_PROJECT_ROOT')
    if root:
        return Path(root)
    return None


def _migrate_legacy_shared(legacy_path, new_path):
    data = _load_json(legacy_path)
    if not data:
        return
    channel = data.pop('update_channel', None)
    _save_json(new_path, data)
    if channel:
        user = _load_json(USER_SETTINGS_PATH)
        if not user.get('update_channel'):
            user['update_channel'] = channel
            _save_json(USER_SETTINGS_PATH, user)


def _get_shared_settings_path():
    root = _get_project_root()
    if not root:
        return None
    path = root / 'mazehub' / 'shared_settings.json'
    legacy = root / 'pipeline' / 'mazehub' / 'shared_settings.json'
    if not path.exists() and legacy.exists():
        _migrate_legacy_shared(legacy, path)
    return path


def _load_registry():
    data = _load_json(PROJECTS_PATH)
    projects = [
        {'name': str(p.get('name') or Path(p['root']).name),
         'root': str(p['root'])}
        for p in data.get('projects', [])
        if isinstance(p, dict) and p.get('root')
    ]
    return {'projects': projects, 'active': str(data.get('active') or '')}


def _save_registry(reg):
    _save_json(PROJECTS_PATH, reg)


def list_projects():
    return _load_registry()['projects']


def _normalize_root(root):
    p = Path(root).expanduser()
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


def add_project(root):
    root = _normalize_root(root)
    reg = _load_registry()
    for entry in reg['projects']:
        if entry['root'] == root:
            if not reg['active']:
                reg['active'] = root
                _save_registry(reg)
            return entry
    entry = {'name': Path(root).name, 'root': root}
    reg['projects'].append(entry)
    if not reg['active']:
        reg['active'] = root
    _save_registry(reg)
    return entry


def remove_project(root):
    reg = _load_registry()
    before = len(reg['projects'])
    active_before = reg['active']
    reg['projects'] = [p for p in reg['projects'] if p['root'] != root]
    if reg['active'] == root:
        reg['active'] = reg['projects'][0]['root'] if reg['projects'] else ''
    if len(reg['projects']) != before or reg['active'] != active_before:
        _save_registry(reg)


def set_active_project(root):
    root = _normalize_root(root)
    reg = _load_registry()
    if not any(p['root'] == root for p in reg['projects']):
        add_project(root)
        reg = _load_registry()
    if reg['active'] != root:
        reg['active'] = root
        _save_registry(reg)


def get_active_project():
    active = _load_registry().get('active') or ''
    if active and Path(active).is_dir():
        return Path(active)
    return None


def resolve_project_root():
    env = os.environ.get('MAZE_PROJECT_ROOT')
    if env and Path(env).expanduser().is_dir():
        return Path(env).expanduser().resolve()
    return get_active_project()


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
