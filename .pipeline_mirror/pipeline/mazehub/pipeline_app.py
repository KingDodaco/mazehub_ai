import os
import sys
import re
import json
import subprocess
import platform
import urllib.request
from pathlib import Path

APP_VERSION = "0.12.2"


def _get_display_name():
    if platform.system() == 'Windows':
        try:
            import ctypes
            import ctypes.wintypes
            size = ctypes.wintypes.DWORD()
            ctypes.windll.secur32.GetUserNameExW(3, None, ctypes.byref(size))
            if size.value > 0:
                buf = ctypes.create_unicode_buffer(size.value)
                ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size))
                if buf.value:
                    return buf.value
        except Exception:
            pass
        return os.environ.get('USERNAME', 'unknown')
    return os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))


def convert_exr_to_png(exr_path, png_path, max_size=512):
    try:
        import OpenEXR
        import Imath
    except ImportError:
        return False
    try:
        from PIL import Image
        import numpy as np

        exr = OpenEXR.InputFile(str(exr_path))
        header = exr.header()
        dw = header['dataWindow']
        width = dw.max.x - dw.min.x + 1
        height = dw.max.y - dw.min.y + 1

        channel_names = list(header['channels'].keys())
        if 'A' in channel_names:
            channels = ['R', 'G', 'B', 'A']
        elif all(c in channel_names for c in ['R', 'G', 'B']):
            channels = ['R', 'G', 'B']
        elif len(channel_names) >= 3:
            channels = channel_names[:3]
        else:
            channels = channel_names[:1]

        pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)
        channel_data = []
        for ch in channels:
            raw = exr.channel(ch, pixel_type)
            arr = np.frombuffer(raw, dtype=np.float32)
            channel_data.append(arr.reshape(height, width))
        exr.close()

        img_array = np.stack(channel_data, axis=-1)
        img_array = np.clip(img_array, 0, None)

        # Apply sRGB OETF (linear to sRGB)
        srgb = np.where(
            img_array <= 0.0031308,
            img_array * 12.92,
            1.055 * np.power(img_array, 1.0 / 2.4) - 0.055
        )
        srgb = np.clip(srgb, 0, 1)
        img_array = (srgb * 255).astype(np.uint8)

        if img_array.shape[-1] == 4:
            img = Image.fromarray(img_array, 'RGBA')
        else:
            img = Image.fromarray(img_array[:, :, :3], 'RGB')

        if max(width, height) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)

        img.save(str(png_path), 'PNG')
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


APP_FILE_EXTENSIONS = {
    'Houdini': ['.hip', '.hipnc', '.hiplc'],
    'NukeX': ['.nk'],
    'Maya': ['.ma', '.mb'],
    'Blender': ['.blend'],
    'Mari': ['.mri', '.mra', '.mfb'],
    'SubstancePainter': ['.spp'],
    'Zbrush': ['.ztl', '.zbp'],
    'Photoshop': ['.psd', '.psb'],
    'USD': ['.usd', '.usda', '.usdc', '.usdz'],
}


def _version_key(text):
    parts = []
    for chunk in str(text or '').strip().lstrip('vV').replace('-', '.').replace('+', '.').split('.'):
        digits = ''
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def _tree_version(path):
    try:
        text = (path / 'pipeline_app.py').read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None
    match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return match.group(1) if match else None


def _app_dir():
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, '_MEIPASS', '')) if getattr(sys, '_MEIPASS', '') else None
        candidates = [
            exe_dir / 'mazehub',
            exe_dir / 'pipeline' / 'mazehub',
            exe_dir / '_internal' / 'pipeline' / 'mazehub',
            exe_dir / '_internal' / 'mazehub',
            exe_dir,
        ]
        if meipass:
            candidates += [
                meipass / 'pipeline' / 'mazehub',
                meipass / 'mazehub',
            ]
        valid = [p for p in candidates
                 if p.exists() and (p / 'pipeline_app.py').exists()
                 and (p / 'pipeline_gui.py').exists()]
        best = None
        best_version = None
        for p in valid:
            version = _version_key(_tree_version(p))
            if best is None or version > best_version:
                best = p
                best_version = version
        if best is not None:
            return best
        return exe_dir
    return Path(__file__).resolve().parent


def find_pipeline_dir():
    app_dir = _app_dir()
    if app_dir.name == 'mazehub':
        app_dir = app_dir.parent
    if getattr(sys, 'frozen', False):
        meipass = Path(getattr(sys, '_MEIPASS', '')) if getattr(sys, '_MEIPASS', '') else None
        if meipass:
            try:
                app_dir.resolve().relative_to(meipass.resolve())
                return Path(sys.executable).resolve().parent
            except ValueError:
                pass
    return app_dir


def find_project_root():
    from settings import resolve_project_root
    resolved = resolve_project_root()
    if resolved:
        return resolved

    if getattr(sys, 'frozen', False):
        return None

    this_dir = _app_dir()

    for parent in [this_dir] + list(this_dir.parents):
        root_marker = parent / 'pipeline' / 'mazehub' / 'apps.json'
        mirror_marker = parent / '.pipeline_mirror' / 'pipeline' / 'mazehub' / 'apps.json'
        if root_marker.exists() or mirror_marker.exists():
            return parent

    if this_dir.name == 'mazehub' and this_dir.parent.name == 'pipeline':
        return this_dir.parent.parent

    return this_dir


SHOT_META_FILENAME = '_metadata.json'

DEFAULT_SHOT_META = {
    'frame_range': '1001-1240',
    'frame_rate': '24',
    'date': '',
    'focal_length': '50mm',
    'iso': '800',
    'nd_filter': '6',
    'light_rig': '',
    'description': '',
}


def read_shot_meta(shot_path):
    meta_path = Path(shot_path) / SHOT_META_FILENAME
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                stored = json.load(f)
        except (OSError, ValueError):
            stored = {}
        if isinstance(stored, dict):
            result = dict(DEFAULT_SHOT_META)
            result.update(stored)
            return result
    return dict(DEFAULT_SHOT_META)


def write_shot_meta(shot_path, metadata):
    meta_path = Path(shot_path) / SHOT_META_FILENAME
    clean = {k: metadata.get(k, '') for k in DEFAULT_SHOT_META}
    with open(meta_path, 'w') as f:
        json.dump(clean, f, indent=2)


LIGHT_RIG_META_FILENAME = '_metadata.json'

DEFAULT_LIGHT_RIG_META = {
    'name': '',
    'date': '',
    'time_of_day': '',
    'lighting_description': '',
    'hdri_path': '',
    'photogrammetry_path': '',
    'usd_scene_path': '',
    'nuke_path': '',
    'houdini_path': '',
}


def read_light_rig_meta(rig_path):
    meta_path = Path(rig_path) / LIGHT_RIG_META_FILENAME
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                stored = json.load(f)
        except (OSError, ValueError):
            stored = {}
        if isinstance(stored, dict):
            result = dict(DEFAULT_LIGHT_RIG_META)
            result.update(stored)
            return result
    return dict(DEFAULT_LIGHT_RIG_META)


def write_light_rig_meta(rig_path, metadata):
    meta_path = Path(rig_path) / LIGHT_RIG_META_FILENAME
    clean = {k: metadata.get(k, '') for k in DEFAULT_LIGHT_RIG_META}
    with open(meta_path, 'w') as f:
        json.dump(clean, f, indent=2)


def list_light_rigs(project_root):
    lightrigs_dir = Path(project_root) / 'lightrigs'
    if not lightrigs_dir.exists():
        return []
    return sorted([
        d.name for d in lightrigs_dir.iterdir()
        if d.is_dir() and not d.name.startswith('_')
    ])


ASSET_META_FILENAME = '_metadata.json'

DEFAULT_ASSET_META = {
    'display_name': '',
    'folder_name': '',
}


def read_asset_meta(asset_path):
    meta_path = Path(asset_path) / ASSET_META_FILENAME
    if meta_path.exists():
        with open(meta_path) as f:
            stored = json.load(f)
            result = dict(DEFAULT_ASSET_META)
            result.update(stored)
            return result
    name = Path(asset_path).name
    return {'display_name': name, 'folder_name': name}


