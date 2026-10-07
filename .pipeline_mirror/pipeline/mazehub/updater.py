"""Self-update support for MazeHub: check, download, verify, apply, exe swap."""
import json
import hashlib
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

GITHUB_REPO = 'KingDodaco/mazehub_ai'
GITHUB_LATEST_URL = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
ZIP_NAME = 'MazeHub-pipeline.zip'
MANIFEST_NAME = 'manifest.json'
EXE_NAME = 'MazeHub.exe'
STATE_DIRNAME = '.update'
LOCK_FILENAME = 'update.lock'
LOCK_TIMEOUT_SECONDS = 120
LOCK_STALE_SECONDS = 900
MERGE_PATHS = ('mazehub/apps.json',)
PRESERVE_PATHS = ('mazehub/styles.qss', 'mazehub/icon.png')
SIDECAR_SUFFIX = '.new'
TMP_SUFFIX = '.mztmp'
HTTP_HEADERS = {
    'User-Agent': 'MazeHub-Updater',
    'Accept': 'application/vnd.github+json',
}
DOWNLOAD_CHUNK = 256 * 1024
STALL_TIMEOUT_SECONDS = 45
SIDECARS_KEY = 'sidecars'


SERVER_AUTH_OID = '1.3.6.1.5.5.7.3.1'


def _system_ca_pems():
    enum = getattr(ssl, 'enum_certificates', None)
    if enum is None:
        return []
    pems = []
    for store_name in ('CA', 'ROOT'):
        try:
            entries = enum(store_name)
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if not isinstance(entry, (tuple, list)) or len(entry) < 2:
                continue
            if len(entry) >= 3:
                cert, encoding, trust = entry[0], entry[1], entry[2]
                if encoding != 'x509_asn':
                    continue
                trusted = trust is True or (
                    bool(trust) and SERVER_AUTH_OID in trust)
                if not trusted:
                    continue
            else:
                cert = entry[0]
            if not isinstance(cert, (bytes, bytearray)):
                cert = next(
                    (v for v in entry
                     if isinstance(v, (bytes, bytearray))), None)
                if cert is None:
                    continue
            try:
                if b'-----BEGIN' in cert[:64]:
                    pems.append(bytes(cert).decode('ascii'))
                else:
                    pems.append(ssl.DER_cert_to_PEM_cert(bytes(cert)))
            except (ValueError, TypeError, ssl.SSLError):
                continue
    return pems


def _ssl_context():
    env_ca = os.environ.get('SSL_CERT_FILE')
    if env_ca and os.path.isfile(env_ca):
        return ssl.create_default_context()
    ctx = None
    try:
        import certifi
        cafile = certifi.where()
        if cafile and os.path.isfile(cafile):
            ctx = ssl.create_default_context(cafile=cafile)
    except Exception:
        ctx = None
    if ctx is None:
        ctx = ssl.create_default_context()
    for pem in _system_ca_pems():
        try:
            ctx.load_verify_locations(cadata=pem)
        except (ssl.SSLError, ValueError):
            continue
    return ctx


def _ssl_debug():
    bits = []
    env_ca = os.environ.get('SSL_CERT_FILE')
    if env_ca:
        bits.append(f'SSL_CERT_FILE={env_ca}'
                    f'({"ok" if os.path.isfile(env_ca) else "missing"})')
    else:
        bits.append('SSL_CERT_FILE=unset')
    try:
        import certifi
        cafile = certifi.where()
        bits.append('certifi=' + (
            'ok' if os.path.isfile(cafile) else f'missing ({cafile})'))
    except Exception as exc:
        bits.append(f'certifi=unavailable ({exc})')
    try:
        bits.append(f'CA certs={len(_ssl_context().get_ca_certs())}')
    except Exception as exc:
        bits.append(f'CA certs=error ({exc})')
    return '; '.join(bits)


def _net_error(prefix, exc):
    text = f'{prefix}: {exc.reason}'
    if 'CERTIFICATE' in str(exc).upper():
        text += (' - SSL certificate could not be verified. Check the '
                 'system clock, a proxy or firewall inspecting TLS, or '
                 'update manually from the GitHub releases page.'
                 f' TLS client info: {_ssl_debug()}')
    return text


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    zip_url: str
    manifest_url: str
    notes: str = ''
    is_newer: bool = False
    channel: str = ''


