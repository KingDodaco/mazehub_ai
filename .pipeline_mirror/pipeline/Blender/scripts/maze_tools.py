import bpy
import datetime
import getpass
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from urllib.parse import quote
from bpy.props import StringProperty, EnumProperty, BoolProperty


def _get_context_info():
    context_type = os.environ.get("MAZE_CONTEXT_TYPE", "")
    context_name = os.environ.get("MAZE_CONTEXT_NAME", "")
    context_path = os.environ.get("MAZE_CONTEXT_PATH", "")
    return context_type, context_name, context_path


def _get_existing_descriptors(usd_dir, context_name):
    descriptors = set()
    if not os.path.isdir(usd_dir):
        return descriptors
    pattern = re.compile(rf"^{re.escape(context_name)}_(.+)_v\d{{3}}\.usd$")
    for f in os.listdir(usd_dir):
        match = pattern.match(f)
        if match:
            descriptors.add(match.group(1))
    return sorted(descriptors)


def _find_next_version(folder, context_name, descriptor):
    if descriptor:
        base = f"{context_name}_{descriptor}"
    else:
        base = context_name
    pattern = re.compile(rf"^{re.escape(base)}_v(\d{{3}})\.usd$")
    max_version = 0
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            match = pattern.match(f)
            if match:
                max_version = max(max_version, int(match.group(1)))
    return max_version + 1


_items_cache = []


class MAZE_OT_export_usd(bpy.types.Operator):
    bl_idname = "maze.export_usd"
    bl_label = "Export Selection as USD"
    bl_description = "Export the selected object as a USD file to the context's blender/USD folder"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and len(context.selected_objects) > 0

    def execute(self, context):
        context_type, context_name, context_path = _get_context_info()

        if not context_path:
            self.report({'ERROR'}, "No MAZE_CONTEXT_PATH set. Launch from MazeHub with a context.")
            return {'CANCELLED'}

        if not context_name:
            self.report({'ERROR'}, "No MAZE_CONTEXT_NAME set. Launch from MazeHub with a context.")
            return {'CANCELLED'}

        global _items_cache
        usd_dir = os.path.join(context_path, "blender", "USD")
        os.makedirs(usd_dir, exist_ok=True)
        _items_cache = _get_existing_descriptors(usd_dir, context_name)

        bpy.ops.maze.export_usd_dialog('INVOKE_DEFAULT')
        return {'FINISHED'}