def write_asset_meta(asset_path, metadata):
    meta_path = Path(asset_path) / ASSET_META_FILENAME
    clean = {k: metadata.get(k, '') for k in DEFAULT_ASSET_META}
    with open(meta_path, 'w') as f:
        json.dump(clean, f, indent=2)


PRODUCTION_FILENAME = '_production.json'

PRODUCTION_STATUSES = ['Not started', 'Work in progress', 'Pending review', 'Finished']
PRODUCTION_VALUES = {'Not started': 0, 'Work in progress': 50, 'Pending review': 50, 'Finished': 100}

ASSET_CATEGORIES = {
    'Modelling': 'core',
    'Texturing': 'core',
    'Lookdev': 'core',
    'Rigging': 'optional',
    'Groom': 'optional',
    'FX Prep': 'optional',
}

SHOT_CATEGORIES = ['Tracking', 'Paint & Roto', 'Animation', 'FX', 'Lighting', 'Rendering', 'Compositing', 'Colour Grading']


def read_production(item_path):
    prod_path = Path(item_path) / PRODUCTION_FILENAME
    if prod_path.exists():
        with open(prod_path, 'r') as f:
            return json.load(f)
    return {}


def write_production(item_path, data):
    prod_path = Path(item_path) / PRODUCTION_FILENAME
    with open(prod_path, 'w') as f:
        json.dump(data, f, indent=2)


def production_score(data):
    values = [PRODUCTION_VALUES.get(v, 0) for v in data.values() if v != 'Not applicable']
    if not values:
        return ''
    return f'{round(sum(values) / len(values))}%'


def _env_ref(root_var):
    if platform.system() == 'Windows':
        return f'%{root_var}%'
    return f'${root_var}'


def _resolve_ref(value, project_root):
    if platform.system() == 'Windows':
        expanded = value.replace(f'%MAZE_PROJECT_ROOT%', str(project_root))
    else:
        expanded = value.replace(f'$MAZE_PROJECT_ROOT', str(project_root))
    # Normalize path separators
    expanded = expanded.replace('/', os.sep).replace('\\', os.sep)
    return expanded


def setup_environment(project_root, pipeline_dir=None):
    if pipeline_dir is None:
        pipeline_dir = find_pipeline_dir()
    root = str(Path(project_root))
    ROOT_VAR = 'MAZE_PROJECT_ROOT'
    ref = _env_ref(ROOT_VAR)
    project_pipeline = Path(root) / 'pipeline'

    ref_vars = {
        ROOT_VAR: root,
        'MZE': root,
        'MAZE_PROJECT': Path(root).name,
        'MAZE_PIPELINE': str(Path(pipeline_dir)),
        'MAZE_PROJECT_PIPELINE': (
            str(project_pipeline) if project_pipeline.is_dir() else ''),
        'MAZE_ASSETS': f'{ref}/asset',
        'MAZE_SEQUENCES': f'{ref}/sequence',
        'MAZE_ONSET': f'{ref}/onset',
        'MAZE_IO': f'{ref}/IO',
        'MAZE_DEVELOPMENT': f'{ref}/development',
        'MAZE_RND': f'{ref}/rnd',
        'MAZE_MISC': f'{ref}/MISC',
    }

    for key, value in ref_vars.items():
        resolved = _resolve_ref(value, project_root) if key != ROOT_VAR else value
        os.environ[key] = resolved

    return ref_vars


APP_CONTEXT_ENV = {
    'Houdini': {
        'HOUDINI_JOB': '{context_path}/houdini',
        'JOB': '{context_path}/houdini',
    },
    'Maya': {
        'MAYA_PROJECT': '{context_path}/maya',
    },
    'NukeX': {},
    'Blender': {},
    'Mari': {},
    'SubstancePainter': {},
    'Zbrush': {},
    'Photoshop': {},
    'USD': {},
}


def _parse_frame_range(value):
    parts = str(value or '').split('-')
    if len(parts) < 2:
        return '', ''
    try:
        return str(int(float(parts[0].strip()))), str(int(float(parts[1].strip())))
    except ValueError:
        return '', ''


def _parse_frame_rate(value):
    try:
        fps = int(round(float(str(value).strip())))
    except ValueError:
        return ''
    return str(fps) if fps > 0 else ''


def build_context_env(context, project_root, pipeline_dir=None):
    if not context:
        return {}
    if pipeline_dir is None:
        pipeline_dir = find_pipeline_dir()
    ctx_path = Path(context['path'])
    project_pipeline = Path(project_root) / 'pipeline'
    env = {
        'MAZE_CONTEXT_TYPE': context['type'],
        'MAZE_CONTEXT_NAME': context['name'],
        'MAZE_CONTEXT_PATH': str(ctx_path),
        'PIPELINE_DIR': str(Path(pipeline_dir)),
        'MAZE_PROJECT_PIPELINE': (
            str(project_pipeline) if project_pipeline.is_dir() else ''),
        'START_FRAME': '',
        'END_FRAME': '',
        'FRAME_RATE': '',
        'MAZE_LIGHT_RIG_HDRI': '',
        'MAZE_LIGHT_RIG_PHOTOGRAWMETRY': '',
        'MAZE_LIGHT_RIG_USD': '',
        'MAZE_LIGHT_RIG_NUKE': '',
        'MAZE_LIGHT_RIG_HOUDINI': '',
    }

    if context['type'] == 'shot':
        meta = read_shot_meta(ctx_path)
        env['START_FRAME'], env['END_FRAME'] = _parse_frame_range(
            meta.get('frame_range', ''))
        env['FRAME_RATE'] = _parse_frame_rate(meta.get('frame_rate', ''))
    elif context['type'] == 'light_rig':
        meta = read_light_rig_meta(ctx_path)
        env['MAZE_LIGHT_RIG_HDRI'] = meta.get('hdri_path', '')
        env['MAZE_LIGHT_RIG_PHOTOGRAWMETRY'] = meta.get('photogrammetry_path', '')
        env['MAZE_LIGHT_RIG_USD'] = meta.get('usd_scene_path', '')
        env['MAZE_LIGHT_RIG_NUKE'] = meta.get('nuke_path', '')
        env['MAZE_LIGHT_RIG_HOUDINI'] = meta.get('houdini_path', '')

    env['JOB'] = str(ctx_path)
    env['HOUDINI_JOB'] = str(ctx_path)

    app_env = APP_CONTEXT_ENV.get(context.get('app_name', ''), {})
    for key, template in app_env.items():
        resolved = template.format(
            context_path=str(ctx_path),
            project_root=str(project_root),
        )
        env[key] = resolved
    return env


def load_apps_config():
    config_path = _app_dir() / 'apps.json'
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def save_apps_config(config):
    config_path = _app_dir() / 'apps.json'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)


def resolve_app_exe(config, version_key=None):
    """Resolve the exe path for an app config, using the given version or the default."""
    versions = config.get('versions', {})
    if not versions:
        return ''
    if version_key and version_key in versions:
        ver = versions[version_key]
        return ver.get('exe', '') if isinstance(ver, dict) else ''
    default = config.get('default_version', '')
    if default and default in versions:
        ver = versions[default]
        return ver.get('exe', '') if isinstance(ver, dict) else ''
    first = next(iter(versions.values()))
    return first.get('exe', '') if isinstance(first, dict) else ''


