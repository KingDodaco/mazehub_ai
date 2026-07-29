import bpy
import os
import re
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
    bpy.utils.register_class(MAZE_OT_export_usd_dialog)
    bpy.utils.register_class(MAZE_MT_menu)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_maze_menu)


def unregister():
    bpy.utils.unregister_class(MAZE_OT_export_usd)
    bpy.utils.unregister_class(MAZE_OT_export_usd_dialog)
    bpy.utils.unregister_class(MAZE_MT_menu)
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_maze_menu)