class MAZE_OT_export_usd_dialog(bpy.types.Operator):
    bl_idname = "maze.export_usd_dialog"
    bl_label = "Export USD"
    bl_description = "Configure USD export settings"

    use_existing: BoolProperty(
        name="Use Existing Descriptor",
        default=False,
    )

    existing_descriptor: EnumProperty(
        name="Descriptor",
        description="Select an existing descriptor",
        items=lambda self, context: [("", "(none)", "")] + [(d, d, "") for d in _items_cache],
    )

    descriptor: StringProperty(
        name="New Descriptor",
        description="Enter a new descriptor name",
        default="",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout

        if _items_cache:
            layout.prop(self, "use_existing")
            if self.use_existing:
                layout.prop(self, "existing_descriptor")
            else:
                layout.prop(self, "descriptor")
        else:
            layout.prop(self, "descriptor")

    def execute(self, context):
        context_type, context_name, context_path = _get_context_info()

        if self.use_existing and self.existing_descriptor:
            descriptor = self.existing_descriptor
        else:
            descriptor = self.descriptor.strip()

        usd_dir = os.path.join(context_path, "blender", "USD")
        os.makedirs(usd_dir, exist_ok=True)

        version = _find_next_version(usd_dir, context_name, descriptor)

        if descriptor:
            filename = f"{context_name}_{descriptor}_v{version:03d}.usd"
        else:
            filename = f"{context_name}_v{version:03d}.usd"

        filepath = os.path.join(usd_dir, filename)

        bpy.ops.wm.usd_export(filepath=filepath)

        self.report({'INFO'}, f"Exported: {filename}")
        return {'FINISHED'}


def _playblast_directory():
    _, _, context_path = _get_context_info()
    if context_path:
        work_dir = os.path.join(context_path, "blender")
    else:
        job = os.environ.get("JOB", "")
        if job and os.path.basename(os.path.normpath(job)).lower() in ("houdini", "maya", "nuke"):
            job = os.path.dirname(os.path.normpath(job))
        if job:
            work_dir = job if os.path.basename(os.path.normpath(job)).lower() == "blender" else os.path.join(job, "blender")
        else:
            work_dir = os.path.dirname(bpy.data.filepath)
    return os.path.join(work_dir, "flipbooks")


def _next_playblast_path(extension, scene_path=None):
    scene_path = scene_path or bpy.data.filepath
    scene_name = os.path.splitext(os.path.basename(scene_path))[0]
    base = re.sub(r"_v\d+$", "", scene_name) or "playblast"
    output_dir = _playblast_directory()
    os.makedirs(output_dir, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(base)}_v(\d{{3}}){re.escape(extension)}$", re.IGNORECASE)
    versions = []
    for filename in os.listdir(output_dir):
        match = pattern.match(filename)
        if match:
            versions.append(int(match.group(1)))
    return os.path.join(output_dir, f"{base}_v{max(versions, default=0) + 1:03d}{extension}")


def _find_ffmpeg():
    candidates = []
    configured = os.environ.get("MAZE_FFMPEG", "")
    if configured:
        candidates.append(configured)
    for root in (os.environ.get("MAZE_PIPELINE", ""), os.environ.get("HFS", "")):
        if root:
            for name in ("hffmpeg.exe", "ffmpeg.exe", "hffmpeg", "ffmpeg"):
                candidates.append(os.path.join(root, "Houdini", "bin", name) if root == os.environ.get("MAZE_PIPELINE") else os.path.join(root, "bin", name))
    for name in ("hffmpeg", "ffmpeg"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        found = shutil.which(candidate) if os.path.dirname(candidate) == "" else candidate
        if found and os.path.isfile(found):
            return found
    return None


def _render_opengl(context, animation, write_still=False):
    windows = list(context.window_manager.windows)
    if context.window and context.window not in windows:
        windows.insert(0, context.window)
    for window in windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((item for item in area.regions if item.type == "WINDOW"), None)
            if not region:
                continue
            with context.temp_override(window=window, area=area, region=region):
                bpy.ops.render.opengl(animation=animation, write_still=write_still, view_context=True)
            return
    raise RuntimeError("Open a 3D Viewport before creating a playblast.")


def _render_settings_snapshot(render):
    snapshot = {
        "filepath": render.filepath,
        "file_format": render.image_settings.file_format,
        "color_mode": render.image_settings.color_mode,
        "resolution_x": render.resolution_x,
        "resolution_y": render.resolution_y,
        "resolution_percentage": render.resolution_percentage,
        "use_file_extension": render.use_file_extension,
    }
    if hasattr(render, "ffmpeg"):
        snapshot["ffmpeg_format"] = render.ffmpeg.format
        snapshot["ffmpeg_codec"] = render.ffmpeg.codec
        snapshot["ffmpeg_quality"] = render.ffmpeg.constant_rate_factor
    return snapshot


def _restore_render_settings(render, snapshot):
    render.filepath = snapshot["filepath"]
    render.image_settings.file_format = snapshot["file_format"]
    render.image_settings.color_mode = snapshot["color_mode"]
    render.resolution_x = snapshot["resolution_x"]
    render.resolution_y = snapshot["resolution_y"]
    render.resolution_percentage = snapshot["resolution_percentage"]
    render.use_file_extension = snapshot["use_file_extension"]
    if "ffmpeg_format" in snapshot:
        render.ffmpeg.format = snapshot["ffmpeg_format"]
        render.ffmpeg.codec = snapshot["ffmpeg_codec"]
        render.ffmpeg.constant_rate_factor = snapshot["ffmpeg_quality"]


def _configure_playblast_render(render, filepath, file_format):
    render.filepath = filepath
    render.image_settings.file_format = file_format
    render.image_settings.color_mode = "RGB"
    render.resolution_x = 1920
    render.resolution_y = 1080
    render.resolution_percentage = 100
    render.use_file_extension = True


def _render_playblast_video(context, output):
    scene = context.scene
    render = scene.render
    snapshot = _render_settings_snapshot(render)
    original_frame = scene.frame_current
    try:
        _configure_playblast_render(render, os.path.splitext(output)[0], "PNG")
        native_ffmpeg = False
        try:
            render.image_settings.file_format = "FFMPEG"
            native_ffmpeg = True
        except (TypeError, ValueError):
            pass
        if native_ffmpeg:
            render.ffmpeg.format = "MPEG4"
            render.ffmpeg.codec = "H264"
            render.ffmpeg.constant_rate_factor = "MEDIUM"
            _render_opengl(context, animation=True)
        else:
            ffmpeg = _find_ffmpeg()
            if not ffmpeg:
                raise RuntimeError("This Blender build has no FFmpeg encoder and no system or Houdini FFmpeg executable was found.")
            with tempfile.TemporaryDirectory(prefix="maze_playblast_") as frame_dir:
                _configure_playblast_render(render, os.path.join(frame_dir, "frame_####"), "PNG")
                _render_opengl(context, animation=True)
                fps = render.fps / render.fps_base
                command = [
                    ffmpeg, "-y", "-framerate", f"{fps:.6g}",
                    "-start_number", str(scene.frame_start),
                    "-i", os.path.join(frame_dir, "frame_%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-preset", "medium", output,
                ]
                options = {"capture_output": True, "text": True}
                if os.name == "nt":
                    options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                result = subprocess.run(command, **options)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or f"FFmpeg exited with code {result.returncode}")
        if not os.path.isfile(output):
            raise RuntimeError(f"Playblast did not create {output}")
    finally:
        _restore_render_settings(render, snapshot)
        scene.frame_set(original_frame)
    return output


def _render_playblast_frame(context, output):
    scene = context.scene
    render = scene.render
    snapshot = _render_settings_snapshot(render)
    original_frame = scene.frame_current
    try:
        _configure_playblast_render(render, os.path.splitext(output)[0], "PNG")
        _render_opengl(context, animation=False, write_still=True)
        if not os.path.isfile(output):
            raise RuntimeError(f"Frame playblast did not create {output}")
    finally:
        _restore_render_settings(render, snapshot)
        scene.frame_set(original_frame)
    return output


def _get_dailies_webhook():
    settings = {}
    project_root = os.environ.get("MAZE_PROJECT_ROOT", "")
    settings_paths = [os.path.expanduser("~/.config/mazehub/user_settings.json")]
    if project_root:
        settings_paths.append(os.path.join(project_root, "pipeline", "mazehub", "shared_settings.json"))
    for settings_path in settings_paths:
        try:
            with open(settings_path, "r") as settings_file:
                settings.update(json.load(settings_file))
        except (OSError, ValueError):
            pass
    return os.environ.get("MAZE_DAILIES_WEBHOOK") or settings.get("dailies_webhook_url", "")


def _playblast_link(output):
    web_root = os.environ.get(
        "MAZE_ONEDRIVE_ROOT",
        "https://livebournemouthac.sharepoint.com/sites/FMP2/Shared%20Documents/PROJECT/MAZE/",
    )
    project_root = os.environ.get("MAZE_PROJECT_ROOT", "")
    if project_root:
        try:
            relative_path = os.path.relpath(os.path.abspath(output), os.path.abspath(project_root))
            if not relative_path.startswith(".."):
                return web_root.rstrip("/") + "/" + quote(relative_path.replace("\\", "/"), safe="/")
        except ValueError:
            pass
    return output.replace("\\", "/")


def _post_playblast(output, comment="", media_type="video"):
    webhook_url = _get_dailies_webhook()
    if not webhook_url:
        return False, "No dailies webhook is configured in MazeHub settings."
    scene_path = bpy.data.filepath
    scene_name = os.path.basename(scene_path) if scene_path else ""
    context_name = os.environ.get("MAZE_CONTEXT_NAME") or os.path.splitext(scene_name)[0] or os.path.basename(output)
    filename = os.path.splitext(os.path.basename(output))[0]
    try:
        username = getpass.getuser()
    except Exception:
        username = os.environ.get("USER", os.environ.get("USERNAME", "Unknown"))
    body = [
        {"type": "TextBlock", "text": f"{context_name} - {filename}", "wrap": True, "weight": "Bolder", "size": "Large"},
        {"type": "TextBlock", "text": scene_name, "wrap": True, "size": "Small", "isSubtle": True},
        {"type": "TextBlock", "text": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "wrap": True},
        {"type": "TextBlock", "text": username, "wrap": True},
    ]
    if comment:
        body.append({"type": "TextBlock", "text": comment, "wrap": True})
    media_url = _playblast_link(output)
    if media_type == "video":
        body.append({"type": "Media", "sources": [{"url": media_url, "mimeType": "video/mp4"}]})
    else:
        body.append({"type": "Image", "url": media_url, "style": "default"})
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": body,
            },
        }],
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 200 <= response.status < 300:
                return True, "Posted to dailies."
            return False, f"Dailies webhook returned HTTP {response.status}."
    except Exception as error:
        return False, f"Dailies submission failed: {error}"