def _houdini_install_dirs(ver=''):
    system = platform.system()
    roots = []
    if system == 'Windows':
        for base in (os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                     os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')):
            sidefx = Path(base) / 'Side Effects Software'
            if sidefx.is_dir():
                roots.append(sidefx)
    elif system == 'Darwin':
        roots.append(Path('/Applications'))
    else:
        roots.extend([Path('/opt'), Path('/usr/local')])

    if system in ('Windows', 'Darwin'):
        patterns = ([f'Houdini {ver}*'] if ver else []) + ['Houdini*']
    else:
        patterns = ([f'hfs{ver}*', f'houdini{ver}*'] if ver else []) + ['hfs*', 'houdini*']

    seen = set()
    dirs = []
    for pattern in patterns:
        for root in roots:
            try:
                hits = sorted(root.glob(pattern), reverse=True)
            except OSError:
                hits = []
            for d in hits:
                if d not in seen:
                    seen.add(d)
                    dirs.append(d)
    return dirs


def resolve_mplay(config):
    """Locate mplay for the default Houdini installation in an app config.

    Order: mplay next to the default version's exe, then the default
    version's install folder, then any installed Houdini, then $HFS."""
    name = 'mplay.exe' if platform.system() == 'Windows' else 'mplay'
    exe = resolve_app_exe(config)
    if exe:
        candidate = Path(exe).parent / name
        if candidate.exists():
            return str(candidate)
    versions = config.get('versions', {}) or {}
    ver = config.get('default_version', '') or next(iter(versions), '')
    for d in _houdini_install_dirs(ver):
        if platform.system() == 'Darwin':
            candidate = d / 'Frameworks' / 'Houdini.framework' / 'Versions' / 'Current' / 'Resources' / 'bin' / name
        else:
            candidate = d / 'bin' / name
        if candidate.exists():
            return str(candidate)
    hfs = os.environ.get('HFS')
    if hfs:
        candidate = Path(hfs) / 'bin' / name
        if candidate.exists():
            return str(candidate)
    return ''


def list_apps(apps_config):
    if not apps_config:
        print('  No applications configured.')
        return
    print()
    for name, cfg in apps_config.items():
        print(f'    {name:20s}  {cfg["display_name"]}')


def launch_app(apps_config, app_name, pipeline_dir):
    cfg = apps_config.get(app_name)
    if not cfg:
        print(f'  Unknown application: {app_name}')
        return

    exec_path = pipeline_dir / cfg['subdir'] / cfg['executable']
    if not exec_path.exists():
        print(f'  Executable not found: {exec_path}')
        return

    print(f'  Launching {cfg["display_name"]}...')
    try:
        if platform.system() == 'Windows':
            subprocess.Popen([str(exec_path)], shell=True)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', str(exec_path)])
        else:
            subprocess.Popen(['xdg-open', str(exec_path)])
    except Exception as e:
        print(f'  Failed to launch: {e}')


def find_project_files(project_root, apps_config):
    results = {}
    for app_name in apps_config:
        extensions = APP_FILE_EXTENSIONS.get(app_name, [])
        if not extensions:
            continue
        found = set()
        for ext in extensions:
            for f in sorted(project_root.rglob(f'*{ext}')):
                parts = f.relative_to(project_root).parts
                if any(p.startswith('.') or p == '__pycache__' or p == '.venv' for p in parts):
                    continue
                found.add(f)
        if found:
            results[app_name] = sorted(found)[:20]
    return results


USD_EXTENSIONS = {'.usd', '.usda', '.usdc'}


def discover_usd_files(shot_path):
    usd_dir = Path(shot_path) / 'houdini' / 'USD'
    if not usd_dir.exists():
        return []
    return sorted(
        f for f in usd_dir.iterdir()
        if f.is_file() and f.suffix.lower() in USD_EXTENSIONS
    )


IMAGE_EXTENSIONS = {'.exr', '.png', '.tiff', '.tif', '.jpeg', '.jpg', '.dpx', '.pic', '.mov', '.mp4'}
VIDEO_EXTENSIONS = {'.mov', '.mp4'}


def _clean_stem(stem):
    removed = []
    m = re.search(r'[\s_-]*WINDOWS-[A-Za-z0-9]+', stem)
    if m:
        removed.append(m.group().lstrip(' _-'))
    stem = re.sub(r'[\s_-]*WINDOWS-[A-Za-z0-9]+', '', stem)
    m = re.search(r'[\s_-]*MAC-[A-Za-z0-9]+', stem)
    if m:
        removed.append(m.group().lstrip(' _-'))
    stem = re.sub(r'[\s_-]*MAC-[A-Za-z0-9]+', '', stem)
    m = re.search(r'[\s_-]*Linux-[A-Za-z0-9]+', stem)
    if m:
        removed.append(m.group().lstrip(' _-'))
    stem = re.sub(r'[\s_-]*Linux-[A-Za-z0-9]+', '', stem)
    m = re.search(r'[\s_-]*[A-Za-z0-9]{8,}$', stem)
    if m:
        removed.append(m.group().lstrip(' _-'))
    stem = re.sub(r'[\s_-]*[A-Za-z0-9]{8,}$', '', stem)
    stem = stem.rstrip(' -_')
    return stem, removed


def _normalize_stem(stem):
    stem, _ = _clean_stem(stem)
    stem = re.sub(r'_\d{4,}$', '', stem)
    stem = stem.rstrip('_')
    return stem


def _normalize_stem_nuke(stem):
    stem, _ = _clean_stem(stem)
    stem = re.sub(r'\.\d{4,}$', '', stem)
    stem = re.sub(r'_\d{4,}$', '', stem)
    stem = stem.rstrip('_')
    return stem


def _extract_prefix(stem):
    m = re.match(r'^(.*?)_\d{4,}$', stem)
    if m:
        return m.group(1) + '_'
    return stem + '_'


def discover_image_sequences(shot_path):
    render_subdirs = [
        ('houdini', Path(shot_path) / 'houdini' / 'render'),
        ('blender', Path(shot_path) / 'blender' / 'render'),
        ('maya', Path(shot_path) / 'maya' / 'images'),
        ('nuke', Path(shot_path) / 'nuke' / 'render'),
    ]
    from collections import defaultdict
    sequences = defaultdict(list)
    software_map = {}
    FORMAT_DIRS = {'exr', 'png', 'jpg', 'jpeg', 'tiff', 'tif', 'dpx', 'pic'}
    for software, render_dir in render_subdirs:
        if not render_dir.exists():
            continue
        for f in render_dir.rglob('*'):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                sequences[f.parent].append(f)
                software_map[f.parent] = software
    merged = defaultdict(list)
    merged_software = {}
    for folder, files in sequences.items():
        if folder.name.lower() in FORMAT_DIRS and folder.parent is not None:
            key = folder.parent
        else:
            key = folder
        merged[key].extend(files)
        merged_software[key] = software_map.get(folder, 'unknown')
    sequences = merged
    software_map = merged_software
    results = []
    for folder in sorted(sequences):
        files = sorted(sequences[folder])
        rel = folder.relative_to(shot_path)
        software = software_map.get(folder, rel.parts[0] if rel.parts else 'unknown')
        version = None
        for part in rel.parts:
            m = re.search(r'_v(\d+)', part)
            if m:
                version = f'v{m.group(1)}'
                break
        if version is None:
            for f in files:
                m = re.search(r'_v(\d+)', f.stem)
                if m:
                    version = f'v{m.group(1)}'
                    break
        if version is None:
            version = ''
        video_files = [f for f in files if f.suffix.lower() in VIDEO_EXTENSIONS]
        for f in video_files:
            _, removed = _clean_stem(f.stem)
            v_warn = None
            if removed:
                v_warn = 'Duplicate files detected'
            file_version = version
            m = re.search(r'_v(\d+)', f.stem)
            if m:
                file_version = f'v{m.group(1)}'
            v_display = f.stem
            v_display = re.sub(r'_v\d+', '', v_display).rstrip('_')
            if not v_display:
                v_display = folder.name
            results.append({
                'pattern': str(f),
                'prefix': v_display,
                'folder': folder,
                'software': software,
                'version': file_version,
                'format': f.suffix.lstrip('.').upper(),
                'count': 1,
                'pad': 0,
                'first_frame': f.name,
                'last_frame': f.name,
                'warning': v_warn,
            })
        files = [f for f in files if f.suffix.lower() not in VIDEO_EXTENSIONS]
        if len(files) < 2:
            continue
        raw_stems = [f.stem for f in files]
        if software == 'nuke':
            cleaned = [_normalize_stem_nuke(s) for s in raw_stems]
        else:
            cleaned = [_normalize_stem(s) for s in raw_stems]
        unique = sorted(set(cleaned))
        ext = files[0].suffix
        groups = defaultdict(list)
        removed_by_group = defaultdict(list)
        all_digits = all(re.match(r'^\d+$', s) for s in cleaned)
        has_mixed_exts = len(set(f.suffix for f in files)) > 1
        for s, f in zip(cleaned, files):
            _, removed = _clean_stem(f.stem)
            if all_digits:
                group_key = ('', f.suffix) if has_mixed_exts else ''
            else:
                group_key = (s, f.suffix) if has_mixed_exts else s
            groups[group_key].append(f)
            removed_by_group[group_key].append((f, tuple(removed)))
        for group_key, group_files in sorted(groups.items()):
            if len(group_files) < 2:
                continue
            norm_stem = group_key[0] if isinstance(group_key, tuple) else group_key
            ext = group_key[1] if isinstance(group_key, tuple) else files[0].suffix
            prefix = _extract_prefix(norm_stem) if not all_digits else ''
            raw = group_files[0].stem
            frame_match = re.search(r'(\d{4,})$', raw)
            pad = len(frame_match.group(1)) if frame_match else 4
            if all_digits:
                display = folder.name
            else:
                display = prefix.rstrip('_')
                display = re.sub(r'_v\d+', '', display).rstrip('_')
                if not display:
                    display = folder.name
            has_mixed_exts_in_group = len(set(f.suffix for f in group_files)) > 1
            removed_map = dict(removed_by_group[group_key])
            ext_groups = defaultdict(list)
            for f in group_files:
                ext_groups[f.suffix.lstrip('.')].append(f)
            has_format_variants = len(ext_groups) > 1
            has_removed_conflicts = False
            for ext_key, ext_files in ext_groups.items():
                ext_removed = set(removed_map.get(f, ()) for f in ext_files)
                non_empty = [r for r in ext_removed if r]
                if non_empty and len(ext_removed) > 1:
                    has_removed_conflicts = True
            if has_format_variants:
                variant_groups = defaultdict(list)
                for f in group_files:
                    ext_key = f.suffix.lstrip('.')
                    variant_groups[ext_key].append(f)
                for ext_key in sorted(variant_groups.keys()):
                    vf = variant_groups[ext_key]
                    v_warning = None
                    ext_removed = set(removed_map.get(f, ()) for f in vf)
                    non_empty = [r for r in ext_removed if r]
                    if non_empty and len(ext_removed) > 1:
                        v_warning = 'Duplicate files detected'
                    sorted_vf = sorted(vf, key=lambda f: f.stem)
                    results.append({
                        'prefix': display,
                        'folder': folder,
                        'software': software,
                        'version': version,
                        'format': ext_key.upper(),
                        'count': len(vf),
                        'pad': pad,
                        'first_frame': sorted_vf[0].name,
                        'last_frame': sorted_vf[-1].name,
                        'warning': v_warning,
                    })
            elif has_removed_conflicts:
                rm_groups = defaultdict(list)
                for f in group_files:
                    rm_key = removed_map.get(f, ())
                    rm_groups[rm_key].append(f)
                for rm_key in sorted(rm_groups.keys()):
                    rf = rm_groups[rm_key]
                    sorted_rf = sorted(rf, key=lambda f: f.stem)
                    fmt = rf[0].suffix.lstrip('.').upper()
                    results.append({
                        'prefix': display,
                        'folder': folder,
                        'software': software,
                        'version': version,
                        'format': fmt,
                        'count': len(rf),
                        'pad': pad,
                        'first_frame': sorted_rf[0].name,
                        'last_frame': sorted_rf[-1].name,
                        'warning': None,
                    })
            else:
                sorted_gf = sorted(group_files, key=lambda f: f.stem)
                fmt = group_files[0].suffix.lstrip('.').upper()
                results.append({
                    'prefix': display,
                    'folder': folder,
                    'software': software,
                    'version': version,
                    'format': fmt,
                    'count': len(group_files),
                    'pad': pad,
                    'first_frame': sorted_gf[0].name,
                    'last_frame': sorted_gf[-1].name,
                    'warning': None,
                })
    return results


def _subprocess_flags():
    """Spawn child processes without flashing console windows."""
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NO_WINDOW}
    return {'start_new_session': True}


