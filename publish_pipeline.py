import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRROR_SOURCE = ROOT / '.pipeline_mirror' / 'pipeline'
PUBLISH_DEST = ROOT / 'publish' / 'pipeline'
LAUNCHER_SRC = ROOT / 'main.py'
BATCH_SRC = ROOT / 'launch_mazehub.bat'
HELPER_SRC = ROOT / 'make_folders.py'


def ensure_source_exists():
    if not MIRROR_SOURCE.exists():
        raise FileNotFoundError('No pipeline source folder found. Expected .pipeline_mirror/pipeline.')


def copy_tree(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def publish_pipeline(target: Path | None = None):
    ensure_source_exists()
    copy_tree(MIRROR_SOURCE, PUBLISH_DEST)

    mazehub_publish_dir = PUBLISH_DEST / 'mazehub'
    mazehub_publish_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LAUNCHER_SRC, mazehub_publish_dir / 'main.py')
    shutil.copy2(BATCH_SRC, mazehub_publish_dir / 'launch_mazehub.bat')
    shutil.copy2(HELPER_SRC, mazehub_publish_dir / 'make_folders.py')

    print(f'Published pipeline to {PUBLISH_DEST}')
    print(f'Placed launcher files in {mazehub_publish_dir}')

    if target:
        target = target.resolve()
        copy_tree(PUBLISH_DEST, target)
        print(f'Also copied pipeline to {target}')


def main():
    parser = argparse.ArgumentParser(description='Sync the mirrored pipeline into the working tree and publish a clean publish/pipeline bundle.')
    parser.add_argument('--target', type=Path, help='Optional destination folder to receive the published pipeline tree')
    args = parser.parse_args()
    publish_pipeline(args.target)


if __name__ == '__main__':
    main()