class MAZE_OT_playblast(bpy.types.Operator):
    bl_idname = "maze.playblast"
    bl_label = "Playblast"
    bl_description = "Render the playback range from the active 3D Viewport and send it to dailies"

    note: StringProperty(name="Note", default="")

    def invoke(self, context, event):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the Blender file before creating a playblast.")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        self.layout.prop(self, "note")

    def execute(self, context):
        try:
            output = _next_playblast_path(".mp4")
            _render_playblast_video(context, output)
        except Exception as error:
            self.report({'ERROR'}, f"Playblast failed: {error}")
            return {'CANCELLED'}
        posted, message = _post_playblast(output, self.note, "video")
        level = {'INFO'} if posted else {'WARNING'}
        self.report(level, f"Saved {os.path.basename(output)}. {message}")
        return {'FINISHED'}


class MAZE_OT_playblast_frame(bpy.types.Operator):
    bl_idname = "maze.playblast_frame"
    bl_label = "Playblast Frame"
    bl_description = "Render the current frame from the active 3D Viewport and send it to dailies"

    note: StringProperty(name="Note", default="")

    def invoke(self, context, event):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the Blender file before creating a playblast.")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        self.layout.prop(self, "note")

    def execute(self, context):
        try:
            output = _next_playblast_path(".png")
            _render_playblast_frame(context, output)
        except Exception as error:
            self.report({'ERROR'}, f"Frame playblast failed: {error}")
            return {'CANCELLED'}
        posted, message = _post_playblast(output, self.note, "image")
        level = {'INFO'} if posted else {'WARNING'}
        self.report(level, f"Saved {os.path.basename(output)}. {message}")
        return {'FINISHED'}


