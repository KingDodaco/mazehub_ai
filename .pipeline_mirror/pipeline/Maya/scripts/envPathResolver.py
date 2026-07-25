import os
import re
import sys

try:
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


def _register_plugin():
    if not _IN_MAYA:
        return
    plugin = om2.MFnPlugin(om2.MGlobal.getPluginName(), "MazeHub")
    try:
        plugin.registerNode(NODE_TYPE_NAME, NODE_ID, EnvPathResolverNode.creator, EnvPathResolverNode.initialize)
    except RuntimeError as e:
        if "already registered" not in str(e):
            raise


def _deregister_plugin():
    if not _IN_MAYA:
        return
    plugin = om2.MFnPlugin(om2.MGlobal.getPluginName())
    try:
        plugin.deregisterNode(NODE_ID)
    except RuntimeError:
        pass


def setup():
    if not _IN_MAYA:
        return
    _register_plugin()


def initializePlugin(plugin):
    _register_plugin()


def uninitializePlugin(plugin):
    _deregister_plugin()