@dataclass
class ApplyResult:
    version: str
    bootstrap: bool = False
    written: list = field(default_factory=list)
    restored: list = field(default_factory=list)
    uptodate: list = field(default_factory=list)
    preserved: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    deleted: list = field(default_factory=list)
    trashed: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    exe_action: str = 'none'
    staged_exe: object = None

    @property
    def changed(self):
        return bool(
            self.written or self.restored or self.deleted or self.trashed
            or self.preserved or self.collisions or self.conflicts or self.failed
        )

    def to_dict(self):
        return {
            'version': self.version,
            'bootstrap': self.bootstrap,
            'written': self.written,
            'restored': self.restored,
            'uptodate': self.uptodate,
            'preserved': self.preserved,
            'collisions': self.collisions,
            'deleted': self.deleted,
            'trashed': self.trashed,
            'conflicts': self.conflicts,
            'failed': self.failed,
            'exe_action': self.exe_action,
            'applied': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }

    def summary(self):
        lines = [f'MazeHub updated to {self.version}']
        if self.bootstrap:
            lines.append('First self-update: existing files synced with the release '
                         '(settings preserved).')
        for label, items in (
            ('Updated', self.written + self.restored),
            ('Kept local changes (release saved as .new)', self.preserved + self.collisions),
            ('Removed', self.deleted),
            ('Moved to trash', self.trashed),
            ('Conflicts (local value kept)', self.conflicts),
            ('Failed', self.failed),
        ):
            if items:
                shown = ', '.join(items[:8])
                more = f' (+{len(items) - 8} more)' if len(items) > 8 else ''
                lines.append(f'{label} {len(items)}: {shown}{more}')
        if len(lines) == 1:
            lines.append('All files already up to date.')
        return '\n'.join(lines)


def semver_key(version):
    parts = []
    text = str(version or '').strip().lstrip('vV')
    text = text.replace('-', '.').replace('+', '.')
    for chunk in text.split('.'):
        digits = ''
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(DOWNLOAD_CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _atomic_write_json(path, data):
    _atomic_write_bytes(path, json.dumps(data, indent=4).encode('utf-8'))


def _copy_atomic(src, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + TMP_SUFFIX)
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)


def _rel(path, root):
    return Path(path).relative_to(root).as_posix()


def build_manifest(root, version):
    root = Path(root)
    files = []
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if STATE_DIRNAME in rel.parts or '__pycache__' in rel.parts:
            continue
        if path.name.endswith(TMP_SUFFIX):
            continue
        posix = rel.as_posix()
        files.append({
            'path': posix,
            'sha256': sha256_file(path),
            'size': path.stat().st_size,
        })
    return {
        'name': 'MazeHub',
        'version': version,
        'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'files': files,
    }


def _manifest_index(manifest):
    return {e['path']: e for e in manifest.get('files', [])}


def find_install_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return None


def _state_dir(install_root):
    return Path(install_root) / STATE_DIRNAME


def load_installed(install_root):
    data = _load_json(_state_dir(install_root) / 'installed_manifest.json')
    if isinstance(data, dict) and isinstance(data.get('files'), list):
        return data
    return None


def _save_installed(install_root, data):
    _atomic_write_json(_state_dir(install_root) / 'installed_manifest.json', data)


def exe_drift(install_root):
    installed = load_installed(install_root)
    if not installed:
        return None
    entry = None
    for item in installed.get('files') or []:
        if isinstance(item, dict) and item.get('path') == EXE_NAME:
            entry = item
            break
    if not entry:
        return None
    exe = Path(install_root) / EXE_NAME
    if not exe.is_file():
        return None
    try:
        actual = sha256_file(exe)
    except OSError:
        return None
    expected = entry.get('sha256')
    if expected and actual != expected:
        return expected, actual
    return None


def get_channel():
    try:
        from settings import get_setting
        return (get_setting('update_channel') or '').strip()
    except Exception:
        return ''


def get_pref(key, default=None):
    try:
        from settings import get_setting
        value = get_setting(key)
        return default if value is None else value
    except Exception:
        return default


def set_pref(key, value):
    try:
        from settings import set_setting
        set_setting(key, value)
    except Exception:
        pass


def record_check(version):
    set_pref('update_last_check', datetime.now().isoformat(timespec='seconds'))
    set_pref('update_last_known_version', version)


