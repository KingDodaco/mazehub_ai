from pathlib import Path
import os
import re
import shutil
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


def _pick_app_dir(candidates):
    valid = []
    for p in candidates:
        _debug_log(f"checking: {p} exists={p.exists()}")
        if p.exists() and (p / 'pipeline_app.py').exists() and (p / 'pipeline_gui.py').exists():
            valid.append(p)
    best = None
    best_version = None
    for p in valid:
        version = _version_key(_tree_version(p))
        if best is None or version > best_version:
            best = p
            best_version = version
    return best


def _materialize_install(exe_dir, meipass):
    src = meipass / 'pipeline'
    if not src.is_dir() or not (src / 'mazehub').is_dir():
        return False
    preserve = {'mazehub/apps.json', 'mazehub/styles.qss', 'mazehub/icon.png'}

    def _copy(s, d):
        if s.is_dir():
            d.mkdir(parents=True, exist_ok=True)
            for child in s.iterdir():
                _copy(child, d / child.name)
            return
        rel = d.relative_to(exe_dir).as_posix()
        if rel in preserve and d.exists():
            return
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)

    try:
        _copy(src, exe_dir)
        _debug_log(f"Materialized bundled pipeline into {exe_dir}")
        return True
    except OSError as exc:
        _debug_log(f"Materialize failed: {exc}")
        return False


def _find_app_dir():
    this_dir = Path(__file__).resolve().parent
    _debug_log(f"this_dir: {this_dir}")
    _debug_log(f"frozen: {getattr(sys, 'frozen', False)}")

    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, '_MEIPASS', '')) if getattr(sys, '_MEIPASS', '') else None
        _debug_log(f"exe_dir: {exe_dir}")
        _debug_log(f"meipass: {meipass}")

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

        best = _pick_app_dir(candidates)
        if best is not None and meipass:
            try:
                best.resolve().relative_to(meipass.resolve())
                under_bundle = True
            except ValueError:
                under_bundle = False
            if under_bundle and _materialize_install(exe_dir, meipass):
                best = _pick_app_dir(candidates) or best
        if best is not None:
            _debug_log(f"FOUND app_dir: {best}")
            return best
    else:
        candidates = [
            this_dir / 'pipeline' / 'mazehub',
            this_dir / '.pipeline_mirror' / 'pipeline' / 'mazehub',
            this_dir,
        ]
        for p in candidates:
            _debug_log(f"checking: {p} exists={p.exists()}")
            if p.exists() and (p / 'pipeline_app.py').exists() and (p / 'pipeline_gui.py').exists():
                _debug_log(f"FOUND app_dir: {p}")
                return p

    _debug_log("ERROR: app_dir not found")
    return None


def _apply_project_arg(argv):
    project = None
    for i, arg in enumerate(argv):
        if arg == '--project' and i + 1 < len(argv):
            project = argv[i + 1]
        elif arg.startswith('--project='):
            project = arg.split('=', 1)[1]
    if not project:
        return
    p = Path(project).expanduser()
    if not p.is_dir():
        _debug_log(f"ERROR: --project is not a directory: {p}")
        sys.exit(1)
    os.environ['MAZE_PROJECT_ROOT'] = str(p.resolve())
    _debug_log(f"Session project override: {p.resolve()}")


def main():
    _debug_log("--- MazeHub starting ---")
    app_dir = _find_app_dir()
    if not app_dir:
        _debug_log("ERROR: pipeline app directory not found.")
        sys.exit(1)

    _apply_project_arg(sys.argv[1:])

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
