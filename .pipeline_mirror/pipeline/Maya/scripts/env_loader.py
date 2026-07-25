"""
env_loader.py - Helper functions for integrating envPathResolver with Maya file nodes.

Usage:
    from env_loader import connect_file_texture, create_env_reference, wrap_existing

    connect_file_texture("file1", "$PROJECT/textures/diffuse.tx")
    create_env_reference("$PROJECT/assets/character.ma", namespace="char")
    wrap_existing("file2")
"""

import maya.cmds as cmds
import os

PLUGIN_NAME = "envPathResolver.py"


def _ensure_plugin():
    if not cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        cmds.loadPlugin(PLUGIN_NAME)


def connect_file_texture(file_node, raw_path, fallback=""):
    """Create envPathResolver connected to file node's fileTextureName."""
    _ensure_plugin()
    resolver = cmds.createNode("envPathResolver", name=file_node + "_envResolver")
    cmds.setAttr(resolver + ".rawPath", raw