class MAZE_MT_menu(bpy.types.Menu):
    bl_label = "MAZE"
    bl_idname = "MAZE_MT_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator(MAZE_OT_export_usd.bl_idname, text="Export Selection as USD")
        layout.separator()
        layout.operator(MAZE_OT_playblast.bl_idname, text="Playblast")
        layout.operator(MAZE_OT_playblast_frame.bl_idname, text="Playblast Frame")


def draw_maze_menu(self, context):
    self.layout.menu(MAZE_MT_menu.bl_idname)


def register():
    bpy.utils.register_class(MAZE_OT_export_usd)
    bpy.utils.register_class(MAZE_OT_export_usd_dialog)
    bpy.utils.register_class(MAZE_OT_playblast)
    bpy.utils.register_class(MAZE_OT_playblast_frame)
    bpy.utils.register_class(MAZE_MT_menu)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_maze_menu)


def unregister():
    bpy.utils.unregister_class(MAZE_OT_playblast_frame)
    bpy.utils.unregister_class(MAZE_OT_playblast)
    bpy.utils.unregister_class(MAZE_OT_export_usd)
    bpy.utils.unregister_class(MAZE_OT_export_usd_dialog)
    bpy.utils.unregister_class(MAZE_MT_menu)
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_maze_menu)