def _pid_alive(pid):
    pid = int(pid)
    if os.name == 'nt':
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ERROR_INVALID_PARAMETER = 87
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return ctypes.windll.kernel32.GetLastError() != ERROR_INVALID_PARAMETER
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class UpdateLock:
    def __init__(self, install_root):
        self.path = _state_dir(install_root) / LOCK_FILENAME
        self.token = None

    def acquire(self, timeout=LOCK_TIMEOUT_SECONDS):
        deadline = time.time() + timeout
        token = uuid.uuid4().hex
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._steal_if_stale():
                    continue
                if time.time() >= deadline:
                    return False
                time.sleep(1)
                continue
            try:
                payload = {
                    'pid': os.getpid(),
                    'host': socket.gethostname(),
                    'time': time.time(),
                    'token': token,
                }
                os.write(fd, json.dumps(payload).encode('utf-8'))
            finally:
                os.close(fd)
            self.token = token
            return True

    def _steal_if_stale(self):
        try:
            if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                self.path.unlink()
                return True
        except FileNotFoundError:
            return True
        data = _load_json(self.path)
        if not isinstance(data, dict):
            try:
                if time.time() - self.path.stat().st_mtime > 30:
                    self.path.unlink()
                    return True
            except FileNotFoundError:
                pass
            return False
        if time.time() - data.get('time', 0) > LOCK_STALE_SECONDS:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return True
        if data.get('host') == socket.gethostname():
            if not _pid_alive(data.get('pid', -1)):
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                return True
        return False

    def release(self):
        if self.token is None:
            return
        data = _load_json(self.path)
        if isinstance(data, dict) and data.get('token') == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.token = None


def _check_github(timeout):
    context = _ssl_context()
    req = urllib.request.Request(GITHUB_LATEST_URL, headers=HTTP_HEADERS)
    body = ''
    try:
        with urllib.request.urlopen(
                req, timeout=timeout, context=context) as resp:
            body = resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(
            f'GitHub API error {exc.code} ({exc.reason})') from exc
    except urllib.error.URLError as exc:
        raise UpdateError(_net_error('Cannot reach GitHub', exc)) from exc
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise UpdateError(
            f'Bad GitHub response: {exc}; body starts {body[:160]!r}'
        ) from exc
    tag = str(data.get('tag_name') or '')
    version = tag.lstrip('vV')
    zip_url = ''
    manifest_url = ''
    for asset in data.get('assets') or []:
        name = asset.get('name')
        url = asset.get('browser_download_url') or ''
        if name == ZIP_NAME:
            zip_url = url
        elif name == MANIFEST_NAME:
            manifest_url = url
    if not version or not zip_url or not manifest_url:
        return None
    return UpdateInfo(
        version=version,
        zip_url=zip_url,
        manifest_url=manifest_url,
        notes=str(data.get('body') or ''),
        channel='github',
    )


def _channel_manifest_url(channel):
    if channel.startswith('http://') or channel.startswith('https://'):
        return channel.rstrip('/') + '/' + MANIFEST_NAME
    path = channel
    if path.startswith('file://'):
        path = path[7:]
        if len(path) > 2 and path[0] == '/' and path[2] == ':':
            path = path[1:]
    return str(Path(path) / MANIFEST_NAME)


def _channel_zip_url(channel, zip_name):
    if channel.startswith('http://') or channel.startswith('https://'):
        return channel.rstrip('/') + '/' + zip_name
    path = channel
    if path.startswith('file://'):
        path = path[7:]
        if len(path) > 2 and path[0] == '/' and path[2] == ':':
            path = path[1:]
    return str(Path(path) / zip_name)


def _fetch_json_url(url, timeout):
    if url.startswith('http://') or url.startswith('https://'):
        context = _ssl_context()
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(
                req, timeout=timeout, context=context) as resp:
            body = resp.read().decode('utf-8', 'replace')
        try:
            return json.loads(body)
        except ValueError as exc:
            raise UpdateError(
                f'Bad manifest response: {exc}; body starts {body[:160]!r}'
            ) from exc
    data = _load_json(url)
    if data is None:
        raise UpdateError(f'Cannot read manifest: {url}')
    return data


def _check_channel(channel, timeout):
    manifest = _fetch_json_url(_channel_manifest_url(channel), timeout)
    version = str(manifest.get('version') or '').lstrip('vV')
    if not version:
        return None
    zip_name = (manifest.get('zip') or {}).get('name') or ZIP_NAME
    return UpdateInfo(
        version=version,
        zip_url=_channel_zip_url(channel, zip_name),
        manifest_url=_channel_manifest_url(channel),
        notes='',
        channel=channel,
    )


def check_for_update(current_version, channel=None, timeout=12):
    """Return UpdateInfo (is_newer set), None if no release is published,
    or raise UpdateError when the check itself fails (network/channel)."""
    if channel is None:
        channel = get_channel()
    try:
        if channel:
            info = _check_channel(channel, timeout)
        else:
            info = _check_github(timeout)
    except UpdateError:
        raise
    except urllib.error.HTTPError as exc:
        raise UpdateError(
            f'HTTP {exc.code} while checking ({exc.reason})') from exc
    except urllib.error.URLError as exc:
        raise UpdateError(_net_error(
            'Cannot reach the update server', exc)) from exc
    except Exception as exc:
        raise UpdateError(str(exc) or exc.__class__.__name__) from exc
    if info is None:
        return None
    info.is_newer = semver_key(info.version) > semver_key(current_version)
    return info


