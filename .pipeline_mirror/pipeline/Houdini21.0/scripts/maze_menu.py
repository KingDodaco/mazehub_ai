"""MAZE Houdini/MPlay tools — flipbook compile + Teams (MZE / $JOB)."""
import hou
import os
import json
import re
import shutil
import subprocess
import tempfile
import getpass
import socket
from datetime import datetime
from pathlib import Path
import urllib.request

try:
    from pxr import UsdGeom
except ImportError:
    UsdGeom = None
try:
    import requests
except ImportError:
    requests = None


def get_mazehub_settings():
    settings_path = Path.home() / '.config' / 'mazehub' / 'settings.json'
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            return json.load(f)
    return {}


def _long_path(p):
    """Expand Windows 8.3 short names (RENDER~1 -> RENDER_TEST)"""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetLongPathNameW(str(p), buf, 512)
        return buf.value or str(p)
    except Exception:
        return str(p)


def get_sharepoint_url(file_path):
    try:
        from urllib.parse import quote
        pipeline_root = _long_path(os.environ.get('MAZE_PIPELINE', ''))
        if not pipeline_root:
            return None
        file_str = _long_path(str(file_path))
        if file_str == '.':
            return None
        sp_base = '/sites/FMP2/Shared Documents/PROJECT/MAZE'
        rel_path = os.path.relpath(file_str, pipeline_root).replace('\\', '/')
        parts = (sp_base + '/' + rel_path).split('/')
        resolved = []
        for p in parts:
            if not p or p == '.':
                continue
            if p == '..':
                if resolved:
                    resolved.pop()
            else:
                resolved.append(p)
        normalized = '/' + '/'.join(resolved)
        encoded = quote(normalized, safe='/')
        return f'https://livebournemouthac.sharepoint.com/sites/FMP2/_layouts/15/stream.aspx?id={encoded}'
    except Exception:
        return None


def send_dailies_notification(webhook_url, shot, artist, file_path, notes=''):
    if not webhook_url:
        return False
    facts = [{'name': 'Artist', 'value': artist}]
    if notes:
        facts.append({'name': 'Notes', 'value': notes})
    sp_url = get_sharepoint_url(file_path)
    text = f'**File:** {file_path}'
    if sp_url:
        text += f'\n**[Open in SharePoint]({sp_url})**'
    card = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'themeColor': 'E8790B',
        'summary': f'Dailies: {shot}',
        'sections': [{
            'activityTitle': f'Dailies: {shot}',
            'facts': facts,
            'markdown': True,
            'text': text,
        }],
    }
    data = json.dumps(card).encode('utf-8')
    req = urllib.request.Request(webhook_url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def get_shot_name():
    hip_file = hou.hipFile.path()
    if hip_file.startswith('untitled'):
        return None
    path = Path(hip_file)
    parts = path.parts
    for i, part in enumerate(parts):
        if part.lower() == 'shot' and i + 1 < len(parts):
            return parts[i + 1]
    return path.stem


def get_artist_name():
    try:
        import ctypes
        size = ctypes.c_ulong(0)
        import ctypes.wintypes
        # secur32 GetUserNameExW display name
        ctypes.windll.secur32.GetUserNameExW(3, None, ctypes.byref(size))
        buf = ctypes.create_unicode_buffer(size.value)
        ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size))
        return buf.value
    except Exception:
        return os.environ.get('USERNAME', 'Unknown')


# --- Provided code adapted for MZE / $JOB / compile-only ---

def version_up(filepath):
    base, ext = os.path.splitext(filepath)
    match = re.search(r"_v(\d+)$", base)
    if match:
        version = int(match.group(1)) + 1
        new_base = re.sub(r"_v(\d+)$", f"_v{version:03d}", base)
    else:
        new_base = f"{base}_v002"
    hou.hipFile.save(file_name=new_base + ext)


def get_default_output():
    """$JOB/flipbooks/<hipname>_vXXX.mp4 — falls back to $HIP, auto-versions."""
    job_dir = hou.getenv("JOB") or os.environ.get("JOB") or os.environ.get("HIP", "")
    hip_name = os.path.splitext(hou.hipFile.basename())[0]
    if not hip_name or hip_name.lower().startswith("untitled"):
        hip_name = "flipbook"
    # Strip existing _vNNN for base
    base = re.sub(r"_v\d+$", "", hip_name)
    flipbooks_dir = os.path.join(job_dir, "flipbooks") if job_dir else ""
    version = 1
    if flipbooks_dir and os.path.isdir(flipbooks_dir):
        pat = re.compile(rf"^{re.escape(base)}_v(\d{{3}})\.mp4$", re.IGNORECASE)
        max_v = 0
        for f in os.listdir(flipbooks_dir):
            m = pat.match(f)
            if m:
                max_v = max(max_v, int(m.group(1)))
        version = max_v + 1
        # If hip already carried version and no files yet, honor that version
        m2 = re.search(r"_v(\d+)$", hip_name)
        if m2 and max_v == 0:
            version = int(m2.group(1))
    return os.path.abspath(os.path.join(job_dir, "flipbooks", f"{base}_v{version:03d}.mp4"))


