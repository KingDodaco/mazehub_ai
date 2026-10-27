import bpy
import os
import runpy
import sys
import tempfile
import traceback

# Blender's console is hidden on Windows, so every step is also written to a
# log file for troubleshooting.
LOG_PATH = os.path.join(tempfile.gettempdir(), "mazehub_blender.log")
# Clear once per Blender session, so a project copy of this script appends.
if os.environ.get("MAZE_BLENDER_LOG_STARTED") != "1":
    os.environ["MAZE_BLENDER_LOG_STARTED"] = "1"
    try:
        open(LOG_PATH, "w", encoding="utf-8").close()
    except OSError:
        pass


def _log(msg):
    line = f"[MAZE] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _log_exc(msg):
    _log(f"{msg}\n{traceback.format_exc()}")


def _redraw_timeline():
    for area in bpy.context.screen.areas:
        if area.type in ('TIMELINE', 'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'NLA_EDITOR'):
            area.tag_redraw()
    return None


def setup_paths():
    # Install scripts take priority so a stray maze_tools.py in a project
    # cannot hide the install tools; project scripts stay importable.
    project_pipeline = os.environ.get("MAZE_PROJECT_PIPELINE", "")
    if project_pipeline:
        project_scripts = os.path.join(project_pipeline, "Blender", "scripts")
        if os.path.isdir(project_scripts) and project_scripts not in sys.path:
            sys.path.insert(0, project_scripts)
            _log(f"project scripts dir: {project_scripts}")

    pipeline = os.environ.get("MAZE_PIPELINE", "")
    scripts_dir = os.path.join(pipeline, "Blender", "scripts") if pipeline else ""
    if not scripts_dir:
        scripts_dir = os.path.dirname(os.path.abspath(globals().get("__file__", "")))
    if scripts_dir in sys.path:
        sys.path.remove(scripts_dir)
    sys.path.insert(0, scripts_dir)
    _log(f"install scripts dir: {scripts_dir}")


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
        _log(f"Render output: {context_path}/blender/render/####")

    if start and end:
        scene.frame_start = int(start)
        scene.frame_end = int(end)
        scene.frame_current = int(start)
        _log(f"Frame range set: {start}-{end}")

    if fps:
        scene.render.fps = int(fps)
        _log(f"Frame rate set: {fps} fps")

    _log(f"Blender launched for {context_type}: {context_name}")


def register_maze_tools():
    try:
        import maze_tools
        maze_tools.register()
        _log(f"MazeHub tools registered ({maze_tools.__file__})")
    except Exception:
        _log_exc("Failed to register MazeHub tools")


# Run the project's own startup.py (if any) last so project settings take priority,
# in its own namespace so it cannot break the install setup above.
def _maze_run_project_script():
    project_pipeline = os.environ.get("MAZE_PROJECT_PIPELINE", "")
    if not project_pipeline:
        return
    path = os.path.join(project_pipeline, "Blender", "scripts", "startup.py")
    if not os.path.isfile(path):
        return
    if os.path.abspath(path) == os.path.abspath(globals().get("__file__", "")):
        return
    _log(f"Running project startup.py: {path}")
    try:
        runpy.run_path(path, run_name="__maze_project_startup__")
        _log("project startup.py finished")
    except Exception:
        _log_exc(f"Failed to run project startup.py ({path})")


_log(f"Running startup script: {globals().get('__file__', '<unknown>')}")
_log(f"blend file: {bpy.data.filepath or '<none>'}")
setup_paths()
try:
    setup_scene()
except Exception:
    _log_exc("Failed to set up scene")
register_maze_tools()
_maze_run_project_script()