def _emit(progress_cb, phase, done, total, detail=''):
    if progress_cb:
        progress_cb(phase, done, total, detail)


def download_file(url, dest, progress_cb=None, timeout=120,
                  stall_timeout=STALL_TIMEOUT_SECONDS):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (url.startswith('http://') or url.startswith('https://')):
        src = Path(url)
        total = src.stat().st_size
        copied = 0
        with open(src, 'rb') as f_in, open(dest, 'wb') as f_out:
            while True:
                chunk = f_in.read(DOWNLOAD_CHUNK)
                if not chunk:
                    break
                f_out.write(chunk)
                copied += len(chunk)
                _emit(progress_cb, 'download', copied, total, dest.name)
        return dest
    req = urllib.request.Request(url, headers={'User-Agent': 'MazeHub-Updater'})
    with urllib.request.urlopen(
            req, timeout=timeout, context=_ssl_context()) as resp:
        total = int(resp.headers.get('Content-Length') or 0)
        sock = getattr(getattr(getattr(resp, 'fp', None), 'raw', None),
                       '_sock', None)
        if sock is not None and stall_timeout:
            try:
                sock.settimeout(stall_timeout)
            except OSError:
                sock = None
        tmp = dest.with_name(dest.name + TMP_SUFFIX)
        copied = 0
        last_data = time.time()
        try:
            with open(tmp, 'wb') as f_out:
                while True:
                    try:
                        chunk = resp.read1(DOWNLOAD_CHUNK)
                    except (socket.timeout, TimeoutError) as exc:
                        raise UpdateError(
                            f'Download stalled — no data for {stall_timeout}s '
                            f'({copied} bytes received).') from exc
                    if not chunk:
                        break
                    now = time.time()
                    if stall_timeout and now - last_data > stall_timeout:
                        raise UpdateError(
                            f'Download stalled — no data for {stall_timeout}s '
                            f'({copied} bytes received).')
                    last_data = now
                    f_out.write(chunk)
                    copied += len(chunk)
                    _emit(progress_cb, 'download', copied, total, dest.name)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        os.replace(tmp, dest)
    _emit(progress_cb, 'download', dest.stat().st_size,
          dest.stat().st_size, dest.name)
    return dest


def _verify_zip(zip_path, manifest):
    expected = (manifest.get('zip') or {}).get('sha256')
    if expected and sha256_file(zip_path) != expected:
        raise UpdateError('Downloaded archive failed checksum verification.')


def _safe_extract(zip_path, dest_dir, progress_cb=None):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        for info in infos:
            name = info.filename
            parts = Path(name).parts
            if name.startswith('/') or name.startswith('\\') or '..' in parts:
                raise UpdateError(f'Unsafe path in archive: {name}')
            if len(name) > 1 and name[1] == ':':
                raise UpdateError(f'Unsafe path in archive: {name}')
        for i, info in enumerate(infos, 1):
            zf.extract(info, str(dest_dir))
            _emit(progress_cb, 'extract', i, len(infos), info.filename)


def _verify_extracted(release_dir, manifest, progress_cb=None):
    missing = []
    bad = []
    entries = manifest.get('files', [])
    for i, entry in enumerate(entries, 1):
        path = Path(release_dir) / entry['path']
        if not path.is_file():
            missing.append(entry['path'])
            continue
        if sha256_file(path) != entry.get('sha256'):
            bad.append(entry['path'])
        _emit(progress_cb, 'verify_files', i, len(entries), entry['path'])
    if missing or bad:
        raise UpdateError(
            f'Extracted release verification failed '
            f'({len(missing)} missing, {len(bad)} corrupted).'
        )


def stage_update(info, progress_cb=None):
    work = Path(tempfile.mkdtemp(prefix='mazehub_update_'))
    try:
        zip_path = work / ZIP_NAME
        download_file(info.zip_url, zip_path, progress_cb)
        _emit(progress_cb, 'verify', 0, 1, 'release checksum')
        manifest = _fetch_json_url(info.manifest_url, timeout=30)
        _verify_zip(zip_path, manifest)
        release_dir = work / 'release'
        _safe_extract(zip_path, release_dir, progress_cb)
        _verify_extracted(release_dir, manifest, progress_cb)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return release_dir, manifest, work


