import json
import os
import platform
from pathlib import Path


SETTINGS_PATH = Path.home() / '.config' / 'mazehub' / 'settings.json'


def _ensure_dir():
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_settings():
    _ensure_dir()
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_settings(settings):
    _ensure_dir()
    try:
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def get_setting(key, default=None):
    return load_settings().get(key, default)


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
