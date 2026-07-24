import maya.cmds as cmds
import os

print("Setting timeline settings")

def set_timeline():

    if "START_FRAME" not in os.environ or "END_FRAME" not in os.environ or "FRAME_RATE" not in os.environ:
        print("Required environment variables (START_FRAME, END_FRAME, FRAME_RATE) are not set. Launching Maya with default timeline settings.")
        cmds.currentUnit(time='24fps')
        cmds.playbackOptions(animationStartTime=1001, animationEndTime=1240, minTime=1001, maxTime=1240, playbackSpeed=1)
    else:
        print(f"START_FRAME: {os.environ.get('START_FRAME')}, END_FRAME: {os.environ.get('END_FRAME')}, FRAME_RATE: {os.environ.get('FRAME_RATE')}")
        cmds.currentUnit(time='24fps')
        cmds.playbackOptions(animationStartTime=int(os.environ.get("START_FRAME")), animationEndTime=int(os.environ.get("END_FRAME")), minTime=int(os.environ.get("START_FRAME")), maxTime=int(os.environ.get("END_FRAME")), playbackSpeed=1)
        cmds.currentTime(int(os.environ.get("START_FRAME")), edit=True)

# Use evalDeferred to ensure Maya is fully loaded before executing
cmds.evalDeferred(set_timeline)