def merge_three_way(base, disk, incoming, conflicts=None, path=''):
    if conflicts is None:
        conflicts = []
    if not isinstance(base, dict):
        base = {}
    if not isinstance(disk, dict):
        disk = {}
    if not isinstance(incoming, dict):
        incoming = {}
    merged = {}
    for key in list(dict.fromkeys(list(base) + list(disk) + list(incoming))):
        here = f'{path}.{key}' if path else key
        in_base = key in base
        in_disk = key in disk
        in_inc = key in incoming
        if in_inc and not in_base and not in_disk:
            merged[key] = incoming[key]
        elif in_inc and not in_base and in_disk:
            merged[key] = disk[key]
        elif in_inc and in_base and not in_disk:
            merged[key] = incoming[key]
        elif not in_inc and in_base and in_disk:
            if disk[key] == base[key]:
                continue
            conflicts.append(f'{here} (removed in release, local change kept)')
            merged[key] = disk[key]
        elif not in_inc and not in_base and in_disk:
            merged[key] = disk[key]
        elif in_inc and in_base and in_disk:
            if (isinstance(base[key], dict)
                    and isinstance(incoming[key], dict)
                    and isinstance(disk[key], dict)):
                sub = []
                value = merge_three_way(
                    base[key], disk[key], incoming[key], sub, here)
                merged[key] = value
                conflicts.extend(sub)
            elif disk[key] == base[key]:
                merged[key] = incoming[key]
            elif incoming[key] == base[key]:
                merged[key] = disk[key]
            else:
                merged[key] = disk[key]
                conflicts.append(f'{here} (release changed it, local value kept)')
    return merged


def _is_exe_deferred(exe_mode):
    if exe_mode == 'direct':
        return False
    if exe_mode == 'defer':
        return True
    return os.name == 'nt' and bool(getattr(sys, 'frozen', False))


def _prune_empty_dirs(install_root, dirs):
    install_root = Path(install_root)
    state_dir = _state_dir(install_root)
    seen = set()
    for d in sorted(dirs, key=lambda p: len(Path(p).parts), reverse=True):
        current = Path(d)
        while current != install_root and install_root in current.parents:
            if current in seen:
                break
            seen.add(current)
            if state_dir == current or state_dir in current.parents:
                break
            try:
                if current.is_dir() and not any(current.iterdir()):
                    current.rmdir()
                else:
                    break
            except OSError:
                break
            current = current.parent


def _clean_pycache(install_root):
    install_root = Path(install_root)
    state_dir = _state_dir(install_root)
    for path in sorted(install_root.rglob('__pycache__'), reverse=True):
        if state_dir == path or state_dir in path.parents:
            continue
        shutil.rmtree(path, ignore_errors=True)


def _clean_tmp_leftovers(install_root):
    install_root = Path(install_root)
    state_dir = _state_dir(install_root)
    for path in list(install_root.rglob(f'*{TMP_SUFFIX}')):
        if state_dir == path or state_dir in path.parents:
            continue
        try:
            path.unlink()
        except OSError:
            pass


def _trash_path(install_root, rel):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    base = _state_dir(install_root) / 'trash' / stamp
    target = base / rel
    counter = 1
    while target.exists():
        counter += 1
        target = base / Path(rel).parent / f'{counter:02d}-{Path(rel).name}'
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def apply_release(install_root, release_root, manifest, exe_mode='auto',
                  progress_cb=None):
    install_root = Path(install_root).resolve()
    release_root = Path(release_root)
    if not isinstance(manifest, dict) or 'files' not in manifest:
        raise UpdateError('Invalid manifest.')
    install_root.mkdir(parents=True, exist_ok=True)
    state_dir = _state_dir(install_root)
    state_dir.mkdir(parents=True, exist_ok=True)

    lock = UpdateLock(install_root)
    if not lock.acquire():
        raise UpdateError('Another update is already in progress on this install.')
    try:
        return _apply_locked(
            install_root, release_root, manifest, exe_mode, progress_cb)
    finally:
        lock.release()


