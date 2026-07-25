import os
import re
import sys

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om2
    _IN_MAYA = True
except ImportError:
    _IN_MAYA = False


PLUGIN_NAME = "envPathResolver.py"
NODE_TYPE_NAME = "envPathResolver"
NODE_ID = om2.MTypeId(0x100001) if _IN_MAYA else None


def _resolve_env_vars(path):
    def _replace(m):
        return os.environ.get(m.group(1) or m.group(2), m.group(0))
    resolved = re.sub(r'\$(\w+)|\%(\w+)\%', _replace, path)
    resolved = resolved.replace('/', os.sep)
    return resolved


class EnvPathResolverNode(om2.MPxNode):
    rawPath = None
    resolvedPath = None

    @classmethod
    def creator(cls):
        return cls()

    @classmethod
    def initialize(cls):
        rawAttr = om2.MFnTypedAttribute()
        cls.rawPath = rawAttr.create("rawPath", "rp", om2.MFnData.kString)
        rawAttr.setWritable(True)
        rawAttr.setStorable(True)
        rawAttr.setKeyable(True)
        cls.addAttribute(cls.rawPath)

        resAttr = om2.MFnTypedAttribute()
        cls.resolvedPath = resAttr.create("resolvedPath", "rsp", om2.MFnData.kString)
        resAttr.setWritable(False)
        resAttr.setStorable(False)
        resAttr.setKeyable(False)
        cls.addAttribute(cls.resolvedPath)

        cls.attributeAffects(cls.rawPath, cls.resolvedPath)

    def compute(self, plug, dataBlock):
        if plug != self.resolvedPath:
            return om2.kUnknownParameter

        raw_data = dataBlock.inputValue(self.rawPath)
        raw_str = raw_data.asString()
        resolved = _resolve_env_vars(raw_str)

        out_data = dataBlock.outputValue(self.resolvedPath)
        out_data.setString(resolved)
        dataBlock.setClean(plug)

        return om2.kSuccess


def _plugin_path():
    pipeline = os.environ.get("MAZE_PIPELINE", "")
    if pipeline:
        return os.path.join(pipeline, "Maya", "scripts", PLUGIN_NAME)
    return PLUGIN_NAME


def setup():
    if not _IN_MAYA:
        return
    if not cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        cmds.loadPlugin(_plugin_path())


def initializePlugin(plugin):
    mfn_plugin = om2.MFnPlugin(plugin, "MazeHub", "1.0")
    mfn_plugin.registerNode(NODE_TYPE_NAME, NODE_ID, EnvPathResolverNode.creator, EnvPathResolverNode.initialize)


def uninitializePlugin(plugin):
    mfn_plugin = om2.MFnPlugin(plugin)
    mfn_plugin.deregisterNode(NODE_ID)
