import json
import os
import platform
import shutil
import sys
import threading
import time
from pathlib import Path


def _local_state_dir():
    """Per-user, per-device folder (not shared with the install)."""
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
        return Path(base) / 'MazeHub'
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(base) / 'mazehub'


def _is_writable_dir(path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f'.write_test_{os.getpid()}'
        probe.write_text('')
        probe.unlink()
        return True
    except OSError:
        return False


def _config_dir():
    override = os.environ.get('MAZE_CONFIG_DIR')
    if override:
        return Path(override)
    try:
        from pipeline_app import _app_dir
        app_dir = _app_dir()
    except Exception:
        return Path(__file__).resolve().parent
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        try:
            Path(app_dir).resolve().relative_to(Path(meipass).resolve())
        except ValueError:
            return app_dir
        # The one-file bundle's temp folder is deleted on exit, so settings and
        # the project list written there would be forgotten every launch.
        exe_side = Path(sys.executable).resolve().parent / 'mazehub'
        target = exe_side if _is_writable_dir(exe_side) else _local_state_dir()
        print(f'[settings] app folder is the temporary bundle ({app_dir}); '
              f'storing settings in {target}')
        return target
    return app_dir


CONFIG_DIR = _config_dir()
USER_SETTINGS_PATH = CONFIG_DIR / 'user_settings.json'
PROJECTS_PATH = CONFIG_DIR / 'projects.json'
PROJECTS_BACKUP_PATH = CONFIG_DIR / 'projects.json.bak'
LOCAL_STATE_PATH = _local_state_dir() / 'local_state.json'
_LEGACY_CONFIG_DIR = Path.home() / '.config' / 'mazehub'


class RegistryUnreadable(Exception):
    """projects.json exists but can't be read (locked by a sync client or
    another computer, half-synced, or corrupt). Callers must not treat this as
    an empty list: saving would overwrite every registered project."""

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
    'project_structure',
    'teams_webhook_url',
    'dailies_webhook_url',
    'production_webhook_url',
    'production_schedule_enabled',
    'production_schedule_url',
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


def _get_shared_settings_path(root=None):
    root = Path(root) if root else _get_project_root()
    if not root:
        return None
    path = root / 'mazehub' / 'shared_settings.json'
    legacy = root / 'pipeline' / 'mazehub' / 'shared_settings.json'
    if not path.exists() and legacy.exists():
        _migrate_legacy_shared(legacy, path)
    return path


def _read_json_strict(path, attempts=3, delay=0.3):
    """Parsed dict, {} if the file is absent. Retries briefly, then raises
    OSError/ValueError if it stays unreadable (locked, half-synced, corrupt)."""
    for attempt in range(attempts):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError('not a JSON object')
            return data
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _load_registry_file():
    try:
        data = _read_json_strict(PROJECTS_PATH)
        error = None
    except (OSError, ValueError) as e:
        data, error = None, e
    if data:
        return data
    # Unreadable, or missing/empty: the backup is the last list saved here.
    try:
        backup = _read_json_strict(PROJECTS_BACKUP_PATH, attempts=1)
    except (OSError, ValueError):
        backup = {}
    if backup.get('projects'):
        reason = f'unreadable ({error})' if error else 'missing or empty'
        print(f'[settings] {PROJECTS_PATH} {reason}; using {PROJECTS_BACKUP_PATH.name}')
        return backup
    if error is not None:
        raise RegistryUnreadable(f'{PROJECTS_PATH}: {error}')
    return data


def _load_registry():
    """Raises RegistryUnreadable rather than returning an empty list."""
    data = _load_registry_file()
    projects = [
        {'name': str(p.get('name') or Path(p['root']).name),
         'root': str(p['root'])}
        for p in data.get('projects', [])
        if isinstance(p, dict) and p.get('root')
    ]
    return {'projects': projects, 'active': str(data.get('active') or '')}


def _save_registry(reg):
    # Every caller built reg from _load_registry(), which raises when the file
    # can't be read, so an unreadable registry is never overwritten here.
    _save_json(PROJECTS_PATH, reg)
    _save_json(PROJECTS_BACKUP_PATH, reg)


def list_projects(strict=False):
    """Registered projects. With strict=False an unreadable registry gives []
    (for display); strict=True raises RegistryUnreadable."""
    try:
        return _load_registry()['projects']
    except RegistryUnreadable as e:
        if strict:
            raise
        print(f'[settings] could not read the project list: {e}')
        return []


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
    _set_last_project(root)


def _get_last_project():
    return str(_load_json(LOCAL_STATE_PATH).get('last_project') or '')


def _set_last_project(root):
    """This user's own last project. The shared 'active' in projects.json is
    whatever anyone last opened on any device, which may not exist here."""
    state = _load_json(LOCAL_STATE_PATH)
    if state.get('last_project') != root:
        state['last_project'] = root
        _save_json(LOCAL_STATE_PATH, state)


def get_active_project():
    active = _load_registry().get('active') or ''
    if active and Path(active).is_dir():
        return Path(active)
    return None


def _reachable(root):
    try:
        return Path(root).expanduser().is_dir()
    except OSError:
        return False


def _probe(roots, timeout):
    """{root: is_dir} for the checks that finish within timeout. A path on a
    dead network share can block for a long time, so each check runs in its
    own daemon thread and slow ones are simply left out."""
    results = {}

    def check(root):
        results[root] = _reachable(root)

    threads = [threading.Thread(target=check, args=(r,), daemon=True) for r in roots]
    for t in threads:
        t.start()
    end = time.monotonic() + timeout
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    return dict(results)


def resolve_project_root(wait=3.0):
    """The project to open at startup, or None.

    Order: MAZE_PROJECT_ROOT, this user's last project, the shared active
    project, then any other registered project. The first two get up to
    `wait` seconds in case their drive is still connecting; after that the
    first reachable registered project opens instead of the "add a project"
    prompt. Raises RegistryUnreadable if projects.json can't be read.
    """
    env = os.environ.get('MAZE_PROJECT_ROOT')
    if env and Path(env).expanduser().is_dir():
        return Path(env).expanduser().resolve()
    reg = _load_registry()
    registered = {p['root'] for p in reg['projects']}
    last = _get_last_project()
    if last not in registered:
        last = ''  # removed from the list since
    preferred = list(dict.fromkeys(r for r in (last, reg['active']) if r))
    candidates = preferred + [p['root'] for p in reg['projects'] if p['root'] not in preferred]
    if not candidates:
        return None
    reachable = set()
    deadline = time.monotonic() + wait
    while True:
        pending = [c for c in candidates if c not in reachable]
        remaining = deadline - time.monotonic()
        found = _probe(pending, max(0.5, min(1.5, remaining)))
        reachable.update(r for r, ok in found.items() if ok)
        for root in preferred:
            if root in reachable:
                if not last:
                    _set_last_project(root)
                return Path(root)
        if time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    for root in preferred:
        print(f'[settings] project not reachable: {root}')
    for root in candidates[len(preferred):]:
        if root in reachable:
            print(f'[settings] opening registered project {root} instead')
            return Path(root)
        print(f'[settings] project not reachable: {root}')
    return None


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


def _save_json(path, data, attempts=3, delay=0.3):
    if not path:
        return
    # Per-process temp name: several devices may share this folder.
    tmp = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    for attempt in range(attempts):
        try:
            _ensure_dir(path)
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
            # os.replace fails while a sync client or virus scanner holds the file.
            os.replace(tmp, path)
            return
        except Exception as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            if not isinstance(e, OSError) or attempt == attempts - 1:
                print(f'[settings] could not save {path}: {e}')
                return
            time.sleep(delay)


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
    for entry in list_projects():
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


def load_settings(root=None):
    """Load all settings (project at root + global)."""
    migrate_legacy_settings()
    shared = _load_json(_get_shared_settings_path(root))
    user = _load_json(USER_SETTINGS_PATH)
    return _merge_settings(shared, user)


def save_settings(settings, root=None):
    """Save settings, splitting into project (at root) and global files."""
    shared = {k: v for k, v in settings.items() if k in SHARED_KEYS}
    user = {k: v for k, v in settings.items() if k not in SHARED_KEYS}
    existing_shared = _load_json(_get_shared_settings_path(root))
    existing_shared.update(shared)
    existing_user = _load_json(USER_SETTINGS_PATH)
    existing_user.update(user)
    _save_json(_get_shared_settings_path(root), existing_shared)
    _save_json(USER_SETTINGS_PATH, existing_user)


def get_setting(key, default=None, root=None):
    settings = load_settings(root)
    return settings.get(key, default)


def set_setting(key, value, root=None):
    settings = load_settings(root)
    settings[key] = value
    save_settings(settings, root)


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