def _apply_locked(install_root, release_root, manifest, exe_mode, progress_cb):
    inc_idx = _manifest_index(manifest)
    installed = load_installed(install_root)
    bootstrap = installed is None
    base_idx = _manifest_index(installed) if installed else {}
    sidecars = set((installed or {}).get(SIDECARS_KEY) or [])
    result = ApplyResult(
        version=str(manifest.get('version') or ''),
        bootstrap=bootstrap,
    )
    new_base = {}
    new_sidecars = set()
    prunable_dirs = set()

    _clean_tmp_leftovers(install_root)
    _clean_pycache(install_root)
    _emit(progress_cb, 'prepare', 0, 1, '')

    exe_entry = inc_idx.get(EXE_NAME)
    defer_exe = bool(exe_entry) and _is_exe_deferred(exe_mode)

    paths = [p for p in inc_idx if p != EXE_NAME]
    total = max(len(paths), 1)
    done = 0

    for rel in paths:
        entry = inc_idx[rel]
        dest = install_root / rel
        src = release_root / rel
        disk_hash = sha256_file(dest) if dest.is_file() else None
        if disk_hash == entry.get('sha256'):
            result.uptodate.append(rel)
            new_base[rel] = entry
            sidecar = dest.with_name(dest.name + SIDECAR_SUFFIX)
            if rel in sidecars and sidecar.is_file():
                try:
                    sidecar.unlink()
                except OSError:
                    pass
            done += 1
            _emit(progress_cb, 'apply', done, total, rel)
            continue

        action = 'write'
        if not bootstrap:
            base_entry = base_idx.get(rel)
            if base_entry is None:
                action = 'write' if disk_hash is None else 'collision'
            elif disk_hash is None:
                action = 'restore'
            elif disk_hash == base_entry.get('sha256'):
                action = 'write'
            else:
                action = 'merge' if rel in MERGE_PATHS else 'preserve'
        else:
            if disk_hash is None:
                action = 'write'
            elif rel in MERGE_PATHS:
                action = 'merge'
            elif rel in PRESERVE_PATHS:
                action = 'preserve'

        failed = False
        made_sidecar = False
        try:
            if action == 'write':
                _copy_atomic(src, dest)
                result.written.append(rel)
            elif action == 'restore':
                _copy_atomic(src, dest)
                result.restored.append(rel)
            elif action in ('preserve', 'collision'):
                _copy_atomic(
                    src, dest.with_name(dest.name + SIDECAR_SUFFIX))
                made_sidecar = True
                if action == 'preserve':
                    result.preserved.append(rel)
                else:
                    result.collisions.append(rel)
                new_sidecars.add(rel)
            elif action == 'merge':
                merge_action = _apply_merge(
                    install_root, release_root, rel, src, dest, result)
                if merge_action in ('write', 'merged'):
                    result.written.append(rel)
                if merge_action == 'backup':
                    result.preserved.append(rel)
                    made_sidecar = True
                    new_sidecars.add(rel)
        except Exception as exc:
            failed = True
            result.failed.append(f'{rel} ({exc})')
            if not bootstrap and rel in base_idx:
                new_base[rel] = base_idx[rel]

        if not failed:
            if (action in ('preserve', 'collision')
                    and rel not in MERGE_PATHS and rel not in PRESERVE_PATHS
                    and disk_hash):
                new_base[rel] = dict(entry, sha256=disk_hash)
            else:
                new_base[rel] = entry
            if made_sidecar:
                new_sidecars.add(rel)
            elif rel in sidecars and action in ('write', 'restore', 'merge'):
                sidecar = dest.with_name(dest.name + SIDECAR_SUFFIX)
                if sidecar.is_file():
                    try:
                        sidecar.unlink()
                    except OSError:
                        pass
                new_sidecars.discard(rel)
        done += 1
        _emit(progress_cb, 'apply', done, total, rel)

    if exe_entry:
        _emit(progress_cb, 'exe', 0, 1, EXE_NAME)
        _apply_exe(
            install_root, release_root, exe_entry, defer_exe, result)
        if result.exe_action != 'failed':
            new_base[EXE_NAME] = exe_entry

    if not bootstrap:
        if EXE_NAME in base_idx and EXE_NAME not in inc_idx:
            new_base[EXE_NAME] = base_idx[EXE_NAME]
        removals = [
            r for r in base_idx if r not in inc_idx and r != EXE_NAME]
        for i, rel in enumerate(removals):
            _emit(progress_cb, 'cleanup', i, len(removals), rel)
            entry = base_idx[rel]
            dest = install_root / rel
            sidecar = dest.with_name(dest.name + SIDECAR_SUFFIX)
            if not dest.is_file():
                if rel in sidecars and sidecar.is_file():
                    try:
                        sidecar.unlink()
                    except OSError:
                        pass
                continue
            disk_hash = sha256_file(dest)
            try:
                if disk_hash == entry.get('sha256'):
                    dest.unlink()
                    result.deleted.append(rel)
                    prunable_dirs.add(dest.parent)
                    if rel in sidecars and sidecar.is_file():
                        sidecar.unlink()
                else:
                    target = _trash_path(install_root, rel)
                    shutil.move(str(dest), str(target))
                    result.trashed.append(rel)
                    prunable_dirs.add(dest.parent)
                    if rel in sidecars and sidecar.is_file():
                        sidecar_target = _trash_path(
                            install_root, rel + SIDECAR_SUFFIX)
                        shutil.move(str(sidecar), str(sidecar_target))
            except Exception as exc:
                result.failed.append(f'{rel} ({exc})')
        _emit(progress_cb, 'cleanup', len(removals), len(removals), '')

    _prune_empty_dirs(install_root, prunable_dirs)

    new_sidecars.update(result.preserved)
    new_sidecars.update(result.collisions)

    final_files = [new_base[rel] for rel in sorted(new_base)]
    installed_data = {
        'name': manifest.get('name', 'MazeHub'),
        'version': result.version,
        'applied': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'files': final_files,
        SIDECARS_KEY: sorted(new_sidecars),
    }
    _emit(progress_cb, 'finalize', 0, 1, '')
    _save_installed(install_root, installed_data)
    save_report(install_root, result)
    return result


