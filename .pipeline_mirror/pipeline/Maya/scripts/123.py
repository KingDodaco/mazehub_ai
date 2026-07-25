import maya.cmds as cmds
import os
import sys

scripts_dir = os.environ.get("MAZE_PIPELINE", "")
if scripts_dir:
    scripts_dir = os.path.join(scripts_dir, "Maya", "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

import envPathResolver
envPathResolver.setup()

START_FRAME = os.environ.get("START_FRAME")
END_FRAME = os.environ.get("END_FRAME")
FRAME_RATE = os.environ.get("FRAME_RATE")


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


# Use evalDeferred to ensure Maya is fully loaded before executing
cmds.evalDeferred(set_timeline)
