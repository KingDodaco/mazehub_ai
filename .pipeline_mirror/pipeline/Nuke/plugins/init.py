import os
import nuke


def _get_mze_path():
    return os.environ.get('MZE', '').replace('\\', '/')


def _get_project_name():
    name = os.environ.get('MAZE_PROJECT', '')
    if not name:
        mze = _get_mze_path()
        if mze:
            name = mze.rstrip('/').rsplit('/', 1)[-1]
    return name


def _resolve_path(val):
    mze = _get_mze_path()
    project_name = _get_project_name()
    if not mze or not project_name or not val:
        return val
    normalized = val.replace('\\', '/')
    marker = '/' + project_name + '/'
    idx = normalized.lower().find(marker.lower())
    if idx == -1:
        idx = normalized.lower().find(project_name.lower() + '/')
        if idx != 0:
            return val
        relative = normalized[len(project_name):].lstrip('/')
        return mze + '/' + relative
    relative = normalized[idx + len(marker):]
    return mze + '/' + relative


def _resolve_all_file_knobs():
    for node in nuke.allNodes(recurseGroups=True):
        for knob_name in ('file', 'proxy'):
            k = node.knob(knob_name)
            if k:
                val = k.value()
                if val:
                    resolved = _resolve_path(val)
                    if resolved != val:
                        k.setValue(resolved)


def _resolve_env_on_edit():
    knob = nuke.thisKnob()
    if knob.name() in ('file', 'proxy'):
        val = knob.value()
        if val:
            resolved = _resolve_path(val)
            if resolved != val:
                knob.setValue(resolved)


def set_project_from_env():
    start_raw = os.environ.get("START_FRAME", "") or "1001"
    end_raw = os.environ.get("END_FRAME", "") or "1240"
    fps_raw = os.environ.get("FRAME_RATE", "") or "24"

    try:
        start_frame = int(float(start_raw))
        end_frame = int(float(end_raw))
        fps_val = int(round(float(fps_raw)))
        if fps_val <= 0:
            raise ValueError(f"invalid frame rate: {fps_raw!r}")
    except (TypeError, ValueError):
        start_frame = 1001
        end_frame = 1240
        fps_val = 24

    nuke.root()['first_frame'].setValue(start_frame)
    nuke.root()['last_frame'].setValue(end_frame)
    nuke.root()['fps'].setValue(fps_val)


nuke.addOnCreate(set_project_from_env, nodeClass='Root')

nuke.pluginAddPath("./plugins/CGDenoiser")
nuke.pluginAddPath('./plugins/MagicTools')
nuke.pluginAddPath('./plugins/FlareSim/Nuke15_2')
nuke.pluginAddPath('./plugins/pixelfudger3')
nuke.pluginAddPath('./gizmos')

nuke.addKnobChanged(_resolve_env_on_edit, nodeClass='Node')
nuke.addOnScriptLoad(_resolve_all_file_knobs)
