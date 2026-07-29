import bpy
import os
import re
from bpy.props import StringProperty


def _get_context_info():
    context_type = os.environ.get("MAZE_CONTEXT_TYPE", "")
    context_name = os.environ.get("MAZE_CONTEXT_NAME", "")
    context_path = os.environ.get("MAZE_CONTEXT_PATH", "")
    return context_type, context_name, context_path


def _find_next_version(folder, base_name):
    pattern = re.compile(rf"^{re.escape(base_name)}_v(\d{{3}})\.usd$")
    max_version = 0
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            match = pattern.match(f)
            if match:
                max_version = max(max_version, int(match.group(1)))
    return max_version + 1


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

        usd_dir = os.path.join(context_path, "blender", "USD")
        os.makedirs(usd_dir, exist_ok=True)

        version = _find_next_version(usd_dir, context_name)
        filename = f"{context_name}_v{version:03d}.usd"
        filepath = os.path.join(usd_dir, filename)

        selected = context.selected_objects
        if not selected:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}

        bpy.ops.wm.usd_export(filepath=filepath, export_selected=True)

        self.report({'INFO'}, f"Exported: {filename}")
        return {'FINISHED'}


class MAZE_MT_menu(bpy.types.Menu):
    bl_label = "MAZE"
    bl_idname = "MAZE_MT_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator(MAZE_OT_export_usd.bl_idname, text="Export Selection as USD")


def draw_maze_menu(self, context):
    self.layout.menu(MAZE_MT_menu.bl_idname)


def register():
    bpy.utils.register_class(MAZE_OT_export_usd)
    bpy.utils.register_class(MAZE_MT_menu)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_maze_menu)


def unregister():
    bpy.utils.unregister_class(MAZE_OT_export_usd)
    bpy.utils.unregister_class(MAZE_MT_menu)
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_maze_menu)