def format_versioned_filename(name):
    return re.sub(r"_v(\d+)$", r" (v\1)", name)


def local_to_onedrive_link(local_path):
    """MAZE mapping: local -> https://livebournemouthac.sharepoint.com/sites/FMP2/Shared%20Documents/PROJECT/MAZE/..."""
    local_path = _long_path(local_path)
    web_root = "https://livebournemouthac.sharepoint.com/sites/FMP2/Shared%20Documents/PROJECT/MAZE/"
    web_root = os.environ.get("MAZE_ONEDRIVE_ROOT", web_root)
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
        job = _long_path(hou.getenv("JOB") or os.environ.get("JOB", ""))
        if job:
            rel = os.path.relpath(local_path, job).replace("\\", "/")
            return web_root + rel.lstrip("/")
    except Exception:
        pass
    raise ValueError(f"Path does not contain 'MAZE' and cannot be mapped: {local_path}")


def get_camera_resolution(viewport, in_solaris=False, camera_path=None, use_custom_resolution=False, custom_resolution=(1920, 1080)):
    if use_custom_resolution:
        return custom_resolution
    if not in_solaris:
        cam = viewport.camera()
        if cam:
            try:
                return (cam.parm("resx").eval(), cam.parm("resy").eval())
            except Exception:
                pass
    elif in_solaris and camera_path and UsdGeom:
        try:
            stage_node = hou.node("/stage").viewerNode()
            if not stage_node:
                raise RuntimeError("No display node in /stage")
            usd_stage = stage_node.stage()
            cam_prim = usd_stage.GetPrimAtPath(camera_path)
            if not cam_prim or not cam_prim.IsValid():
                raise RuntimeError(f"Invalid USD camera: {camera_path}")
            usd_camera = UsdGeom.Camera(cam_prim)
            horiz = usd_camera.GetHorizontalApertureAttr().Get()
            vert = usd_camera.GetVerticalApertureAttr().Get()
            if horiz and vert and horiz > 0 and vert > 0:
                aspect_ratio = horiz / vert
                if aspect_ratio >= 1.0:
                    resx = 1920
                    resy = int(resx / aspect_ratio)
                else:
                    resy = 1920
                    resx = int(resy * aspect_ratio)
                return (resx, resy)
        except Exception as e:
            print(f"Failed to get Solaris camera resolution: {e}")
    x, y, width, height = viewport.size()
    if hou.isApprentice():
        scale = min(1280 / width, 720 / height, 1.0)
        width = int(width * scale)
        height = int(height * scale)
    return (width, height)


