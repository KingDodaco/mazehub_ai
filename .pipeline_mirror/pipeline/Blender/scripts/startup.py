import bpy
import os
import sys


def _redraw_timeline():
    for area in bpy.context.screen.areas:
        if area.type in ('TIMELINE', 'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'NLA_EDITOR'):
            area.tag_redraw()
    return None


def setup_scene():
    scene = bpy.context.scene

    start = os.environ.get("START_FRAME")
    end = os.environ.get("END_FRAME")
    fps = os.environ.get("FRAME_RATE")

    context_type = os.environ.get("MAZE_CONTEXT_TYPE", "")
    context_name = os.environ.get("MAZE_CONTEXT_NAME", "")
    context_path = os.environ.get("MAZE_CONTEXT_PATH", "")

    if context_path:
        blend_dir = os.path.join(context_path, "blender", "blend")
        if not os.path.exists(blend_dir):
            os.makedirs(blend_dir, exist_ok=True)
        scene.render.filepath = os.path.join(context_path, "blender", "render", "####")
        print(f"Render output: {context_path}/blender/render/####")

    if start and end:
        scene.frame_start = int(start)
        scene.frame_end = int(end)
        scene.frame_current = int(start)
        print(f"Frame range set: {start}-{end}")

    if fps:
        scene.render.fps = int(fps)
        print(f"Frame rate set: {fps} fps")

    pipeline = os.environ.get("MAZE_PIPELINE", "")
    if pipeline:
        scripts_dir = os.path.join(pipeline, "Blender", "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

    print(f"Blender launched for {context_type}: {context_name}")


def register_maze_tools():
    try:
        import maze_tools
        maze_tools.register()
        print("MazeHub tools registered")
    except Exception as e:
        print(f"Failed to register MazeHub tools: {e}")


print("Running startup script...")
setup_scene()
register_maze_tools()