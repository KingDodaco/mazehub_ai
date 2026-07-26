import os
import re
import sys

try:
    import maya.cmds as cmds
except ImportError:
    cmds = None

try:
    import maya.OpenMaya as om
    import maya.OpenMayaMPx as ompx
except ImportError:
    try:
        import maya.api.OpenMaya as om
        import maya.api.OpenMayaMPx as ompx
    except ImportError:
        om = None
        ompx = None

_IN_MAYA = cmds is not None and om is not None and ompx is not None


PLUGIN_NAME = "envPathResolver.py"
NODE_TYPE_NAME = "envPathResolver"
NODE_ID = om.MTypeId(0x100001) if _IN_MAYA else None


def _resolve_env_vars(path):
    def _replace(m):
        return os.environ.get(m.group(1) or m.group(2), m.group(0))
    resolved = re.sub(r'\$(\w+)|\%(\w+)\%', _replace, path)
    resolved = resolved.replace('/', os.sep)
    return resolved


if _IN_MAYA:
    class EnvPathResolverNode(ompx.MPxNode):
        rawPath = None
        resolvedPath = None

        @classmethod
        def creator(cls):
            return cls()

        @classmethod
        def initialize(cls):
            rawAttr = om.MFnTypedAttribute()
            cls.rawPath = rawAttr.create("rawPath", "rp", om.MFnData.kString)
            rawAttr.setWritable(True)
            rawAttr.setStorable(True)
            rawAttr.setKeyable(True)
            cls.addAttribute(cls.rawPath)

            resAttr = om.MFnTypedAttribute()
            cls.resolvedPath = resAttr.create("resolvedPath", "rsp", om.MFnData.kString)
            resAttr.setWritable(False)
            resAttr.setStorable(False)
            resAttr.setKeyable(False)
            cls.addAttribute(cls.resolvedPath)

            cls.attributeAffects(cls.rawPath, cls.resolvedPath)

        def compute(self, plug, dataBlock):
            if plug != self.resolvedPath:
                return om.kUnknownParameter

            raw_data = dataBlock.inputValue(self.rawPath)
            raw_str = raw_data.asString()
            resolved = _resolve_env_vars(raw_str)

            out_data = dataBlock.outputValue(self.resolvedPath)
            out_data.setString(resolved)
            dataBlock.setClean(plug)

            return om.kSuccess
else:
    class EnvPathResolverNode(object):
        pass


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


def _get_mfn_plugin(plugin):
    if ompx is not None:
        try:
            return ompx.MFnPlugin(plugin)
        except TypeError:
            pass

    raise RuntimeError("Unable to create an MFnPlugin instance for this Maya environment.")


def initializePlugin(plugin):
    mfn_plugin = _get_mfn_plugin(plugin)
    mfn_plugin.registerNode(NODE_TYPE_NAME, NODE_ID, EnvPathResolverNode.creator, EnvPathResolverNode.initialize)


def uninitializePlugin(plugin):
    mfn_plugin = _get_mfn_plugin(plugin)
    mfn_plugin.deregisterNode(NODE_ID)
