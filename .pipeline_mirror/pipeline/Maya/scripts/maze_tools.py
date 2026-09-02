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
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnOffset=("both", 10))

    use_existing_var = cmds.checkBoxGrp(
        label="Use existing descriptor: ",
        value1=False,
        columnWidth2=(130, 30),
        changeCommand=lambda val: _toggle_descriptorUI(val),
    )

    if existing:
        descriptor_menu = cmds.optionMenu(label="Descriptor: ")
        cmds.menuItem(label="(none)")
        for d in existing:
            cmds.menuItem(label=d)
    else:
        descriptor_menu = None

    descriptor_field = cmds.textFieldGrp(label="Descriptor: ", text="")

    if existing:
        cmds.optionMenu(descriptor_menu, edit=True, visible=True)
        cmds.textFieldGrp(descriptor_field, edit=True, visible=False)
    else:
        cmds.textFieldGrp(descriptor_field, edit=True, visible=True)

    def _toggle_descriptorUI(val):
        if not existing:
            return
        use_new = not val
        cmds.optionMenu(descriptor_menu, edit=True, visible=not use_new)
        cmds.textFieldGrp(descriptor_field, edit=True, visible=use_new)

    cmds.separator(height=5, style="none")

    def do_export(*_):
        use_existing = cmds.checkBoxGrp(use_existing_var, query=True, value1=True)

        if use_existing and descriptor_menu:
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

    cmds.button(label="Export", command=do_export, height=30)

    cmds.showWindow(win)


def _show_autorigger(*args):
    from autorigger import gui
    gui.show()


def _get_display_name():
    if os.name == 'nt':
        try:
            import ctypes
            size = ctypes.c_ulong(0)
            ctypes.windll.secur32.GetUserNameExW(3, None, ctypes.byref(size))
            if size.value > 0:
                buf = ctypes.create_unicode_buffer(size.value)
                ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size))
                if buf.value:
                    return buf.value
        except Exception:
            pass
        return os.environ.get('USERNAME', 'unknown')
    return os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))


def _long_path(p):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetLongPathNameW(str(p), buf, 512)
        return buf.value or str(p)
    except Exception:
        return str(p)


def _get_default_playblast_output():
    # Prefer explicit maya context folder, never write to asset/shot root
    ctx = os.environ.get('MAZE_CONTEXT_PATH') or ""
    if ctx:
        job = os.path.join(ctx, "maya")
    else:
        job = os.environ.get('JOB') or os.environ.get('MAYA_PROJECT') or ""
        # If JOB is a Houdini working dir (ends with houdini), switch to maya
        if job and os.path.basename(job).lower() == "houdini":
            job = os.path.join(os.path.dirname(job), "maya")
    scene = cmds.file(q=True, sn=True) or ""
    hip_name = os.path.splitext(os.path.basename(scene))[0] if scene else "playblast"
    if not hip_name or hip_name.lower().startswith("untitled"):
        hip_name = "playblast"
    base = re.sub(r"_v\d+$", "", hip_name)
    flipbooks_dir = os.path.join(job, "flipbooks") if job else ""
    version = 1
    if flipbooks_dir and os.path.isdir(flipbooks_dir):
        pat = re.compile(rf"^{re.escape(base)}_v(\d{{3}})\.mp4$", re.IGNORECASE)
        max_v = 0
        try:
            for f in os.listdir(flipbooks_dir):
                m = pat.match(f)
                if m:
                    max_v = max(max_v, int(m.group(1)))
        except Exception:
            pass
        version = max_v + 1
        m2 = re.search(r"_v(\d+)$", hip_name)
        if m2 and max_v == 0:
            version = int(m2.group(1))
    job = job or os.path.expanduser("~")
    return os.path.abspath(os.path.join(job, "flipbooks", f"{base}_v{version:03d}.mp4"))


def _format_versioned_filename(name):
    return re.sub(r"_v(\d+)$", r" (v\1)", name)


def _local_to_onedrive_link(local_path):
    web_root = "https://livebournemouthac.sharepoint.com/sites/FMP2/Shared%20Documents/PROJECT/MAZE/"
    web_root = os.environ.get("MAZE_ONEDRIVE_ROOT", web_root)
    local_path = _long_path(local_path)
    for anchor in ("MAZE", os.path.basename(_long_path(os.environ.get("MAZE_PROJECT_ROOT", "")))):
        if anchor and anchor in local_path:
            parts = local_path.split(anchor, 1)
            if len(parts) == 2:
                return web_root + parts[1].replace("\\", "/").lstrip("/")
    try:
        root = _long_path(os.environ.get("MAZE_PROJECT_ROOT", ""))
        if root:
            rel = os.path.relpath(local_path, root).replace("\\", "/").lstrip("/")
            if not rel.startswith(".."):
                return web_root + rel
    except Exception:
        pass
    try:
        job = _long_path(os.environ.get("JOB") or os.environ.get("MAZE_CONTEXT_PATH", ""))
        if job:
            rel = os.path.relpath(local_path, job).replace("\\", "/")
            return web_root + rel.lstrip("/")
    except Exception:
        pass
    raise ValueError(f"Path does not contain 'MAZE': {local_path}")


