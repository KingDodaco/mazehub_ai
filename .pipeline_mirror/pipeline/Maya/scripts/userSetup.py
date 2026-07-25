import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

import envPathResolver
envPathResolver.setup()

import maya.cmds as cmds

START_FRAME = os.environ.get("START_FRAME")
END_FRAME = os.environ.get("END_FRAME")
FRAME_RATE = os.environ.get("FRAME_RATE")

if START_FRAME and END_FRAME and FRAME_RATE:
    def _set_timeline():
        cmds.currentUnit(time='24fps')
        start = int(START_FRAME)
        end = int(END_FRAME)
        cmds.playbackOptions(
            animationStartTime=start, animationEndTime=end,
            minTime=start, maxTime=end, playbackSpeed=1,
        )
        cmds.currentTime(start, edit=True)
    cmds.evalDeferred(_set_timeline)
