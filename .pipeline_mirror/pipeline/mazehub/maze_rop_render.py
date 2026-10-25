"""hrender-style ROP renderer for MazeHub. Run with hython, not MazeHub's Python.

  hython maze_rop_render.py --list <file.hip>
      Prints one tab-separated line per finding:
        rop   <path> <type>
        pass  <rop>  <RenderPass prim path>
        parm  <rop>  <parm name>        (pass/settings/args parms, for diagnostics)

  hython maze_rop_render.py --render <file.hip> --rop <path> [--pass <prim>]
                            --frames <start> <end> <inc> [--out <file with $F4>]
      Renders the ROP over the frame range. Prints MAZE_FRAME <n> before each frame.
      The scene is changed in memory only; the .hip is never saved.
"""
import argparse
import sys

import hou

OUTPUT_PARMS = ('outputimage', 'vm_picture', 'picture', 'RS_outputFileNamePrefix', 'ar_picture')
PARM_HINTS = ('pass', 'rendersettings', 'args')


def log(*parts):
    sys.stdout.write('\t'.join(str(p) for p in parts) + '\n')
    sys.stdout.flush()


def load_hip(hip):
    hou.hipFile.load(hip, suppress_save_prompt=True, ignore_load_warnings=True)


def is_rop(node):
    if node.type().category().name() == 'Driver':
        return True
    # ROPs living inside LOP networks (e.g. /stage/usdrender_rop1).
    return isinstance(node, hou.RopNode) or node.type().name().startswith('usdrender_rop')


def find_rops():
    return [n for n in hou.node('/').allSubChildren(recurse_in_locked_nodes=False) if is_rop(n)]


def rop_stage(rop):
    """The USD stage a LOP-based ROP renders, or None."""
    candidates = []
    loppath = rop.parm('loppath')
    if loppath and loppath.eval():
        candidates.append(rop.node(loppath.eval()) or hou.node(loppath.eval()))
    candidates.append(rop)
    candidates.extend(rop.inputs())
    for node in candidates:
        if node is None or not hasattr(node, 'stage'):
            continue
        try:
            stage = node.stage()
        except hou.Error:
            continue
        if stage:
            return stage
    return None


def render_passes(rop):
    stage = rop_stage(rop)
    if not stage:
        return []
    return [str(p.GetPath()) for p in stage.Traverse() if p.GetTypeName() == 'RenderPass']


def cmd_list(hip):
    load_hip(hip)
    for rop in find_rops():
        log('rop', rop.path(), rop.type().name())
        for prim in render_passes(rop):
            log('pass', rop.path(), prim)
        for parm in rop.parms():
            name = parm.name()
            if any(h in name.lower() for h in PARM_HINTS):
                log('parm', rop.path(), name)
    return 0


def set_string_parm(parm, value):
    parm.deleteAllKeyframes()
    parm.set(value)


def select_pass(rop, render_pass):
    for parm in rop.parms():
        name = parm.name().lower()
        if 'renderpass' in name and parm.parmTemplate().type() == hou.parmTemplateType.String:
            set_string_parm(parm, render_pass)
            log('MAZE_INFO', f'pass set via parm {parm.name()}')
            return True
    for parm in rop.parms():
        name = parm.name().lower()
        if 'args' in name and parm.parmTemplate().type() == hou.parmTemplateType.String:
            set_string_parm(parm, f'{parm.evalAsString()} --pass {render_pass}'.strip())
            log('MAZE_INFO', f'pass set via husk args parm {parm.name()}')
            return True
    names = ', '.join(p.name() for p in rop.parms() if any(h in p.name().lower() for h in PARM_HINTS))
    log('MAZE_ERROR', f'No way to select render pass on {rop.path()}. Candidate parms: {names or "none"}')
    return False


def set_output(rop, out):
    for name in OUTPUT_PARMS:
        parm = rop.parm(name)
        if parm is not None:
            set_string_parm(parm, out)
            log('MAZE_INFO', f'output set via parm {name}')
            return True
    return False


def cmd_render(hip, rop_path, render_pass, frames, out):
    load_hip(hip)
    rop = hou.node(rop_path)
    if rop is None:
        log('MAZE_ERROR', f'ROP not found: {rop_path}')
        return 1
    if render_pass and not select_pass(rop, render_pass):
        return 1
    output_file = None
    if out and not set_output(rop, out):
        output_file = out

    def on_event(node, event_type, time):
        if event_type == hou.ropRenderEventType.PreFrame:
            log('MAZE_FRAME', int(round(hou.timeToFrame(time))))

    if hasattr(rop, 'addRenderEventCallback'):
        rop.addRenderEventCallback(on_event)

    start, end, inc = frames
    try:
        if hasattr(rop, 'render'):
            kwargs = {'frame_range': (start, end, inc), 'verbose': True, 'output_progress': True}
            if output_file:
                kwargs['output_file'] = output_file
            rop.render(**kwargs)
        else:
            for name, value in (('trange', 1), ('f1', start), ('f2', end), ('f3', inc)):
                parm = rop.parm(name)
                if parm is not None:
                    parm.deleteAllKeyframes()
                    parm.set(value)
            rop.parm('execute').pressButton()
    except hou.Error as e:
        log('MAZE_ERROR', str(e))
        return 1
    errors = rop.errors()
    if errors:
        for err in errors:
            log('MAZE_ERROR', err)
        return 1
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', metavar='HIP')
    ap.add_argument('--render', metavar='HIP')
    ap.add_argument('--rop')
    ap.add_argument('--pass', dest='render_pass', default='')
    ap.add_argument('--frames', nargs=3, type=int, metavar=('START', 'END', 'INC'))
    ap.add_argument('--out', default='')
    args = ap.parse_args(argv)
    if args.list:
        return cmd_list(args.list)
    if args.render and args.rop and args.frames:
        return cmd_render(args.render, args.rop, args.render_pass, args.frames, args.out)
    ap.print_usage()
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
