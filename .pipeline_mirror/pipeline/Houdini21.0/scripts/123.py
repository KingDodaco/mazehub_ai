import hou
import os

print("Setting timeline settings")

if "START_FRAME" not in os.environ or "END_FRAME" not in os.environ or "FRAME_RATE" not in os.environ:
    print("Required environment variables (START_FRAME, END_FRAME, FRAME_RATE) are not set. Launching Houdini with default timeline settings.")
    
    hou.setFps(24)
    
    hou.playbar.setFrameRange(1001, 1240)
    hou.playbar.setPlaybackRange(1001, 1240)

    hou.setFrame(1001)

else:
    print(f"START_FRAME: {os.environ.get('START_FRAME')}, END_FRAME: {os.environ.get('END_FRAME')}, FRAME_RATE: {os.environ.get('FRAME_RATE')}")

    hou.setFps(int(os.environ.get("FRAME_RATE")))
    
    hou.playbar.setFrameRange(int(os.environ.get("START_FRAME")), int(os.environ.get("END_FRAME")))
    hou.playbar.setPlaybackRange(int(os.environ.get("START_FRAME")), int(os.environ.get("END_FRAME")))

    hou.setFrame(int(os.environ.get("START_FRAME")))

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