def discover_husk_passes(husk_path, usd_file):
    if not husk_path or not Path(husk_path).exists():
        return [], ''
    try:
        usd_file = Path(usd_file)
        if not sync_file(usd_file):
            return [], f'USD file is missing or did not sync: {usd_file}'

        result = subprocess.run(
            [husk_path, '--list-passes', str(usd_file)],
            capture_output=True, text=True, timeout=30,
            **_subprocess_flags(),
        )
        output = (result.stdout or '') + '\n' + (result.stderr or '')
        passes = []
        for line in output.splitlines():
            cleaned = re.sub(r'\[\d{2}:\d{2}:\d{2}\]\s*', '', line).strip()
            if not cleaned:
                continue
            if any(cleaned.lower().startswith(p) for p in ('error', 'warning', 'fatal', 'failed')):
                continue
            for part in cleaned.split():
                if part.startswith('/') and len(part) > 1:
                    passes.append(part)
        return passes, output
    except subprocess.TimeoutExpired as e:
        return [], f'husk pass discovery timed out: {e}'
    except Exception as e:
        return [], f'husk pass discovery failed: {e}'


def is_usd_ascii(usd_file):
    try:
        with open(usd_file, 'r', errors='ignore') as f:
            return f.read(8).startswith('#usda')
    except Exception:
        return False


USD_ASSET_ENDINGS = (
    '.vdb', '.usd', '.usda', '.usdc', '.usdz',
    '.bgeo', '.bgeo.sc', '.bgeo.lc', '.bgeo.nc',
    '.abc', '.obj', '.fbx', '.pyro',
    '.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.dpx',
    '.tx', '.rat', '.mov', '.mp4',
    '.hip', '.hipnc', '.hiplc', '.ma', '.mb', '.blend', '.nk',
)
USD_LAYER_ENDINGS = ('.usd', '.usda', '.usdc', '.usdz')
USD_TOKEN_RE = re.compile(r'<(UDIM|F\d*|face|frame)>', re.IGNORECASE)
# Also matches '#' frame runs used by value-clip templateAssetPath ("clip.#.usd").
USD_PATTERN_RE = re.compile(r'<(UDIM|F\d*|face|frame)>|(#+)', re.IGNORECASE)
USD_STATIC_VDB_RE = re.compile(r'asset\s+filePath\s*=\s*@([^@\n]+\.vdb)@', re.IGNORECASE)


def _ref_looks_like_asset(path_str):
    low = str(path_str).lower()
    return any(low.endswith(e) for e in USD_ASSET_ENDINGS)


def _is_usd_layer_name(path_str):
    low = str(path_str).lower()
    return any(low.endswith(e) for e in USD_LAYER_ENDINGS)


def _usd_token_regex(name):
    if name.startswith('#'):
        return r'\d+'
    if name.upper() == 'UDIM':
        return r'\d{4}'
    return r'\d+'


def _extract_refs_from_text(text):
    refs = set()
    for token in re.findall(r'@([^@\n]+?)@', text):
        token = token.strip()
        if not token or token.startswith('<'):
            continue
        if token.startswith('/') and not _ref_looks_like_asset(token):
            continue
        if _ref_looks_like_asset(token) or USD_TOKEN_RE.search(token):
            refs.add(token)
    for token in re.findall(r'"([^"\n]+)"', text):
        token = token.strip()
        if not token:
            continue
        if _ref_looks_like_asset(token) or USD_TOKEN_RE.search(token):
            refs.add(token)
    return refs


def _houdini_bin_dirs(husk_path=None):
    dirs = []
    if husk_path:
        dirs.append(Path(husk_path).parent)
    try:
        from settings import find_husk
        husk = find_husk()
        if husk and Path(husk).parent not in dirs:
            dirs.append(Path(husk).parent)
    except Exception:
        pass
    return dirs


def _find_houdini_tool(tool, husk_path=None):
    names = (f'{tool}.exe', f'{tool}.cmd', f'{tool}.bat', tool)
    for bin_dir in _houdini_bin_dirs(husk_path):
        for name in names:
            candidate = bin_dir / name
            if candidate.is_file():
                return str(candidate)
    import shutil
    return shutil.which(tool)


