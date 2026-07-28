from pathlib import Path
import sys
import tempfile
import traceback


def _debug_log(msg):
    try:
        log_path = Path(tempfile.gettempdir()) / 'mazehub_debug.log'
        with open(log_path, 'a') as f:
            f.write(msg + '\n')
    except Exception:
        pass


def _find_app_dir():
    this_dir = Path(__file__).resolve().parent
    _debug_log(f"this_dir: {this_dir}")
    _debug_log(f"frozen: {getattr(sys, 'frozen', False)}")
    paths = []

    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, '_MEIPASS', ''))
        _debug_log(f"exe_dir: {exe_dir}")
        _debug_log(f"meipass: {meipass}")
        paths.extend([
            meipass / 'pipeline' / 'mazehub' if meipass else None,
            meipass / 'mazehub' if meipass else None,
            exe_dir / 'pipeline' / 'mazehub',
            exe_dir / 'mazehub',
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
        _debug_log(f"checking: {p} exists={p.exists()}")
        if p.exists() and (p / 'pipeline_app.py').exists() and (p / 'pipeline_gui.py').exists():
            _debug_log(f"FOUND app_dir: {p}")
            return p

    if getattr(sys, 'frozen', False):
        bundled_dir = Path(sys.executable).resolve().parent / '_internal' / 'pipeline' / 'mazehub'
        _debug_log(f"checking bundled_dir: {bundled_dir}")
        if bundled_dir.exists() and (bundled_dir / 'pipeline_app.py').exists():
            _debug_log(f"FOUND app_dir: {bundled_dir}")
            return bundled_dir

    _debug_log("ERROR: app_dir not found")
    return None


def main():
    _debug_log("--- MazeHub starting ---")
    app_dir = _find_app_dir()
    if not app_dir:
        _debug_log("ERROR: pipeline app directory not found.")
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

    _debug_log(f"Starting MazeHub from: {this_dir}")
    _debug_log(f"Using app directory: {app_dir}")
    _debug_log(f"sys.path: {sys.path[:5]}")

    try:
        from pipeline_gui import main as gui_main
        _debug_log("Launching GUI entry point...")
        gui_main()
    except Exception as exc:
        _debug_log(f"GUI startup failed: {exc}")
        _debug_log(traceback.format_exc())
        try:
            from pipeline_app import main as cli_main
            _debug_log("Falling back to CLI entry point...")
            cli_main()
        except Exception as cli_exc:
            _debug_log(f"CLI fallback failed: {cli_exc}")
            _debug_log(traceback.format_exc())
            sys.exit(1)


if __name__ == '__main__':
    main()
