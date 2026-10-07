import nuke
import os
import re
import json
import getpass
import datetime
import tempfile
from pathlib import Path
try:
    import requests
except ImportError:
    requests = None
try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None


FLIPBOOK_DISPLAY = "arri709 - Display"
FLIPBOOK_VIEW = "arri709 - View"


def _get_mazehub_settings():
    settings = {}
    candidates = []
    pipeline = os.environ.get('MAZE_PIPELINE')
    if pipeline:
        candidates.append(Path(pipeline) / 'mazehub' / 'user_settings.json')
    candidates.append(Path.home() / '.config' / 'mazehub' / 'user_settings.json')
    for path in candidates:
        try:
            with open(path, 'r') as f:
                settings.update(json.load(f))
            break
        except Exception:
            pass
    shared = {}
    project_root = os.environ.get('MAZE_PROJECT_ROOT')
    if project_root:
        for rel in (('pipeline', 'mazehub', 'shared_settings.json'),
                    ('mazehub', 'shared_settings.json')):
            try:
                with open(Path(project_root).joinpath(*rel), 'r') as f:
                    shared.update(json.load(f))
            except Exception:
                pass
        settings.update(shared)
    for key in ('teams_webhook_url', 'dailies_webhook_url',
                'production_webhook_url'):
        settings.pop(key, None)
        if key in shared:
            settings[key] = shared[key]
    return settings


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
        return os.environ.get('USERNAME', getpass.getuser())
    return os.environ.get('USER', getpass.getuser())


def _long_path(p):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetLongPathNameW(str(p), buf, 512)
        return buf.value or str(p)
    except Exception:
        return str(p)


def _ensure_flip_dir(script_path):
    # Always use <context>/nuke/flipbooks when context is set, otherwise fallback
    ctx = os.environ.get('MAZE_CONTEXT_PATH') or ""
    if ctx:
        flipdir = os.path.join(ctx, "nuke", "flipbooks")
    else:
        job = os.environ.get('JOB') or ""
        if job:
            job_p = Path(job)
            if job_p.name.lower() == "houdini":
                flipdir = str(job_p.parent / "nuke" / "flipbooks")
            else:
                # JOB is already a nuke-adjacent dir? ensure nuke subfolder
                if "nuke" in job_p.parts:
                    flipdir = os.path.join(job, "flipbooks")
                else:
                    flipdir = os.path.join(job, "nuke", "flipbooks")
        else:
            dirpath = os.path.dirname(script_path) if script_path and script_path != "Root" else ""
            flipdir = os.path.join(dirpath, "flipbooks") if dirpath else os.path.join(os.path.expanduser("~"), "flipbooks")
    flipdir = _long_path(flipdir)
    if not os.path.exists(flipdir):
        os.makedirs(flipdir, exist_ok=True)
    return flipdir


def local_to_onedrive_link(local_path):
    web_root = "https://livebournemouthac.sharepoint.com/sites/FMP2/Shared%20Documents/PROJECT/MAZE/"
    web_root = os.environ.get("MAZE_ONEDRIVE_ROOT", web_root)
    local_path = _long_path(local_path)
    for anchor in ("MAZE", os.path.basename(_long_path(os.environ.get("MAZE_PROJECT_ROOT", "")))):
        if anchor and anchor in local_path:
            parts = local_path.split(anchor, 1)
            if len(parts) == 2:
                relative_path = parts[1].replace("\\", "/").lstrip("/")
                return web_root + relative_path
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
    raise ValueError(f"Path does not contain 'MAZE' and cannot be mapped: {local_path}")


def format_versioned_filename(name):
    return re.sub(r"_v(\d+)$", r" (v\1)", name)


def _get_next_versioned_path(flipdir, base):
    """Return <flipdir>/<base>_vXXX.mp4 next version, stripping existing _vNNN."""
    base = re.sub(r"_v\d+$", "", base)
    pat = re.compile(rf"^{re.escape(base)}_v(\d{{3}})\.mp4$", re.IGNORECASE)
    max_v = 0
    if os.path.isdir(flipdir):
        for f in os.listdir(flipdir):
            m = pat.match(f)
            if m:
                max_v = max(max_v, int(m.group(1)))
    version = max_v + 1
    # If no files yet and base had no version, start at 001
    return os.path.join(flipdir, f"{base}_v{version:03d}.mp4"), version