def _find_usdcat(husk_path=None):
    return _find_houdini_tool('usdcat', husk_path)


def _hython_to_text(usd_file, husk_path=None):
    hython = _find_houdini_tool('hython', husk_path)
    if not hython:
        return None
    script = (
        'import sys\n'
        'from pxr import Sdf\n'
        'layer = Sdf.Layer.FindOrOpen(sys.argv[1])\n'
        'sys.stdout.write(layer.ExportToString() if layer else "")\n'
    )
    try:
        result = subprocess.run(
            [hython, '-c', script, str(usd_file)],
            capture_output=True, text=True, timeout=180,
            **_subprocess_flags(),
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass
    return None


def _usdcat_to_text(usd_file, husk_path=None):
    import tempfile
    usdcat = _find_usdcat(husk_path)
    if not usdcat:
        return None
    try:
        result = subprocess.run(
            [usdcat, str(usd_file), '--stdout'],
            capture_output=True, text=True, timeout=60,
            **_subprocess_flags(),
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix='.usda')
        os.close(fd)
        result = subprocess.run(
            [usdcat, str(usd_file), '-o', tmp_path],
            capture_output=True, text=True, timeout=60,
            **_subprocess_flags(),
        )
        if result.returncode == 0:
            return Path(tmp_path).read_text(errors='ignore')
    except Exception:
        pass
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return None


def _read_usd_text(usd_file, husk_path=None):
    ext = usd_file.suffix.lower()
    if ext == '.usda' or is_usd_ascii(usd_file):
        try:
            return usd_file.read_text(errors='ignore')
        except OSError:
            return None
    if ext in ('.usdc', '.usd', '.usdz'):
        try:
            from pxr import Sdf
            layer = Sdf.Layer.FindOrOpen(str(usd_file))
            if layer:
                return layer.ExportToString()
        except Exception:
            pass
        return _usdcat_to_text(usd_file, husk_path) or _hython_to_text(usd_file, husk_path)
    return None


def parse_usd_references(usd_file, _visited=None, _depth=0, husk_path=None, report=None):
    """Recursively collect asset paths referenced by a USD layer.

    If report is a dict, it collects 'unreadable_layers', 'static_volumes'
    and 'has_clips' for diagnostics.
    """
    usd_file = Path(usd_file)
    if _visited is None:
        _visited = set()
    if _depth > 8:
        return []
    try:
        key = str(usd_file.resolve())
    except OSError:
        key = str(usd_file)
    if key in _visited:
        return []
    _visited.add(key)
    if not usd_file.exists() or not usd_file.is_file():
        return []
    # A cloud placeholder of the layer itself would otherwise parse as empty.
    if needs_sync(usd_file):
        sync_file(usd_file)
    text = _read_usd_text(usd_file, husk_path)
    if not text:
        if report is not None:
            report.setdefault('unreadable_layers', []).append(str(usd_file))
        return []
    if report is not None:
        if 'templateAssetPath' in text or 'clipSets' in text:
            report['has_clips'] = True
        if 'filePath.timeSamples' not in text:
            for vdb in USD_STATIC_VDB_RE.findall(text):
                vdb_path = _expand_ref_path(vdb.strip())
                if not os.path.isabs(vdb_path):
                    vdb_path = str(usd_file.parent / vdb_path)
                report.setdefault('static_volumes', []).append(vdb_path)
    refs = _extract_refs_from_text(text)
    all_refs = set()
    anchor = usd_file.parent
    for ref in refs:
        all_refs.add(ref)
        if not _is_usd_layer_name(ref):
            continue
        child_str = _expand_ref_path(ref)
        if USD_PATTERN_RE.search(child_str):
            children = _expand_usd_tokens(anchor, child_str)
        else:
            children = [Path(child_str) if os.path.isabs(child_str) else anchor / child_str]
        for child in children:
            try:
                if not child.exists() or not child.is_file():
                    continue
            except OSError:
                continue
            for sub in parse_usd_references(child, _visited, _depth + 1, husk_path, report):
                if os.path.isabs(sub) or (len(sub) > 1 and sub[1] == ':'):
                    all_refs.add(sub)
                else:
                    all_refs.add(str(child.parent / sub))
    return sorted(all_refs)


def _expand_ref_path(ref):
    expanded = os.path.expandvars(str(ref))
    match = re.match(r'^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?', expanded)
    if match and match.group(1) in os.environ:
        expanded = os.path.expandvars(expanded)
    return expanded


def _expand_usd_tokens(anchor, pattern):
    dir_str, _, name = pattern.replace('\\', '/').rpartition('/')
    parts = []
    last = 0
    for m in USD_PATTERN_RE.finditer(name):
        parts.append(re.escape(name[last:m.start()]))
        parts.append(_usd_token_regex(m.group(1) or m.group(2)))
        last = m.end()
    parts.append(re.escape(name[last:]))
    try:
        regex = re.compile('^' + ''.join(parts) + '$', re.IGNORECASE)
    except re.error:
        return []
    base = Path(dir_str) if dir_str else anchor
    if not base.is_absolute():
        base = anchor / base
    try:
        if not base.is_dir():
            return []
        return sorted(f for f in base.iterdir() if f.is_file() and regex.match(f.name))
    except OSError:
        return []


def _resolve_references(usd_file, refs):
    usd_file = Path(usd_file)
    resolved = []
    missing = []
    seen = set()
    for ref in refs:
        expanded = _expand_ref_path(ref)
        if USD_PATTERN_RE.search(expanded):
            matches = _expand_usd_tokens(usd_file.parent, expanded)
            if matches:
                for m in matches:
                    if str(m) not in seen:
                        seen.add(str(m))
                        resolved.append(m)
            else:
                missing.append(str(ref))
            continue
        p = Path(expanded)
        if not p.is_absolute():
            p = usd_file.parent / p
        try:
            if p.exists():
                if str(p) not in seen:
                    seen.add(str(p))
                    resolved.append(p)
            else:
                missing.append(str(p))
        except OSError:
            missing.append(str(p))
    return resolved, missing


def needs_sync(path):
    """True if the file is an online-only cloud placeholder or a 0-byte stub."""
    path = Path(path)
    try:
        st = os.stat(path)
    except OSError:
        return False
    if _is_windows_online_only(path):
        return True
    return st.st_size == 0


def sync_file(file_path, timeout=60):
    file_path = Path(file_path)
    if not file_path.exists():
        return False
    if not needs_sync(file_path):
        return True
    # Read the file through: opening alone can leave a cloud placeholder
    # only partially hydrated — reading to EOF forces the full download.
    try:
        with open(file_path, 'rb') as f:
            while f.read(1024 * 1024):
                pass
        if file_path.stat().st_size > 0:
            return True
    except OSError:
        pass
    # Still 0 bytes (async stub) — poll until the download lands.
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if file_path.exists() and not needs_sync(file_path):
            return True
        time.sleep(0.5)
    return file_path.exists() and not needs_sync(file_path)


def sync_usd_references(usd_file, progress_callback=None, cancel_check=None, husk_path=None):
    """Parse a USD file (recursively) and hydrate its dependencies.

    progress_callback(done, total, path) is called per file.
    Returns a report dict: ok, cancelled, refs, total, synced, failed,
    missing, unreadable_layers, static_volumes.
    """
    usd_file = Path(usd_file)
    report = {}
    refs = parse_usd_references(usd_file, husk_path=husk_path, report=report)
    resolved, missing = _resolve_references(usd_file, refs)
    unsynced = [p for p in resolved if needs_sync(p)]
    total = len(unsynced)
    synced = 0
    failed = []
    cancelled = False
    for p in unsynced:
        if cancel_check and cancel_check():
            cancelled = True
            break
        if progress_callback:
            progress_callback(synced, total, str(p))
        if sync_file(p):
            synced += 1
        else:
            failed.append(str(p))
    if progress_callback and total:
        progress_callback(synced, total, '')
    # Per-frame clip layers each hold one static filePath — that's expected.
    static_volumes = [] if report.get('has_clips') else sorted(set(report.get('static_volumes', [])))
    return {
        'ok': not cancelled and synced == total,
        'cancelled': cancelled,
        'refs': len(resolved),
        'total': total,
        'synced': synced,
        'failed': failed,
        'missing': sorted(set(missing)),
        'unreadable_layers': report.get('unreadable_layers', []),
        'static_volumes': static_volumes,
    }


HIP_EXTENSIONS = {'.hip', '.hipnc', '.hiplc'}
ROP_RENDER_SCRIPT = Path(__file__).resolve().parent / 'maze_rop_render.py'
RENDERER_ROP_HINTS = ('usdrender', 'karma', 'ifd', 'opengl', 'redshift', 'arnold')


def discover_hip_files(shot_path):
    hip_dir = Path(shot_path) / 'houdini' / 'hip'
    if not hip_dir.exists():
        return []
    files = [f for f in hip_dir.iterdir() if f.is_file() and f.suffix.lower() in HIP_EXTENSIONS]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def find_hython(husk_path=None):
    return _find_houdini_tool('hython', husk_path)


def is_renderer_rop(type_name):
    low = type_name.lower()
    return any(h in low for h in RENDERER_ROP_HINTS)


def parse_rop_listing(output):
    """Parse maze_rop_render.py --list output into [{rop, type, passes, parms}]."""
    rops = {}
    order = []
    for line in output.splitlines():
        parts = line.rstrip('\r').split('\t')
        if len(parts) != 3:
            continue
        kind, rop, value = parts
        if kind == 'rop':
            if rop not in rops:
                order.append(rop)
            rops[rop] = {'rop': rop, 'type': value, 'passes': [], 'parms': []}
        elif kind == 'pass' and rop in rops:
            rops[rop]['passes'].append(value)
        elif kind == 'parm' and rop in rops:
            rops[rop]['parms'].append(value)
    return [rops[r] for r in order]


def discover_hip_rops(hython, hip_file):
    """List ROPs and their RenderPass prims in a .hip. Returns (rops, raw_output)."""
    if not hython:
        return [], 'hython not found next to husk'
    hip_file = Path(hip_file)
    if needs_sync(hip_file):
        sync_file(hip_file)
    try:
        result = subprocess.run(
            [hython, str(ROP_RENDER_SCRIPT), '--list', str(hip_file)],
            capture_output=True, text=True, timeout=300,
            **_subprocess_flags(),
        )
        output = (result.stdout or '') + (result.stderr or '')
        return parse_rop_listing(result.stdout or ''), output
    except subprocess.TimeoutExpired as e:
        return [], f'ROP discovery timed out: {e}'
    except Exception as e:
        return [], f'ROP discovery failed: {e}'


def build_rop_render_cmd(hython, hip, rop, render_pass, start, end, inc, out_file):
    cmd = [hython, str(ROP_RENDER_SCRIPT), '--render', str(hip), '--rop', rop]
    if render_pass:
        cmd += ['--pass', render_pass]
    cmd += ['--frames', str(start), str(end), str(inc), '--out', str(out_file)]
    return cmd


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

BACKUP_EXCLUDE_DIR_NAMES = {'__pycache__', '.git'}
BACKUP_EXCLUDE_SUBSTR = '_backup'

WORKING_FILE_EXTENSIONS = sorted({
    ext.lower() for exts in APP_FILE_EXTENSIONS.values() for ext in exts
})

BACKUP_RULES = [
    {
        'id': 'working_files',
        'label': 'Working files',
        'hint': 'DCC scene files: .hip/.hipnc/.hiplc, .ma/.mb, .blend, .nk, .psd, .spp, .ztl …',
        'default': True,
        'extensions': set(WORKING_FILE_EXTENSIONS),
        'basenames': None,
        'path_any': None,
        'path_none': None,
    },
    {
        'id': 'usd_scenes',
        'label': 'USD scenes',
        'hint': '.usd/.usda/.usdc/.usdz anywhere except render folders',
        'default': True,
        'extensions': {'.usd', '.usda', '.usdc', '.usdz'},
        'basenames': None,
        'path_any': None,
        'path_none': ('render',),
    },
    {
        'id': 'metadata',
        'label': 'Metadata & thumbnails',
        'hint': '_metadata.json, _production.json, _thumbnail.png',
        'default': True,
        'extensions': None,
        'basenames': {'_metadata.json', '_production.json', '_thumbnail.png'},
        'path_any': None,
        'path_none': None,
    },
    {
        'id': 'configs',
        'label': 'Project config files',
        'hint': '.json/.csv/.txt/.yaml/.env in mazehub/, DB/, pipeline/',
        'default': True,
        'extensions': {'.json', '.csv', '.txt', '.yaml', '.yml', '.env'},
        'basenames': None,
        'path_any': ('mazehub', 'db', 'pipeline'),
        'path_none': None,
    },
    {
        'id': 'input_footage',
        'label': 'Input footage',
        'hint': 'Any file under input/, plates/, footage/ (e.g. live-action plates)',
        'default': False,
        'extensions': None,
        'basenames': None,
        'path_any': ('input', 'plates', 'footage'),
        'path_none': None,
    },
    {
        'id': 'onset_media',
        'label': 'Onset media',
        'hint': 'Camera/plate media (.mov .ari .r3d .exr …) under onset/, lensgrid/, grainref/',
        'default': False,
        'extensions': {'.mov', '.mp4', '.mxf', '.ari', '.r3d', '.braw', '.exr', '.dpx'},
        'basenames': None,
        'path_any': ('onset', 'lensgrid', 'grainref'),
        'path_none': None,
    },
    {
        'id': 'hdri_photogrammetry',
        'label': 'HDRI & photogrammetry',
        'hint': 'Images under hdri/, photogrammetry/, panorama/ (stitched HDRIs etc.)',
        'default': False,
        'extensions': {'.exr', '.hdr', '.tif', '.tiff', '.jpg', '.jpeg', '.png'},
        'basenames': None,
        'path_any': ('hdri', 'photogrammetry', 'panorama'),
        'path_none': None,
    },
    {
        'id': 'textures',
        'label': 'Textures',
        'hint': 'Any file under texture/, textures/, tex/',
        'default': False,
        'extensions': None,
        'basenames': None,
        'path_any': ('texture', 'textures', 'tex'),
        'path_none': None,
    },
    {
        'id': 'caches_geo',
        'label': 'Caches, geo & exports',
        'hint': 'Any file under cache/, geo/, export/',
        'default': False,
        'extensions': None,
        'basenames': None,
        'path_any': ('cache', 'geo', 'export'),
        'path_none': None,
    },
    {
        'id': 'renders',
        'label': 'Renders',
        'hint': 'Any file under render/ and images/',
        'default': False,
        'extensions': None,
        'basenames': None,
        'path_any': ('render', 'images'),
        'path_none': None,
    },
    {
        'id': 'reference',
        'label': 'Reference & concept',
        'hint': 'Any file under reference/, concept/, storyboard/, annotations/',
        'default': False,
        'extensions': None,
        'basenames': None,
        'path_any': ('reference', 'concept', 'storyboard', 'annotations'),
        'path_none': None,
    },
    {
        'id': 'everything',
        'label': 'Everything',
        'hint': 'All files in the selected folders, ignoring the rules above',
        'default': False,
        'extensions': None,
        'basenames': None,
        'path_any': None,
        'path_none': None,
    },
]

BACKUP_TOP_LEVEL = [
    ('sequence', 'Shots'),
    ('asset', 'Assets'),
    ('lightrigs', 'Light Rigs'),
    ('onset', 'Onset'),
    ('development', 'Development'),
    ('IO', 'IO'),
    ('rnd', 'rnd'),
    ('MISC', 'MISC'),
    ('DB', 'DB'),
    ('mazehub', 'mazehub'),
    ('pipeline', 'pipeline'),
]


def _backup_excluded_part(name):
    lowered = name.lower()
    return name in BACKUP_EXCLUDE_DIR_NAMES or BACKUP_EXCLUDE_SUBSTR in lowered


def _backup_dir_children(base):
    if not base.is_dir():
        return []
    try:
        return sorted(
            (e for e in base.iterdir()
             if e.is_dir() and not e.name.startswith('_')
             and not _backup_excluded_part(e.name)),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return []


def list_backup_items(project_root):
    root = Path(project_root)

    def _node(path, label=None):
        return {'label': label or path.name, 'path': path, 'children': []}

    items = []
    for folder, label in BACKUP_TOP_LEVEL:
        base = root / folder
        if not base.is_dir():
            continue
        node = _node(base, label)
        if folder == 'asset':
            for cat in _backup_dir_children(base):
                cat_node = _node(cat)
                cat_node['children'] = [_node(a) for a in _backup_dir_children(cat)]
                node['children'].append(cat_node)
        elif folder in ('sequence', 'lightrigs', 'onset'):
            node['children'] = [_node(c) for c in _backup_dir_children(base)]
        items.append(node)
    return items


def _rule_matches(rule, name, suffix, parts_lower):
    extensions = rule.get('extensions')
    if extensions is not None and suffix not in extensions:
        return False
    basenames = rule.get('basenames')
    if basenames is not None and name not in basenames:
        return False
    path_any = rule.get('path_any')
    if path_any:
        if not any(sub in part for part in parts_lower for sub in path_any):
            return False
    path_none = rule.get('path_none')
    if path_none:
        if any(sub in part for part in parts_lower for sub in path_none):
            return False
    return True


def collect_backup_files(project_root, item_paths, enabled_rule_ids,
                         progress_cb=None, cancel_check=None):
    project_root = Path(project_root).resolve()
    rules_by_id = {r['id']: r for r in BACKUP_RULES}
    rules = [rules_by_id[rid] for rid in enabled_rule_ids if rid in rules_by_id]
    catch_all = 'everything' in enabled_rule_ids
    files = []
    seen = set()
    for item in item_paths:
        item = Path(item)
        if not item.exists():
            continue
        base = item if item.is_dir() else item.parent
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not _backup_excluded_part(d)]
            if cancel_check and cancel_check():
                return files
            for filename in filenames:
                if cancel_check and cancel_check():
                    return files
                src = Path(dirpath) / filename
                try:
                    rel = src.resolve().relative_to(project_root)
                except (OSError, ValueError):
                    continue
                parts_lower = [p.lower() for p in rel.parts]
                if any(_backup_excluded_part(p) for p in rel.parts):
                    continue
                key = str(rel)
                if key in seen:
                    continue
                if not catch_all:
                    suffix = src.suffix.lower()
                    if not any(_rule_matches(r, src.name.lower(), suffix, parts_lower)
                               for r in rules):
                        continue
                seen.add(key)
                files.append((src, rel.as_posix()))
                if progress_cb:
                    progress_cb(len(files), key)
    files.sort(key=lambda pair: pair[1])
    return files


def _is_windows_online_only(path):
    if platform.system() != 'Windows':
        return False
    try:
        import ctypes
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        GetFileAttributesW.restype = ctypes.c_uint32
        attrs = GetFileAttributesW(str(path))
        if attrs == 0xFFFFFFFF:
            return False
        FILE_ATTRIBUTE_OFFLINE = 0x1000
        FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
        FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
        return bool(attrs & (FILE_ATTRIBUTE_OFFLINE |
                             FILE_ATTRIBUTE_RECALL_ON_OPEN |
                             FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS))
    except Exception:
        return False


def scan_file_size(path):
    """Return (size, is_online_only, is_unsized) from metadata only.

    Never opens the file, so online-only cloud placeholders (OneDrive
    Files On-Demand, rclone mounts) are not hydrated. On Windows the
    reported st_size for placeholders is the remote size.
    """
    try:
        st = os.stat(path)
    except OSError:
        return 0, False, True
    size = st.st_size
    online = _is_windows_online_only(path)
    if size == 0 and not online:
        return 0, False, True
    return size, online, False


def _size_result():
    return {
        'count': 0,
        'bytes': 0,
        'online_count': 0,
        'online_bytes': 0,
        'unsized_count': 0,
    }


def backup_total_size(files):
    result = _size_result()
    for src, _rel in files:
        size, online, unsized = scan_file_size(src)
        result['count'] += 1
        result['bytes'] += size
        if online:
            result['online_count'] += 1
            result['online_bytes'] += size
        if unsized:
            result['unsized_count'] += 1
    return result


def scan_project_size(project_root, progress_cb=None, cancel_check=None):
    """Size of the whole project from metadata only (no file reads)."""
    root = Path(project_root)
    result = _size_result()
    if not root.is_dir():
        return result
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _backup_excluded_part(d)]
        for filename in filenames:
            if cancel_check and cancel_check():
                return result
            size, online, unsized = scan_file_size(Path(dirpath) / filename)
            result['count'] += 1
            result['bytes'] += size
            if online:
                result['online_count'] += 1
                result['online_bytes'] += size
            if unsized:
                result['unsized_count'] += 1
            scanned += 1
            if progress_cb and scanned % 200 == 0:
                progress_cb(scanned)
    return result


