import os
import sys
import re
import json
import subprocess
import platform
import urllib.request
from pathlib import Path

APP_VERSION = "0.5.1"


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


def _app_dir():
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir / 'pipeline' / 'mazehub'
        if candidate.exists():
            return candidate
        candidate = exe_dir / 'mazehub'
        if candidate.exists():
            return candidate
        meipass = Path(getattr(sys, '_MEIPASS', ''))
        if meipass:
            candidate = meipass / 'pipeline' / 'mazehub'
            if candidate.exists():
                return candidate
            candidate = meipass / 'mazehub'
            if candidate.exists():
                return candidate
        return exe_dir
    return Path(__file__).resolve().parent


def find_project_root():
    env_root = os.environ.get('MAZE_PROJECT_ROOT')
    if env_root:
        return Path(env_root).resolve()

    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        for parent in [exe_dir] + list(exe_dir.parents):
            root_marker = parent / 'pipeline' / 'mazehub' / 'apps.json'
            mirror_marker = parent / '.pipeline_mirror' / 'pipeline' / 'mazehub' / 'apps.json'
            if root_marker.exists() or mirror_marker.exists():
                return parent
        return exe_dir

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
        with open(meta_path) as f:
            stored = json.load(f)
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
}


def read_light_rig_meta(rig_path):
    meta_path = Path(rig_path) / LIGHT_RIG_META_FILENAME
    if meta_path.exists():
        with open(meta_path) as f:
            stored = json.load(f)
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
    lightrigs_dir = Path(project_root) / 'Light_Rigs'
    if not lightrigs_dir.exists():
        return []
    return sorted([
        d.name for d in lightrigs_dir.iterdir()
        if d.is_dir() and not d.name.startswith('_')
    ])


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


def setup_environment(project_root):
    root = str(Path(project_root))
    ROOT_VAR = 'MAZE_PROJECT_ROOT'
    ref = _env_ref(ROOT_VAR)

    ref_vars = {
        ROOT_VAR: root,
        'MZE': root,
        'MAZE_PROJECT': Path(root).name,
        'MAZE_PIPELINE': f'{ref}/pipeline',
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
        'HOUDINI_JOB': '{context_path}',
        'JOB': '{context_path}',
    },
    'Maya': {
        'MAYA_PROJECT': '{context_path}',
    },
    'NukeX': {},
    'Blender': {},
    'Mari': {},
    'SubstancePainter': {},
    'Zbrush': {},
    'Photoshop': {},
    'USD': {},
}


def build_context_env(context, project_root):
    if not context:
        return {}
    ctx_path = Path(context['path'])
    env = {
        'MAZE_CONTEXT_TYPE': context['type'],
        'MAZE_CONTEXT_NAME': context['name'],
        'MAZE_CONTEXT_PATH': str(ctx_path),
        'PIPELINE_DIR': str(Path(project_root) / 'pipeline'),
    }

    if context['type'] == 'shot':
        meta = read_shot_meta(ctx_path)
        fr = meta.get('frame_range', '')
        if fr and '-' in fr:
            parts = fr.split('-')
            env['START_FRAME'] = parts[0]
            env['END_FRAME'] = parts[1]
        fps = meta.get('frame_rate', '')
        if fps:
            env['FRAME_RATE'] = fps

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


def discover_husk_passes(husk_path, usd_file):
    if not husk_path or not Path(husk_path).exists():
        return []
    try:
        result = subprocess.run(
            [husk_path, '--list-passes', str(usd_file)],
            capture_output=True, text=True, timeout=30,
        )
        output = (result.stdout or '') + '\n' + (result.stderr or '')
        passes = []
        in_passes = False
        for line in output.splitlines():
            raw = line.strip()
            if not raw:
                continue
            lower = raw.lower()
            if 'available render passes' in lower or 'render passes found' in lower:
                in_passes = True
                continue
            if in_passes:
                if raw.startswith(('[', '#', '//')) or len(raw) > 80 or '://' in raw:
                    continue
                passes.append(raw)
                continue
            if raw.startswith('[') or raw.startswith('#') or len(raw) > 80:
                continue
            if '://' in raw:
                continue
            if not any(c in raw for c in (' ', '\t')) and len(raw) < 80:
                passes.append(raw)
        return passes
    except Exception:
        return []


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


def handle_create_shot(project_root):
    name = input('  Shot name (e.g. SH010): ').strip()
    if not name:
        return
    from make_folders import make_working_directory
    shot_path = project_root / 'sequence' / name
    if shot_path.exists():
        print(f'  Shot already exists: {name}')
        return
    make_working_directory(str(shot_path))
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
    asset_path = project_root / 'asset' / category / name
    if asset_path.exists():
        print(f'  Asset already exists: {category}/{name}')
        return
    make_working_directory(str(asset_path))
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
    pipeline_dir = project_root / 'pipeline'
    mazehub_dir = pipeline_dir / 'mazehub'

    env_vars = setup_environment(project_root)
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
        {'name': 'Engine', 'value': f'Karma {render_engine.upper()}'},
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
