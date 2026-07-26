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
