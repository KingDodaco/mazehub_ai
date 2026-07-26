import maya.cmds as cmds

PLUGIN_NAME = "envPathResolver.py"


def _ensure_plugin():
    if not cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        cmds.loadPlugin(PLUGIN_NAME)


def connect_file_texture(file_node, raw_path, fallback=""):
    """Create envPathResolver connected to file node's fileTextureName."""
    _ensure_plugin()
    resolver = cmds.createNode("envPathResolver", name=file_node + "_envResolver")
    cmds.setAttr(resolver + ".rawPath", raw_path, type="string")
    cmds.connectAttr(resolver + ".resolvedPath", file_node + ".fileTextureName", force=True)


def create_env_reference(raw_path, namespace=""):
    """Create a reference using a raw path with env var references."""
    _ensure_plugin()
    resolver = cmds.createNode("envPathResolver", name="ref_envResolver")
    cmds.setAttr(resolver + ".rawPath", raw_path, type="string")
    resolved = cmds.getAttr(resolver + ".resolvedPath")
    ref_node = cmds.file(resolved, reference=True, namespace=namespace, returnNewNodes=True)
    return ref_node


def wrap_existing(file_node):
    """Wrap an existing file node's texture path through envPathResolver."""
    _ensure_plugin()
    current = cmds.getAttr(file_node + ".fileTextureName")
    if not current:
        return
    resolver = cmds.createNode("envPathResolver", name=file_node + "_envResolver")
    cmds.setAttr(resolver + ".rawPath", current, type="string")
    cmds.connectAttr(resolver + ".resolvedPath", file_node + ".fileTextureName", force=True)
