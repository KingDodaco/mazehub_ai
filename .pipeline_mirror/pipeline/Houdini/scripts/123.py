import hou
import os

print("Setting timeline settings")

start_raw = os.environ.get("START_FRAME", "")
end_raw = os.environ.get("END_FRAME", "")
fps_raw = os.environ.get("FRAME_RATE", "")

print(f"START_FRAME: {start_raw!r}, END_FRAME: {end_raw!r}, FRAME_RATE: {fps_raw!r}")

try:
    start_frame = int(float(start_raw))
    end_frame = int(float(end_raw))
    fps = float(fps_raw)
    if fps <= 0:
        raise ValueError(f"invalid frame rate: {fps_raw!r}")
except (TypeError, ValueError) as e:
    print(f"Timeline environment not usable ({e}). Launching Houdini with default timeline settings.")
    hou.setFps(24)

    hou.playbar.setFrameRange(1001, 1240)
    hou.playbar.setPlaybackRange(1001, 1240)

    hou.setFrame(1001)
else:
    hou.setFps(fps)

    hou.playbar.setFrameRange(start_frame, end_frame)
    hou.playbar.setPlaybackRange(start_frame, end_frame)

    hou.setFrame(start_frame)

# Default flipbook output to $JOB/flipbooks so native Flipbook button saves to disk for MPlay Send
def _maze_set_flipbook_output():
    try:
        job = hou.getenv("JOB") or os.environ.get("JOB", "")
        if not job:
            return
        out = os.path.join(job, "flipbooks", "flipbook.$F4.jpeg")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        panes = []
        try:
            panes = hou.ui.paneTabsOfType(hou.paneTabType.SceneViewer)
        except AttributeError:
            try:
                p = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
                panes = [p] if p else []
            except Exception:
                panes = []
        for pane in panes:
            if not pane:
                continue
            try:
                s = pane.flipbookSettings()
                s.output(out)
            except Exception:
                pass
        print(f"[MAZE] Default flipbook output: {out}")
    except Exception as e:
        print(f"[MAZE] Failed to set flipbook output: {e}")

try:
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1500, _maze_set_flipbook_output)
except Exception:
    try:
        _maze_set_flipbook_output()
    except Exception:
        pass

# Open a .hip in Manual update mode (MazeHub "Manual mode" checkbox). The launcher
# starts Houdini empty so this script runs, then the file is loaded here.
def _maze_load_manual():
    path = os.environ.pop("MAZE_HOUDINI_LOAD_FILE", "")
    if not path:
        return
    try:
        hou.unsetenv("MAZE_HOUDINI_LOAD_FILE")
    except Exception:
        pass
    try:
        hou.setUpdateMode(hou.updateMode.Manual)
        hou.hipFile.load(path, suppress_save_prompt=True)
        hou.setUpdateMode(hou.updateMode.Manual)
        print(f"[MAZE] Opened {path} in Manual update mode")
    except Exception as e:
        print(f"[MAZE] Failed to open {path} in Manual mode: {e}")

_maze_load_manual()
