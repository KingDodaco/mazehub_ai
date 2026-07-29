import maya.cmds as cmds
import os
import re


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


def _export_usd(filepath):
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    sel = cmds.ls(selection=True, long=True)
    if not sel:
        cmds.warning("No objects selected.")
        return False
    cmds.mayaUSDExport(
        file=filepath,
        selection=True,
        exportVisibility=True,
        mergeTransformAndShape=True,
    )
    return True


def _show_export_dialog(*args):
    context_type, context_name, context_path = _get_context_info()

    if not context_path:
        cmds.warning("No MAZE_CONTEXT_PATH set. Launch from MazeHub with a context.")
        return

    if not context_name:
        cmds.warning("No MAZE_CONTEXT_NAME set. Launch from MazeHub with a context.")
        return

    sel = cmds.ls(selection=True)
    if not sel:
        cmds.warning("No objects selected.")
        return

    usd_dir = os.path.join(context_path, "maya", "USD")
    os.makedirs(usd_dir, exist_ok=True)

    existing = _get_existing_descriptors(usd_dir, context_name)

    win = "mazeExportUsdWindow"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)

    cmds.window(win, title="Export USD", widthHeight=(350, 120), sizeable=True)

    form = cmds.formLayout()

    use_existing_var = cmds.checkBoxGrp(
        label="Use existing descriptor: ",
        value1=False,
        columnWidth2=(120, 30),
    )

    if existing:
        descriptor_menu = cmds.optionMenu(label="Descriptor: ")
        cmds.menuItem(label="(none)")
        for d in existing:
            cmds.menuItem(label=d)
    else:
        descriptor_field = cmds.textFieldGrp(label="Descriptor: ", text="")

    cmds.formLayout(
        form,
        edit=True,
        attachForm=[
            (use_existing_var, "top", 10),
            (use_existing_var, "left", 10),
        ],
    )

    if existing:
        cmds.formLayout(
            form,
            edit=True,
            attachControl=[
                (descriptor_menu, "top", 5, use_existing_var),
            ],
            attachForm=[
                (descriptor_menu, "left", 10),
            ],
        )
        cmds.formLayout(
            form,
            edit=True,
            attachControl=[
                (descriptor_field, "top", 5, descriptor_menu),
            ],
            attachForm=[
                (descriptor_field, "left", 10),
            ],
        )
    else:
        cmds.formLayout(
            form,
            edit=True,
            attachControl=[
                (descriptor_field, "top", 5, use_existing_var),
            ],
            attachForm=[
                (descriptor_field, "left", 10),
            ],
        )

    def do_export(*_):
        use_existing = cmds.checkBoxGrp(use_existing_var, query=True, value1=True)

        if use_existing and existing:
            descriptor = cmds.optionMenu(descriptor_menu, query=True, value=True)
            if descriptor == "(none)":
                descriptor = ""
        else:
            descriptor = cmds.textFieldGrp(descriptor_field, query=True, text=True).strip()

        version = _find_next_version(usd_dir, context_name, descriptor)

        if descriptor:
            filename = f"{context_name}_{descriptor}_v{version:03d}.usd"
        else:
            filename = f"{context_name}_v{version:03d}.usd"

        filepath = os.path.join(usd_dir, filename)

        if _export_usd(filepath):
            cmds.confirmDialog(
                title="Export Complete",
                message=f"Exported: {filename}",
                button=["OK"],
            )

        cmds.deleteUI(win)

    cmds.button(
        label="Export",
        command=do_export,
        height=30,
    )

    cmds.formLayout(
        form,
        edit=True,
        attachForm=[
            (cmds.formLayout(query=True, childArray=True)[-1], "bottom", 10),
            (cmds.formLayout(query=True, childArray=True)[-1], "left", 10),
            (cmds.formLayout(query=True, childArray=True)[-1], "right", 10),
        ],
    )

    cmds.showWindow(win)


def create_maze_menu():
    if cmds.menu("maze_menu", exists=True):
        cmds.deleteUI("maze_menu")

    cmds.menu(
        "maze_menu",
        label="MAZE",
        parent="MayaWindow",
        tearOff=False,
    )

    cmds.menuItem(
        label="Export Selection as USD",
        command=_show_export_dialog,
        parent="maze_menu",
    )


create_maze_menu()
