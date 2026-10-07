import json
import os
import platform
import shutil
from pathlib import Path


def _config_dir():
    override = os.environ.get('MAZE_CONFIG_DIR')
    if override:
        return Path(override)
    try:
        from pipeline_app import _app_dir
        return _app_dir()
    except Exception:
        return Path(__file__).resolve().parent


CONFIG_DIR = _config_dir()
USER_SETTINGS_PATH = CONFIG_DIR / 'user_settings.json'
PROJECTS_PATH = CONFIG_DIR / 'projects.json'
_LEGACY_CONFIG_DIR = Path.home() / '.config' / 'mazehub'

_HOME_MIGRATED = False


def migrate_home_config(force=False):
    """One-time move of the legacy ~/.config/mazehub/{user_settings,projects}.json
    into the install config dir. First writer wins: an existing install copy is
    never overwritten, so every device converges on the shared files."""
    global _HOME_MIGRATED
    if _HOME_MIGRATED and not force:
        return
    _HOME_MIGRATED = True
    for name in ('user_settings.json', 'projects.json'):
        dest = CONFIG_DIR / name
        legacy = _LEGACY_CONFIG_DIR / name
        if dest.exists() or not legacy.exists():
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(legacy, dest)
        except OSError:
            pass


migrate_home_config()

# Keys scoped to the active project (stored in <project>/mazehub/shared_settings.json).
# Everything else is global and stored with the install (CONFIG_DIR/user_settings.json)
# so every device that can see the install sees the same settings.
SHARED_KEYS = {
    'teams_webhook_url',
    'dailies_webhook_url',
    'production_webhook_url',
}

# Formerly project-scoped; now global.
_MIGRATED_GLOBAL_KEYS = ('husk_path', 'yt_screensaver_url')

# Project settings files, oldest first so newer paths win on conflict.
_SHARED_FILE_RELS = (
    ('pipeline', 'mazehub', 'shared_settings.json'),
    ('mazehub', 'shared_settings.json'),
)


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
        tmp = path.with_name(path.name + '.tmp')
        try:
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _merge_settings(shared, user):
    """Merge shared and user settings (strict classification).

    Project-scoped keys are read only from the project file and global keys
    only from the user file, so webhook values left over in global settings
    are ignored and project copies of global keys are ignored too.
    """
    result = {k: v for k, v in user.items() if k not in SHARED_KEYS}
    result.update({k: v for k, v in shared.items() if k in SHARED_KEYS})
    return result


_MIGRATED = False


def migrate_legacy_settings(force=False):
    """One-time cleanup: move husk_path/yt_screensaver_url from project
    files into global per-device settings and strip them from projects."""
    global _MIGRATED
    if _MIGRATED and not force:
        return
    _MIGRATED = True
    active = _get_project_root()
    active_shared = {}
    if active:
        for rel in _SHARED_FILE_RELS:
            active_shared.update(_load_json(active.joinpath(*rel)))
    user = _load_json(USER_SETTINGS_PATH)
    changed = False
    for key in _MIGRATED_GLOBAL_KEYS:
        value = active_shared.get(key)
        if value and user.get(key) != value:
            user[key] = value
            changed = True
    if changed:
        _save_json(USER_SETTINGS_PATH, user)
    roots = {str(active)} if active else set()
    for entry in _load_registry()['projects']:
        roots.add(entry['root'])
    for root in roots:
        for rel in _SHARED_FILE_RELS:
            path = Path(root).joinpath(*rel)
            data = _load_json(path)
            if not data:
                continue
            removed = False
            for key in _MIGRATED_GLOBAL_KEYS:
                if key in data:
                    del data[key]
                    removed = True
            if removed:
                _save_json(path, data)


def load_settings():
    """Load all settings (project + global)."""
    migrate_legacy_settings()
    shared = _load_json(_get_shared_settings_path())
    user = _load_json(USER_SETTINGS_PATH)
    return _merge_settings(shared, user)


def save_settings(settings):
    """Save settings, splitting into project and global files."""
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
