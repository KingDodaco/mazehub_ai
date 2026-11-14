"""List a USD file's dependencies with USD itself. Run with hython, not MazeHub's Python.

  hython maze_usd_deps.py <root.usd>
  hython maze_usd_deps.py --layer-info <root.usd>

Prints one JSON object between MAZE_DEPS_BEGIN / MAZE_DEPS_END lines:
  layers      real paths of every layer in the composition (sublayers, references, payloads, clips)
  assets      resolved paths of non-layer assets (VDBs, textures, ...)
  unresolved  paths that could not be resolved
  origins     {anchored asset path: layer that references it}
  has_clips   any prim uses value clips
  static_volumes  .vdb filePath attributes with a default value but no time samples
--layer-info opens only the root layer (no stage, nothing referenced is opened) and prints
{passes, layer_refs} between MAZE_LAYER_BEGIN / MAZE_LAYER_END: RenderPass prim paths defined in
that layer, and the asset paths of its sublayers, references and payloads.
One process for the whole scene, using the same resolver husk uses, so render
outputs (productName) and assetInfo identifiers are never reported as inputs.
"""
import json
import os
import sys

from pxr import Sdf, UsdUtils


def scan(root):
    origins = {}

    def record(layer, info):
        paths = [info.assetPath] + list(getattr(info, 'dependencies', []) or [])
        for p in paths:
            if p:
                origins.setdefault(os.path.normpath(layer.ComputeAbsolutePath(p)), layer.realPath)
        return info

    try:
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(root), record)
    except TypeError:
        # Older USD without the processing callback: no referenced-by information.
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(root))

    has_clips = False
    static_volumes = []
    for layer in layers:
        def visit(path, layer=layer):
            nonlocal has_clips
            if path.IsPrimPath():
                prim = layer.GetPrimAtPath(path)
                if prim and (prim.HasInfo('clips') or prim.HasInfo('clipSets')):
                    has_clips = True
            elif path.IsPropertyPath() and path.name == 'filePath':
                attr = layer.GetAttributeAtPath(path)
                value = attr.default if attr and attr.HasDefaultValue() else None
                if (isinstance(value, Sdf.AssetPath) and value.path.lower().endswith('.vdb')
                        and not layer.ListTimeSamplesForPath(path)):
                    static_volumes.append(os.path.normpath(layer.ComputeAbsolutePath(value.path)))
        layer.Traverse(Sdf.Path.absoluteRootPath, visit)

    return {
        'layers': [layer.realPath for layer in layers if layer.realPath],
        'assets': list(assets),
        'unresolved': list(unresolved),
        'origins': origins,
        'has_clips': has_clips,
        'static_volumes': static_volumes,
    }


def _list_op_assets(list_op):
    items = []
    for name in ('explicitItems', 'addedItems', 'prependedItems', 'appendedItems'):
        items.extend(getattr(list_op, name, None) or [])
    return [item.assetPath for item in items if getattr(item, 'assetPath', '')]


def layer_info(path):
    """RenderPass prims and external layer refs of one layer, without composing a stage."""
    layer = Sdf.Layer.FindOrOpen(path)
    if layer is None:
        raise RuntimeError(f'could not open layer {path}')
    passes = []
    refs = list(layer.subLayerPaths)

    def visit(spec_path):
        if not spec_path.IsPrimPath():
            return
        prim = layer.GetPrimAtPath(spec_path)
        if not prim:
            return
        if prim.typeName == 'RenderPass':
            passes.append(str(spec_path))
        if prim.HasInfo('references'):
            refs.extend(_list_op_assets(prim.referenceList))
        if prim.HasInfo('payload'):
            refs.extend(_list_op_assets(prim.payloadList))

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return {'passes': sorted(passes), 'layer_refs': list(dict.fromkeys(r for r in refs if r))}


def main(argv):
    if len(argv) == 2 and argv[0] == '--layer-info':
        try:
            result, code = layer_info(argv[1]), 0
        except Exception as e:
            result, code = {'error': f'{type(e).__name__}: {e}'}, 1
        sys.stdout.write('MAZE_LAYER_BEGIN\n' + json.dumps(result) + '\nMAZE_LAYER_END\n')
        sys.stdout.flush()
        return code
    if len(argv) != 1:
        print('usage: hython maze_usd_deps.py [--layer-info] <root.usd>')
        return 2
    try:
        result, code = scan(argv[0]), 0
    except Exception as e:  # reported to MazeHub, which falls back to its text scanner
        result, code = {'error': f'{type(e).__name__}: {e}'}, 1
    sys.stdout.write('MAZE_DEPS_BEGIN\n' + json.dumps(result) + '\nMAZE_DEPS_END\n')
    sys.stdout.flush()
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
