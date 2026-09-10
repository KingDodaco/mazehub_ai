import os
import nuke


MZE_VAR = 'MZE'
MZE_ENV_TAG = '%' + MZE_VAR + '%'

_saving = False


def _get_mze_path():
    return os.environ.get(MZE_VAR, '').replace('\\', '/')


def set_project_from_env():
    start_frame = "1001"
    end_frame = "1240"
    fps_val = "24"

    if "START_FRAME" in os.environ:
        start_frame = os.environ.get("START_FRAME")
    if "END_FRAME" in os.environ:
        end_frame = os.environ.get("END_FRAME")
    if "FRAME_RATE" in os.environ:
        fps_val = os.environ.get("FRAME_RATE")

    nuke.root()['first_frame'].setValue(int(start_frame))
    nuke.root()['last_frame'].setValue(int(end_frame))
    nuke.root()['fps'].setValue(int(fps_val))


nuke.addOnCreate(set_project_from_env, nodeClass='Root')

nuke.pluginAddPath("./plugins/CGDenoiser")
nuke.pluginAddPath('./plugins/MagicTools')
nuke.pluginAddPath('./plugins/FlareSim/Nuke15_2')
nuke.pluginAddPath('./plugins/pixelfudger3')
nuke.pluginAddPath('./gizmos')


def _resolve_all_file_knobs():
    mze = _get_mze_path()
    if not mze:
        return
    for node in nuke.allNodes(recurseGroups=True):
        for knob_name in ('file', 'proxy'):
            k = node.knob(knob_name)
            if k:
                val = k.value()
                if MZE_ENV_TAG in val:
                    k.setValue(val.replace(MZE_ENV_TAG, mze))


def _reverse_map_all_file_knobs():
    mze = _get_mze_path()
    if not mze:
        return
    mze_norm = mze.rstrip('/').rstrip('\\').lower()
    for node in nuke.allNodes(recurseGroups=True):
        for knob_name in ('file', 'proxy'):
            k = node.knob(knob_name)
            if k:
                val = k.value()
                if MZE_ENV_TAG not in val:
                    normalized = val.replace('\\', '/')
                    if normalized.lower().startswith(mze_norm):
                        k.setValue(MZE_ENV_TAG + normalized[len(mze):])


def _resolve_env_on_edit():
    mze = _get_mze_path()
    if not mze:
        return
    knob = nuke.thisKnob()
    if knob.name() in ('file', 'proxy'):
        val = knob.value()
        if MZE_ENV_TAG in val:
            knob.setValue(val.replace(MZE_ENV_TAG, mze))


def _on_save_callback():
    global _saving
    if _saving:
        return
    _saving = True
    _resolve_all_file_knobs()
    _saving = False


def _save_with_tags():
    global _saving
    _saving = True
    _reverse_map_all_file_knobs()
    nuke.scriptSave(nuke.root().name())
    _saving = False
    _resolve_all_file_knobs()


nuke.addFilenameFilter(lambda f: f.replace(MZE_ENV_TAG, _get_mze_path()) if f and MZE_ENV_TAG in f else f)
nuke.addKnobChanged(_resolve_env_on_edit, nodeClass='Node')
nuke.addOnScriptLoad(_resolve_all_file_knobs)
nuke.addOnScriptSave(_on_save_callback)
nuke.menu('Nuke').addCommand('File/Save with MZE Tags', _save_with_tags, 'Ctrl+Alt+Shift+S')
nuke.menu('Nuke').addCommand('File/Save', _save_with_tags, 'Ctrl+S')