def _maya_compile_sequence(input_pattern, output, start_frame):
    import subprocess, shutil, glob
    os.makedirs(os.path.dirname(output), exist_ok=True)
    ffmpeg_input = input_pattern.replace("$F4", "%04d")
    candidates = []
    hfs = os.environ.get("HFS", "")
    if hfs:
        candidates.append(os.path.join(hfs, "bin", "hffmpeg"))
        candidates.append(os.path.join(hfs, "bin", "ffmpeg"))
    # Houdini installs not in HFS when in Maya
    for cand in glob.glob("C:/Program Files/Side Effects Software/Houdini*/bin/hffmpeg.exe"):
        candidates.append(cand)
    for cand in glob.glob("C:/Program Files/Side Effects Software/Houdini*/bin/ffmpeg.exe"):
        candidates.append(cand)
    # PATH lookups
    for name in ("hffmpeg", "ffmpeg", "ffmpeg.exe"):
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)
    candidates.extend(["hffmpeg", "ffmpeg"])
    # Unique existing or PATH candidates first
    tried = []
    for cand in candidates:
        # If contains path, check exists, else assume in PATH
        if os.path.sep in cand and not os.path.exists(cand):
            continue
        tried.append(cand)
    if not tried:
        tried = ["ffmpeg"]
    try:
        fps = int(cmds.playbackOptions(q=True, framesPerSecond=True) or 24)
    except Exception:
        fps = 24
    last_err = ""
    for ffmpeg_path in tried:
        for codec in ("h264_nvenc", "libx264"):
            cmd = [ffmpeg_path, "-y", "-framerate", str(fps), "-start_number", str(start_frame), "-i", ffmpeg_input, "-c:v", codec, "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium", output]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags)
                if result.returncode == 0 and os.path.exists(output):
                    print(f"Compiled {output} via {ffmpeg_path} {codec}")
                    return output
                last_err = result.stderr.strip()[:500] if result.stderr else f"code {result.returncode}"
                print(f"hffmpeg {codec} failed ({ffmpeg_path}): {last_err}")
            except FileNotFoundError:
                last_err = f"{ffmpeg_path} not found"
                print(last_err)
                break
            except Exception as e:
                last_err = str(e)
                print(f"Compile error: {e}")
                continue
    raise RuntimeError(f"hffmpeg failed {input_pattern} -> {output} | last: {last_err} | input exists: {os.path.exists(ffmpeg_input.replace('%04d', f'{start_frame:04d}'))}")


def _post_playblast(output, comment=""):
    import json, getpass, socket, datetime
    try:
        onedrive_link = _local_to_onedrive_link(output)
    except Exception as e:
        print(f"local_to_onedrive_link failed ({e})")
        onedrive_link = output.replace("\\", "/")
    # settings
    settings_path = os.path.expanduser("~/.config/mazehub/settings.json")
    webhook_url = ""
    try:
        import json as _j
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                webhook_url = _j.load(f).get("dailies_webhook_url", "")
    except Exception:
        pass
    if not webhook_url:
        webhook_url = os.environ.get("MAZE_DAILIES_WEBHOOK") or "https://defaultede29655d09742e4bbb5f38d427fbf.b8.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/cdf54a2c13564d2dba8edc95a608ff50/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=PaCvoX6XhuOJC3S4ubnKnOQuuWZUasyKX52AdQp33OA"
    try:
        username = _get_display_name()
    except Exception:
        username = getpass.getuser()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = os.path.splitext(os.path.basename(output))[0]
    context_name = os.environ.get("MAZE_CONTEXT_NAME", "")
    hip_path = ""
    try:
        hp = cmds.file(q=True, sn=True) or ""
        if hp and "untitled" not in os.path.basename(hp).lower():
            hip_path = _long_path(hp)
    except Exception:
        pass
    if not context_name and hip_path:
        parts = hip_path.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if part.lower() == "shot" and i + 1 < len(parts):
                context_name = parts[i + 1]
                break
        if not context_name:
            context_name = os.path.splitext(os.path.basename(hip_path))[0]
    if not context_name:
        context_name = os.path.splitext(os.path.basename(hip_path))[0] if hip_path else filename
    title_text = f"{context_name} — {_format_versioned_filename(filename)}" if context_name else _format_versioned_filename(filename)
    hip_text = os.path.basename(hip_path) if hip_path else ""
    pretty_comment = f'"{comment}"' if comment else ""
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.5",
                "body": [
                    {"type": "Container", "items": [
                        {"type": "TextBlock", "text": title_text, "wrap": True, "weight": "Bolder", "size": "Large"},
                        {"type": "TextBlock", "text": hip_text, "wrap": True, "spacing": "None", "size": "Small", "isSubtle": True, "fontType": "Monospace"} if hip_text else {"type": "TextBlock", "text": "", "isVisible": False},
                        {"type": "TextBlock", "text": current_time, "wrap": True, "spacing": "Small"},
                        {"type": "TextBlock", "text": username, "wrap": True, "spacing": "Small"},
                        {"type": "TextBlock", "text": pretty_comment, "wrap": True, "spacing": "Small"},
                    ], "style": "emphasis", "bleed": True},
                    {"type": "Media", "sources": [{"url": onedrive_link, "mimeType": "video/mp4"}]},
                ],
            },
        }],
    }
    try:
        import requests
        r = requests.post(webhook_url, json=payload, timeout=15)
        if 200 <= r.status_code < 300:
            print("Posted to Teams")
            return True
        print(f"Failed to post: {r.status_code} - {r.text}")
        return False
    except Exception:
        pass
    try:
        import urllib.request, json as _j2
        data = _j2.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            print("Posted to Teams")
            return True
    except Exception as e:
        print(f"Failed to post: {e}")
        return False