def compile_existing_flipbook(input_pattern, output, start_frame=1001):
    """Compile existing image sequence (e.g. $JOB/flipbooks/flipbook.$F4.jpeg) to MP4 via hffmpeg. No scene.flipbook() call."""
    os.makedirs(os.path.dirname(output), exist_ok=True)
    # input_pattern is like /path/flipbook.$F4.jpeg -> need %04d form for ffmpeg
    ffmpeg_input = input_pattern.replace("$F4", "%04d")
    ffmpeg_path = os.path.join(os.environ.get("HFS", ""), "bin", "hffmpeg")
    if not os.path.exists(ffmpeg_path):
        ffmpeg_path = "hffmpeg"
    framerate = int(hou.fps())
    # Try hardware then software fallback
    for codec in ("h264_nvenc", "libx264"):
        cmd = [
            ffmpeg_path, "-y", "-framerate", str(framerate),
            "-start_number", str(start_frame), "-i", ffmpeg_input,
            "-c:v", codec, "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium",
            output,
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        if result.returncode == 0 and os.path.exists(output):
            return output
    raise RuntimeError(f"hffmpeg failed to compile {input_pattern} -> {output}")


def flipbook(output=None, start_frame=1001, end_frame=1101, use_custom_resolution=False, custom_resolution=(1920, 1080)):
    """Legacy: render then compile. Kept for Houdini FlipbookUI; MPlay path uses compile_existing_flipbook."""
    if not output:
        output = get_default_output()
    temp_dir = tempfile.mkdtemp(prefix="flipbook_")
    local_output = os.path.join(temp_dir, os.path.basename(output))
    input_pattern = os.path.join(temp_dir, "flipbook.$F4.jpeg")
    scene = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    viewport = scene.curViewport()
    settings = scene.flipbookSettings().stash()
    camera_path = viewport.cameraPath()
    cam = viewport.camera()
    in_solaris = cam is None and camera_path is not None
    settings.output(input_pattern)
    settings.frameRange((start_frame, end_frame))
    settings.useResolution(True)
    settings.outputToMPlay(True)
    settings.resolution(get_camera_resolution(viewport, in_solaris, camera_path, use_custom_resolution, custom_resolution))
    print(f"Rendering flipbook frames to {temp_dir}")
    scene.flipbook(viewport, settings=settings)
    # Keep jpeg sequence in $JOB/flipbooks for MPlay compile
    try:
        job_dir = hou.getenv("JOB") or os.environ.get("JOB") or ""
        if job_dir:
            keep_dir = os.path.join(job_dir, "flipbooks")
            os.makedirs(keep_dir, exist_ok=True)
            for f in Path(temp_dir).glob("*.jpeg"):
                shutil.copy2(str(f), os.path.join(keep_dir, f.name))
            # also copy as .jpg variant if needed
            print(f"Saved jpeg sequence to {keep_dir}")
    except Exception as e:
        print(f"Failed to keep jpeg sequence: {e}")
    ffmpeg_path = os.path.join(os.environ.get("HFS", ""), "bin", "hffmpeg")
    framerate = int(hou.fps())
    cmd = [ffmpeg_path, "-y", "-framerate", str(framerate), "-start_number", str(start_frame), "-i", input_pattern.replace("$F4", "%04d"), "-c:v", "h264_nvenc", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium", local_output]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, creationflags=flags)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    shutil.copy2(local_output, output)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return output


def post_flipbook(output, comment=""):
    """Post flipbook MP4 to Teams via PowerAutomate Adaptive Card. Webhook from settings dailies_webhook_url, fallback hardcoded."""
    try:
        onedrive_link = local_to_onedrive_link(output)
    except Exception as e:
        print(f"local_to_onedrive_link failed ({e}), trying get_sharepoint_url")
        onedrive_link = get_sharepoint_url(output)
        if not onedrive_link:
            # last fallback: use local path as-is (will fail in Teams but show error)
            raise
    settings = get_mazehub_settings()
    webhook_url = settings.get("dailies_webhook_url") or os.environ.get("MAZE_DAILIES_WEBHOOK") or "https://defaultede29655d09742e4bbb5f38d427fbf.b8.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/cdf54a2c13564d2dba8edc95a608ff50/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=PaCvoX6XhuOJC3S4ubnKnOQuuWZUasyKX52AdQp33OA"
    try:
        username = get_artist_name()
    except Exception:
        username = getpass.getuser()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = os.path.splitext(os.path.basename(output))[0]
    # Shot/asset + hip file for title
    context_name = os.environ.get("MAZE_CONTEXT_NAME") or ""
    hip_path = ""
    try:
        hp = hou.hipFile.path()
        if hp and "untitled" not in Path(hp).name.lower():
            hip_path = _long_path(hp)
    except Exception:
        pass
    if not context_name:
        try:
            context_name = get_shot_name() or ""
        except Exception:
            pass
    if not context_name:
        context_name = Path(hip_path).stem if hip_path else filename
    title_text = f"{context_name} — {format_versioned_filename(filename)}" if context_name else format_versioned_filename(filename)
    hip_text = hip_path or ""
    message = username
    pretty_comment = f'"{comment}"' if comment else ""
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.5",
                "body": [
                    {"type": "Container", "items": [
                        {"type": "TextBlock", "text": title_text, "wrap": True, "weight": "Bolder", "size": "Large", "color": "Accent"},
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
    url = webhook_url
    if requests is not None:
        r = requests.post(url, json=payload, timeout=15)
        if 200 <= r.status_code < 300:
            print("Posted to Teams")
            return True
        print(f"Failed to post: {r.status_code} - {r.text}")
        return False
    else:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=15)
            print("Posted to Teams")
            return True
        except Exception as e:
            print(f"Failed to post: {e}")
            return False


def send_to_dailies():
    """MPlay MAZE menu entry: compile existing $JOB/flipbooks sequence to MP4, render if missing, then send. No image-sequence send."""
    # Guard: hip must be saved under MZE (check JOB/context in MPlay where hou.hipFile is untitled)
    hip_saved = False
    try:
        hp = hou.hipFile.path()
        if hp and "untitled" not in Path(hp).name.lower():
            hip_saved = True
    except Exception:
        pass
    if not hip_saved:
        job = hou.getenv("JOB") or os.environ.get("JOB", "")
        ctx = os.environ.get("MAZE_CONTEXT_PATH", "")
        if job and os.path.isdir(job):
            hip_saved = True
        elif ctx and os.path.isdir(ctx):
            hip_saved = True
    if not hip_saved:
        msg = "Hip file not saved.\n\nPlease save your hip under MZE (e.g. via MAZE > Save) before sending to Teams."
        print(msg)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Save Hip First", msg)
        except Exception:
            try:
                from PySide2.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Save Hip First", msg)
            except Exception:
                pass
        return
    settings = get_mazehub_settings()
    job_dir = hou.getenv("JOB") or os.environ.get("JOB") or ""
    flipbooks_dir = os.path.join(job_dir, "flipbooks") if job_dir else ""
    output = get_default_output()
    # Ensure flipbooks dir exists
    if flipbooks_dir:
        try:
            os.makedirs(flipbooks_dir, exist_ok=True)
        except Exception:
            pass
    # If no mp4, try compile existing jpeg sequence; if none, render a new flipbook first
    if not os.path.exists(output):
        compiled = False
        if flipbooks_dir and os.path.isdir(flipbooks_dir):
            seq_files = sorted([p for p in Path(flipbooks_dir).glob("*.jpeg")])
            # also try jpg
            if not seq_files:
                seq_files = sorted([p for p in Path(flipbooks_dir).glob("*.jpg")])
            if seq_files:
                first = seq_files[0].name
                m = re.search(r"(\d{4})(?=\.jpe?g$)", first)
                if m:
                    start_frame = int(m.group(1))
                    input_pat = str(Path(flipbooks_dir) / re.sub(r"\d{4}(?=\.jpe?g$)", "$F4", first))
                    try:
                        output = compile_existing_flipbook(input_pat, output, start_frame=start_frame)
                        compiled = True
                        print(f"Compiled existing sequence {input_pat} -> {output}")
                    except Exception as e:
                        print(f"Compile existing failed: {e}")
                        import traceback; traceback.print_exc()
        if not compiled:
            msg = f"No flipbook images found in:\n{flipbooks_dir}\n\nIn Houdini use MAZE > Flipbook to $JOB/flipbooks (or set Flipbook Output to $JOB/flipbooks/flipbook.$F4.jpeg) then open in MPlay and Send again."
            print(msg)
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(None, "No Flipbook Found", msg)
            except Exception:
                try:
                    from PySide2.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "No Flipbook Found", msg)
                except Exception:
                    pass
            return

    shot = 'untitled'
    source_path = None
    context_path = os.environ.get('MAZE_CONTEXT_PATH', '')
    if context_path:
        source_path = Path(context_path)
        shot = source_path.name
    if not source_path or 'untitled' in shot.lower():
        try:
            hip_file = hou.hipFile.path()
            if hip_file and 'untitled' not in Path(hip_file).name.lower():
                source_path = Path(hip_file)
                parts = source_path.parts
                for i, part in enumerate(parts):
                    if part.lower() == 'shot' and i + 1 < len(parts):
                        shot = parts[i + 1]
                        break
        except Exception:
            pass
    # Prefer the compiled mp4 as source_path for sharepoint link if it exists
    if os.path.exists(output):
        source_path = Path(output)

    webhook_url = settings.get('dailies_webhook_url', '')
    artist = get_artist_name()
    notes = ''
    try:
        from PySide6.QtWidgets import QInputDialog, QApplication
        app = QApplication.instance() or QApplication([])
        notes, ok = QInputDialog.getText(None, 'Dailies', 'Add a note (optional):')
        if not ok:
            return
    except Exception:
        try:
            from PySide2.QtWidgets import QInputDialog, QApplication
            app = QApplication.instance() or QApplication([])
            notes, ok = QInputDialog.getText(None, 'Dailies', 'Add a note (optional):')
            if not ok:
                return
        except Exception:
            pass

    # If mp4 exists, post via Adaptive Card Media (video), else fallback to MessageCard
    if os.path.exists(output):
        ok = post_flipbook(output, notes)
        if not ok:
            try:
                hou.ui.displayMessage(f"Teams post failed. Check console. File saved to:\n{output}")
            except Exception:
                pass
    else:
        send_dailies_notification(webhook_url, shot, artist, source_path or Path('.'), notes)

