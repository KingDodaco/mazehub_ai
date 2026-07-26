import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

for path in [
    ROOT / 'build',
    ROOT / 'dist',
    ROOT / 'Build_App.bat',
    ROOT / 'build_app.py',
    ROOT / 'Build_App.spec',
    ROOT / 'MazeHub.spec',
    ROOT / 'portable_launcher.py',
    ROOT / 'publish_update.py',
    ROOT / 'run_app.py',
    ROOT / 'sync_pipeline.bat',
    ROOT / 'sync_pipeline.py',
    ROOT / 'sync_to_cloud.bat',
]:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

for pycache in ROOT.rglob('__pycache__'):
    if pycache.is_dir():
        shutil.rmtree(pycache)

print('Cleanup complete')
