import os
import sys
import json
import subprocess
import platform
from pathlib import Path


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
    'frame_range': '',
    'frame_rate': '',
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


if __name__ == '__main__':
    main()