def post_flipbook(output, comment=""):
    # OneDrive link with fallback
    try:
        onedrive_link = local_to_onedrive_link(output)
    except Exception as e:
        print(f"local_to_onedrive_link failed ({e}), trying fallback")
        onedrive_link = output.replace("\\", "/")

    settings = _get_mazehub_settings()
    webhook_url = settings.get("dailies_webhook_url") or os.environ.get("MAZE_DAILIES_WEBHOOK", "")
    if not webhook_url:
        print("Dailies webhook is not configured in MazeHub settings.")
        return False

    # Display name, no device
    try:
        username = _get_display_name()
    except Exception:
        username = getpass.getuser()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = os.path.splitext(os.path.basename(output))[0]

    # Shot/asset + script file for title
    context_name = os.environ.get("MAZE_CONTEXT_NAME", "")
    script_path = ""
    try:
        sp = nuke.root().name()
        if sp and sp != "Root" and "untitled" not in Path(sp).name.lower():
            script_path = _long_path(sp)
    except Exception:
        pass
    if not context_name and script_path:
        # Try parse /shot/ from script path
        parts = Path(script_path).parts
        for i, part in enumerate(parts):
            if part.lower() == "shot" and i + 1 < len(parts):
                context_name = parts[i + 1]
                break
        if not context_name:
            context_name = Path(script_path).stem
    if not context_name:
        context_name = Path(script_path).stem if script_path else filename
    title_text = f"{context_name} — {format_versioned_filename(filename)}" if context_name else format_versioned_filename(filename)
    hip_text = Path(script_path).name if script_path else ""

    message = username
    pretty_comment = f'"{comment}"' if comment else ""

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {"type": "Container", "items": [
                        {"type": "TextBlock", "text": title_text, "wrap": True, "weight": "Bolder", "size": "Large"},
                        {"type": "TextBlock", "text": hip_text, "wrap": True, "spacing": "None", "size": "Small", "isSubtle": True, "fontType": "Monospace"} if hip_text else {"type": "TextBlock", "text": "", "wrap": True, "spacing": "None", "isVisible": False},
                        {"type": "TextBlock", "text": current_time, "wrap": True, "spacing": "Small"},
                        {"type": "TextBlock", "text": message, "wrap": True, "spacing": "Small"},
                        {"type": "TextBlock", "text": pretty_comment, "wrap": True, "spacing": "Small"},
                    ], "style": "emphasis", "bleed": True},
                    {"type": "Media", "sources": [{"url": onedrive_link, "mimeType": "video/mp4"}]},
                ],
            },
        }],
    }

    if requests is not None:
        try:
            response = requests.post(webhook_url, json=payload, timeout=15)
            if 200 <= response.status_code < 300:
                print("Posted successfully to Teams!")
                return True
            else:
                print(f"Failed to post: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"requests.post failed ({e}), trying urllib")
    # Fallback to urllib
    try:
        import json as _json
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                print("Posted successfully to Teams!")
                return True
            else:
                print(f"Failed to post: {resp.status} - {resp.read().decode()}")
                return False
    except Exception as e:
        print(f"Failed to post: {e}")
        return False


def post_frame(output, comment=""):
    """Post a single PNG frame to Teams via Adaptive Card Image."""
    try:
        onedrive_link = local_to_onedrive_link(output)
    except Exception as e:
        print(f"local_to_onedrive_link failed ({e}), trying fallback")
        onedrive_link = output.replace("\\", "/")

    settings = _get_mazehub_settings()
    webhook_url = settings.get("dailies_webhook_url") or os.environ.get("MAZE_DAILIES_WEBHOOK", "")
    if not webhook_url:
        print("Dailies webhook is not configured in MazeHub settings.")
        return False

    try:
        username = _get_display_name()
    except Exception:
        username = getpass.getuser()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = os.path.splitext(os.path.basename(output))[0]

    context_name = os.environ.get("MAZE_CONTEXT_NAME", "")
    script_path = ""
    try:
        sp = nuke.root().name()
        if sp and sp != "Root" and "untitled" not in Path(sp).name.lower():
            script_path = _long_path(sp)
    except Exception:
        pass
    if not context_name and script_path:
        parts = Path(script_path).parts
        for i, part in enumerate(parts):
            if part.lower() == "shot" and i + 1 < len(parts):
                context_name = parts[i + 1]
                break
        if not context_name:
            context_name = Path(script_path).stem
    if not context_name:
        context_name = Path(script_path).stem if script_path else filename
    title_text = f"{context_name} — {format_versioned_filename(filename)}" if context_name else format_versioned_filename(filename)
    hip_text = Path(script_path).name if script_path else ""
    message = username
    pretty_comment = f'"{comment}"' if comment else ""

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {"type": "Container", "items": [
                        {"type": "TextBlock", "text": title_text, "wrap": True, "weight": "Bolder", "size": "Large"},
                        {"type": "TextBlock", "text": hip_text, "wrap": True, "spacing": "None", "size": "Small", "isSubtle": True, "fontType": "Monospace"} if hip_text else {"type": "TextBlock", "text": "", "wrap": True, "spacing": "None", "isVisible": False},
                        {"type": "TextBlock", "text": current_time, "wrap": True, "spacing": "Small"},
                        {"type": "TextBlock", "text": message, "wrap": True, "spacing": "Small"},
                        {"type": "TextBlock", "text": pretty_comment, "wrap": True, "spacing": "Small"},
                    ], "style": "emphasis", "bleed": True},
                    {"type": "Image", "url": onedrive_link, "style": "default"},
                ],
            },
        }],
    }

    if requests is not None:
        try:
            response = requests.post(webhook_url, json=payload, timeout=15)
            if 200 <= response.status_code < 300:
                print("Posted to Teams")
                return True
            print(f"Failed to post: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"requests.post failed ({e}), trying urllib")
    try:
        import json as _json
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                print("Posted to Teams")
                return True
            print(f"Failed to post: {resp.status} - {resp.read().decode()}")
            return False
    except Exception as e:
        print(f"Failed to post: {e}")
        return False


def send_frame_to_dailies(node=None):
    """Render the current frame as PNG and send to Teams."""
    try:
        script_path = nuke.root().name()
        if not script_path or script_path == "Root" or "untitled" in Path(script_path).name.lower():
            nuke.message("Please save the script before sending a frame.")
            return

        long_script = _long_path(script_path)
        root = _long_path(os.environ.get("MAZE_PROJECT_ROOT", ""))
        if root and ".." in os.path.relpath(long_script, root).replace("\\", "/"):
            nuke.message("Script not under MZE project.\nPlease save under MZE before sending to Teams.")
            return

        flipdir = _ensure_flip_dir(script_path)
        script_base = os.path.splitext(os.path.basename(script_path))[0]
        script_clean = re.sub(r"_v\d+$", "", script_base.replace(".nk", ""))

        base = re.sub(r"_v\d+$", "", script_clean)
        pat = re.compile(rf"^{re.escape(base)}_v(\d{{3}})\.png$", re.IGNORECASE)
        max_v = 0
        if os.path.isdir(flipdir):
            for f in os.listdir(flipdir):
                m = pat.match(f)
                if m:
                    max_v = max(max_v, int(m.group(1)))
        version = max_v + 1
        png_path = os.path.join(flipdir, f"{base}_v{version:03d}.png")

        current_frame = int(nuke.frame())

        try:
            viewer = nuke.activeViewer()
            viewer_node = viewer.node() if viewer else None
            active_input = viewer.activeInput() if viewer else -1
            viewer_input = viewer_node.input(active_input) if viewer_node and active_input >= 0 else None
        except Exception:
            viewer_input = None
        if viewer_input is None:
            nuke.message("Connect a node to the active Viewer before sending a frame.")
            return

        tmp_dir = tempfile.mkdtemp(prefix="maze_frame_")
        tmp_png = os.path.join(tmp_dir, "frame.png")

        ocio_node = nuke.nodes.OCIODisplay(name="MazeFrameOCIO")
        ocio_node.setInput(0, viewer_input)
        if ocio_node.knob("display"):
            ocio_node["display"].setValue(FLIPBOOK_DISPLAY)
        if ocio_node.knob("view"):
            ocio_node["view"].setValue(FLIPBOOK_VIEW)

        write_node = nuke.nodes.Write(
            name="MazeFrameWrite",
            file=tmp_png.replace("\\", "/"),
            file_type="png"
        )
        write_node.setInput(0, ocio_node)
        if write_node.knob("create_directories"):
            write_node["create_directories"].setValue(True)
        if write_node.knob("raw"):
            write_node["raw"].setValue(True)

        try:
            nuke.execute(write_node, start=current_frame, end=current_frame, continueOnError=True)
        except Exception as e:
            nuke.message(f"Render failed: {e}")
            return
        finally:
            try:
                write_node.knob("remove")()
            except Exception:
                pass
            try:
                ocio_node.knob("remove")()
            except Exception:
                pass

        if not os.path.exists(tmp_png):
            nuke.message("Frame render produced no output.")
            return

        import shutil
        shutil.copy2(tmp_png, png_path)
        try:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

        comment = ""
        if node:
            try:
                comment = node["message_text"].value()
            except Exception:
                pass
        if not comment:
            try:
                from PySide6.QtWidgets import QInputDialog
                comment, ok = QInputDialog.getText(None, "Dailies", "Add a note (optional):")
                if not ok:
                    return
            except Exception:
                pass

        ok = post_frame(png_path, comment)
        if not ok:
            nuke.message(f"Teams post failed. Check console. File saved to:\n{png_path}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        nuke.message(f"Frame send error:\n{e}")

# --- Flipbook execution ---
def flipbook_sender_execute(node):
    try:
        node['do_flip'].setEnabled(False)
    except Exception as e:
        print(f"Could not disable button: {e}")

    try:
        script_path = nuke.root().name()
        if not script_path or script_path == "Root" or "untitled" in Path(script_path).name.lower():
            nuke.message("Please save the script before running Flipbook.")
            return

        # Guard: script should be under MZE/MAZE project for OneDrive link
        long_script = _long_path(script_path)
        root = _long_path(os.environ.get("MAZE_PROJECT_ROOT", ""))
        if root and ".." in os.path.relpath(long_script, root).replace("\\", "/"):
            nuke.message("Script not under MZE project.\nPlease save under MZE before sending to Teams.")
            return

        flipdir = _ensure_flip_dir(script_path)
        script_base = os.path.splitext(os.path.basename(script_path))[0]
        script_clean = re.sub(r"_v\d+$", "", script_base.replace(".nk", ""))

        mp4_path, _ = _get_next_versioned_path(flipdir, script_clean)

        first_frame = int(node['first_frame'].value())
        last_frame = int(node['last_frame'].value())
        fps_val = int(node['fps'].value() or 24)

        # Get the write node safely
        write_node = None
        for child_node in node.nodes():
            if child_node.name() == "FlipbookWrite":
                write_node = child_node
                break

        if not write_node:
            nuke.message("Could not find FlipbookWrite node inside group.")
            return

        # Update write node settings: file, range, fps
        node.begin()
        try:
            write_node['file'].setValue(mp4_path.replace("\\", "/"))
            write_node['first'].setValue(first_frame)
            write_node['last'].setValue(last_frame)
            if write_node.knob('mov64_fps'):
                write_node['mov64_fps'].setValue(fps_val)
        finally:
            node.end()

        # Execute the render in main thread
        def execute_render():
            try:
                print("Rendering flipbook...")
                nuke.execute(write_node, start=first_frame, end=last_frame, continueOnError=True)
                print(f"Rendered flipbook {mp4_path} ({first_frame}-{last_frame} @ {fps_val}fps)")
                if not post_flipbook(mp4_path, node["message_text"].value()):
                    nuke.message(f"Teams post failed. Check the Nuke Script Editor. File saved to:\n{mp4_path}")
            except Exception as e:
                if "already executing" not in str(e):
                    nuke.message(f"Render failed: {str(e)}")
                else:
                    print("Render already in progress. Ignoring new request.")

        print("About to render")
        execute_render()

    except Exception as e:
        import traceback
        traceback.print_exc()
        nuke.message(f"Flipbook error:\n{e}")

    finally:
        try:
            node['do_flip'].setEnabled(True)
        except Exception:
            pass

# --- Group node creation ---
def create_flipbook_sender_node():
    script_path = nuke.root().name()
    if not script_path or script_path == "Root" or "untitled" in Path(script_path).name.lower():
        nuke.message("Please save the script before creating Flipbook node.")
        return None

    existing = [n.name() for n in nuke.allNodes() if n.Class() == "Group" and n.name().startswith("Flipbook")]
    name = "Flipbook" if "Flipbook" not in existing else f"Flipbook{len(existing)+1}"

    g = nuke.createNode("Group", f"name {name}", inpanel=False)
    g.begin()
    try:
        inp = nuke.nodes.Input(name="input1")

        ocio_node = nuke.nodes.OCIODisplay(name="FlipbookOCIO")
        ocio_node.setInput(0, inp)

        if ocio_node.knob("display"):
            ocio_node["display"].setValue(FLIPBOOK_DISPLAY)
        if ocio_node.knob("view"):
            ocio_node["view"].setValue(FLIPBOOK_VIEW)

        dirpath = os.path.dirname(script_path)
        flipdir = _ensure_flip_dir(script_path)
        script_base = os.path.splitext(os.path.basename(script_path))[0]
        script_clean = re.sub(r"_v\d+$", "", script_base.replace(".nk", ""))
        mp4_path, _ = _get_next_versioned_path(flipdir, script_clean)
        mp4_path = mp4_path.replace("\\", "/")

        write_node = nuke.nodes.Write(
            name="FlipbookWrite",
            file=mp4_path,
            file_type="mov"
        )
        write_node.setInput(0, ocio_node)
        out = nuke.nodes.Output(name="output1")
        out.setInput(0, write_node)

        if write_node.knob("raw"):
            write_node["raw"].setValue(True)
        if write_node.knob("meta_codec"):
            write_node["mov64_codec"].setValue("hevc")
        elif write_node.knob("codec"):
            write_node["codec"].setValue("hevc")
        if write_node.knob("create_directories"):
            write_node["create_directories"].setValue(True)
        if write_node.knob("use_limit"):
            write_node["use_limit"].setValue(True)

        write_node['first'].setValue(int(nuke.root()['first_frame'].value()))
        write_node['last'].setValue(int(nuke.root()['last_frame'].value()))

    except Exception as e:
        import traceback
        traceback.print_exc()
        nuke.message(f"Error creating flipbook node: {str(e)}")
        g.kill()
        return None
    finally:
        g.end()

    g.addKnob(nuke.Int_Knob("first_frame", "First Frame"))
    g.addKnob(nuke.Int_Knob("last_frame", "Last Frame"))
    g.addKnob(nuke.Int_Knob("fps", "FPS"))
    g.addKnob(nuke.String_Knob("message_text", "Message Text"))
    g.addKnob(nuke.PyScript_Knob("do_flip", "Create Flipbook"))
    g.addKnob(nuke.PyScript_Knob("send_frame", "Send Frame"))

    g['first_frame'].setValue(int(nuke.root()['first_frame'].value()))
    g['last_frame'].setValue(int(nuke.root()['last_frame'].value()))
    g['fps'].setValue(24)
    g['message_text'].setValue("")

    module_name = __name__
    g['do_flip'].setCommand(f'{module_name}.flipbook_sender_execute(nuke.thisNode())')
    g['send_frame'].setCommand(f'{module_name}.send_frame_to_dailies(nuke.thisNode())')

    return g

# --- Global KnobChanged callback ---
def _flipbook_knob_changed():
    try:
        node = nuke.thisNode()
        knob = nuke.thisKnob()
        if not node or node.Class() != "Group":
            return
        if not node.name().startswith("Flipbook"):
            return
        if not knob:
            return
        if knob.name() in ["first_frame", "last_frame", "fps"]:
            node.begin()
            try:
                wn = nuke.toNode("FlipbookWrite")
                if wn:
                    if knob.name() == "first_frame":
                        wn["first"].setValue(int(knob.value()))
                    elif knob.name() == "last_frame":
                        wn["last"].setValue(int(knob.value()))
                    elif knob.name() == "fps" and wn.knob("mov64_fps"):
                        wn["mov64_fps"].setValue(int(knob.value()))
            finally:
                node.end()
    except Exception:
        import traceback
        traceback.print_exc()

# --- Menu registration ---
def main():
    # Top menu bar MAZE -> Playblast / Send Frame
    try:
        m = nuke.menu("Nuke").addMenu("MAZE", index=999)
        m.addCommand("Playblast", create_flipbook_sender_node, "ctrl+shift+f")
        m.addCommand("Send Frame", lambda: send_frame_to_dailies(), "ctrl+shift+g")
    except Exception:
        pass
    # Side bar (Nodes toolbar) MAZE -> Playblast / Send Frame
    try:
        tb = nuke.toolbar("Nodes")
        mtb = tb.addMenu("MAZE", index=999)
        mtb.addCommand("Playblast", create_flipbook_sender_node, "ctrl+shift+f")
        mtb.addCommand("Send Frame", lambda: send_frame_to_dailies(), "ctrl+shift+g")
    except Exception:
        # Fallback to Nodes menu
        try:
            menu = nuke.menu("Nodes")
            fm = menu.addMenu("MAZE Flipbook", index=999)
            fm.addCommand("Create Flipbook Node", create_flipbook_sender_node, "ctrl+shift+f")
            fm.addCommand("Send Frame", lambda: send_frame_to_dailies(), "ctrl+shift+g")
        except Exception:
            pass

    if not hasattr(nuke, "_maze_flipbook_knobcb_installed"):
        nuke.addKnobChanged(_flipbook_knob_changed)
        nuke._maze_flipbook_knobcb_installed = True

main()