def _apply_merge(install_root, release_root, rel, src, dest, result):
    incoming_data = _load_json(src)
    if not isinstance(incoming_data, dict):
        raise UpdateError(f'Invalid JSON in release: {rel}')
    snapshot_path = _state_dir(install_root) / 'apps_base.json'

    if not dest.is_file():
        _copy_atomic(src, dest)
        _atomic_write_json(snapshot_path, incoming_data)
        return 'write'

    disk_data = _load_json(dest)
    if not isinstance(disk_data, dict):
        _copy_atomic(dest, dest.with_name(dest.name + SIDECAR_SUFFIX))
        _copy_atomic(src, dest)
        _atomic_write_json(snapshot_path, incoming_data)
        result.conflicts.append(
            f'{rel}: local copy was not valid JSON (backed up as .new)')
        return 'backup'

    base_data = _load_json(snapshot_path, {})
    conflicts = []
    merged = merge_three_way(base_data, disk_data, incoming_data, conflicts)
    result.conflicts.extend(f'{rel}: {c}' for c in conflicts)
    if merged != disk_data:
        _atomic_write_bytes(dest, json.dumps(merged, indent=4).encode('utf-8'))
        action = 'merged'
    else:
        action = 'skip'
    _atomic_write_json(snapshot_path, incoming_data)
    return action


def _apply_exe(install_root, release_root, entry, defer_exe, result):
    dest = install_root / EXE_NAME
    src = release_root / EXE_NAME
    disk_hash = sha256_file(dest) if dest.is_file() else None
    if disk_hash == entry.get('sha256'):
        result.exe_action = 'none'
        return
    if defer_exe:
        stage_dir = Path(tempfile.mkdtemp(prefix='mazehub_exe_'))
        staged = stage_dir / EXE_NAME
        shutil.copy2(src, staged)
        result.exe_action = 'staged'
        result.staged_exe = staged
        return
    try:
        _copy_atomic(src, dest)
        result.exe_action = 'direct'
    except Exception as exc:
        result.exe_action = 'failed'
        result.failed.append(f'{EXE_NAME} ({exc})')


def summary_from_report(report):
    result = ApplyResult(
        version=str(report.get('version') or ''),
        bootstrap=bool(report.get('bootstrap')),
    )
    for key in ('written', 'restored', 'uptodate', 'preserved', 'collisions',
                'deleted', 'trashed', 'conflicts', 'failed'):
        value = report.get(key)
        if isinstance(value, list):
            setattr(result, key, value)
    result.exe_action = str(report.get('exe_action') or 'none')
    return result.summary()


def save_report(install_root, result):
    try:
        _atomic_write_json(
            _state_dir(install_root) / 'last_report.json', result.to_dict())
    except Exception:
        pass


def pop_report(install_root):
    path = _state_dir(install_root) / 'last_report.json'
    data = _load_json(path)
    if isinstance(data, dict):
        try:
            path.unlink()
        except OSError:
            pass
        return data
    return None


def _batch_quote(value):
    return str(value).replace('%', '%%')


