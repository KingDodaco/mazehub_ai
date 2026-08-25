"""MAZE Houdini tools."""
import hou
import os
import json
import urllib.request
from pathlib import Path


def get_mazehub_settings():
    settings_path = Path.home() / '.config' / 'mazehub' / 'settings.json'
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            return json.load(f)
    return {}


def get_sharepoint_url(file_path):
    try:
        from urllib.parse import quote

        pipeline_root = os.environ.get('MAZE_PIPELINE', '')
        if not pipeline_root:
            return None

        file_str = str(file_path)
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

    facts = [
        {'name': 'Artist', 'value': artist},
    ]
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
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
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
        import secur32
        import ctypes

        size = ctypes.c_ulong(0)
        secur32.GetUserNameExW(3, None, ctypes.byref(size))
        buf = ctypes.create_unicode_buffer(size.value)
        secur32.GetUserNameExW(3, buf, ctypes.byref(size))
        return buf.value
    except Exception:
        return os.environ.get('USERNAME', 'Unknown')


def send_to_dailies():
    settings = get_mazehub_settings()
    webhook_url = settings.get('dailies_webhook_url', '')
    if not webhook_url:
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

    artist = get_artist_name()

    notes = ''
    try:
        from PySide6.QtWidgets import QInputDialog, QApplication
        app = QApplication.instance() or QApplication([])
        notes, ok = QInputDialog.getText(None, 'Dailies', 'Add a note (optional):')
        if not ok:
            return
    except Exception:
        pass

    result = send_dailies_notification(
        webhook_url=webhook_url,
        shot=shot,
        artist=artist,
        file_path=source_path or Path('.'),
        notes=notes,
    )
