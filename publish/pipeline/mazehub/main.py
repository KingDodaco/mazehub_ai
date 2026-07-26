from pathlib import Path
import sys


def _find_app_dir():
    this_dir = Path(__file__).resolve().parent
    paths = []

    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, '_MEIPASS', ''))
        paths.extend([
            exe_dir / 'pipeline' / 'mazehub',
            exe_dir / 'mazehub',
            meipass / 'pipeline' / 'mazehub' if meipass else None,
            meipass / 'mazehub' if meipass else None,
            exe_dir,
            this_dir / 'pipeline' / 'mazehub',
            this_dir / '.pipeline_mirror' / 'pipeline' / 'mazehub',
        ])
    else:
        paths.extend([
            this_dir / 'pipeline' / 'mazehub',
            this_dir / '.pipeline_mirror' / 'pipeline' / 'mazehub',
            this_dir,
        ])

    for p in paths:
        if p is None:
            continue
        if p.exists() and (p / 'pipeline_app.py').exists() and (p / 'pipeline_gui.py').exists():
            return p

    if getattr(sys, 'frozen', False):
        bundled_dir = Path(sys.executable).resolve().parent / '_internal' / 'pipeline' / 'mazehub'
        if bundled_dir.exists() and (bundled_dir / 'pipeline_app.py').exists():
            return bundled_dir

    return None


def main():
    app_dir = _find_app_dir()
    if not app_dir:
        print("ERROR: pipeline app directory not found.")
        sys.exit(1)

    this_dir = Path(__file__).resolve().parent
    project_root = this_dir.parent if this_dir.name == 'mazehub' else this_dir

    sys.path.insert(0, str(this_dir))
    sys.path.insert(0, str(app_dir))
    sys.path.insert(0, str(project_root))

    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    print(f"Starting MazeHub from: {this_dir}")
    print(f"Using app directory: {app_dir}")

    try:
        from pipeline_gui import main as gui_main
        print("Launching GUI entry point...")
        gui_main()
    except Exception as exc:
        print(f"GUI startup failed: {exc}")
        import traceback
        traceback.print_exc()
        try:
            from pipeline_app import main as cli_main
            print("Falling back to CLI entry point...")
            cli_main()
        except Exception as cli_exc:
            print(f"CLI fallback failed: {cli_exc}")
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    main()