def write_update_helper(install_root, staged_exe, parent_pid):
    install_root = Path(install_root).resolve()
    staged_exe = Path(staged_exe)
    helper_dir = Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()) / 'MazeHub'
    helper_dir.mkdir(parents=True, exist_ok=True)
    helper_path = helper_dir / 'update_helper.bat'
    install = _batch_quote(install_root)
    staging = _batch_quote(staged_exe.parent)
    log = _batch_quote(helper_dir / 'update_helper.log')
    lines = [
        '@echo off',
        'setlocal',
        f'set "INSTALL={install}"',
        f'set "STAGING={staging}"',
        f'set "PARENT_PID={int(parent_pid)}"',
        f'set "EXE={EXE_NAME}"',
        f'set "LOG={log}"',
        'call :log "start install=%INSTALL% staging=%STAGING% parent=%PARENT_PID%"',
        'powershell -NoProfile -NonInteractive -Command '
        '"Wait-Process -Id %PARENT_PID% -Timeout 180 -ErrorAction SilentlyContinue" >nul 2>&1',
        'call :log "parent wait done"',
        'if not exist "%INSTALL%\\%EXE%" goto swap',
        'if exist "%INSTALL%\\%EXE%.old" del /f /q "%INSTALL%\\%EXE%.old" >nul 2>&1',
        'set /a tries=0',
        ':ren_try',
        'ren "%INSTALL%\\%EXE%" "%EXE%.old" >nul 2>&1',
        'if not errorlevel 1 goto ren_ok',
        'set /a tries+=1',
        'if %tries% GEQ 12 goto ren_fail',
        'ping -n 3 127.0.0.1 >nul',
        'goto ren_try',
        ':ren_fail',
        'call :log "FAIL ren locked tries=%tries%"',
        'goto swap',
        ':ren_ok',
        'call :log "ren ok"',
        ':swap',
        'set /a tries=0',
        ':copy_try',
        'copy /Y "%STAGING%\\%EXE%" "%INSTALL%\\%EXE%" >nul 2>&1',
        'if not errorlevel 1 goto copy_ok',
        'set /a tries+=1',
        'if %tries% GEQ 12 goto copy_fail',
        'ping -n 3 127.0.0.1 >nul',
        'goto copy_try',
        ':copy_fail',
        'call :log "FAIL copy tries=%tries%"',
        'goto verify',
        ':copy_ok',
        'call :log "copy ok"',
        ':verify',
        'set "STAGED_SIZE="',
        'set "INST_SIZE="',
        'for %%A in ("%STAGING%\\%EXE%") do set "STAGED_SIZE=%%~zA"',
        'for %%A in ("%INSTALL%\\%EXE%") do set "INST_SIZE=%%~zA"',
        'call :log "verify staged=%STAGED_SIZE% installed=%INST_SIZE%"',
        'if "%STAGED_SIZE%"=="" goto rollback',
        'if "%INST_SIZE%"=="" goto rollback',
        'if not "%STAGED_SIZE%"=="%INST_SIZE%" goto rollback',
        'call :log "verify ok, starting new exe"',
        'start "" "%INSTALL%\\%EXE%"',
        'set /a tries=0',
        ':waitup',
        'powershell -NoProfile -NonInteractive -Command '
        '"if (Get-Process -Name MazeHub -ErrorAction SilentlyContinue) { exit 0 } '
        'else { exit 1 }" >nul 2>&1',
        'if not errorlevel 1 goto alive',
        'set /a tries+=1',
        'if %tries% GEQ 45 goto rollback',
        'ping -n 2 127.0.0.1 >nul',
        'goto waitup',
        ':alive',
        'call :log "new exe alive"',
        'ping -n 11 127.0.0.1 >nul',
        'powershell -NoProfile -NonInteractive -Command '
        '"if (Get-Process -Name MazeHub -ErrorAction SilentlyContinue) { exit 0 } '
        'else { exit 1 }" >nul 2>&1',
        'if not errorlevel 1 goto cleanup',
        'call :log "WARN process gone after startup, rolling back"',
        ':rollback',
        'call :log "rollback"',
        'if not exist "%INSTALL%\\%EXE%.old" goto rb_norestore',
        'del /f /q "%INSTALL%\\%EXE%" >nul 2>&1',
        'ren "%INSTALL%\\%EXE%.old" "%EXE%" >nul 2>&1',
        ':rb_norestore',
        'if not exist "%INSTALL%\\%EXE%" copy /Y "%STAGING%\\%EXE%" "%INSTALL%\\%EXE%" >nul 2>&1',
        'if not exist "%INSTALL%\\%EXE%" goto rb_failed',
        'call :log "rollback done, starting exe"',
        'start "" "%INSTALL%\\%EXE%"',
        'goto cleanup',
        ':rb_failed',
        'call :log "FATAL no exe after rollback"',
        'goto cleanup',
        ':cleanup',
        'if exist "%STAGING%" rmdir /s /q "%STAGING%" >nul 2>&1',
        'if exist "%INSTALL%\\%EXE%.old" del /f /q "%INSTALL%\\%EXE%.old" >nul 2>&1',
        'call :log "done"',
        'del /f /q "%~f0" >nul 2>&1',
        'exit /b 0',
        ':log',
        '>>"%LOG%" echo [%date% %time%] %~1',
        'exit /b 0',
    ]
    helper_path.write_bytes(('\r\n'.join(lines) + '\r\n').encode('utf-8'))
    return helper_path


def spawn_update_helper(helper_path):
    subprocess.Popen(
        [str(helper_path)],
        cwd=str(Path(helper_path).parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0),
    )


def relaunch():
    exe = Path(sys.executable)
    subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
