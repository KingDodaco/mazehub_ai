print("Loading Maya environment setup script...")

import maya.cmds as cmds
import os
import runpy
import sys
import tempfile
import traceback

# Output during Maya's -command goes to the Output Window, not the Script
# Editor, so every step is also written to a log file for troubleshooting.
LOG_PATH = os.path.join(tempfile.gettempdir(), "mazehub_maya.log")
try:
    open(LOG_PATH, "w", encoding="utf-8").close()
except OSError:
    pass


def _log(msg):
    line = f"[MazeHub] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _log_exc(msg):
    _log(f"{msg}\n{traceback.format_exc()}")


_log(f"bootstrap: {globals().get('__file__', '<unknown>')}")
_log(f"MAZE_PIPELINE={os.environ.get('MAZE_PIPELINE', '')}")
_log(f"MAZE_PROJECT_PIPELINE={os.environ.get('MAZE_PROJECT_PIPELINE', '')}")

scripts_dir = os.environ.get("MAZE_PIPELINE", "")
if scripts_dir:
    scripts_dir = os.path.join(scripts_dir, "Maya", "scripts")
    _log(f"install scripts dir: {scripts_dir}")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

project_pipeline = os.environ.get("MAZE_PROJECT_PIPELINE", "")
project_scripts = ""
if project_pipeline:
    project_scripts = os.path.join(project_pipeline, "Maya", "scripts")
    if os.path.isdir(project_scripts):
        _log(f"project scripts dir: {project_scripts}")
        if project_scripts not in sys.path:
            sys.path.insert(0, project_scripts)
    else:
        _log(f"project scripts dir missing: {project_scripts}")
        project_scripts = ""
else:
    _log("MAZE_PROJECT_PIPELINE is not set - skipping project scripts")

try:
    import envPathResolver
    envPathResolver.setup()
    _log("envPathResolver loaded")
except Exception:
    _log_exc("Failed to load envPathResolver")

START_FRAME = os.environ.get("START_FRAME")
END_FRAME = os.environ.get("END_FRAME")
FRAME_RATE = os.environ.get("FRAME_RATE")
OPEN_FILE = os.environ.get("MAZE_OPEN_FILE")

MENU_RETRIES = 20


def set_timeline():
    try:
        if not START_FRAME or not END_FRAME or not FRAME_RATE:
            print("Required environment variables (START_FRAME, END_FRAME, FRAME_RATE) are not set. Launching Maya with default timeline settings.")
            cmds.currentUnit(time='24fps')
            cmds.playbackOptions(animationStartTime=1001, animationEndTime=1240, minTime=1001, maxTime=1240, playbackSpeed=1)
        else:
            print(f"START_FRAME: {START_FRAME}, END_FRAME: {END_FRAME}, FRAME_RATE: {FRAME_RATE}")
            cmds.currentUnit(time='24fps')
            cmds.playbackOptions(animationStartTime=int(START_FRAME), animationEndTime=int(END_FRAME), minTime=int(START_FRAME), maxTime=int(END_FRAME), playbackSpeed=1)
            cmds.currentTime(int(START_FRAME), edit=True)
        _log("timeline set")
    except Exception:
        _log_exc("Failed to set timeline")


def open_file():
    try:
        if OPEN_FILE and os.path.isfile(OPEN_FILE):
            _log(f"Opening file: {OPEN_FILE}")
            cmds.file(OPEN_FILE, open=True, force=True)
        elif OPEN_FILE:
            _log(f"File not found: {OPEN_FILE}")
    except Exception:
        _log_exc(f"Failed to open file: {OPEN_FILE}")


def register_maze_tools(retries=MENU_RETRIES):
    # The menu is parented to the main window, which may not exist yet when
    # the startup command runs; wait for it instead of failing.
    if not cmds.window("MayaWindow", exists=True):
        if retries > 0:
            cmds.evalDeferred(lambda: register_maze_tools(retries - 1), lowestPriority=True)
        else:
            _log("MayaWindow never appeared - MAZE menu not created")
        return
    try:
        import maze_tools
        maze_tools.create_maze_menu()
        _log(f"MazeHub tools registered ({maze_tools.__file__})")
    except Exception:
        _log_exc("Failed to register MazeHub tools")


def run_project_123():
    # Runs last so project settings take priority, in its own namespace so it
    # cannot break the install bootstrap.
    if not project_scripts:
        return
    project_123 = os.path.join(project_scripts, "123.py")
    here = globals().get("__file__")
    if here and os.path.abspath(project_123) == os.path.abspath(here):
        return
    if not os.path.isfile(project_123):
        _log(f"No project 123.py found at: {project_123}")
        return
    _log(f"Running project 123.py: {project_123}")
    try:
        runpy.run_path(project_123, run_name="__maze_project_123__")
        _log("project 123.py finished")
    except KeyboardInterrupt:
        raise
    except BaseException:
        _log_exc(f"Failed to run project 123.py ({project_123})")


cmds.evalDeferred(open_file)
cmds.evalDeferred(set_timeline)
cmds.evalDeferred(register_maze_tools)
cmds.evalDeferred(run_project_123, lowestPriority=True)
_log(f"bootstrap queued startup steps (log: {LOG_PATH})")
