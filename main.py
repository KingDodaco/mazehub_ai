from pathlib import Path
import sys


def _find_app_dir():
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        paths = [
            exe_dir / 'pipeline' / 'mazehub',
            exe_dir,
        ]
    else:
        this_dir = Path(__file__).resolve().parent
        paths = [
            this_dir / '.pipeline_mirror' / 'pipeline' / 'mazehub',
            this_dir / 'pipeline' / 'mazehub',
        ]
    for p in paths:
        if p.exists():
            return p
    return None


def main():
    app_dir = _find_app_dir()
    if not app_dir:
        print("ERROR: pipeline app directory not found.")
        sys.exit(1)

    if not getattr(sys, 'frozen', False):
        this_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(this_dir))
    sys.path.insert(0, str(app_dir))

    try:
        from pipeline_gui import main as gui_main
        gui_main()
    except ImportError:
        from pipeline_app import main as cli_main
        cli_main()


if __name__ == '__main__':
    main()