def _do_playblast(*args):
    # Guard: scene must be saved
    scene = cmds.file(q=True, sn=True) or ""
    if not scene or "untitled" in os.path.basename(scene).lower():
        cmds.confirmDialog(title="Save Scene", message="Please save your scene under MZE before playblasting.", button=["OK"])
        return
    # Check JOB/context
    job = os.environ.get("JOB") or os.environ.get("MAYA_PROJECT") or os.environ.get("MAZE_CONTEXT_PATH") or ""
    if job and not os.path.isdir(job):
        try:
            os.makedirs(job, exist_ok=True)
        except Exception:
            pass
    # Get comment via input dialog
    comment = ""
    try:
        from PySide6.QtWidgets import QInputDialog
        from shiboken6 import wrapInstance
        import maya.OpenMayaUI as omui
        parent = wrapInstance(int(omui.MQtUtil.mainWindow()), __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget)
        text, ok = QInputDialog.getText(parent, "Playblast", "Add a note (optional):")
        if not ok:
            return
        comment = text
    except Exception:
        comment = ""
    # Playblast range from playback
    start = int(cmds.playbackOptions(q=True, minTime=True))
    end = int(cmds.playbackOptions(q=True, maxTime=True))
    output = _get_default_playblast_output()
    flipbooks_dir = os.path.dirname(output)
    os.makedirs(flipbooks_dir, exist_ok=True)
    # Maya playblast to jpeg sequence - Maya uses bare basename, appends .####.jpg automatically
    playblast_base = os.path.join(flipbooks_dir, "playblast").replace("\\", "/")
    # Get active model panel
    panel = None
    try:
        panel = cmds.getPanel(withFocus=True)
        if not cmds.getPanel(typeOf=panel) == "modelPanel":
            panel = cmds.getPanel(wf=True)
            if cmds.getPanel(typeOf=panel) != "modelPanel":
                # fallback to first modelPanel
                for p in cmds.getPanel(type="modelPanel"):
                    panel = p
                    break
    except Exception:
        pass
    if not panel:
        cmds.warning("No modelPanel found for playblast")
        return
    try:
        # playblast images - use bare basename, Maya adds .####.png
        import glob
        for ext in ("jpg", "png", "jpeg"):
            for old in glob.glob(os.path.join(flipbooks_dir, f"playblast.*.{ext}")):
                try:
                    os.remove(old)
                except Exception:
                    pass
        result = cmds.playblast(format="image", filename=playblast_base, forceOverwrite=True, clearCache=True, viewer=False, showOrnaments=False, percent=100, quality=100, widthHeight=[1920, 1080], startTime=start, endTime=end)
        # Verify files were created (Maya defaults to png when no ext)
        created = sorted(glob.glob(os.path.join(flipbooks_dir, "playblast.*.jpg")) + glob.glob(os.path.join(flipbooks_dir, "playblast.*.png")) + glob.glob(os.path.join(flipbooks_dir, "playblast.*.jpeg")))
        if not created:
            # also check exact result pattern e.g. playblast.####.png not yet expanded - list all playblast.*
            created = sorted(glob.glob(os.path.join(flipbooks_dir, "playblast.*")))
            created = [c for c in created if os.path.splitext(c)[1].lower() in (".jpg", ".jpeg", ".png")]
        if not created:
            raise RuntimeError(f"Playblast created no files in {flipbooks_dir} (result={result})")
        print(f"Playblast created {len(created)} frames: {created[0]} -> {created[-1]}")
        ext = os.path.splitext(created[0])[1]  # .png or .jpg
        input_pat = os.path.join(flipbooks_dir, f"playblast.$F4{ext}").replace("\\", "/")
        compiled = _maya_compile_sequence(input_pat, output, start_frame=start)
        cmds.confirmDialog(title="Playblast", message=f"Saved {os.path.basename(compiled)}", button=["OK"])
        _post_playblast(compiled, comment)
    except Exception as e:
        import traceback; traceback.print_exc()
        cmds.warning(f"Playblast failed: {e}")


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

    cmds.menuItem(
        label="Playblast",
        command=_do_playblast,
        parent="maze_menu",
    )

    cmds.menuItem(divider=True, parent="maze_menu")

    cmds.menuItem(
        label="Autorigger",
        command=_show_autorigger,
        parent="maze_menu",
    )


create_maze_menu()