def human_size(num_bytes):
    size = float(num_bytes or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024.0 or unit == 'TB':
            if unit == 'B':
                return f'{int(size)} B'
            return f'{size:.1f} {unit}'
        size /= 1024.0
    return f'{size:.1f} TB'


def run_backup(files, dest, fmt='copy', progress_cb=None, cancel_check=None):
    import shutil
    import zipfile
    dest = Path(dest)
    result = {'done': 0, 'total': len(files), 'errors': [], 'cancelled': False,
              'dest': str(dest)}
    if fmt == 'zip':
        if dest.suffix.lower() != '.zip':
            dest = dest if dest.suffix else dest.with_suffix('.zip')
            result['dest'] = str(dest)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            result['errors'].append(str(e))
            return result
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
            for src, rel in files:
                if cancel_check and cancel_check():
                    result['cancelled'] = True
                    return result
                try:
                    zf.write(src, rel)
                except (OSError, ValueError) as e:
                    result['errors'].append(f'{rel}: {e}')
                result['done'] += 1
                if progress_cb:
                    progress_cb(result['done'], result['total'], rel)
    else:
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            result['errors'].append(str(e))
            return result
        for src, rel in files:
            if cancel_check and cancel_check():
                result['cancelled'] = True
                return result
            target = dest / rel
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            except (OSError, ValueError) as e:
                result['errors'].append(f'{rel}: {e}')
            result['done'] += 1
            if progress_cb:
                progress_cb(result['done'], result['total'], rel)
    return result


def print_header(project_root):
    print()
    print('=' * 60)
    print(f'  MAZEHUB PIPELINE TOOL')
    print(f'  Project: {project_root.name}')
    print(f'  Root:    {project_root}')
    print('=' * 60)


def print_menu():
    print()
    print('  MAIN MENU')
    print('  ' + '-' * 40)
    print('   1) Launch Application')
    print('   2) Create Shot Directories')
    print('   3) Create Asset Directories')
    print('   4) Find & Open Project Files')
    print('   5) Show Environment Variables')
    print('   0) Exit')
    print()


def handle_launch_app(apps_config, pipeline_dir):
    print('\n  Available applications:')
    list_apps(apps_config)
    name = input('\n  Enter app name to launch: ').strip()
    if name:
        launch_app(apps_config, name, pipeline_dir)


def get_project_structure(project_root):
    """The project's enabled features/folders/software (all enabled if unset)."""
    from make_folders import normalize_structure
    from settings import get_setting
    return normalize_structure(get_setting('project_structure', None, root=project_root))


def set_project_structure(project_root, structure):
    from make_folders import normalize_structure
    from settings import set_setting
    set_setting('project_structure', normalize_structure(structure), root=project_root)


def handle_create_shot(project_root):
    name = input('  Shot name (e.g. SH010): ').strip()
    if not name:
        return
    from make_folders import make_working_directory
    shot_path = project_root / 'sequence' / name
    if shot_path.exists():
        print(f'  Shot already exists: {name}')
        return
    make_working_directory(str(shot_path), get_project_structure(project_root))
    print(f'  Created shot: {name}')
    print(f'  Location: {shot_path}')


def handle_create_asset(project_root):
    from make_folders import NEW_ASSET_CATEGORY_LIST
    print(f'\n  Categories: {", ".join(NEW_ASSET_CATEGORY_LIST)}')
    category = input('  Category: ').strip().lower()
    if category not in NEW_ASSET_CATEGORY_LIST:
        print(f'  Invalid category. Options: {", ".join(NEW_ASSET_CATEGORY_LIST)}')
        return
    name = input('  Asset name (e.g. MainCharacter): ').strip()
    if not name:
        return
    from make_folders import make_working_directory
    folder_name = name.lower().replace(' ', '_')
    asset_path = project_root / 'asset' / category / folder_name
    if asset_path.exists():
        print(f'  Asset already exists: {category}/{folder_name}')
        return
    make_working_directory(str(asset_path), get_project_structure(project_root))
    write_asset_meta(asset_path, {
        'display_name': name,
        'folder_name': folder_name,
    })
    print(f'  Created asset: {category}/{name}')
    print(f'  Location: {asset_path}')


def handle_find_files(project_root, apps_config, pipeline_dir):
    print('\n  Searching for project files...')
    results = find_project_files(project_root, apps_config)

    if not results:
        print('  No project files found for configured applications.')
        return

    idx = 1
    file_map = {}
    for app_name in sorted(results):
        print(f'\n  [{app_name}]')
        for fp in results[app_name]:
            rel = fp.relative_to(project_root)
            print(f'    {idx:3d}. {rel}')
            file_map[idx] = (app_name, fp, rel)
            idx += 1

    choice = input('\n  Enter number to open file (or Enter to skip): ').strip()
    if not choice.isdigit():
        return
    num = int(choice)
    if num not in file_map:
        return

    app_name, file_path, rel = file_map[num]
    cfg = apps_config[app_name]
    exec_path = pipeline_dir / cfg['subdir'] / cfg['executable']

    print(f'  Opening {rel} with {cfg["display_name"]}...')
    try:
        if platform.system() == 'Windows':
            subprocess.Popen([str(exec_path), str(file_path)], shell=True)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', str(file_path)])
        else:
            subprocess.Popen([str(exec_path), str(file_path)], shell=True)
    except Exception as e:
        print(f'  Failed to open file: {e}')


def show_env_vars(env_vars):
    print()
    for key in sorted(env_vars):
        print(f'    {key:25s} = {env_vars[key]}')


def main():
    project_root = find_project_root()
    if project_root is None:
        from settings import list_projects, add_project, set_active_project
        print('\n  No active project.')
        for p in list_projects():
            print(f"    - {p['name']}: {p['root']}")
        choice = input('  Enter project root to add (blank to quit): ').strip()
        if not choice:
            return
        candidate = Path(choice).expanduser()
        if not candidate.is_dir():
            print(f'  Not a directory: {candidate}')
            return
        add_project(candidate)
        set_active_project(str(candidate))
        project_root = candidate
    pipeline_dir = find_pipeline_dir()

    env_vars = setup_environment(project_root, pipeline_dir)
    apps_config = load_apps_config()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    print_header(project_root)

    while True:
        print_menu()
        choice = input('  Select option: ').strip()

        if choice == '1':
            handle_launch_app(apps_config, pipeline_dir)
        elif choice == '2':
            handle_create_shot(project_root)
        elif choice == '3':
            handle_create_asset(project_root)
        elif choice == '4':
            handle_find_files(project_root, apps_config, pipeline_dir)
        elif choice == '5':
            show_env_vars(env_vars)
        elif choice == '0':
            print('\n  Goodbye!\n')
            break
        else:
            print('  Invalid option.')

def send_teams_notification(webhook_url, shot, usd_file, passes, start_frame,
                            end_frame, interval, version, render_engine,
                            exit_code, render_time, project_root='',
                            cancelled=False, start_time='', end_time='',
                            first_frame_path=''):
    if not webhook_url:
        return False

    if cancelled:
        status = 'Cancelled'
        color = 'F39C12'
    elif exit_code == 0:
        status = 'Succeeded'
        color = '2ECC71'
    else:
        status = 'Failed'
        color = 'E74C3C'

    frames = list(range(start_frame, end_frame + 1, max(interval, 1)))
    total_frames = len(frames) * len(passes)

    summary_facts = [
        {'name': 'Shot', 'value': shot},
        {'name': 'Status', 'value': status},
        {'name': 'Passes', 'value': ', '.join(passes)},
        {'name': 'Frame Range', 'value': f'{start_frame} - {end_frame}'},
        {'name': 'Version', 'value': f'v{version:03d}'},
        {'name': 'Started By', 'value': _get_display_name()},
    ]

    detail_facts = [
        {'name': 'USD File', 'value': usd_file},
        {'name': 'Interval', 'value': str(interval)},
        {'name': 'Total Frames', 'value': str(total_frames)},
        {'name': 'Engine', 'value': f'Karma {render_engine.upper()}' if render_engine in ('xpu', 'cpu') else render_engine},
        {'name': 'Render Time', 'value': render_time},
    ]
    if start_time:
        detail_facts.append({'name': 'Start Time', 'value': start_time})
    if end_time:
        detail_facts.append({'name': 'End Time', 'value': end_time})
    if first_frame_path:
        detail_facts.append({'name': 'First Frame', 'value': first_frame_path})

    card = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'themeColor': color,
        'summary': f'Render {status}: {shot}',
        'sections': [{
            'activityTitle': f'Render {status}',
            'activitySubtitle': f'{shot} — {usd_file}',
            'facts': summary_facts,
            'markdown': True,
        }, {
            'title': 'Details',
            'facts': detail_facts,
            'markdown': True,
        }],
    }

    if project_root:
        card['potentialAction'] = [{
            '@type': 'OpenUri',
            'name': 'Open in MazeHub',
            'targets': [{'os': 'default', 'uri': str(project_root)}],
        }]

    data = json.dumps(card).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def send_dailies_notification(webhook_url, shot, artist, file_path,
                              frame_range='', notes=''):
    if not webhook_url:
        return False

    facts = [
        {'name': 'Shot', 'value': shot},
        {'name': 'Artist', 'value': artist},
    ]
    if frame_range:
        facts.append({'name': 'Frame Range', 'value': frame_range})
    if notes:
        facts.append({'name': 'Notes', 'value': notes})

    card = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'themeColor': '3498DB',
        'summary': f'Dailies: {shot}',
        'sections': [{
            'activityTitle': f'Dailies: {shot}',
            'facts': facts,
            'markdown': True,
        }],
        'potentialAction': [{
            '@type': 'OpenUri',
            'name': 'Open File',
            'targets': [{'os': 'default', 'uri': str(file_path)}],
        }],
    }

    data = json.dumps(card).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def send_production_notification(webhook_url, item_type, item_name, category,
                               task, from_status, to_status, user=''):
    if not webhook_url:
        return False
    if to_status == 'Not applicable':
        return False

    if not user:
        user = _get_display_name()

    # Color by new status
    color_map = {
        'Not started': 'E74C3C',
        'Work in progress': 'F39C12',
        'Pending review': '3498DB',
        'Finished': '2ECC71',
        'Not applicable': '95A5A6',
    }
    color = color_map.get(to_status, '3498DB')

    label = f'{item_type.title()}: {item_name}' if item_type else item_name

    facts = [
        {'name': 'Item', 'value': label},
        {'name': 'Task', 'value': task},
        {'name': 'Status', 'value': f'{from_status} → {to_status}'},
        {'name': 'Updated By', 'value': user},
    ]
    if category and category != item_name:
        # Only add extra context if useful; for assets include category prefix already in label?
        # Keep category as separate fact for assets
        if item_type == 'asset':
            facts.insert(1, {'name': 'Category', 'value': category})

    card = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'themeColor': color,
        'summary': f'Production: {label} — {task} {from_status} → {to_status}',
        'sections': [{
            'activityTitle': f'Production Update — {task}',
            'activitySubtitle': label,
            'facts': facts,
            'markdown': True,
        }],
    }

    data = json.dumps(card).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


if __name__ == '__main__':
    main()
