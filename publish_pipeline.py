import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRROR_SOURCE = ROOT / '.pipeline_mirror' / 'pipeline'
MIRROR_APP_DIR = MIRROR_SOURCE / 'mazehub'
PUBLISH_DEST = ROOT / 'publish' / 'pipeline'
EXE_SRC = ROOT / 'dist' / 'MazeHub.exe'
HELPER_SRC = ROOT / 'make_folders.py'
ZIP_DEST = ROOT / 'publish' / 'MazeHub-pipeline.zip'
MANIFEST_DEST = ROOT / 'publish' / 'manifest.json'

CONFIG_FILES = ['apps.json', 'styles.qss', 'icon.png']

DCC_DIRS = [
    'Blender', 'Houdini', 'Mari', 'Maya',
    'Nuke', 'OCIO', 'Photoshop', 'Substance', 'Zbrush',
]

sys.path.insert(0, str(MIRROR_APP_DIR))
import updater  # noqa: E402


def read_version():
    try:
        import tomllib
        with open(ROOT / 'pyproject.toml', 'rb') as f:
            data = tomllib.load(f)
        version = data.get('project', {}).get('version')
        if version:
            return version
    except Exception:
        pass
    app_py = MIRROR_APP_DIR / 'pipeline_app.py'
    if app_py.exists():
        match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', app_py.read_text())
        if match:
            return match.group(1)
    raise SystemExit('Could not determine version from pyproject.toml or pipeline_app.py')


def ensure_source_exists():
    if not MIRROR_SOURCE.exists():
        raise FileNotFoundError('No pipeline source folder found. Expected .pipeline_mirror/pipeline.')


def copy_tree(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'),
    )


def make_release_zip(src_root: Path, zip_path: Path):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_root.rglob('*')):
            if path.is_file():
                zf.write(path, path.relative_to(src_root).as_posix())
    return updater.sha256_file(zip_path), zip_path.stat().st_size


def publish_pipeline(target: Path | None = None, exe_only: bool = False,
                     make_zip: bool = False):
    ensure_source_exists()
    version = read_version()

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

    manifest = updater.build_manifest(PUBLISH_DEST, version)

    if make_zip:
        zip_hash, zip_size = make_release_zip(PUBLISH_DEST, ZIP_DEST)
        manifest['zip'] = {
            'name': ZIP_DEST.name,
            'sha256': zip_hash,
            'size': zip_size,
        }
        MANIFEST_DEST.write_text(json.dumps(manifest, indent=4))
        print(f'Created {ZIP_DEST}')
        print(f'Wrote {MANIFEST_DEST}')

    print(f'Published pipeline to {PUBLISH_DEST} (version {version}, '
          f'{len(manifest["files"])} files)')
    if EXE_SRC.exists() and not exe_only:
        print(f'Copied MazeHub.exe to {PUBLISH_DEST}')

    if target:
        target = target.resolve()
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        result = updater.apply_release(target, PUBLISH_DEST, manifest)
        print(result.summary())
        print(f'Synced to {target}')


def main():
    parser = argparse.ArgumentParser(
        description='Publish a clean deployable bundle: exe + pipeline data (no Python source).',
    )
    parser.add_argument('--target', type=Path,
                        help='Optional destination folder to receive the published bundle '
                             '(syncs manifest-aware: preserves local edits and user data)')
    parser.add_argument('--no-exe', action='store_true',
                        help='Skip copying the exe (publish pipeline data only)')
    parser.add_argument('--zip', action='store_true', dest='make_zip',
                        help='Also build MazeHub-pipeline.zip + manifest.json for releases')
    args = parser.parse_args()
    publish_pipeline(args.target, exe_only=args.no_exe, make_zip=args.make_zip)


if __name__ == '__main__':
    main()
