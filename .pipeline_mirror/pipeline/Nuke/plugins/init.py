import nuke
import os

def set_project_from_env():
    start_frame = "1001"
    end_frame = "1240"
    fps_val = "24"
    
    if "START_FRAME" in os.environ:
        start_frame = os.environ.get("START_FRAME")
    if "END_FRAME" in os.environ:
        end_frame = os.environ.get("END_FRAME")
    if "FRAME_RATE" in os.environ:
        fps_val = os.environ.get("FRAME_RATE")
    

    nuke.root()['first_frame'].setValue(int(start_frame))
    nuke.root()['last_frame'].setValue(int(end_frame))
    nuke.root()['fps'].setValue(int(fps_val))

nuke.addOnCreate(set_project_from_env, nodeClass='Root')

nuke.pluginAddPath("./plugins/CGDenoiser")

nuke.pluginAddPath('./plugins/MagicTools')

nuke.pluginAddPath('./plugins/FlareSim/Nuke15_2')

nuke.pluginAddPath('./plugins/pixelfudger3')

nuke.pluginAddPath('./gizmos')