import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRROR_SOURCE = ROOT / '.pipeline_mirror' / 'pipeline'
PUBLISH_DEST = ROOT / 'publish' / 'pipeline'
EXE_SRC = ROOT / 'dist' / 'MazeHub.exe'
HELPER_SRC = ROOT / 'make_folders.py'

CONFIG_FILES = ['apps.json', 'styles.qss', 'icon.svg']

DCC_DIRS = [
    'Blender', 'Houdini21.0', 'Mari', 'Maya',
    'Nuke', 'OCIO', 'Photoshop', 'Substance', 'Zbrush',
]


def ensure_source_exists():
    if not MIRROR_SOURCE.exists():
        raise FileNotFoundError('No pipeline source folder found. Expected .pipeline_mirror/pipeline.')


def copy_tree(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def publish_pipeline(target: Path | None = None, exe_only: bool = False):
    ensure_source_exists()

    if PUBLISH_DEST.exists():
        shutil.rmtree(PUBLISH_DEST)
    PUBLISH_DEST.mkdir(parents=True)

    for d in DCC_DIRS:
        src = MIRROR_SOURCE / d
        if src.exists():
            copy_tree(src, PUBLISH_DEST / d)

    mazehub_dir = PUBLISH_DEST / 'mazehub'
    mazehub_dir.mkdir(parents=True, exist_ok=True)

    for f in CONFIG_FILES:
        src = MIRROR_SOURCE / 'mazehub' / f
        if src.exists():
            shutil.copy2(src, mazehub_dir / f)

    if HELPER_SRC.exists():
        shutil.copy2(HELPER_SRC, mazehub_dir / 'make_folders.py')

    if not exe_only and EXE_SRC.exists():
        shutil.copy2(EXE_SRC, PUBLISH_DEST / 'MazeHub.exe')
    elif not EXE_SRC.exists():
        print(f'Warning: exe not found at {EXE_SRC}. Run build.bat first.')

    launcher = PUBLISH_DEST / 'launch_mazehub.bat'
    launcher.write_text(
        '@echo off\r\n'
        'setlocal\r\n'
        'cd /d "%~dp0"\r\n'
        'if exist "MazeHub.exe" (\r\n'
        '    start "" "MazeHub.exe"\r\n'
        '    exit /b 0\r\n'
        ')\r\n'
        'echo MazeHub.exe not found in %~dp0\r\n'
        'exit /b 1\r\n'
    )

    print(f'Published pipeline to {PUBLISH_DEST}')
    if EXE_SRC.exists() and not exe_only:
        print(f'Copied MazeHub.exe to {PUBLISH_DEST}')

    if target:
        target = target.resolve()
        if target.exists():
            shutil.rmtree(target)
        copy_tree(PUBLISH_DEST, target)
        print(f'Also copied to {target}')


def main():
    parser = argparse.ArgumentParser(
        description='Publish a clean deployable bundle: exe + pipeline data (no Python source).'
    )
    parser.add_argument('--target', type=Path, help='Optional destination folder to receive the published bundle')
    parser.add_argument('--no-exe', action='store_true', help='Skip copying the exe (publish pipeline data only)')
    args = parser.parse_args()
    publish_pipeline(args.target, exe_only=args.no_exe)


if __name__ == '__main__':
    main()
