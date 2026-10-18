print("Loading Maya environment setup script...")

import maya.cmds as cmds
import os
import sys

scripts_dir = os.environ.get("MAZE_PIPELINE", "")
if scripts_dir:
    scripts_dir = os.path.join(scripts_dir, "Maya", "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

project_pipeline = os.environ.get("MAZE_PROJECT_PIPELINE", "")
if project_pipeline:
    project_scripts = os.path.join(project_pipeline, "Maya", "scripts")
    if os.path.isdir(project_scripts) and project_scripts not in sys.path:
        sys.path.insert(0, project_scripts)

import envPathResolver
envPathResolver.setup()

# Run the project-specific 123.py (if any) after this bootstrap so project
# settings always take priority while install tools still register.
if project_pipeline:
    project_123 = os.path.join(project_pipeline, "Maya", "scripts", "123.py")
    if os.path.isfile(project_123) and os.path.abspath(project_123) != os.path.abspath(__file__):
        print(f"Running project 123.py: {project_123}")
        try:
            with open(project_123, "r", encoding="utf-8") as f:
                exec(compile(f.read(), project_123, "exec"))
        except Exception as e:
            print(f"Failed to run project 123.py ({project_123}): {e}")

START_FRAME = os.environ.get("START_FRAME")
END_FRAME = os.environ.get("END_FRAME")
FRAME_RATE = os.environ.get("FRAME_RATE")
OPEN_FILE = os.environ.get("MAZE_OPEN_FILE")


def set_timeline():
    if not START_FRAME or not END_FRAME or not FRAME_RATE:
        print("Required environment variables (START_FRAME, END_FRAME, FRAME_RATE) are not set. Launching Maya with default timeline settings.")
        cmds.currentUnit(time='24fps')
        cmds.playbackOptions(animationStartTime=1001, animationEndTime=1240, minTime=1001, maxTime=1240, playbackSpeed=1)
    else:
        print(f"START_FRAME: {START_FRAME}, END_FRAME: {END_FRAME}, FRAME_RATE: {FRAME_RATE}")
        cmds.currentUnit(time='24fps')
        cmds.playbackOptions(animationStartTime=int(START_FRAME), animationEndTime=int(END_FRAME), minTime=int(START_FRAME), maxTime=int(END_FRAME), playbackSpeed=1)
        cmds.currentTime(int(START_FRAME), edit=True)


def open_file():
    if OPEN_FILE and os.path.isfile(OPEN_FILE):
        print(f"Opening file: {OPEN_FILE}")
        cmds.file(OPEN_FILE, open=True, force=True)
    elif OPEN_FILE:
        print(f"File not found: {OPEN_FILE}")


def register_maze_tools():
    try:
        import maze_tools
        print("MazeHub tools registered")
    except Exception as e:
        print(f"Failed to register MazeHub tools: {e}")


cmds.evalDeferred(open_file)
cmds.evalDeferred(set_timeline)
cmds.evalDeferred(register_maze_tools)
