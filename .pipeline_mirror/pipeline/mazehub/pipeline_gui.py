import os
import sys
import re
import subprocess
import platform
import time
import threading
import webbrowser
import shutil
from pathlib import Path
from collections import defaultdict

from PySide6.QtCore import Qt, QThread, Signal, QObject, QDateTime, QTimer, QDate
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QStackedWidget, QTextEdit, QFrame,
    QHeaderView, QTreeWidget, QTreeWidgetItem, QStatusBar, QGroupBox,
    QFormLayout, QGridLayout, QScrollArea, QSplitter, QDialog, QTabWidget,
    QMenu, QCheckBox, QSpinBox, QProgressBar, QDateEdit,
)

from pipeline_app import (
    find_project_root, setup_environment, load_apps_config,
    read_shot_meta, write_shot_meta, DEFAULT_SHOT_META,
    read_light_rig_meta, write_light_rig_meta, list_light_rigs,
    DEFAULT_LIGHT_RIG_META,
    APP_FILE_EXTENSIONS,
    build_context_env, _app_dir, APP_VERSION,
    discover_usd_files, discover_husk_passes,
    discover_image_sequences,
    read_production, write_production, production_score,
    PRODUCTION_STATUSES, PRODUCTION_VALUES,
    ASSET_CATEGORIES, SHOT_CATEGORIES,
)
from recent_files import get_last_app_version, set_last_app_version


def _score_color(score_str):
    if not score_str:
        return None
    pct = int(score_str.replace('%', ''))
    r = 220 if pct < 50 else int(220 * (1 - (pct - 50) / 50))
    g = int(180 * (pct / 50)) if pct < 50 else 180
    return QColor(min(r, 220), min(g, 180), 60)


def _status_color(status):
    colors = {
        'Not started': QColor(180, 60, 60),
        'Work in progress': QColor(200, 160, 40),
        'Pending review': QColor(60, 140, 200),
        'Finished': QColor(60, 180, 60),
        'Not applicable': QColor(120, 120, 120),
    }
    return colors.get(status, QColor(180, 180, 180))


def _open_in_explorer(path):
    if path is None:
        return
    path = Path(path)
    if path.is_file():
        subprocess.Popen(['explorer', '/select,', str(path)])
    elif path.is_dir():
        os.startfile(str(path))


def _add_explorer_action(menu, path):
    action = menu.addAction('Open in Explorer')
    action.triggered.connect(lambda: _open_in_explorer(path))
    return action


class _SortItem(QTableWidgetItem):
    def __init__(self, text, sort_value=None):
        super().__init__(text)
        self._sort_value = sort_value

    def __lt__(self, other):
        if self._sort_value is not None and isinstance(other, _SortItem) and other._sort_value is not None:
            return self._sort_value < other._sort_value
        return super().__lt__(other)

from recent_files import add_recent_file, get_recent_files as load_recent_files, clear_recent_files


SIDEBAR_ITEMS = [
    ('Home', 'Dashboard with project info and quick launch'),
    ('Launch Apps', 'Launch VFX applications'),
    ('Shot Explorer', 'Browse existing shots and create new ones'),
    ('Light Rigs', 'Manage and browse light rigs'),
    ('Asset Explorer', 'Browse existing assets and create new ones'),
    ('Production', 'Track production progress across shots and assets'),
    ('Render', 'Headless USD rendering with husk'),
    ('Preview', 'Preview image sequences in MPlay'),
    ('Env Vars', 'View environment variables'),
    ('Settings', 'Repair file structure and configure options'),
    ('Log', 'View application and launch output'),
    ('Help', 'Complete user guide for MazeHub'),
]


class SidebarButton(QPushButton):
    def __init__(self, text, tooltip):
        super().__init__(text)
        self.setToolTip(tooltip)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)


class LogStream:
    def __init__(self):
        import threading
        self._buffer = ''
        self._queue = []
        self._lock = threading.Lock()

    def write(self, text):
        if not text:
            return
        self._buffer += text
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            if line:
                ts = QDateTime.currentDateTime().toString('HH:mm:ss')
                with self._lock:
                    self._queue.append(f'[{ts}] {line}')
        if self._buffer and not text.endswith('\n'):
            ts = QDateTime.currentDateTime().toString('HH:mm:ss')
            with self._lock:
                self._queue.append(f'[{ts}] {self._buffer}')
            self._buffer = ''
            return
        if self._buffer:
            ts = QDateTime.currentDateTime().toString('HH:mm:ss')
            with self._lock:
                self._queue.append(f'[{ts}] {self._buffer}')
            self._buffer = ''

    def flush(self):
        if self._buffer:
            ts = QDateTime.currentDateTime().toString('HH:mm:ss')
            with self._lock:
                self._queue.append(f'[{ts}] {self._buffer}')
            self._buffer = ''

    def isatty(self):
        return False

    @property
    def encoding(self):
        return 'utf-8'

    def get_lines(self):
        with self._lock:
            lines = list(self._queue)
            self._queue.clear()
        return lines


_log_stream = None


def get_log_stream():
    global _log_stream
    if _log_stream is None:
        _log_stream = LogStream()
    return _log_stream


class AppLauncherThread(QThread):
    finished = Signal(str, bool)

    def __init__(self, config, pipeline_dir, project_root=None, context=None):
        super().__init__()
        self.config = config
        self.pipeline_dir = pipeline_dir
        self.project_root = project_root
        self.context = context

    def run(self):
        log = get_log_stream()
        try:
            exec_path = self.pipeline_dir / self.config['subdir'] / self.config['executable']
            if not exec_path.exists():
                log.write(f'[launch] Executable not found: {exec_path}')
                self.finished.emit(f'Executable not found: {exec_path}', False)
                return

            if exec_path.suffix.lower() == '.bat' and platform.system() != 'Windows':
                log.write(f'[launch] Cannot launch .bat file on {platform.system()}: {exec_path.name}')
                log.write(f'[launch] Only Windows can run .bat files')
                self.finished.emit(f'.bat files cannot run on {platform.system()}', False)
                return

            launch_env = os.environ.copy()
            if self.context and self.project_root:
                ctx = dict(self.context, app_name=self.config.get('_key', ''))
                ctx_env = build_context_env(ctx, self.project_root)
                launch_env.update(ctx_env)

            log.write(f'[launch] Starting {self.config["display_name"]}...')
            if platform.system() == 'Windows':
                import tempfile
                bat_log = os.path.join(tempfile.gettempdir(), 'mazehub_houdini_launch.log')
                if os.path.exists(bat_log):
                    os.unlink(bat_log)
                proc = subprocess.Popen(
                    [str(exec_path)],
                    shell=True, env=launch_env,
                )
                proc.wait()
                time.sleep(0.5)
                try:
                    with open(bat_log, 'r') as f:
                        for line in f.read().strip().splitlines():
                            log.write(f'[launch] {line}')
                except FileNotFoundError:
                    log.write(f'[launch] No bat log found at {bat_log}')
                if os.path.exists(bat_log):
                    os.unlink(bat_log)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(exec_path)], env=launch_env)
            else:
                subprocess.Popen([str(exec_path)], shell=True, env=launch_env)
            log.write(f'[launch] {self.config["display_name"]} launched successfully')
            self.finished.emit(f'Launched {self.config["display_name"]}', True)
        except Exception as e:
            log.write(f'[launch] Failed to launch: {e}')
            self.finished.emit(f'Failed: {e}', False)


class FileOpenThread(QThread):
    finished = Signal(str, bool)

    def __init__(self, app_config, pipeline_dir, file_path, project_root=None, context=None):
        super().__init__()
        self.config = app_config
        self.pipeline_dir = pipeline_dir
        self.file_path = file_path
        self.project_root = project_root
        self.context = context

    def run(self):
        log = get_log_stream()
        try:
            exec_path = self.pipeline_dir / self.config['subdir'] / self.config['executable']

            if exec_path.suffix.lower() == '.bat' and platform.system() != 'Windows':
                log.write(f'[open] Cannot launch .bat file on {platform.system()}: {exec_path.name}')
                self.finished.emit(f'.bat files cannot run on {platform.system()}', False)
                return

            launch_env = os.environ.copy()
            if self.context and self.project_root:
                ctx = dict(self.context, app_name=self.config.get('_key', ''))
                ctx_env = build_context_env(ctx, self.project_root)
                launch_env.update(ctx_env)

            log.write(f'[open] Opening {self.file_path.name} with {self.config["display_name"]}...')
            log.write(f'[open] MAZE_PIPELINE={launch_env.get("MAZE_PIPELINE", "<not set>")}')
            log.write(f'[open] PIPELINE_DIR={launch_env.get("PIPELINE_DIR", "<not set>")}')
            log.write(f'[open] MAZE_OPEN_FILE={launch_env.get("MAZE_OPEN_FILE", "<not set>")}')
            log.write(f'[open] HOUDINI_PATH={launch_env.get("HOUDINI_PATH", "<not set>")}')
            if platform.system() == 'Windows':
                import tempfile
                launch_env['MAZE_OPEN_FILE'] = str(self.file_path)
                bat_log = os.path.join(tempfile.gettempdir(), 'mazehub_houdini_launch.log')
                if os.path.exists(bat_log):
                    os.unlink(bat_log)
                proc = subprocess.Popen(
                    [str(exec_path), str(self.file_path)],
                    shell=True, env=launch_env,
                )
                proc.wait()
                time.sleep(0.5)
                try:
                    with open(bat_log, 'r') as f:
                        for line in f.read().strip().splitlines():
                            log.write(f'[open] {line}')
                except FileNotFoundError:
                    log.write(f'[open] No bat log found at {bat_log}')
                if os.path.exists(bat_log):
                    os.unlink(bat_log)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(self.file_path)], env=launch_env)
            else:
                subprocess.Popen([str(exec_path), str(self.file_path)], shell=True, env=launch_env)
            log.write(f'[open] {self.file_path.name} opened with {self.config["display_name"]}')
            self.finished.emit(f'Opened {self.file_path.name} with {self.config["display_name"]}', True)
        except Exception as e:
            log.write(f'[open] Failed to open: {e}')
            self.finished.emit(f'Failed: {e}', False)


REVERSE_EXT_MAP = {}
for _app, exts in APP_FILE_EXTENSIONS.items():
    for ext in exts:
        REVERSE_EXT_MAP[ext] = _app


class FileBrowserPanel(QWidget):
    def __init__(self, project_root, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._current_path = None
        self._current_context = None
        self._file_map = {}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self.path_label = QLabel('Select a shot or asset to browse files')
        self.path_label.setObjectName('browserPath')
        header.addWidget(self.path_label, 1)
        self.file_count_label = QLabel('')
        self.file_count_label.setObjectName('browserCount')
        header.addWidget(self.file_count_label)
        layout.addLayout(header)

        filter_row = QHBoxLayout()
        self.show_backups_cb = QCheckBox('Show backup files')
        self.show_backups_cb.setChecked(False)
        self.show_backups_cb.stateChanged.connect(lambda: self._refresh())
        filter_row.addWidget(self.show_backups_cb)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['File', 'Application', 'Path'])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 130)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._open_selected)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.open_btn = QPushButton('Open Selected')
        self.open_btn.setMinimumHeight(32)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_selected)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.tree.itemSelectionChanged.connect(
            lambda: self.open_btn.setEnabled(bool(self.tree.selectedItems()))
        )

    def set_directory(self, path, context=None):
        self._current_path = Path(path) if path else None
        self._current_context = context
        self._refresh()

    def clear(self):
        self._current_path = None
        self._current_context = None
        self.path_label.setText('Select a shot or asset to browse files')
        self.file_count_label.setText('')
        self.tree.clear()
        self._file_map.clear()
        self.open_btn.setEnabled(False)

    def _refresh(self):
        self.tree.clear()
        self._file_map.clear()
        self.open_btn.setEnabled(False)

        if not self._current_path or not self._current_path.exists():
            self.path_label.setText('Directory not found')
            self.file_count_label.setText('')
            return

        self.path_label.setText(str(self._current_path.relative_to(self.project_root)))

        show_backups = self.show_backups_cb.isChecked()

        groups = {}
        for ext, app_name in sorted(REVERSE_EXT_MAP.items()):
            for fp in sorted(self._current_path.rglob(f'*{ext}')):
                parts = fp.relative_to(self._current_path).parts
                if any(p.startswith('_') or p.startswith('.') for p in parts):
                    continue
                if not show_backups and 'backup' in parts:
                    continue
                groups.setdefault(app_name, []).append(fp)

        idx = 1
        for app_name in sorted(groups):
            cfg = self.apps_config.get(app_name, {})
            display = cfg.get('file_label', cfg.get('display_name', app_name))
            parent = QTreeWidgetItem([f'{display}', '', ''])
            parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            self.tree.addTopLevelItem(parent)
            for fp in groups[app_name]:
                rel = fp.relative_to(self.project_root)
                child = QTreeWidgetItem([fp.name, app_name, str(rel.parent)])
                parent.addChild(child)
                self._file_map[idx] = (app_name, fp, rel, child)
                idx += 1
            parent.setExpanded(True)

        count = idx - 1
        self.file_count_label.setText(f'{count} file{"s" if count != 1 else ""}')

        if count == 0:
            item = QTreeWidgetItem(['No project files found in this directory', '', ''])
            self.tree.addTopLevelItem(item)

    def _open_selected(self):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        for idx, (app_name, fp, rel, tree_item) in self._file_map.items():
            if tree_item is item:
                cfg = self.apps_config.get(app_name)
                if not cfg:
                    window = self.window()
                    if hasattr(window, 'show_status'):
                        window.show_status(f'No config for {app_name}', False)
                    return
                cfg['_key'] = app_name
                self.thread = FileOpenThread(
                    cfg, self.pipeline_dir, fp,
                    project_root=self.project_root, context=self._current_context,
                )
                self.thread.finished.connect(lambda msg, ok: self._result(msg, ok))
                self.thread.start()
                ctx_type = self._current_context.get('type', '') if self._current_context else ''
                ctx_name = self._current_context.get('name', '') if self._current_context else ''
                ctx_cat = self._current_context.get('category', '') if self._current_context else ''
                add_recent_file(fp, cfg.get('display_name', app_name), ctx_type, ctx_name, ctx_cat, app_key=app_name)
                return

    def _result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)

    def _context_menu(self, pos):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        path = None
        for idx, (app_name, fp, rel, tree_item) in self._file_map.items():
            if tree_item is item:
                path = fp
                break
        if path is None:
            path = self._current_path
        menu = QMenu(self)
        _add_explorer_action(menu, path)
        menu.exec(self.tree.viewport().mapToGlobal(pos))


class ShotDialog(QDialog):
    def __init__(self, parent=None, shot_name='', meta=None, project_root=None):
        super().__init__(parent)
        self.setWindowTitle('New Shot' if not shot_name else f'Edit Shot: {shot_name}')
        self.setMinimumWidth(500)
        self._result = None

        if meta is None:
            meta = DEFAULT_SHOT_META

        fr = meta.get('frame_range', DEFAULT_SHOT_META['frame_range'])
        parts = fr.split('-')
        frame_start = parts[0] if parts else ''
        frame_end = parts[1] if len(parts) > 1 else parts[0]

        focal = meta.get('focal_length', DEFAULT_SHOT_META['focal_length'])
        if focal.endswith('mm'):
            focal = focal[:-2]

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(shot_name)
        self.name_edit.setPlaceholderText('e.g. SH010')
        form.addRow('Shot Name:', self.name_edit)

        range_row = QHBoxLayout()
        self.fr_start = QLineEdit(frame_start)
        self.fr_start.setPlaceholderText('Start')
        range_row.addWidget(self.fr_start)
        range_row.addWidget(QLabel('—'))
        self.fr_end = QLineEdit(frame_end)
        self.fr_end.setPlaceholderText('End')
        range_row.addWidget(self.fr_end)
        form.addRow('Frame Range:', range_row)

        self.fps_edit = QLineEdit(meta.get('frame_rate', DEFAULT_SHOT_META['frame_rate']))
        self.fps_edit.setPlaceholderText('e.g. 24')
        form.addRow('Frame Rate:', self.fps_edit)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat('yyyy-MM-dd')
        stored_date = meta.get('date', '')
        if stored_date:
            self.date_edit.setDate(QDate.fromString(stored_date, 'yyyy-MM-dd'))
        else:
            self.date_edit.setDate(QDate.currentDate())
        form.addRow('Date:', self.date_edit)

        self.focal_edit = QLineEdit(focal)
        self.focal_edit.setPlaceholderText('e.g. 50')
        form.addRow('Focal Length (mm):', self.focal_edit)

        self.iso_edit = QLineEdit(meta.get('iso', DEFAULT_SHOT_META['iso']))
        self.iso_edit.setPlaceholderText('e.g. 800')
        form.addRow('ISO:', self.iso_edit)

        self.nd_edit = QLineEdit(meta.get('nd_filter', DEFAULT_SHOT_META['nd_filter']))
        self.nd_edit.setPlaceholderText('e.g. 6')
        form.addRow('ND Filter (stops):', self.nd_edit)

        self.light_rig_combo = QComboBox()
        self.light_rig_combo.addItem('')
        if project_root:
            for rig_name in list_light_rigs(project_root):
                self.light_rig_combo.addItem(rig_name)
        current_rig = meta.get('light_rig', '')
        if current_rig:
            idx = self.light_rig_combo.findText(current_rig)
            if idx >= 0:
                self.light_rig_combo.setCurrentIndex(idx)
        form.addRow('Light Rig:', self.light_rig_combo)

        self.desc_edit = QLineEdit(meta.get('description', DEFAULT_SHOT_META['description']))
        self.desc_edit.setPlaceholderText('e.g. Establishing wide shot')
        form.addRow('Description:', self.desc_edit)
        layout.addLayout(form)

        self.error_label = QLabel('')
        self.error_label.setObjectName('dialogError')
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton('Save' if shot_name else 'Create')
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self._accept)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setMinimumHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _accept(self):
        name = self.name_edit.text().strip()
        start = self.fr_start.text().strip()
        end = self.fr_end.text().strip()
        fps = self.fps_edit.text().strip()
        errors = []
        if not name:
            errors.append('Shot Name')
        if not start:
            errors.append('Frame Start')
        if not end:
            errors.append('Frame End')
        if not fps:
            errors.append('Frame Rate')
        if errors:
            self.error_label.setText(f'Required: {", ".join(errors)}')
            self.error_label.setVisible(True)
            return
        focal = self.focal_edit.text().strip()
        if focal and not focal.endswith('mm'):
            focal = f'{focal}mm'
        self._result = {
            'name': name,
            'frame_range': f'{start}-{end}',
            'frame_rate': fps,
            'date': self.date_edit.date().toString('yyyy-MM-dd'),
            'focal_length': focal,
            'iso': self.iso_edit.text().strip(),
            'nd_filter': self.nd_edit.text().strip(),
            'light_rig': self.light_rig_combo.currentText(),
            'description': self.desc_edit.text().strip(),
        }
        self.accept()

    def result_data(self):
        return self._result


class AssetDialog(QDialog):
    def __init__(self, parent=None, category='', asset_name=''):
        super().__init__(parent)
        self.setWindowTitle('New Asset' if not asset_name else f'Edit Asset: {asset_name}')
        self.setMinimumWidth(400)
        self._result = None

        from make_folders import NEW_ASSET_CATEGORY_LIST

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(NEW_ASSET_CATEGORY_LIST)
        if category:
            idx = self.cat_combo.findText(category)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)
        form.addRow('Category:', self.cat_combo)

        self.name_edit = QLineEdit(asset_name)
        self.name_edit.setPlaceholderText('e.g. MainCharacter')
        form.addRow('Asset Name:', self.name_edit)
        layout.addLayout(form)

        self.error_label = QLabel('')
        self.error_label.setObjectName('dialogError')
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton('Save' if asset_name else 'Create')
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self._accept)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setMinimumHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _accept(self):
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText('Required: Asset Name')
            self.error_label.setVisible(True)
            return
        self._result = {
            'category': self.cat_combo.currentText(),
            'name': name,
        }
        self.accept()

    def result_data(self):
        return self._result


class LightRigDialog(QDialog):
    def __init__(self, parent=None, project_root=None, rig_name='', meta=None):
        super().__init__(parent)
        self.setWindowTitle('New Light Rig' if not rig_name else f'Edit Light Rig: {rig_name}')
        self.setMinimumWidth(500)
        self._result = None
        self._project_root = project_root

        if meta is None:
            meta = DEFAULT_LIGHT_RIG_META

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(rig_name or meta.get('name', ''))
        self.name_edit.setPlaceholderText('e.g. Sunset Key')
        form.addRow('Name:', self.name_edit)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat('yyyy-MM-dd')
        stored_date = meta.get('date', '')
        if stored_date:
            self.date_edit.setDate(QDate.fromString(stored_date, 'yyyy-MM-dd'))
        else:
            self.date_edit.setDate(QDate.currentDate())
        form.addRow('Date:', self.date_edit)

        self.time_edit = QLineEdit(meta.get('time_of_day', ''))
        self.time_edit.setPlaceholderText('e.g. Golden Hour')
        form.addRow('Time of Day:', self.time_edit)

        self.desc_edit = QLineEdit(meta.get('lighting_description', ''))
        self.desc_edit.setPlaceholderText('e.g. Warm key, cool fill')
        form.addRow('Description:', self.desc_edit)

        hdri_row = QHBoxLayout()
        self.hdri_edit = QLineEdit(meta.get('hdri_path', ''))
        self.hdri_edit.setPlaceholderText('No HDRI selected')
        self.hdri_edit.setReadOnly(True)
        hdri_row.addWidget(self.hdri_edit, 1)
        self.hdri_browse_btn = QPushButton('Browse')
        self.hdri_browse_btn.setCursor(Qt.PointingHandCursor)
        self.hdri_browse_btn.clicked.connect(self._browse_hdri)
        hdri_row.addWidget(self.hdri_browse_btn)
        form.addRow('HDRI:', hdri_row)

        photogrammetry_row = QHBoxLayout()
        self.photogrammetry_edit = QLineEdit(meta.get('photogrammetry_path', ''))
        self.photogrammetry_edit.setPlaceholderText('No photogrammetry selected')
        self.photogrammetry_edit.setReadOnly(True)
        photogrammetry_row.addWidget(self.photogrammetry_edit, 1)
        self.photogrammetry_browse_btn = QPushButton('Browse')
        self.photogrammetry_browse_btn.setCursor(Qt.PointingHandCursor)
        self.photogrammetry_browse_btn.clicked.connect(self._browse_photogrammetry)
        photogrammetry_row.addWidget(self.photogrammetry_browse_btn)
        form.addRow('Photogrammetry:', photogrammetry_row)

        usd_row = QHBoxLayout()
        self.usd_scene_edit = QLineEdit(meta.get('usd_scene_path', ''))
        self.usd_scene_edit.setPlaceholderText('No USD scene selected')
        self.usd_scene_edit.setReadOnly(True)
        usd_row.addWidget(self.usd_scene_edit, 1)
        self.usd_scene_browse_btn = QPushButton('Browse')
        self.usd_scene_browse_btn.setCursor(Qt.PointingHandCursor)
        self.usd_scene_browse_btn.clicked.connect(self._browse_usd_scene)
        usd_row.addWidget(self.usd_scene_browse_btn)
        form.addRow('USD Scene:', usd_row)

        nuke_row = QHBoxLayout()
        self.nuke_edit = QLineEdit(meta.get('nuke_path', ''))
        self.nuke_edit.setPlaceholderText('No Nuke script selected')
        self.nuke_edit.setReadOnly(True)
        nuke_row.addWidget(self.nuke_edit, 1)
        self.nuke_browse_btn = QPushButton('Browse')
        self.nuke_browse_btn.setCursor(Qt.PointingHandCursor)
        self.nuke_browse_btn.clicked.connect(self._browse_nuke)
        nuke_row.addWidget(self.nuke_browse_btn)
        form.addRow('Nuke Script:', nuke_row)

        houdini_row = QHBoxLayout()
        self.houdini_edit = QLineEdit(meta.get('houdini_path', ''))
        self.houdini_edit.setPlaceholderText('No Houdini scene selected')
        self.houdini_edit.setReadOnly(True)
        houdini_row.addWidget(self.houdini_edit, 1)
        self.houdini_browse_btn = QPushButton('Browse')
        self.houdini_browse_btn.setCursor(Qt.PointingHandCursor)
        self.houdini_browse_btn.clicked.connect(self._browse_houdini)
        houdini_row.addWidget(self.houdini_browse_btn)
        form.addRow('Houdini Scene:', houdini_row)

        layout.addLayout(form)

        self.error_label = QLabel('')
        self.error_label.setObjectName('dialogError')
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton('Save' if rig_name else 'Create')
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self._accept)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setMinimumHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _browse_hdri(self):
        from PySide6.QtWidgets import QFileDialog
        start_dir = str(self._project_root) if self._project_root else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select HDRI File', start_dir,
            'HDRI Files (*.exr *.hdr *.png *.jpg *.jpeg);;All Files (*)'
        )
        if path:
            self.hdri_edit.setText(path)

    def _browse_photogrammetry(self):
        from PySide6.QtWidgets import QFileDialog
        start_dir = str(self._project_root) if self._project_root else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Photogrammetry File', start_dir,
            '3D Files (*.obj *.fbx *.ply *.stl *.scn);;All Files (*)'
        )
        if path:
            self.photogrammetry_edit.setText(path)

    def _browse_usd_scene(self):
        from PySide6.QtWidgets import QFileDialog
        start_dir = str(self._project_root) if self._project_root else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select USD Scene File', start_dir,
            'USD Files (*.usd *.usda *.usdc);;All Files (*)'
        )
        if path:
            self.usd_scene_edit.setText(path)

    def _browse_nuke(self):
        from PySide6.QtWidgets import QFileDialog
        start_dir = str(self._project_root) if self._project_root else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Nuke Script', start_dir,
            'Nuke Scripts (*.nk);;All Files (*)'
        )
        if path:
            self.nuke_edit.setText(path)

    def _browse_houdini(self):
        from PySide6.QtWidgets import QFileDialog
        start_dir = str(self._project_root) if self._project_root else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Houdini Scene', start_dir,
            'Houdini Files (*.hip *.hiplc *.hipnc);;All Files (*)'
        )
        if path:
            self.houdini_edit.setText(path)

    def _accept(self):
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText('Required: Name')
            self.error_label.setVisible(True)
            return
        self._result = {
            'name': name,
            'date': self.date_edit.date().toString('yyyy-MM-dd'),
            'time_of_day': self.time_edit.text().strip(),
            'lighting_description': self.desc_edit.text().strip(),
            'hdri_path': self.hdri_edit.text().strip(),
            'photogrammetry_path': self.photogrammetry_edit.text().strip(),
            'usd_scene_path': self.usd_scene_edit.text().strip(),
            'nuke_path': self.nuke_edit.text().strip(),
            'houdini_path': self.houdini_edit.text().strip(),
        }
        self.accept()

    def result_data(self):
        return self._result


class DashboardPage(QWidget):
    def __init__(self, project_root, env_vars, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.env_vars = env_vars
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Welcome to MazeHub Pipeline')
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh_all)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        subtitle = QLabel(f'Project: {self.project_root.name}')
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle.setFont(subtitle_font)
        layout.addWidget(subtitle)

        layout.addWidget(QLabel(f'Root: {self.project_root}'))
        layout.addSpacing(16)

        stats_layout = QHBoxLayout()
        seq_count = len([d for d in (self.project_root / 'sequence').iterdir() if d.is_dir() and not d.name.startswith('_')]) if (self.project_root / 'sequence').exists() else 0
        asset_count = 0
        asset_dir = self.project_root / 'asset'
        if asset_dir.exists():
            for cat_dir in asset_dir.iterdir():
                if cat_dir.is_dir() and not cat_dir.name.startswith('_'):
                    asset_count += len([d for d in cat_dir.iterdir() if d.is_dir() and not d.name.startswith('_')])
        stats_layout.addWidget(self._stat_card('Shots', str(seq_count)))
        stats_layout.addWidget(self._stat_card('Assets', str(asset_count)))
        stats_layout.addWidget(self._stat_card('Apps', str(len(self.apps_config))))
        progress_score = self._calc_overall_score()
        progress_card = self._stat_card('Progress', progress_score if progress_score else '-')
        if progress_score:
            color = _score_color(progress_score)
            if color:
                progress_card.findChild(QLabel).setStyleSheet(f'color: {color.name()};')
        stats_layout.addWidget(progress_card)
        layout.addLayout(stats_layout)
        layout.addSpacing(16)

        quick_group = QGroupBox('Quick Launch')
        quick_layout = QVBoxLayout(quick_group)
        if self.apps_config:
            grid = QGridLayout()
            row, col = 0, 0
            for name, cfg in self.apps_config.items():
                btn = QPushButton(cfg['display_name'])
                btn.setMinimumHeight(48)
                btn.setMinimumWidth(140)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda checked, n=name: self._quick_launch(n))
                grid.addWidget(btn, row, col)
                col += 1
                if col > 3:
                    col = 0
                    row += 1
            self.yt_screensaver_btn = QPushButton('YT Screensaver')
            self.yt_screensaver_btn.setMinimumHeight(48)
            self.yt_screensaver_btn.setMinimumWidth(140)
            self.yt_screensaver_btn.setCursor(Qt.PointingHandCursor)
            self.yt_screensaver_btn.clicked.connect(self._open_yt_screensaver)
            grid.addWidget(self.yt_screensaver_btn, row, col)
            quick_layout.addLayout(grid)
        else:
            quick_layout.addWidget(QLabel('No applications configured.'))
        layout.addWidget(quick_group)

        recent_group = QGroupBox('Recent Files')
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setSpacing(8)

        self.recent_table = QTableWidget()
        self.recent_table.setColumnCount(5)
        self.recent_table.setHorizontalHeaderLabels(['File', 'Path', 'Context', 'App', 'Opened'])
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.recent_table.setMaximumHeight(180)
        self.recent_table.itemDoubleClicked.connect(self._open_recent_file)
        self.recent_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_table.customContextMenuRequested.connect(self._show_recent_context_menu)
        self.recent_table.itemSelectionChanged.connect(
            lambda: self.open_recent_btn.setEnabled(bool(self.recent_table.selectedItems()))
        )
        recent_layout.addWidget(self.recent_table)

        self.empty_label = QLabel('No recent files')
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet('color: #888;')
        self.empty_label.setVisible(False)
        recent_layout.addWidget(self.empty_label)

        btn_row = QHBoxLayout()
        self.open_recent_btn = QPushButton('Open')
        self.open_recent_btn.setCursor(Qt.PointingHandCursor)
        self.open_recent_btn.setMinimumHeight(32)
        self.open_recent_btn.setEnabled(False)
        self.open_recent_btn.clicked.connect(self._open_selected_recent_file)
        btn_row.addWidget(self.open_recent_btn)
        btn_row.addStretch()
        clear_btn = QPushButton('Clear History')
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_recent_files)
        btn_row.addWidget(clear_btn)
        recent_layout.addLayout(btn_row)
        layout.addWidget(recent_group)

        self._refresh_recent_files()

        layout.addStretch()

    def _stat_card(self, label, value):
        card = QFrame()
        card.setObjectName('statCard')
        card.setFixedSize(140, 80)
        cl = QVBoxLayout(card)
        cl.setAlignment(Qt.AlignCenter)
        v = QLabel(value)
        v_font = QFont()
        v_font.setPointSize(22)
        v_font.setBold(True)
        v.setFont(v_font)
        v.setAlignment(Qt.AlignCenter)
        cl.addWidget(v)
        l = QLabel(label)
        l.setAlignment(Qt.AlignCenter)
        cl.addWidget(l)
        return card

    def _calc_overall_score(self):
        from pipeline_app import read_production, production_score, SHOT_CATEGORIES
        all_scores = []
        seq_dir = self.project_root / 'sequence'
        if seq_dir.exists():
            for d in sorted(seq_dir.iterdir()):
                if d.is_dir() and not d.name.startswith('_'):
                    prod = read_production(d)
                    if not prod:
                        prod = {cat: 'Not started' for cat in SHOT_CATEGORIES}
                    vals = [PRODUCTION_VALUES.get(v, 0) for v in prod.values() if v != 'Not applicable']
                    if vals:
                        all_scores.append(sum(vals) / len(vals))
        asset_dir = self.project_root / 'asset'
        if asset_dir.exists():
            for cat_dir in sorted(asset_dir.iterdir()):
                if not cat_dir.is_dir() or cat_dir.name.startswith('_'):
                    continue
                for asset in sorted(cat_dir.iterdir()):
                    if asset.is_dir() and not asset.name.startswith('_'):
                        prod = read_production(asset)
                        if not prod:
                            continue
                        vals = [PRODUCTION_VALUES.get(v, 0) for v in prod.values() if v != 'Not applicable']
                        if vals:
                            all_scores.append(sum(vals) / len(vals))
        if all_scores:
            return f'{round(sum(all_scores) / len(all_scores))}%'
        return ''

    def _refresh_all(self):
        self._refresh_recent_files()

    def _refresh_recent_files(self):
        files = load_recent_files()[:8]
        self.recent_table.setRowCount(len(files))
        self.empty_label.setVisible(len(files) == 0)
        self.recent_table.setVisible(len(files) > 0)
        for i, f in enumerate(files):
            item0 = QTableWidgetItem(f.get('display_name', f.get('path', '')))
            item0.setData(Qt.UserRole, f.get('path', ''))
            self.recent_table.setItem(i, 0, item0)
            self.recent_table.setItem(i, 1, QTableWidgetItem(f.get('path', '')))
            ctx_type = f.get('context_type', '')
            ctx_name = f.get('context_name', '')
            ctx_cat = f.get('context_category', '')
            if ctx_type and ctx_name:
                if ctx_type.lower() == 'asset' and ctx_cat:
                    ctx_str = f'Asset: {ctx_cat}/{ctx_name}'
                else:
                    ctx_str = f'{ctx_type.title()}: {ctx_name}'
            else:
                ctx_str = ''
            self.recent_table.setItem(i, 2, QTableWidgetItem(ctx_str))
            self.recent_table.setItem(i, 3, QTableWidgetItem(f.get('app_name', '')))
            ts = f.get('timestamp', 0)
            date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else '-'
            self.recent_table.setItem(i, 4, QTableWidgetItem(date_str))
        self.recent_table.resizeColumnsToContents()
        self.open_recent_btn.setEnabled(False)

    def _show_recent_context_menu(self, pos):
        item = self.recent_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        path = self.recent_table.item(row, 0).data(Qt.UserRole)
        menu = QMenu(self)
        _add_explorer_action(menu, path)
        menu.addSeparator()
        remove_action = menu.addAction('Remove from History')
        remove_action.triggered.connect(lambda: self._remove_recent_file(path))
        menu.exec(self.recent_table.viewport().mapToGlobal(pos))

    def _remove_recent_file(self, path):
        from recent_files import remove_recent_file
        remove_recent_file(path)
        self._refresh_recent_files()

    def _clear_recent_files(self):
        from recent_files import clear_recent_files
        clear_recent_files()
        self._refresh_recent_files()

    def _open_recent_file(self, item):
        row = item.row()
        path = self.recent_table.item(row, 0).data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        # Find the full recent entry with context info
        recent_files = load_recent_files()
        entry = next((f for f in recent_files if f.get('path') == path), None)
        if not entry:
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status(f'No context info for {path}', False)
            return
        
        app_key = entry.get('app_key', '')
        app_name = entry.get('app_name', '')
        cfg = None
        if app_key:
            cfg = self.apps_config.get(app_key)
        if not cfg:
            for key, c in self.apps_config.items():
                if c.get('display_name') == app_name:
                    cfg = c
                    app_key = key
                    break
        if not cfg:
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status(f'No config for app: {app_name}', False)
            return
        
        ctx_type = entry.get('context_type', '')
        ctx_name = entry.get('context_name', '')
        context = None
        if ctx_type and ctx_name:
            if ctx_type == 'shot':
                context = {'type': 'shot', 'name': ctx_name, 'path': self.project_root / 'sequence' / ctx_name}
            elif ctx_type == 'asset':
                context = {'type': 'asset', 'name': ctx_name, 'path': self.project_root / 'asset' / entry.get('context_category', '') / ctx_name}
        
        cfg['_key'] = entry.get('app_key', app_name)
        self.thread = FileOpenThread(
            cfg, self.pipeline_dir, Path(path),
            project_root=self.project_root, context=context,
        )
        self.thread.finished.connect(lambda msg, ok: self._show_launch_result(msg, ok))
        self.thread.start()
        add_recent_file(
            path,
            cfg.get('display_name', app_name),
            ctx_type,
            ctx_name,
            entry.get('context_category', ''),
            app_key=app_key,
        )
        self._refresh_recent_files()

    def _open_selected_recent_file(self):
        items = self.recent_table.selectedItems()
        if items:
            self._open_recent_file(items[0])

    def _refresh(self):
        self._refresh_recent_files()

    def _quick_launch(self, app_name):
        cfg = self.apps_config.get(app_name)
        if cfg:
            saved_version = get_last_app_version(app_name)
            if saved_version and 'version_executables' in cfg and saved_version in cfg['version_executables']:
                cfg = dict(cfg)
                cfg['executable'] = cfg['version_executables'][saved_version]
            self._run_launch(cfg)

    def _run_launch(self, cfg):
        self.thread = AppLauncherThread(cfg, self.pipeline_dir)
        self.thread.finished.connect(lambda msg, ok: self._show_launch_result(msg, ok))
        self.thread.start()

    def _show_launch_result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)

    def _open_yt_screensaver(self):
        from settings import get_setting
        url = get_setting('yt_screensaver_url', '')
        if url:
            webbrowser.open(url)
        else:
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status('No YouTube Screensaver URL configured. Set it in Settings.', False)


class LaunchAppsPage(QWidget):
    def __init__(self, apps_config, pipeline_dir, project_root, parent=None):
        super().__init__(parent)
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self.project_root = project_root
        self._context = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Launch Application')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        layout.addSpacing(8)

        ctx_group = QGroupBox('Context (optional)')
        ctx_layout = QVBoxLayout(ctx_group)

        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel('Context:'))
        self.ctx_combo = QComboBox()
        self.ctx_combo.addItems(['None', 'Shot', 'Asset', 'Light Rig'])
        self.ctx_combo.currentTextChanged.connect(self._on_context_type_change)
        ctx_row.addWidget(self.ctx_combo)

        self.ctx_shot_combo = QComboBox()
        self.ctx_shot_combo.setVisible(False)
        self.ctx_shot_combo.currentTextChanged.connect(self._update_context)
        ctx_row.addWidget(self.ctx_shot_combo)

        self.ctx_cat_combo = QComboBox()
        self.ctx_cat_combo.setVisible(False)
        self.ctx_cat_combo.currentTextChanged.connect(self._on_category_change)
        ctx_row.addWidget(self.ctx_cat_combo)

        self.ctx_asset_combo = QComboBox()
        self.ctx_asset_combo.setVisible(False)
        self.ctx_asset_combo.currentTextChanged.connect(self._update_context)
        ctx_row.addWidget(self.ctx_asset_combo)

        self.ctx_lightrig_combo = QComboBox()
        self.ctx_lightrig_combo.setVisible(False)
        self.ctx_lightrig_combo.currentTextChanged.connect(self._update_context)
        ctx_row.addWidget(self.ctx_lightrig_combo)

        ctx_row.addStretch()
        ctx_layout.addLayout(ctx_row)

        self.ctx_info = QLabel('')
        self.ctx_info.setObjectName('hint')
        ctx_layout.addWidget(self.ctx_info)

        layout.addWidget(ctx_group)
        layout.addSpacing(8)

        body = QHBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setObjectName('launchContainer')
        container_layout = QGridLayout(container)
        container_layout.setSpacing(12)

        self._version_menus = {}
        self._version_labels = {}
        self._version_buttons = {}
        self._app_configs = {}

        if self.apps_config:
            row = 0
            col = 0
            for name, cfg in self.apps_config.items():
                cfg['_key'] = name
                self._app_configs[name] = cfg
                btn_row = QHBoxLayout()
                launch_btn = QPushButton(cfg['display_name'])
                launch_btn.setMinimumHeight(48)
                launch_btn.setCursor(Qt.PointingHandCursor)
                launch_btn.setObjectName('appLaunchBtn')
                launch_btn.clicked.connect(lambda checked, c=cfg: self._launch(c))
                btn_row.addWidget(launch_btn, 1)
                if 'versions' in cfg and cfg['versions']:
                    saved_version = get_last_app_version(name)
                    last_ver = saved_version if saved_version in cfg['versions'] else cfg['versions'][-1]
                    self._version_labels[name] = last_ver
                    version_btn = QPushButton(last_ver)
                    version_btn.setMinimumHeight(48)
                    version_btn.setMinimumWidth(32)
                    version_btn.setCursor(Qt.PointingHandCursor)
                    version_btn.setObjectName('appVersionBtn')
                    menu = QMenu()
                    for v in cfg['versions']:
                        action = menu.addAction(v)
                        action.triggered.connect(lambda checked, ver=v, k=name: self._select_version(k, ver))
                    version_btn.setMenu(menu)
                    self._version_menus[name] = menu
                    self._version_buttons[name] = version_btn
                    btn_row.addWidget(version_btn)
                container_layout.addLayout(btn_row, row, col)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1
            yt_btn = QPushButton('YT Screensaver')
            yt_btn.setMinimumHeight(48)
            yt_btn.setCursor(Qt.PointingHandCursor)
            yt_btn.clicked.connect(self._open_yt_screensaver)
            container_layout.addWidget(yt_btn, row, col)
            container_layout.setRowStretch(row + 1, 1)
        else:
            container_layout.addWidget(QLabel('No applications configured.'), 0, 0, 1, 2)
            container_layout.setRowStretch(1, 1)
        scroll.setWidget(container)
        body.addWidget(scroll, 1)
        layout.addLayout(body, 1)

        self._file_panel = FileBrowserPanel(self.project_root, self.apps_config, self.pipeline_dir)
        self._file_panel.setVisible(False)
        layout.addWidget(self._file_panel)

        self._populate_contexts()

    def _refresh(self):
        self._populate_contexts()

    def _populate_contexts(self):
        seq_dir = self.project_root / 'sequence'
        if seq_dir.exists():
            shots = sorted(d.name for d in seq_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
        else:
            shots = []
        self.ctx_shot_combo.clear()
        self.ctx_shot_combo.addItems(shots)

        from make_folders import NEW_ASSET_CATEGORY_LIST
        self.ctx_cat_combo.clear()
        self.ctx_cat_combo.addItems(NEW_ASSET_CATEGORY_LIST)

    def _on_context_type_change(self, text):
        self.ctx_shot_combo.setVisible(text == 'Shot')
        self.ctx_cat_combo.setVisible(text == 'Asset')
        self.ctx_asset_combo.setVisible(text == 'Asset')
        self.ctx_lightrig_combo.setVisible(text == 'Light Rig')
        if text == 'Asset':
            self._on_category_change(self.ctx_cat_combo.currentText())
        if text == 'Light Rig':
            self._populate_light_rigs()
        self._update_context()

    def _on_category_change(self, category):
        self.ctx_asset_combo.clear()
        asset_dir = self.project_root / 'asset' / category
        if asset_dir.exists():
            assets = sorted(d.name for d in asset_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
            self.ctx_asset_combo.addItems(assets)
        self._update_context()

    def _populate_light_rigs(self):
        self.ctx_lightrig_combo.clear()
        lightrigs_dir = self.project_root / 'lightrigs'
        if lightrigs_dir.exists():
            rigs = sorted(d.name for d in lightrigs_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
            self.ctx_lightrig_combo.addItems(rigs)

    def _update_context(self):
        ctx_type = self.ctx_combo.currentText()
        if ctx_type == 'None':
            self._context = None
            self.ctx_info.setText('No context — app launches without asset/shot working directory.')
            self._file_panel.setVisible(False)
            return

        if ctx_type == 'Shot':
            name = self.ctx_shot_combo.currentText()
            if not name:
                self._context = None
                self.ctx_info.setText('No shots available.')
                return
            path = self.project_root / 'sequence' / name
        elif ctx_type == 'Light Rig':
            name = self.ctx_lightrig_combo.currentText()
            if not name:
                self._context = None
                self.ctx_info.setText('No light rigs available.')
                return
            path = self.project_root / 'lightrigs' / name
        else:
            cat = self.ctx_cat_combo.currentText()
            name = self.ctx_asset_combo.currentText()
            if not name:
                self._context = None
                self.ctx_info.setText('No assets available in this category.')
                return
            path = self.project_root / 'asset' / cat / name

        self._context = {'type': ctx_type.lower(), 'name': name, 'path': path}
        if ctx_type == 'Asset':
            self._context['category'] = self.ctx_cat_combo.currentText()
        self.ctx_info.setText(f'Launch context: {ctx_type} — {name}  ({path})')
        self._file_panel.setVisible(True)
        self._file_panel.set_directory(path, self._context)

    def _launch(self, cfg):
        key = cfg.get('_key', '')
        if key in self._version_labels:
            version = self._version_labels[key]
            if 'version_executables' in cfg and version in cfg['version_executables']:
                cfg = dict(cfg)
                cfg['executable'] = cfg['version_executables'][version]
                set_last_app_version(key, version)
        self.thread = AppLauncherThread(
            cfg, self.pipeline_dir,
            project_root=self.project_root, context=self._context,
        )
        self.thread.finished.connect(lambda msg, ok: self._result(msg, ok))
        self.thread.start()

    def _select_version(self, app_key, version):
        self._version_labels[app_key] = version
        btn = self._version_buttons.get(app_key)
        if btn:
            btn.setText(version)

    def _result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)

    def _open_yt_screensaver(self):
        from settings import get_setting
        url = get_setting('yt_screensaver_url', '')
        if url:
            webbrowser.open(url)
        else:
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status('No YouTube Screensaver URL configured. Set it in Settings.', False)


class ShotExplorerPage(QWidget):
    def __init__(self, project_root, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Shot Explorer')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        layout.addSpacing(8)

        toolbar = QHBoxLayout()
        self.new_btn = QPushButton('New Shot')
        self.new_btn.setMinimumHeight(32)
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self._new_shot)
        toolbar.addWidget(self.new_btn)

        self.edit_btn = QPushButton('Edit Selected')
        self.edit_btn.setMinimumHeight(32)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_shot)
        toolbar.addWidget(self.edit_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels(
            ['', 'Shot', 'Progress', 'Path', 'Frame Range', 'Frame Rate', 'Date', 'Focal Length', 'ISO', 'ND Filter', 'Light Rig', 'Description', 'Working Dirs']
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QPixmap(64, 64).size())
        self.table.setColumnWidth(0, 72)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_change)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table, 1)

        self.file_browser = QGroupBox('Shot Files')
        fb_layout = QVBoxLayout(self.file_browser)
        self._file_panel = FileBrowserPanel(
            self.project_root, self.apps_config, self.pipeline_dir
        )
        fb_layout.addWidget(self._file_panel)
        layout.addWidget(self.file_browser)
        self.file_browser.setVisible(False)

        self._refresh()

    def _new_shot(self):
        dialog = ShotDialog(self, project_root=self.project_root)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        name = data['name']

        from make_folders import make_working_directory

        shot_path = self.project_root / 'sequence' / name
        if shot_path.exists():
            self._status(f'Shot already exists: {name}', False)
            return

        try:
            make_working_directory(str(shot_path))
            write_shot_meta(shot_path, {
                'frame_range': data['frame_range'],
                'frame_rate': data['frame_rate'],
                'date': data['date'],
                'focal_length': data['focal_length'],
                'iso': data['iso'],
                'nd_filter': data['nd_filter'],
                'light_rig': data['light_rig'],
                'description': data['description'],
            })
            self._refresh()
            self._status(f'Shot created: {name}', True)
        except Exception as e:
            self._status(f'Error: {e}', False)

    def _edit_shot(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        shot_name = self.table.item(row, 1).text()
        shot_path = self.project_root / 'sequence' / shot_name
        meta = read_shot_meta(shot_path)

        dialog = ShotDialog(self, shot_name=shot_name, meta=meta, project_root=self.project_root)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()

        write_shot_meta(shot_path, {
            'frame_range': data['frame_range'],
            'frame_rate': data['frame_rate'],
            'date': data['date'],
            'focal_length': data['focal_length'],
            'iso': data['iso'],
            'nd_filter': data['nd_filter'],
            'light_rig': data['light_rig'],
            'description': data['description'],
        })
        self._refresh()
        self._status(f'Metadata updated: {shot_name}', True)

    def _on_selection_change(self):
        items = self.table.selectedItems()
        self.edit_btn.setEnabled(bool(items))
        if items:
            row = items[0].row()
            shot_name = self.table.item(row, 1).text()
            shot_path = self.project_root / 'sequence' / shot_name
            ctx = {'type': 'shot', 'name': shot_name, 'path': shot_path}
            self._file_panel.set_directory(shot_path, context=ctx)
            self.file_browser.setTitle(f'Files: {shot_name}')
            self.file_browser.setVisible(True)
        else:
            self._file_panel.clear()
            self.file_browser.setVisible(False)

    def _refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        seq_dir = self.project_root / 'sequence'
        if not seq_dir.exists():
            return
        shots = sorted([d.name for d in seq_dir.iterdir() if d.is_dir() and not d.name.startswith('_')])
        self.table.setRowCount(len(shots))
        for i, name in enumerate(shots):
            shot_path = seq_dir / name
            meta = read_shot_meta(shot_path)
            prod = read_production(shot_path)
            if not prod:
                prod = {cat: 'Not started' for cat in SHOT_CATEGORIES}
                write_production(shot_path, prod)
            score = production_score(prod)
            working_count = sum(1 for d in shot_path.iterdir() if d.is_dir() and not d.name.startswith('_'))
            self.table.setRowHeight(i, 64)
            thumb_item = QTableWidgetItem()
            thumb_path = shot_path / '_thumbnail.png'
            if thumb_path.exists():
                thumb_item.setIcon(QIcon(str(thumb_path)))
            self.table.setItem(i, 0, thumb_item)
            self.table.setItem(i, 1, QTableWidgetItem(name))
            score_item = _SortItem(score, int(score.replace('%', '')) if score else None)
            color = _score_color(score)
            if color:
                score_item.setForeground(color)
            self.table.setItem(i, 2, score_item)
            self.table.setItem(i, 3, QTableWidgetItem(str(shot_path.relative_to(self.project_root))))
            self.table.setItem(i, 4, QTableWidgetItem(meta['frame_range']))
            self.table.setItem(i, 5, QTableWidgetItem(meta['frame_rate']))
            self.table.setItem(i, 6, QTableWidgetItem(meta.get('date', '')))
            self.table.setItem(i, 7, QTableWidgetItem(meta['focal_length']))
            self.table.setItem(i, 8, QTableWidgetItem(meta['iso']))
            self.table.setItem(i, 9, QTableWidgetItem(meta['nd_filter']))
            self.table.setItem(i, 10, QTableWidgetItem(meta.get('light_rig', '')))
            self.table.setItem(i, 11, QTableWidgetItem(meta['description']))
            self.table.setItem(i, 12, QTableWidgetItem(f'{working_count} dirs'))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(3, max(self.table.columnWidth(3), 200))
        self.table.setColumnWidth(12, max(self.table.columnWidth(12), 200))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSortingEnabled(True)

    def _context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        shot_name = self.table.item(row, 1).text()
        shot_path = self.project_root / 'sequence' / shot_name
        prod = read_production(shot_path)

        menu = QMenu(self)
        _add_explorer_action(menu, shot_path)
        menu.addSeparator()

        for cat in SHOT_CATEGORIES:
            status = prod.get(cat, 'Not started')
            cat_menu = menu.addMenu(f'{cat}: {status}')
            for s in PRODUCTION_STATUSES + ['Not applicable']:
                action = cat_menu.addAction(s)
                action.setData((cat, s))
                if s == status:
                    font = action.font()
                    font.setBold(True)
                    action.setFont(font)

        menu.addSeparator()
        set_thumb = menu.addAction('Set Thumbnail...')
        thumb_path = shot_path / '_thumbnail.png'
        remove_thumb = None
        if thumb_path.exists():
            remove_thumb = menu.addAction('Remove Thumbnail')

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action and action.data():
            cat, status = action.data()
            prod[cat] = status
            write_production(shot_path, prod)
            self._refresh()
        elif action == set_thumb:
            self._set_thumbnail(shot_path)
        elif remove_thumb and action == remove_thumb:
            thumb_path.unlink()
            self._refresh()

    def _set_thumbnail(self, item_path):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Thumbnail', str(item_path),
            'Images (*.png *.jpg *.jpeg *.bmp *.tiff *.exr);;All Files (*)'
        )
        if not file_path:
            return
        from pipeline_app import convert_exr_to_png
        if file_path.lower().endswith('.exr'):
            if not convert_exr_to_png(file_path, item_path / '_thumbnail.png'):
                self._status('Failed to convert EXR file', False)
                return
        else:
            import shutil
            shutil.copy2(file_path, item_path / '_thumbnail.png')
        self._refresh()

    def _status(self, msg, ok=True):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


class LightRigsPage(QWidget):
    def __init__(self, project_root, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Light Rigs')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        layout.addSpacing(8)

        toolbar = QHBoxLayout()
        new_btn = QPushButton('New Light Rig')
        new_btn.setMinimumHeight(32)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._new_rig)
        toolbar.addWidget(new_btn)
        self.edit_btn = QPushButton('Edit')
        self.edit_btn.setMinimumHeight(32)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_rig)
        toolbar.addWidget(self.edit_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ['', 'Name', 'Date', 'Time of Day', 'Description', 'HDRI', 'Photogrammetry', 'USD Scene']
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QPixmap(64, 64).size())
        self.table.setColumnWidth(0, 72)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_change)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table, 1)

        self.file_browser = QGroupBox('Light Rig Files')
        fb_layout = QVBoxLayout(self.file_browser)
        self._file_panel = FileBrowserPanel(
            self.project_root, self.apps_config, self.pipeline_dir
        )
        fb_layout.addWidget(self._file_panel)
        layout.addWidget(self.file_browser)
        self.file_browser.setVisible(False)

        self._refresh()

    def _new_rig(self):
        dialog = LightRigDialog(self, project_root=self.project_root)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        name = data['name']

        from make_folders import make_light_rig_directory

        rig_path = self.project_root / 'lightrigs' / name
        if rig_path.exists():
            self._status(f'Light rig already exists: {name}', False)
            return

        try:
            make_light_rig_directory(str(rig_path))
            hdri_src = data.get('hdri_path', '')
            hdri_rel = ''
            if hdri_src and os.path.isfile(hdri_src):
                hdri_dir = rig_path / 'hdri'
                hdri_filename = os.path.basename(hdri_src)
                hdri_dest = hdri_dir / hdri_filename
                shutil.copy2(hdri_src, str(hdri_dest))
                hdri_rel = f'hdri/{hdri_filename}'
                if hdri_src.lower().endswith('.exr'):
                    from pipeline_app import convert_exr_to_png
                    thumb_path = rig_path / '_thumbnail.png'
                    convert_exr_to_png(hdri_src, str(thumb_path))
            photogrammetry_src = data.get('photogrammetry_path', '')
            photogrammetry_rel = ''
            if photogrammetry_src and os.path.isfile(photogrammetry_src):
                photogrammetry_dir = rig_path / 'photogrammetry'
                photogrammetry_filename = os.path.basename(photogrammetry_src)
                photogrammetry_dest = photogrammetry_dir / photogrammetry_filename
                shutil.copy2(photogrammetry_src, str(photogrammetry_dest))
                photogrammetry_rel = f'photogrammetry/{photogrammetry_filename}'
            usd_src = data.get('usd_scene_path', '')
            usd_rel = ''
            if usd_src and os.path.isfile(usd_src):
                usd_dir = rig_path / 'usd_scene'
                usd_filename = os.path.basename(usd_src)
                usd_dest = usd_dir / usd_filename
                shutil.copy2(usd_src, str(usd_dest))
                usd_rel = f'usd_scene/{usd_filename}'
            write_light_rig_meta(rig_path, {
                'name': name,
                'date': data['date'],
                'time_of_day': data['time_of_day'],
                'lighting_description': data['lighting_description'],
                'hdri_path': hdri_rel,
                'photogrammetry_path': photogrammetry_rel,
                'usd_scene_path': usd_rel,
            })
            self._refresh()
            self._status(f'Light rig created: {name}', True)
        except Exception as e:
            self._status(f'Error: {e}', False)

    def _edit_rig(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        rig_name = self.table.item(row, 1).text()
        rig_path = self.project_root / 'lightrigs' / rig_name
        meta = read_light_rig_meta(rig_path)

        dialog = LightRigDialog(
            self, project_root=self.project_root,
            rig_name=rig_name, meta=meta,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()

        hdri_src = data.get('hdri_path', '')
        hdri_rel = meta.get('hdri_path', '')
        if hdri_src and os.path.isfile(hdri_src) and not hdri_src.startswith(str(rig_path)):
            hdri_dir = rig_path / 'hdri'
            hdri_dir.mkdir(exist_ok=True)
            hdri_filename = os.path.basename(hdri_src)
            hdri_dest = hdri_dir / hdri_filename
            shutil.copy2(hdri_src, str(hdri_dest))
            hdri_rel = f'hdri/{hdri_filename}'
            if hdri_src.lower().endswith('.exr'):
                from pipeline_app import convert_exr_to_png
                thumb_path = rig_path / '_thumbnail.png'
                convert_exr_to_png(hdri_src, str(thumb_path))

        photogrammetry_src = data.get('photogrammetry_path', '')
        photogrammetry_rel = meta.get('photogrammetry_path', '')
        if photogrammetry_src and os.path.isfile(photogrammetry_src) and not photogrammetry_src.startswith(str(rig_path)):
            photogrammetry_dir = rig_path / 'photogrammetry'
            photogrammetry_dir.mkdir(exist_ok=True)
            photogrammetry_filename = os.path.basename(photogrammetry_src)
            photogrammetry_dest = photogrammetry_dir / photogrammetry_filename
            shutil.copy2(photogrammetry_src, str(photogrammetry_dest))
            photogrammetry_rel = f'photogrammetry/{photogrammetry_filename}'

        usd_src = data.get('usd_scene_path', '')
        usd_rel = meta.get('usd_scene_path', '')
        if usd_src and os.path.isfile(usd_src) and not usd_src.startswith(str(rig_path)):
            usd_dir = rig_path / 'usd_scene'
            usd_dir.mkdir(exist_ok=True)
            usd_filename = os.path.basename(usd_src)
            usd_dest = usd_dir / usd_filename
            shutil.copy2(usd_src, str(usd_dest))
            usd_rel = f'usd_scene/{usd_filename}'

        write_light_rig_meta(rig_path, {
            'name': data['name'],
            'date': data['date'],
            'time_of_day': data['time_of_day'],
            'lighting_description': data['lighting_description'],
            'hdri_path': hdri_rel,
            'photogrammetry_path': photogrammetry_rel,
            'usd_scene_path': usd_rel,
        })
        self._refresh()
        self._status(f'Light rig updated: {rig_name}', True)

    def _on_selection_change(self):
        items = self.table.selectedItems()
        self.edit_btn.setEnabled(bool(items))
        if items:
            row = items[0].row()
            rig_name = self.table.item(row, 1).text()
            rig_path = self.project_root / 'lightrigs' / rig_name
            ctx = {'type': 'light_rig', 'name': rig_name, 'path': rig_path}
            self._file_panel.set_directory(rig_path, context=ctx)
            self.file_browser.setTitle(f'Files: {rig_name}')
            self.file_browser.setVisible(True)
        else:
            self._file_panel.clear()
            self.file_browser.setVisible(False)

    def _context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        rig_name = self.table.item(row, 1).text()
        rig_path = self.project_root / 'lightrigs' / rig_name
        menu = QMenu(self)
        _add_explorer_action(menu, rig_path)
        menu.addSeparator()
        edit_action = menu.addAction('Edit Light Rig...')
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == edit_action:
            self.table.selectRow(row)
            self._edit_rig()

    def _refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        lightrigs_dir = self.project_root / 'lightrigs'
        if not lightrigs_dir.exists():
            return
        rigs = sorted([
            d.name for d in lightrigs_dir.iterdir()
            if d.is_dir() and not d.name.startswith('_')
        ])
        self.table.setRowCount(len(rigs))
        for i, name in enumerate(rigs):
            rig_path = lightrigs_dir / name
            meta = read_light_rig_meta(rig_path)
            self.table.setRowHeight(i, 64)
            thumb_item = QTableWidgetItem()
            thumb_path = rig_path / '_thumbnail.png'
            if thumb_path.exists():
                thumb_item.setIcon(QIcon(str(thumb_path)))
            self.table.setItem(i, 0, thumb_item)
            self.table.setItem(i, 1, QTableWidgetItem(name))
            self.table.setItem(i, 2, QTableWidgetItem(meta.get('date', '')))
            self.table.setItem(i, 3, QTableWidgetItem(meta.get('time_of_day', '')))
            self.table.setItem(i, 4, QTableWidgetItem(meta.get('lighting_description', '')))
            self.table.setItem(i, 5, QTableWidgetItem(meta.get('hdri_path', '')))
            self.table.setItem(i, 6, QTableWidgetItem(meta.get('photogrammetry_path', '')))
            self.table.setItem(i, 7, QTableWidgetItem(meta.get('usd_scene_path', '')))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(4, max(self.table.columnWidth(4), 250))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSortingEnabled(True)

    def _status(self, msg, ok=True):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


class AssetExplorerPage(QWidget):
    def __init__(self, project_root, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Asset Explorer')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        layout.addSpacing(8)

        toolbar = QHBoxLayout()
        self.new_btn = QPushButton('New Asset')
        self.new_btn.setMinimumHeight(32)
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self._new_asset)
        toolbar.addWidget(self.new_btn)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel('Category:'))
        self.filter_combo = QComboBox()
        from make_folders import NEW_ASSET_CATEGORY_LIST
        self.filter_combo.addItems(['All'] + list(NEW_ASSET_CATEGORY_LIST))
        self.filter_combo.currentTextChanged.connect(self._refresh)
        filter_row.addWidget(self.filter_combo)
        toolbar.addLayout(filter_row)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['', 'Asset', 'Progress', 'Category', 'Path', 'Working Dirs'])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QPixmap(64, 64).size())
        self.table.setColumnWidth(0, 72)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_change)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table, 1)

        self.file_browser = QGroupBox('Asset Files')
        fb_layout = QVBoxLayout(self.file_browser)
        self._file_panel = FileBrowserPanel(
            self.project_root, self.apps_config, self.pipeline_dir
        )
        fb_layout.addWidget(self._file_panel)
        layout.addWidget(self.file_browser)
        self.file_browser.setVisible(False)

        self._refresh()

    def _new_asset(self):
        dialog = AssetDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        category = data['category']
        name = data['name']

        from make_folders import make_working_directory

        asset_path = self.project_root / 'asset' / category / name
        if asset_path.exists():
            self._status(f'Asset already exists: {category}/{name}', False)
            return

        try:
            make_working_directory(str(asset_path))
            self._refresh()
            self._status(f'Asset created: {category}/{name}', True)
        except Exception as e:
            self._status(f'Error: {e}', False)

    def _on_selection_change(self):
        items = self.table.selectedItems()
        if items:
            row = items[0].row()
            asset_name = self.table.item(row, 1).text()
            cat = self.table.item(row, 3).text()
            asset_path = self.project_root / 'asset' / cat / asset_name
            ctx = {'type': 'asset', 'name': asset_name, 'path': asset_path, 'category': cat}
            self._file_panel.set_directory(asset_path, context=ctx)
            self.file_browser.setTitle(f'Files: {asset_name}')
            self.file_browser.setVisible(True)
        else:
            self._file_panel.clear()
            self.file_browser.setVisible(False)

    def _refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        asset_dir = self.project_root / 'asset'
        if not asset_dir.exists():
            return
        selected = self.filter_combo.currentText()
        rows = []
        for cat_dir in asset_dir.iterdir():
            if not cat_dir.is_dir() or cat_dir.name.startswith('_'):
                continue
            if selected != 'All' and cat_dir.name != selected:
                continue
            for asset in sorted(cat_dir.iterdir()):
                if asset.is_dir() and not asset.name.startswith('_'):
                    prod = read_production(asset)
                    if not prod:
                        prod = {cat_name: 'Not applicable' if info == 'optional' else 'Not started'
                                for cat_name, info in ASSET_CATEGORIES.items()}
                        write_production(asset, prod)
                    score = production_score(prod)
                    working_count = sum(1 for d in asset.iterdir() if d.is_dir())
                    rows.append((asset.name, cat_dir.name, str(asset.relative_to(self.project_root)), score, f'{working_count} dirs'))
        self.table.setRowCount(len(rows))
        for i, (name, cat, path, score, count) in enumerate(rows):
            self.table.setRowHeight(i, 64)
            thumb_item = QTableWidgetItem()
            asset_path = self.project_root / 'asset' / cat / name
            thumb_path = asset_path / '_thumbnail.png'
            if thumb_path.exists():
                thumb_item.setIcon(QIcon(str(thumb_path)))
            self.table.setItem(i, 0, thumb_item)
            self.table.setItem(i, 1, QTableWidgetItem(name))
            score_item = _SortItem(score, int(score.replace('%', '')) if score else None)
            color = _score_color(score)
            if color:
                score_item.setForeground(color)
            self.table.setItem(i, 2, score_item)
            self.table.setItem(i, 3, QTableWidgetItem(cat))
            self.table.setItem(i, 4, QTableWidgetItem(path))
            self.table.setItem(i, 5, QTableWidgetItem(count))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(4, max(self.table.columnWidth(4), 300))
        self.table.setSortingEnabled(True)

    def _context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        asset_name = self.table.item(row, 1).text()
        cat = self.table.item(row, 3).text()
        asset_path = self.project_root / 'asset' / cat / asset_name
        prod = read_production(asset_path)

        menu = QMenu(self)
        _add_explorer_action(menu, asset_path)
        menu.addSeparator()

        for cat_name, cat_type in ASSET_CATEGORIES.items():
            status = prod.get(cat_name, 'Not started')
            label = f'{cat_name} ({cat_type})' if cat_type == 'optional' else cat_name
            cat_menu = menu.addMenu(f'{label}: {status}')
            for s in PRODUCTION_STATUSES + ['Not applicable']:
                action = cat_menu.addAction(s)
                action.setData((cat_name, s))
                if s == status:
                    font = action.font()
                    font.setBold(True)
                    action.setFont(font)

        menu.addSeparator()
        set_thumb = menu.addAction('Set Thumbnail...')
        thumb_path = asset_path / '_thumbnail.png'
        remove_thumb = None
        if thumb_path.exists():
            remove_thumb = menu.addAction('Remove Thumbnail')

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action and action.data():
            cat_name, status = action.data()
            prod[cat_name] = status
            write_production(asset_path, prod)
            self._refresh()
        elif action == set_thumb:
            self._set_thumbnail(asset_path)
        elif remove_thumb and action == remove_thumb:
            thumb_path.unlink()
            self._refresh()

    def _set_thumbnail(self, item_path):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Thumbnail', str(item_path),
            'Images (*.png *.jpg *.jpeg *.bmp *.tiff *.exr);;All Files (*)'
        )
        if not file_path:
            return
        from pipeline_app import convert_exr_to_png
        if file_path.lower().endswith('.exr'):
            if not convert_exr_to_png(file_path, item_path / '_thumbnail.png'):
                self._status('Failed to convert EXR file', False)
                return
        else:
            import shutil
            shutil.copy2(file_path, item_path / '_thumbnail.png')
        self._refresh()

    def _status(self, msg, ok=True):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


CONTEXT_ENV_KEYS = [
    'MAZE_CONTEXT_TYPE', 'MAZE_CONTEXT_NAME', 'MAZE_CONTEXT_PATH',
    'PIPELINE_DIR', 'START_FRAME', 'END_FRAME', 'FRAME_RATE',
    'HOUDINI_JOB', 'JOB', 'MAYA_PROJECT',
]

ENV_DESCRIPTIONS = {
    'MZE': 'Root directory of the project (short alias)',
    'MAZE_PROJECT_ROOT': 'Root directory of the project',
    'MAZE_PROJECT': 'Project folder name',
    'MAZE_PIPELINE': 'Pipeline tools directory',
    'MAZE_ASSETS': 'Asset storage directory',
    'MAZE_SEQUENCES': 'Shot sequences directory',
    'MAZE_ONSET': 'On-set data directory',
    'MAZE_IO': 'Import/export directory',
    'MAZE_DEVELOPMENT': 'Development workspace',
    'MAZE_RND': 'Research and development directory',
    'MAZE_MISC': 'Miscellaneous files directory',
    'MAZE_CONTEXT_TYPE': 'Context type (shot or asset)',
    'MAZE_CONTEXT_NAME': 'Current shot or asset name',
    'MAZE_CONTEXT_PATH': 'Full path to the context directory',
    'PIPELINE_DIR': 'Pipeline root directory',
    'START_FRAME': 'Shot start frame',
    'END_FRAME': 'Shot end frame',
    'FRAME_RATE': 'Shot frame rate',
    'HOUDINI_JOB': 'Houdini job directory',
    'JOB': 'Generic job directory (Houdini)',
    'MAYA_PROJECT': 'Maya project directory',
}


import os
from recent_files import load_recent_files, clear_recent_files


class RecentFilesPage(QWidget):
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Recent Files')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        refresh_btn = QPushButton('Refresh')
        refresh_btn.setMinimumHeight(32)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
        clear_btn = QPushButton('Clear History')
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)
        layout.addLayout(header)
        layout.addSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['File', 'App', 'Context', 'Opened'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemDoubleClicked.connect(self._open_file)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table, 1)

        self._refresh()

    def _refresh(self):
        files = load_recent_files()
        self.table.setRowCount(len(files))
        for i, f in enumerate(files):
            item0 = QTableWidgetItem(f.get('display_name', f.get('path', '')))
            item0.setData(Qt.UserRole, f.get('path', ''))
            self.table.setItem(i, 0, item0)
            self.table.setItem(i, 1, QTableWidgetItem(f.get('app_name', '')))
            ctx = f.get('context_type', '')
            ctx_name = f.get('context_name', '')
            ctx_display = f'{ctx}: {ctx_name}' if ctx and ctx_name else (ctx or '-')
            self.table.setItem(i, 2, QTableWidgetItem(ctx_display))
            ts = f.get('timestamp', 0)
            date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else '-'
            self.table.setItem(i, 3, QTableWidgetItem(date_str))
        self.table.resizeColumnsToContents()

    def _open_file(self, item):
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            os.startfile(path) if os.name == 'nt' else subprocess.Popen(['xdg-open', path])

    def _clear_history(self):
        clear_recent_files()
        self._refresh()

    def _context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.UserRole)
        menu = QMenu(self)
        _add_explorer_action(menu, path)
        menu.exec(self.table.viewport().mapToGlobal(pos))


class PreviewPage(QWidget):
    def __init__(self, project_root, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.pipeline_dir = pipeline_dir
        self._sequences = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel('Preview')
        title.setObjectName('sectionTitle')
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh_shots)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        shot_row = QHBoxLayout()
        shot_row.addWidget(QLabel('Shot:'))
        self.shot_combo = QComboBox()
        self.shot_combo.setMinimumWidth(260)
        self.shot_combo.currentTextChanged.connect(self._on_shot_changed)
        shot_row.addWidget(self.shot_combo, 1)
        layout.addLayout(shot_row)

        self.seq_list = QTreeWidget()
        self.seq_list.setHeaderLabels(['Name', 'Format', 'Frames', 'Folder', 'Warning'])
        self.seq_list.setSelectionMode(QTreeWidget.SingleSelection)
        self.seq_list.setAlternatingRowColors(True)
        self.seq_list.itemDoubleClicked.connect(self._open_in_mplay)
        self.seq_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.seq_list.customContextMenuRequested.connect(self._context_menu)
        self.seq_list.setColumnWidth(0, 280)
        self.seq_list.setColumnWidth(2, 60)
        self.seq_list.setColumnWidth(3, 280)
        self.seq_list.header().setStretchLastSection(False)
        layout.addWidget(self.seq_list, 1)

        btn_row = QHBoxLayout()
        self.open_btn = QPushButton('Open in MPlay')
        self.open_btn.setMinimumHeight(36)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_in_mplay)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_label = QLabel('')
        self.status_label.setStyleSheet('color: #888;')
        layout.addWidget(self.status_label)

        self.seq_list.itemSelectionChanged.connect(
            lambda: self.open_btn.setEnabled(bool(self.seq_list.selectedItems()))
        )

        self._refresh_shots()

    def _refresh_shots(self):
        current = self.shot_combo.currentText()
        self.shot_combo.blockSignals(True)
        self.shot_combo.clear()
        seq_dir = self.project_root / 'sequence'
        if seq_dir.exists():
            shots = sorted(
                d.name for d in seq_dir.iterdir()
                if d.is_dir() and not d.name.startswith('_')
            )
            self.shot_combo.addItems(shots)
        idx = self.shot_combo.findText(current)
        if idx >= 0:
            self.shot_combo.setCurrentIndex(idx)
        self.shot_combo.blockSignals(False)
        self._on_shot_changed(self.shot_combo.currentText())

    def _on_shot_changed(self, shot_name):
        self.seq_list.clear()
        self._sequences = []
        if not shot_name:
            self.status_label.setText('No shot selected')
            return
        shot_path = self.project_root / 'sequence' / shot_name
        try:
            sequences = discover_image_sequences(shot_path)
        except Exception as e:
            self.status_label.setText(f'Error discovering sequences: {e}')
            return
        self._sequences = sequences
        try:
            self._build_tree(sequences, shot_path)
        except Exception as e:
            self.status_label.setText(f'Error building tree: {e}')
            return
        self.seq_list.sortItems(0, Qt.AscendingOrder)
        self.status_label.setText(
            f'{len(sequences)} sequence{"s" if len(sequences) != 1 else ""} found'
            if sequences else 'No image sequences found'
        )

    def _build_tree(self, sequences, shot_path):
        software_items = {}
        name_items = {}
        version_parents = {}
        warned_versions = set()
        for i, seq in enumerate(sequences):
            sw = seq['software']
            if sw not in software_items:
                sw_item = QTreeWidgetItem(self.seq_list, [sw])
                sw_item.setFlags(sw_item.flags() & ~Qt.ItemIsSelectable)
                software_items[sw] = sw_item
            sw_item = software_items[sw]
            warning = seq.get('warning', None)
            base_prefix = seq['prefix']
            name_key = (sw, base_prefix)
            if name_key not in name_items:
                name_item = QTreeWidgetItem(sw_item, [base_prefix])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsSelectable)
                name_items[name_key] = name_item
            name_item = name_items[name_key]
            version = seq.get('version', '')
            fmt = seq.get('format', '')
            if version:
                vp_key = (sw, base_prefix, version)
                if vp_key not in version_parents:
                    v_parent = QTreeWidgetItem(name_item, [version])
                    v_parent.setFlags(v_parent.flags() & ~Qt.ItemIsSelectable)
                    version_parents[vp_key] = v_parent
                v_parent = version_parents[vp_key]
                if warning:
                    warned_versions.add(vp_key)
                v_item = QTreeWidgetItem(v_parent, [
                    seq['prefix'],
                    fmt,
                    str(seq['count']),
                    str(seq['folder'].relative_to(shot_path)),
                    '',
                ])
            else:
                v_item = QTreeWidgetItem(name_item, [
                    seq['prefix'],
                    fmt,
                    str(seq['count']),
                    str(seq['folder'].relative_to(shot_path)),
                    warning or '',
                ])
            v_item.setData(0, Qt.UserRole, i)
            if warning:
                for col in range(v_item.columnCount()):
                    v_item.setForeground(col, QColor('#ffa726'))
        for vp_key in warned_versions:
            v_parent = version_parents[vp_key]
            v_parent.setText(4, 'Duplicate files detected')
            for col in range(v_parent.columnCount()):
                v_parent.setForeground(col, QColor('#ffa726'))

    def _open_in_mplay(self, *args):
        items = self.seq_list.selectedItems()
        if not items:
            return
        idx = items[0].data(0, Qt.UserRole)
        if idx is None:
            return
        seq = self._sequences[idx]

        if Path(seq['first_frame']).suffix.lower() in ('.mov', '.mp4'):
            video_path = seq['folder'] / seq['first_frame']
            os.startfile(str(video_path))
            self.status_label.setText(f'Opened {seq["prefix"]}')
            return

        mplay_path = self.pipeline_dir / 'Houdini' / 'bin' / 'mplay.exe'
        if not mplay_path.exists():
            mplay_path = Path(r'C:\Program Files\Side Effects Software\Houdini 22.0.416\bin\mplay.exe')
        if not mplay_path.exists():
            mplay_path = Path(r'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\mplay.exe')
        if not mplay_path.exists():
            self.status_label.setText('mplay.exe not found')
            return

        launch_env = os.environ.copy()
        ctx_env = build_context_env(
            {'type': 'shot', 'name': self.shot_combo.currentText(),
             'path': str(self.project_root / 'sequence' / self.shot_combo.currentText())},
            self.project_root,
        )
        launch_env.update(ctx_env)
        launch_env['HOUDINI_PATH'] = str(self.pipeline_dir / 'Houdini') + ';&;' + launch_env.get('HOUDINI_PATH', '')

        ocio_config = self.pipeline_dir / 'OCIO' / 'BU_nov2024_config.ocio'
        if ocio_config.exists():
            launch_env['OCIO'] = str(ocio_config)
            launch_env['OCIO_ACTIVE_DISPLAYS'] = 'arri709 - Display:sRGB - Display'
            launch_env['OCIO_ACTIVE_VIEWS'] = 'arri709 - View:Raw'

        first = seq['first_frame']
        last = seq['last_frame']
        frame_match = re.search(r'(\d+)(?=\.\w+$)', first)
        if not frame_match:
            self.status_label.setText('Could not detect frame number')
            return
        start_frame = int(frame_match.group(1))
        pad = len(frame_match.group(1))
        end_frame = int(re.search(r'(\d+)(?=\.\w+$)', last).group(1))
        actual_name = first[:frame_match.start()] + f'$F{pad}' + first[frame_match.end():]
        seq_folder = seq['folder']
        fmt = seq.get('format', '').lower()
        if fmt:
            fmt_dir = seq_folder / fmt
            if fmt_dir.is_dir():
                seq_folder = fmt_dir
        pattern = str(seq_folder / actual_name)
        try:
            subprocess.Popen([str(mplay_path), '-f', str(start_frame), str(end_frame), '1', pattern], env=launch_env)
            self.status_label.setText(f'Opened {seq["prefix"]} in MPlay')
        except Exception as e:
            self.status_label.setText(f'Failed to launch MPlay: {e}')

    def _context_menu(self, pos):
        items = self.seq_list.selectedItems()
        if not items:
            return
        item = items[0]
        path = None
        idx = item.data(0, Qt.UserRole)
        if idx is not None and idx < len(self._sequences):
            seq = self._sequences[idx]
            path = seq['folder']
            fmt = seq.get('format', '').lower()
            if fmt:
                fmt_dir = path / fmt
                if fmt_dir.is_dir():
                    path = fmt_dir
        menu = QMenu(self)
        _add_explorer_action(menu, path)
        menu.exec(self.seq_list.viewport().mapToGlobal(pos))


class ProductionPage(QWidget):
    def __init__(self, project_root, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.pipeline_dir = pipeline_dir
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel('Production Tracking')
        title.setObjectName('sectionTitle')
        header.addWidget(title)
        header.addStretch()
        refresh_btn = QPushButton('Refresh')
        refresh_btn.setMinimumHeight(32)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        summary_group = QGroupBox('Progress')
        summary_layout = QVBoxLayout(summary_group)

        overall_row = QHBoxLayout()
        overall_row.addWidget(QLabel('Overall Progress'))
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(False)
        self.overall_progress.setMinimumHeight(24)
        overall_row.addWidget(self.overall_progress, 1)
        self.overall_label = QLabel('')
        self.overall_label.setMinimumWidth(50)
        overall_row.addWidget(self.overall_label)
        summary_layout.addLayout(overall_row)

        self.cat_group = QGroupBox('Progress by Category')
        self.cat_group.setCheckable(True)
        self.cat_group.setFlat(True)
        self.cat_group.setChecked(False)
        self.cat_group.toggled.connect(self._toggle_cat_bars)
        cat_layout = QVBoxLayout(self.cat_group)

        self.cat_bars = {}
        asset_label = QLabel('Assets:')
        asset_label.setObjectName('hint')
        cat_layout.addWidget(asset_label)

        for cat_name in ASSET_CATEGORIES:
            row = QHBoxLayout()
            row.addWidget(QLabel(cat_name), 1)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setMinimumHeight(18)
            row.addWidget(bar, 2)
            pct_label = QLabel('')
            pct_label.setMinimumWidth(40)
            row.addWidget(pct_label)
            cat_layout.addLayout(row)
            self.cat_bars[cat_name] = (bar, pct_label)

        shot_sep = QLabel('Shots:')
        shot_sep.setObjectName('hint')
        cat_layout.addWidget(shot_sep)

        for cat in SHOT_CATEGORIES:
            row = QHBoxLayout()
            row.addWidget(QLabel(cat), 1)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setMinimumHeight(18)
            row.addWidget(bar, 2)
            pct_label = QLabel('')
            pct_label.setMinimumWidth(40)
            row.addWidget(pct_label)
            cat_layout.addLayout(row)
            self.cat_bars[cat] = (bar, pct_label)

        self._toggle_cat_bars(False)
        summary_layout.addWidget(self.cat_group)

        layout.addWidget(summary_group)

        tabs = QTabWidget()

        shot_tab = QWidget()
        shot_layout = QVBoxLayout(shot_tab)
        self.shot_table = QTableWidget()
        self.shot_table.setAlternatingRowColors(True)
        self.shot_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.shot_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.shot_table.verticalHeader().setVisible(False)
        self.shot_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.shot_table.customContextMenuRequested.connect(self._shot_context_menu)
        self.shot_table.setSortingEnabled(True)
        shot_layout.addWidget(self.shot_table)
        tabs.addTab(shot_tab, 'Shots')

        asset_tab = QWidget()
        asset_layout = QVBoxLayout(asset_tab)
        self.asset_table = QTableWidget()
        self.asset_table.setAlternatingRowColors(True)
        self.asset_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.asset_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.asset_table.verticalHeader().setVisible(False)
        self.asset_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.asset_table.customContextMenuRequested.connect(self._asset_context_menu)
        self.asset_table.setSortingEnabled(True)
        asset_layout.addWidget(self.asset_table)
        tabs.addTab(asset_tab, 'Assets')

        layout.addWidget(tabs)

        self._refresh()

    def _refresh(self):
        self._refresh_shots()
        self._refresh_assets()
        self._refresh_summary()

    def _refresh_shots(self):
        self.shot_table.setSortingEnabled(False)
        self.shot_table.clear()
        seq_dir = self.project_root / 'sequence'
        if not seq_dir.exists():
            return
        shots = sorted(d.name for d in seq_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
        cols = ['Shot'] + SHOT_CATEGORIES + ['Progress']
        self.shot_table.setColumnCount(len(cols))
        self.shot_table.setHorizontalHeaderLabels(cols)
        self.shot_table.setRowCount(len(shots))
        for i, name in enumerate(shots):
            shot_path = seq_dir / name
            prod = read_production(shot_path)
            if not prod:
                prod = {cat: 'Not started' for cat in SHOT_CATEGORIES}
                write_production(shot_path, prod)
            self.shot_table.setItem(i, 0, QTableWidgetItem(name))
            for j, cat in enumerate(SHOT_CATEGORIES):
                status = prod.get(cat, 'Not started')
                item = _SortItem(status, PRODUCTION_VALUES.get(status, 0))
                item.setData(Qt.UserRole, (name, cat))
                item.setForeground(_status_color(status))
                self.shot_table.setItem(i, j + 1, item)
            score = production_score(prod)
            score_item = _SortItem(score, int(score.replace('%', '')) if score else None)
            color = _score_color(score)
            if color:
                score_item.setForeground(color)
            self.shot_table.setItem(i, len(cols) - 1, score_item)
        self.shot_table.resizeColumnsToContents()
        self.shot_table.setSortingEnabled(True)

    def _refresh_assets(self):
        self.asset_table.setSortingEnabled(False)
        self.asset_table.clear()
        asset_dir = self.project_root / 'asset'
        if not asset_dir.exists():
            return
        all_cats = list(ASSET_CATEGORIES.keys())
        cols = ['Asset', 'Category'] + all_cats + ['Progress']
        self.asset_table.setColumnCount(len(cols))
        self.asset_table.setHorizontalHeaderLabels(cols)
        rows = []
        for cat_dir in sorted(asset_dir.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name.startswith('_'):
                continue
            for asset in sorted(cat_dir.iterdir()):
                if asset.is_dir() and not asset.name.startswith('_'):
                    prod = read_production(asset)
                    if not prod:
                        prod = {cat_name: 'Not applicable' if info == 'optional' else 'Not started'
                                for cat_name, info in ASSET_CATEGORIES.items()}
                        write_production(asset, prod)
                    rows.append((asset.name, cat_dir.name, prod))
        self.asset_table.setRowCount(len(rows))
        for i, (name, cat, prod) in enumerate(rows):
            self.asset_table.setItem(i, 0, QTableWidgetItem(name))
            self.asset_table.setItem(i, 1, QTableWidgetItem(cat))
            for j, cat_name in enumerate(all_cats):
                status = prod.get(cat_name, 'Not started')
                item = _SortItem(status, PRODUCTION_VALUES.get(status, 0))
                item.setData(Qt.UserRole, (name, cat, cat_name))
                item.setForeground(_status_color(status))
                self.asset_table.setItem(i, j + 2, item)
            score = production_score(prod)
            score_item = _SortItem(score, int(score.replace('%', '')) if score else None)
            color = _score_color(score)
            if color:
                score_item.setForeground(color)
            self.asset_table.setItem(i, len(cols) - 1, score_item)
        self.asset_table.resizeColumnsToContents()
        self.asset_table.setSortingEnabled(True)

    def _toggle_cat_bars(self, checked):
        layout = self.cat_group.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                item.widget().setVisible(checked)
            elif item and item.layout():
                for j in range(item.layout().count()):
                    child = item.layout().itemAt(j)
                    if child and child.widget():
                        child.widget().setVisible(checked)

    def _refresh_summary(self):
        all_scores = []
        cat_values = {cat: [] for cat in SHOT_CATEGORIES}
        asset_cat_values = {cat: [] for cat in ASSET_CATEGORIES}

        seq_dir = self.project_root / 'sequence'
        if seq_dir.exists():
            for d in sorted(seq_dir.iterdir()):
                if d.is_dir() and not d.name.startswith('_'):
                    prod = read_production(d)
                    if not prod:
                        prod = {cat: 'Not started' for cat in SHOT_CATEGORIES}
                    vals = [PRODUCTION_VALUES.get(v, 0) for v in prod.values() if v != 'Not applicable']
                    if vals:
                        all_scores.append(sum(vals) / len(vals))
                    for cat in SHOT_CATEGORIES:
                        status = prod.get(cat, 'Not started')
                        if status != 'Not applicable':
                            cat_values[cat].append(PRODUCTION_VALUES.get(status, 0))

        asset_dir = self.project_root / 'asset'
        if asset_dir.exists():
            for cat_dir in sorted(asset_dir.iterdir()):
                if not cat_dir.is_dir() or cat_dir.name.startswith('_'):
                    continue
                for asset in sorted(cat_dir.iterdir()):
                    if asset.is_dir() and not asset.name.startswith('_'):
                        prod = read_production(asset)
                        if not prod:
                            continue
                        vals = [PRODUCTION_VALUES.get(v, 0) for v in prod.values() if v != 'Not applicable']
                        if vals:
                            all_scores.append(sum(vals) / len(vals))
                        for cat_name in ASSET_CATEGORIES:
                            status = prod.get(cat_name, 'Not started')
                            if status != 'Not applicable':
                                asset_cat_values[cat_name].append(PRODUCTION_VALUES.get(status, 0))

        if all_scores:
            avg = round(sum(all_scores) / len(all_scores))
            self.overall_progress.setValue(avg)
            self.overall_label.setText(f'{avg}%')
            color = _score_color(f'{avg}%')
            if color:
                self.overall_label.setStyleSheet(f'color: {color.name()};')
        else:
            self.overall_progress.setValue(0)
            self.overall_label.setText('')

        for cat in SHOT_CATEGORIES:
            bar, pct_label = self.cat_bars[cat]
            vals = cat_values[cat]
            if vals:
                avg = round(sum(vals) / len(vals))
                bar.setValue(avg)
                pct_label.setText(f'{avg}%')
                color = _score_color(f'{avg}%')
                if color:
                    pct_label.setStyleSheet(f'color: {color.name()};')
            else:
                bar.setValue(0)
                pct_label.setText('')

        for cat_name in ASSET_CATEGORIES:
            bar, pct_label = self.cat_bars[cat_name]
            vals = asset_cat_values[cat_name]
            if vals:
                avg = round(sum(vals) / len(vals))
                bar.setValue(avg)
                pct_label.setText(f'{avg}%')
                color = _score_color(f'{avg}%')
                if color:
                    pct_label.setStyleSheet(f'color: {color.name()};')
            else:
                bar.setValue(0)
                pct_label.setText('')

    def _shot_context_menu(self, pos):
        item = self.shot_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        shot_name = self.shot_table.item(row, 0).text()
        shot_path = self.project_root / 'sequence' / shot_name
        col = item.column()
        if col == 0:
            menu = QMenu(self)
            _add_explorer_action(menu, shot_path)
            menu.exec(self.shot_table.viewport().mapToGlobal(pos))
            return
        if col - 1 >= len(SHOT_CATEGORIES):
            return
        cat = SHOT_CATEGORIES[col - 1]
        prod = read_production(shot_path)
        current = prod.get(cat, 'Not started')

        menu = QMenu(self)
        _add_explorer_action(menu, shot_path)
        menu.addSeparator()
        for s in PRODUCTION_STATUSES + ['Not applicable']:
            action = menu.addAction(s)
            action.setData(s)
            if s == current:
                font = action.font()
                font.setBold(True)
                action.setFont(font)

        action = menu.exec(self.shot_table.viewport().mapToGlobal(pos))
        if action and action.data():
            new_status = action.data()
            if new_status != current:
                prod[cat] = new_status
                write_production(shot_path, prod)
                self._refresh_shots()
                self._refresh_summary()
                self._send_production_webhook('shot', shot_name, '', cat, current, new_status)

    def _send_production_webhook(self, item_type, item_name, category, task, from_status, to_status):
        if to_status == 'Not applicable':
            return
        try:
            from settings import get_setting
            url = get_setting('production_webhook_url', '')
            if not url:
                return
            from pipeline_app import send_production_notification
            import threading
            threading.Thread(
                target=send_production_notification,
                args=(url, item_type, item_name, category, task, from_status, to_status),
                daemon=True,
            ).start()
        except Exception:
            pass

    def _asset_context_menu(self, pos):
        item = self.asset_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        asset_name = self.asset_table.item(row, 0).text()
        cat = self.asset_table.item(row, 1).text()
        asset_path = self.project_root / 'asset' / cat / asset_name
        col = item.column()
        if col < 2:
            menu = QMenu(self)
            _add_explorer_action(menu, asset_path)
            menu.exec(self.asset_table.viewport().mapToGlobal(pos))
            return
        all_cats = list(ASSET_CATEGORIES.keys())
        if col - 2 >= len(all_cats):
            return
        cat_name = all_cats[col - 2]
        prod = read_production(asset_path)
        current = prod.get(cat_name, 'Not started')

        menu = QMenu(self)
        _add_explorer_action(menu, asset_path)
        menu.addSeparator()
        for s in PRODUCTION_STATUSES + ['Not applicable']:
            action = menu.addAction(s)
            action.setData(s)
            if s == current:
                font = action.font()
                font.setBold(True)
                action.setFont(font)

        action = menu.exec(self.asset_table.viewport().mapToGlobal(pos))
        if action and action.data():
            new_status = action.data()
            if new_status != current:
                prod[cat_name] = new_status
                write_production(asset_path, prod)
                self._refresh_assets()
                self._refresh_summary()
                self._send_production_webhook('asset', asset_name, cat, cat_name, current, new_status)


class EnvVarsPage(QWidget):
    def __init__(self, env_vars, parent=None):
        super().__init__(parent)
        self.env_vars = env_vars
        self._build()

    def _refresh(self):
        base_vars = sorted(self.env_vars.items())
        self._fill_table(self.base_table, base_vars)

        ctx_pairs = [(k, os.environ.get(k, '') or '—') for k in CONTEXT_ENV_KEYS]
        self._fill_table(self.ctx_table, ctx_pairs)

    @staticmethod
    def _fill_table(table, pairs):
        table.setRowCount(len(pairs))
        for i, (key, value) in enumerate(pairs):
            table.setItem(i, 0, QTableWidgetItem(key))
            table.setItem(i, 1, QTableWidgetItem(value))
            table.setItem(i, 2, QTableWidgetItem(ENV_DESCRIPTIONS.get(key, '')))
        table.resizeColumnsToContents()

    def _make_table(self):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Variable', 'Value', 'Description'])
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        return table

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel('Environment Variables')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        note = QLabel(
            'Base paths use MAZE_PROJECT_ROOT references. '
            'Context variables populate after launching an app with a context.'
        )
        note.setWordWrap(True)
        note.setObjectName('hint')
        layout.addWidget(note)
        layout.addSpacing(8)

        layout.addWidget(QLabel('Static Variables'))
        self.base_table = self._make_table()
        layout.addWidget(self.base_table)

        layout.addSpacing(12)

        layout.addWidget(QLabel('Context Variables'))
        self.ctx_table = self._make_table()
        layout.addWidget(self.ctx_table)

        self._refresh()


class LogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel('Log')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addSpacing(8)

        toolbar = QHBoxLayout()
        self.clear_btn = QPushButton('Clear Log')
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch()
        self.line_count_label = QLabel('')
        self.line_count_label.setObjectName('hint')
        toolbar.addWidget(self.line_count_label)
        layout.addLayout(toolbar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setObjectName('renderLog')
        layout.addWidget(self.log_output, 1)

        self._line_count = 0

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_log)
        self._poll_timer.start(100)

    def _poll_log(self):
        log_stream = get_log_stream()
        for line in log_stream.get_lines():
            self._append_line(line)

    def _append_line(self, line):
        self.log_output.append(line)
        self._line_count += 1
        self.line_count_label.setText(f'{self._line_count} lines')
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear(self):
        self.log_output.clear()
        self._line_count = 0
        self.line_count_label.setText('')

    def _refresh(self):
        pass


class HelpPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _add_section(self, layout, title, html, expanded=False):
        box = QGroupBox(title)
        box.setCheckable(True)
        box.setChecked(expanded)
        box.setFlat(False)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 12, 12, 12)
        label = QLabel(html)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(False)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        inner.addWidget(label)
        # toggle visibility of contents via groupbox checked state (Qt handles checkable groupbox content enabled)
        # Use visiblity of inner widget
        def _toggled(checked, b=box):
            for i in range(b.layout().count()):
                w = b.layout().itemAt(i).widget()
                if w:
                    w.setVisible(checked)
            b.setFlat(not checked)
        # init visibility
        _toggled(expanded, box)
        box.toggled.connect(lambda c, b=box: _toggled(c, b))
        layout.addWidget(box)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel('MazeHub User Guide')
        tf = QFont()
        tf.setPointSize(16)
        tf.setBold(True)
        title.setFont(tf)
        layout.addWidget(title)
        hint = QLabel('Click a section header to expand or collapse it.')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        layout.addWidget(hint)
        layout.addSpacing(8)

        self._add_section(layout, '1 — Overview', """
        <p><b>MazeHub</b> is your hub for the whole MAZE project. Open it to see your shots, assets and light rigs, launch Houdini, Maya, Nuke and more with the right context already loaded, and keep track of progress.</p>
        <p>Everything is organised by <b>Shots</b> (like SH010, SH020), <b>Assets</b> (characters, props), and <b>Light Rigs</b> (HDRI setups). MazeHub makes sure each app opens in the right place with the right settings, so you don't have to hunt for files.</p>
        """, expanded=True)

        self._add_section(layout, '2 — Home', """
        <p>Your landing page. At the top you see how many shots and assets you have and how much is done overall.</p>
        <p><b>Quick Launch</b> — click a button to open an app quickly. The app launches with the last used version you selected. <b>Recent Files</b> — double-click any file you opened recently to jump straight back in. Right-click to show it in Windows Explorer or remove it from the list.</p>
        """)

        self._add_section(layout, '3 — Launching Apps', """
        <p>Want to work on a specific shot, asset or light rig? Choose <b>Shot</b>, <b>Asset</b> or <b>Light Rig</b> at the top, pick the name from the list, then click the app you need.</p>
        <p>MazeHub opens the app with that context already set as the working area, with the correct frame range and colour settings. You can also choose <b>None</b> to just open an app without a context.</p>
        <p><b>Version Selection:</b> Apps with multiple versions (like Houdini, Nuke, Maya) show a small version button on the right of the launch button. Click it to choose which version to launch. Your last choice is remembered for next time.</p>
        <p>The file list below shows you what's already in that folder and lets you open a file directly.</p>
        """)

        self._add_section(layout, '4 — Shots & Assets', """
        <p>See all your shots and assets in a table with a preview image, progress and basic info. Click a row to see the files inside that shot/asset.</p>
        <p><b>New Shot / New Asset</b> — give it a name, frame range and description. MazeHub creates all the folders you need.<br>
        <b>Edit</b> — change the name or frame settings.<br>
        <b>Right-click</b> a shot/asset to set a thumbnail image (you can pick a PNG, JPG or an EXR render) or to open its folder in Windows Explorer.<br>
        Double-click a file below to open it in the right app.</p>
        """)

        self._add_section(layout, '5 — Light Rigs', """
        <p>Manage your HDRI lighting setups. Each light rig can store an HDRI, photogrammetry, USD scene, Nuke script and Houdini scene.</p>
        <p><b>New Light Rig</b> — create a new light rig with name, date, time of day and description. Browse for files to associate with it.<br>
        <b>Edit</b> — modify an existing light rig's settings and files.<br>
        Click a row to see the files in that light rig's folder structure.</p>
        <p><b>Using as Context:</b> When launching apps, you can select "Light Rig" as the context type. This sets the app's working directory to the light rig folder and exposes light rig file paths as environment variables.</p>
        """)

        self._add_section(layout, '6 — Production Tracking', """
        <p>Keep track of where everything is. There are two tabs: <b>Shots</b> and <b>Assets</b>.</p>
        <p>Each column is a task - for shots that's things like Animation, Lighting, Compositing; for assets it's Modelling, Texturing, Lookdev, etc. Colours show the state: red = Not started, amber = Work in progress, blue = Pending review, green = Finished, grey = Not applicable.</p>
        <p><b>To update:</b> right-click a task cell and pick a new status. The progress bars at the top update automatically.</p>
        """)

        self._add_section(layout, '7 — Rendering', """
        <p>Render your USD scenes without opening Houdini.</p>
        <p><b>How to:</b> pick a Shot, pick the USD file, choose a version (it suggests the next one), select the Houdini version (22.0 or 21.0), choose Karma XPU or CPU, tick the passes you need, set the frame range and press <b>Render Selected Passes</b>.</p>
        <p>You'll see progress for each frame and pass, with time estimates. You can pause or cancel at any time.</p>
        """)

        self._add_section(layout, '8 — Preview', """
        <p>Want to check a render? Pick a shot and MazeHub finds all the image sequences and videos for you.</p>
        <p>They're grouped by app, name and version. Double-click or press <b>Open in MPlay</b> to view them. Right-click to show the files in Windows Explorer.</p>
        """)

        self._add_section(layout, '9 — Environment Info', """
        <p>This page is just for reference. It shows the paths and shot settings MazeHub sets up for your apps (like where to find files and what frame range you're on). You don't need to change anything here - it's there if you need to check what MazeHub is doing behind the scenes.</p>
        """)

        self._add_section(layout, '10 — Settings', """
        <p><b>Where is the Husk renderer?</b> Usually found automatically. If not, use Browse or Auto-Detect.</p>
        <p><b>YouTube Screensaver:</b> paste a YouTube link for the Home page button.</p>
        <p><b>Teams Notifications:</b> paste your Teams webhook links for<br>
        &bull; <b>Render</b> — get notified when renders finish<br>
        &bull; <b>Dailies</b> — share playblasts/flipbooks<br>
        &bull; <b>Production</b> — get notified when someone updates a task<br>
        Leave empty if you don't need it. Click Save after pasting.</p>
        <p><b>Repair File Structure:</b> if folders are missing, click this to recreate them.</p>
        """)

        self._add_section(layout, '11 — Playblasts & Flipbooks (Houdini / Maya / Nuke)', """
        <p><b>Houdini:</b> open a shot, make a flipbook. It saves to the shot's flipbooks folder. Then in MPlay click <b>MAZE > Send to Dailies</b>, add a comment and it will be posted to Teams with your name.</p>
        <p><b>Maya:</b> open a shot, then <b>MAZE > Playblast</b>. Choose a comment and it renders a playblast and posts it for you.</p>
        <p><b>Nuke:</b> use <b>MAZE > Playblast</b> in the top menu or the Nodes toolbar to create a flipbook node, set the frame range and press <b>Create Flipbook</b>. It renders and posts to Teams. Make sure your script is saved first.</p>
        <p>The video needs to be in your project folder so Teams can link to it.</p>
        """)

        self._add_section(layout, '12 — Tips', """
        <p><b>No preview?</b> Try refreshing the page or check you picked the right shot.<br>
        <b>Can't post to Teams?</b> Make sure your scene/script is saved inside the project and that the Teams links are pasted in Settings.<br>
        <b>Houdini menu not showing?</b> Restart Houdini through MazeHub.<br>
        <b>Progress looks wrong?</b> Tasks set to "Not applicable" don't count - set them properly for the right percentage.<br>
        <b>Version not sticking?</b> Make sure you select the version from the dropdown button on the launch button, not from the context menu.</p>
        """)

        layout.addStretch()

    def _refresh(self):
        pass


class RenderThread(QThread):
    output = Signal(str)
    finished = Signal(int)
    progress = Signal(int, int)
    pass_changed = Signal(str)
    frame_started = Signal(int, int, int)
    frame_finished = Signal()
    bucket_progress = Signal(int)

    def __init__(self, commands, working_dir=None, env=None):
        super().__init__()
        self.commands = commands
        self.working_dir = working_dir
        self._env = env
        self._process = None
        self._cancel = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._paused = False

    def run(self):
        exit_code = 0
        total = len(self.commands)
        current_pass = ''
        pass_frame_count = 0
        pass_frames_done = 0
        for i, cmd in enumerate(self.commands):
            if self._cancel:
                self.output.emit('[cancelled]')
                break
            self._pause_event.wait()
            if self._cancel:
                self.output.emit('[cancelled]')
                break
            pass_name = ''
            frame_num = 0
            try:
                idx = cmd.index('--pass')
                pass_name = cmd[idx + 1]
            except (ValueError, IndexError):
                pass
            try:
                idx = cmd.index('-f')
                frame_num = int(cmd[idx + 1])
            except (ValueError, IndexError):
                pass
            if pass_name != current_pass:
                current_pass = pass_name
                pass_frame_count = sum(
                    1 for c in self.commands
                    if c[cmd.index('--pass') + 1] == pass_name
                ) if '--pass' in cmd else 0
                pass_frames_done = 0
            self.pass_changed.emit(pass_name)
            pass_frames_done += 1
            self.frame_started.emit(frame_num, pass_frame_count, pass_frames_done)
            self.output.emit(f'[rendering pass {i + 1}/{total}: {pass_name} frame {frame_num}]')
            self.output.emit(f'  cmd: {" ".join(cmd)}')
            try:
                cmd_env = os.environ.copy()
                if self._env:
                    cmd_env.update(self._env)
                if pass_name:
                    cmd_env['RENDERPASS'] = pass_name
                creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.working_dir,
                    env=cmd_env,
                    creationflags=creation_flags,
                )
                for line in self._process.stdout:
                    if self._cancel:
                        self._process.terminate()
                        break
                    self._pause_event.wait()
                    if self._cancel:
                        self._process.terminate()
                        break
                    stripped = line.rstrip('\n')
                    self.output.emit(stripped)
                    if 'ALF_PROGRESS' in stripped:
                        m = re.search(r'ALF_PROGRESS\s+(\d+)', stripped)
                        if m:
                            self.bucket_progress.emit(int(m.group(1)))
                self._process.wait()
                self.frame_finished.emit()
                code = self._process.returncode
                if code != 0:
                    exit_code = code
                    self.output.emit(f'[warning: husk exited with code {code}]')
                self._process = None
            except Exception as e:
                self.frame_finished.emit()
                self.output.emit(f'[error: {e}]')
                exit_code = 1
            self.progress.emit(i + 1, total)
        self.finished.emit(exit_code)

    def cancel(self):
        self._cancel = True
        self._pause_event.set()
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass

    def pause(self):
        self._paused = True
        self._pause_event.clear()

    def resume(self):
        self._paused = False
        self._pause_event.set()

    @property
    def is_paused(self):
        return self._paused


class RenderProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Rendering')
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._render_start = 0
        self._frame_start = 0
        self._current_pass = ''
        self._pass_times = {}
        self._frames_in_pass = 0
        self._frames_done = 0
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.shot_label = QLabel('Shot: —')
        shot_font = QFont()
        shot_font.setBold(True)
        self.shot_label.setFont(shot_font)
        layout.addWidget(self.shot_label)

        self.pass_label = QLabel('Pass: —')
        layout.addWidget(self.pass_label)

        self.frame_label = QLabel('Frame: —')
        layout.addWidget(self.frame_label)

        frame_progress_group = QGroupBox('Frame Progress')
        frame_progress_layout = QVBoxLayout(frame_progress_group)
        self.bucket_progress = QProgressBar()
        self.bucket_progress.setTextVisible(True)
        self.bucket_progress.setFormat('%p%')
        self.bucket_progress.setMaximum(100)
        frame_progress_layout.addWidget(self.bucket_progress)
        layout.addWidget(frame_progress_group)

        info_group = QGroupBox('Timing')
        self.info_layout = QGridLayout(info_group)

        self.info_layout.addWidget(QLabel('Total time:'), 0, 0)
        self.uptime_label = QLabel('0:00:00')
        self.info_layout.addWidget(self.uptime_label, 0, 1)

        self.info_layout.addWidget(QLabel('Frame time:'), 1, 0)
        self.frame_time_label = QLabel('—')
        self.info_layout.addWidget(self.frame_time_label, 1, 1)

        self._avg_row = 2
        self._avg_labels = {}

        layout.addWidget(info_group)

        total_group = QGroupBox('Total Job')
        total_layout = QVBoxLayout(total_group)
        self.total_progress = QProgressBar()
        self.total_progress.setTextVisible(True)
        self.total_progress.setFormat('%v / %m')
        total_layout.addWidget(self.total_progress)
        layout.addWidget(total_group)

        btn_row = QHBoxLayout()
        self.pause_btn = QPushButton('Pause')
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self.pause_btn)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(self.cancel_btn)
        self.yt_screensaver_btn = QPushButton('YT Screensaver')
        self.yt_screensaver_btn.setCursor(Qt.PointingHandCursor)
        self.yt_screensaver_btn.clicked.connect(self._open_yt_screensaver)
        btn_row.addWidget(self.yt_screensaver_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.close_btn = QPushButton('Close')
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setVisible(False)
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

    def start_render(self):
        self._render_start = time.monotonic()
        self._clock_timer.start()
        self._tick_clock()

    def set_shot(self, name):
        self.shot_label.setText(f'Shot: {name}')

    def set_pass(self, name):
        self._current_pass = name.split('/')[-1]
        self.pass_label.setText(f'Pass: {self._current_pass}')

    def init_passes(self, passes):
        self._pass_times = {p.split('/')[-1]: [] for p in passes}
        self._update_avg_pass()

    def start_frame(self, frame_num=0, frames_in_pass=0, frames_done=0):
        self._frame_start = time.monotonic()
        self._frames_in_pass = frames_in_pass
        self._frames_done = frames_done
        self.bucket_progress.setValue(0)
        if frames_in_pass:
            self.frame_label.setText(f'Frame: {frame_num} ({frames_done} of {frames_in_pass})')
        else:
            self.frame_label.setText(f'Frame: {frame_num}')

    def set_bucket_progress(self, percent):
        self.bucket_progress.setValue(min(percent, 100))

    def stop_frame(self):
        if self._frame_start:
            elapsed = time.monotonic() - self._frame_start
            self.frame_time_label.setText(self._format_duration(elapsed))
            if self._current_pass:
                self._pass_times.setdefault(self._current_pass, []).append(elapsed)
            self._update_avg_pass()
            self._frame_start = 0

    def _update_avg_pass(self):
        if not self._pass_times:
            return
        for pass_name, times in self._pass_times.items():
            if pass_name not in self._avg_labels:
                lbl_name = QLabel(f'{pass_name}:')
                lbl_name.setObjectName('hint')
                lbl_time = QLabel('-:--:--')
                lbl_time.setObjectName('hint')
                self.info_layout.addWidget(lbl_name, self._avg_row, 0)
                self.info_layout.addWidget(lbl_time, self._avg_row, 1)
                self._avg_labels[pass_name] = lbl_time
                self._avg_row += 1
            if times:
                avg = sum(times) / len(times)
                self._avg_labels[pass_name].setText(self._format_duration(avg))

    def set_total(self, current, total):
        self.total_progress.setMaximum(total)
        self.total_progress.setValue(current)

    def _tick_clock(self):
        if self._render_start:
            elapsed = time.monotonic() - self._render_start
            self.uptime_label.setText(self._format_duration(elapsed))
        if self._frame_start:
            elapsed = time.monotonic() - self._frame_start
            self.frame_time_label.setText(self._format_duration(elapsed))

    def _format_duration(self, seconds):
        h = int(seconds) // 3600
        m = (int(seconds) % 3600) // 60
        s = int(seconds) % 60
        return f'{h}:{m:02d}:{s:02d}'

    def _toggle_pause(self):
        thread = self._render_thread
        if not thread:
            return
        if thread.is_paused:
            thread.resume()
            self.pause_btn.setText('Pause')
        else:
            thread.pause()
            self.pause_btn.setText('Resume')

    def _open_yt_screensaver(self):
        from settings import get_setting
        url = get_setting('yt_screensaver_url', '')
        if url:
            webbrowser.open(url)

    def set_render_thread(self, thread):
        self._render_thread = thread

    def finish_render(self):
        self._clock_timer.stop()
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.close_btn.setVisible(True)


class RenderPage(QWidget):
    def __init__(self, project_root, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.pipeline_dir = pipeline_dir
        self._render_thread = None
        self._render_dialog = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        title = QLabel('Render')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh_all)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        layout.addSpacing(8)

        shot_row = QHBoxLayout()
        shot_row.addWidget(QLabel('Shot:'))
        self.shot_combo = QComboBox()
        self.shot_combo.setMinimumWidth(260)
        self.shot_combo.currentTextChanged.connect(self._on_shot_changed)
        shot_row.addWidget(self.shot_combo, 1)
        layout.addLayout(shot_row)

        usd_row = QHBoxLayout()
        usd_row.addWidget(QLabel('USD File:'))
        self.usd_combo = QComboBox()
        self.usd_combo.setMinimumWidth(260)
        self.usd_combo.currentTextChanged.connect(self._on_usd_changed)
        usd_row.addWidget(self.usd_combo, 1)
        layout.addLayout(usd_row)

        version_row = QHBoxLayout()
        version_row.addWidget(QLabel('Version:'))
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(260)
        version_row.addWidget(self.version_combo, 1)
        version_row.addStretch()
        layout.addLayout(version_row)

        houdini_version_row = QHBoxLayout()
        houdini_version_row.addWidget(QLabel('Houdini Version:'))
        self.houdini_version_combo = QComboBox()
        self.houdini_version_combo.setMinimumWidth(260)
        self.houdini_version_combo.addItems(['22.0', '21.0'])
        houdini_version_row.addWidget(self.houdini_version_combo, 1)
        houdini_version_row.addStretch()
        layout.addLayout(houdini_version_row)

        render_engine_row = QHBoxLayout()
        render_engine_row.addWidget(QLabel('Render Engine:'))
        self.render_engine_combo = QComboBox()
        self.render_engine_combo.setMinimumWidth(260)
        self.render_engine_combo.addItem('Karma XPU', 'xpu')
        self.render_engine_combo.addItem('Karma CPU', 'cpu')
        render_engine_row.addWidget(self.render_engine_combo, 1)
        render_engine_row.addStretch()
        layout.addLayout(render_engine_row)

        layout.addSpacing(8)

        passes_group = QGroupBox('Render Passes')
        passes_layout = QVBoxLayout(passes_group)

        passes_toolbar = QHBoxLayout()
        self.select_all_btn = QPushButton('Select All')
        self.select_all_btn.setMinimumHeight(32)
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.clicked.connect(self._select_all_passes)
        passes_toolbar.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton('Deselect All')
        self.deselect_all_btn.setMinimumHeight(32)
        self.deselect_all_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_btn.clicked.connect(self._deselect_all_passes)
        passes_toolbar.addWidget(self.deselect_all_btn)
        passes_toolbar.addStretch()
        passes_layout.addLayout(passes_toolbar)

        self.passes_container = QWidget()
        self.passes_layout = QVBoxLayout(self.passes_container)
        self.passes_layout.setAlignment(Qt.AlignTop)
        passes_layout.addWidget(self.passes_container)

        self.no_passes_label = QLabel('No passes found. Select a USD file to discover passes.')
        self.no_passes_label.setObjectName('hint')
        passes_layout.addWidget(self.no_passes_label)

        layout.addWidget(passes_group)

        layout.addSpacing(8)

        frame_group = QGroupBox('Frame Range')
        frame_layout = QHBoxLayout(frame_group)

        frame_layout.addWidget(QLabel('Start:'))
        self.start_frame_spin = QSpinBox()
        self.start_frame_spin.setRange(0, 999999)
        self.start_frame_spin.setValue(1001)
        frame_layout.addWidget(self.start_frame_spin)

        frame_layout.addWidget(QLabel('End:'))
        self.end_frame_spin = QSpinBox()
        self.end_frame_spin.setRange(0, 999999)
        self.end_frame_spin.setValue(1240)
        frame_layout.addWidget(self.end_frame_spin)

        frame_layout.addWidget(QLabel('Interval:'))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 9999)
        self.interval_spin.setValue(1)
        self.interval_spin.setToolTip('Render every Nth frame (1 = every frame)')
        frame_layout.addWidget(self.interval_spin)

        frame_layout.addStretch()
        layout.addWidget(frame_group)

        layout.addSpacing(8)

        btn_row = QHBoxLayout()
        self.render_btn = QPushButton('Render Selected Passes')
        self.render_btn.setMinimumHeight(36)
        self.render_btn.setCursor(Qt.PointingHandCursor)
        self.render_btn.clicked.connect(self._start_render)
        btn_row.addWidget(self.render_btn)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_render)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addSpacing(8)

        log_group = QGroupBox('Output Log')
        log_layout = QVBoxLayout(log_group)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setObjectName('renderLog')
        self.log_output.setMinimumHeight(150)
        log_layout.addWidget(self.log_output)
        self.clear_log_btn = QPushButton('Clear Log')
        self.clear_log_btn.setCursor(Qt.PointingHandCursor)
        self.clear_log_btn.clicked.connect(self.log_output.clear)
        log_layout.addWidget(self.clear_log_btn)
        layout.addWidget(log_group)

        layout.addStretch()

        scroll.setWidget(container)
        self._refresh_shots()

    def _refresh_all(self):
        self._refresh_shots()
        self._refresh_usd_files()

    def _refresh_shots(self):
        self.shot_combo.blockSignals(True)
        self.shot_combo.clear()
        seq_dir = self.project_root / 'sequence'
        if seq_dir.exists():
            shots = sorted(
                d.name for d in seq_dir.iterdir()
                if d.is_dir() and not d.name.startswith('_')
            )
            self.shot_combo.addItems(shots)
        self.shot_combo.setCurrentIndex(-1)
        self.shot_combo.blockSignals(False)
        self._on_shot_changed('')

    def _on_shot_changed(self, shot_name):
        self.usd_combo.blockSignals(True)
        self.usd_combo.clear()
        if shot_name:
            shot_path = self.project_root / 'sequence' / shot_name
            meta = read_shot_meta(shot_path)
            fr = meta.get('frame_range', '')
            if fr and '-' in fr:
                parts = fr.split('-')
                try:
                    self.start_frame_spin.setValue(int(parts[0]))
                    self.end_frame_spin.setValue(int(parts[1]))
                except ValueError:
                    pass
            usd_files = discover_usd_files(shot_path)
            self.usd_combo.addItems([f.name for f in usd_files])
        self.usd_combo.setCurrentIndex(-1)
        self.usd_combo.blockSignals(False)
        self._refresh_versions()
        self._on_usd_changed('')

    def _refresh_versions(self):
        self.version_combo.clear()
        shot_name = self.shot_combo.currentText()
        if not shot_name:
            return
        render_base = self.project_root / 'sequence' / shot_name / 'houdini' / 'render'
        versions = []
        if render_base.exists():
            for d in render_base.iterdir():
                if d.is_dir() and d.name.startswith(f'{shot_name}_v'):
                    try:
                        v = int(d.name.split('_v')[1])
                        versions.append(v)
                    except (ValueError, IndexError):
                        pass
        versions.sort()
        next_version = (versions[-1] + 1) if versions else 1
        for v in versions:
            self.version_combo.addItem(f'v{v:03d}', v)
        self.version_combo.addItem(f'v{next_version:03d} (new)', next_version)
        self.version_combo.setCurrentIndex(-1)

    def _refresh_usd_files(self):
        self._on_shot_changed(self.shot_combo.currentText())

    def _on_usd_changed(self, usd_name):
        self._refresh_passes()

    def _clear_passes(self):
        while self.passes_layout.count():
            item = self.passes_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.no_passes_label.setVisible(True)

    def _refresh_passes(self):
        self._clear_passes()
        usd_name = self.usd_combo.currentText()
        shot_name = self.shot_combo.currentText()
        if not shot_name or not usd_name:
            return
        shot_path = self.project_root / 'sequence' / shot_name
        usd_file = shot_path / 'houdini' / 'USD' / usd_name

        from settings import find_husk
        husk_path = find_husk()
        if not husk_path:
            self.log_output.append('[info] husk not found — configure in Settings')
            return

        houdini_version = self.houdini_version_combo.currentText()
        if houdini_version == '22.0':
            husk_candidates = [
                Path(r'C:\Program Files\Side Effects Software\Houdini 22.0.416\bin\husk.exe'),
            ]
        else:
            husk_candidates = [
                Path(r'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\husk.exe'),
            ]
        for candidate in husk_candidates:
            if candidate.exists():
                husk_path = str(candidate)
                break

        self.log_output.append(f'[info] Discovering passes: {husk_path} --list-passes {usd_file.name}')
        passes = discover_husk_passes(husk_path, usd_file)
        if not passes:
            self.log_output.append('[info] No passes found')
            self.no_passes_label.setVisible(True)
            return
        self.log_output.append(f'[info] Found {len(passes)} passes: {", ".join(passes)}')
        self.no_passes_label.setVisible(False)
        for p in passes:
            cb = QCheckBox(p)
            cb.setChecked(True)
            self.passes_layout.addWidget(cb)

    def _get_selected_passes(self):
        passes = []
        for i in range(self.passes_layout.count()):
            item = self.passes_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                if item.widget().isChecked():
                    passes.append(item.widget().text())
        return passes

    def _select_all_passes(self):
        for i in range(self.passes_layout.count()):
            item = self.passes_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                item.widget().setChecked(True)

    def _deselect_all_passes(self):
        for i in range(self.passes_layout.count()):
            item = self.passes_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                item.widget().setChecked(False)

    def _start_render(self):
        from settings import find_husk

        shot_name = self.shot_combo.currentText()
        usd_name = self.usd_combo.currentText()
        if not shot_name or not usd_name:
            self.log_output.append('[error] Select a shot and USD file first')
            self._status('Select a shot and USD file first', False)
            return

        passes = self._get_selected_passes()
        if not passes:
            self.log_output.append('[error] Select at least one render pass')
            self._status('Select at least one render pass', False)
            return

        houdini_version = self.houdini_version_combo.currentText()
        husk_path = find_husk()
        if not husk_path:
            self.log_output.append('[error] husk binary not found — configure in Settings')
            self._status('husk binary not found — configure in Settings', False)
            return

        if houdini_version == '22.0':
            husk_candidates = [
                Path(r'C:\Program Files\Side Effects Software\Houdini 22.0.416\bin\husk.exe'),
            ]
        else:
            husk_candidates = [
                Path(r'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\husk.exe'),
            ]
        for candidate in husk_candidates:
            if candidate.exists():
                husk_path = str(candidate)
                break

        shot_path = self.project_root / 'sequence' / shot_name
        usd_file = shot_path / 'houdini' / 'USD' / usd_name
        if not usd_file.exists():
            self.log_output.append(f'[error] USD file not found: {usd_file}')
            self._status(f'USD file not found: {usd_file}', False)
            return

        start = self.start_frame_spin.value()
        end = self.end_frame_spin.value()
        interval = self.interval_spin.value()
        if start > end:
            self.log_output.append('[error] Start frame must be <= end frame')
            self._status('Start frame must be <= end frame', False)
            return

        commands = []
        render_base = shot_path / 'houdini' / 'render'
        version = self.version_combo.currentData()
        render_engine = self.render_engine_combo.currentData()
        version_dir_name = f'{shot_name}_v{version:03d}'
        frames = list(range(start, end + 1, max(interval, 1)))
        for p in passes:
            pass_safe = p.split('/')[-1]
            out_dir = render_base / version_dir_name / pass_safe
            out_dir.mkdir(parents=True, exist_ok=True)
            for frame in frames:
                out_file = out_dir / f'{shot_name}_{pass_safe}_v{version:03d}_{frame:04d}.exr'
                cmd = [
                    husk_path,
                    '--engine', render_engine,
                    '--pass', p,
                    '-f', str(frame),
                    '-n', '1',
                    '-o', str(out_file),
                    '--make-output-path',
                    '-V', '2a',
                    str(usd_file),
                ]
                commands.append(cmd)

        self.log_output.clear()
        self.log_output.append(f'Rendering: {usd_name}')
        self.log_output.append(f'Passes: {", ".join(passes)}')
        self.log_output.append(f'Frames: {start}-{end} (interval {interval})')
        self.log_output.append(f'Engine: Karma {render_engine.upper()}')
        self.log_output.append(f'Commands: {len(commands)}')
        self.log_output.append('')

        self.render_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self._render_meta = {
            'shot': shot_name,
            'usd_file': usd_name,
            'passes': passes,
            'start_frame': start,
            'end_frame': end,
            'interval': interval,
            'version': version,
            'render_engine': render_engine,
            'start_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': '',
        }

        render_env = {
            'MAZE_CONTEXT_NAME': shot_name,
            'MAZE_CONTEXT_TYPE': 'shot',
            'JOB': str(shot_path),
        }

        self._render_thread = RenderThread(commands, working_dir=str(shot_path), env=render_env)

        self._render_dialog = RenderProgressDialog(self.window())
        self._render_dialog.set_render_thread(self._render_thread)
        self._render_dialog.cancel_btn.clicked.connect(self._cancel_render)
        self._render_dialog.set_total(0, len(commands))
        self._render_dialog.set_shot(shot_name)
        self._render_dialog.init_passes(passes)

        self._render_thread.output.connect(self._on_render_output)
        self._render_thread.finished.connect(self._on_render_finished)
        self._render_thread.progress.connect(self._render_dialog.set_total)
        self._render_thread.pass_changed.connect(self._render_dialog.set_pass)
        self._render_thread.frame_started.connect(self._render_dialog.start_frame)
        self._render_thread.frame_finished.connect(self._render_dialog.stop_frame)
        self._render_thread.bucket_progress.connect(self._render_dialog.set_bucket_progress)
        self._render_thread.start()

        self._render_dialog.open()
        self._render_dialog.start_render()

    def _cancel_render(self):
        if self._render_thread:
            if hasattr(self, '_render_meta'):
                self._render_meta['cancelled'] = True
            self._render_thread.cancel()

    def _on_render_output(self, line):
        self.log_output.append(line)
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_render_finished(self, exit_code):
        self.render_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        render_time = ''
        if self._render_dialog:
            if self._render_dialog._render_start:
                elapsed = time.monotonic() - self._render_dialog._render_start
                h = int(elapsed) // 3600
                m = (int(elapsed) % 3600) // 60
                s = int(elapsed) % 60
                render_time = f'{h}:{m:02d}:{s:02d}'
            self._render_dialog.finish_render()

        if exit_code == 0:
            self.log_output.append('')
            self.log_output.append('[render complete]')
            self._status('Render complete', True)
        else:
            self.log_output.append('')
            self.log_output.append(f'[render finished with errors (exit code {exit_code})]')
            self._status(f'Render finished with errors', False)

        meta = getattr(self, '_render_meta', None)
        if meta:
            meta['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            first_frame_path = ''
            if meta['passes']:
                shot_path = self.project_root / 'sequence' / meta['shot']
                pass_name = meta['passes'][0].split('/')[-1]
                version_dir = f'{meta["shot"]}_v{meta["version"]:03d}'
                first_frame = f'{meta["shot"]}_{pass_name}_v{meta["version"]:03d}_{meta["start_frame"]:04d}.exr'
                first_frame_path = str(shot_path / 'houdini' / 'render' / version_dir / pass_name / first_frame)
            from settings import get_setting
            from pipeline_app import send_teams_notification
            webhook_url = get_setting('teams_webhook_url', '')
            if webhook_url:
                send_teams_notification(
                    webhook_url=webhook_url,
                    shot=meta['shot'],
                    usd_file=meta['usd_file'],
                    passes=meta['passes'],
                    start_frame=meta['start_frame'],
                    end_frame=meta['end_frame'],
                    interval=meta['interval'],
                    version=meta['version'],
                    render_engine=meta['render_engine'],
                    exit_code=exit_code,
                    render_time=render_time,
                    project_root=self.project_root,
                    cancelled=meta.get('cancelled', False),
                    start_time=meta.get('start_time', ''),
                    end_time=meta.get('end_time', ''),
                    first_frame_path=first_frame_path,
                )

    def _status(self, msg, ok=True):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)

    def _refresh(self):
        self._refresh_shots()


class SettingsPage(QWidget):
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel('Settings')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addSpacing(16)

        husk_group = QGroupBox('Husk Render Binary')
        husk_layout = QVBoxLayout(husk_group)

        husk_layout.addWidget(QLabel(
            'Path to the husk executable for headless USD rendering.'
        ))

        husk_path_row = QHBoxLayout()
        self.husk_path_input = QLineEdit()
        self.husk_path_input.setPlaceholderText('Auto-detected from Houdini install...')
        husk_path_row.addWidget(self.husk_path_input, 1)
        self.husk_browse_btn = QPushButton('Browse')
        self.husk_browse_btn.setCursor(Qt.PointingHandCursor)
        self.husk_browse_btn.clicked.connect(self._browse_husk)
        husk_path_row.addWidget(self.husk_browse_btn)
        husk_layout.addLayout(husk_path_row)

        husk_btn_row = QHBoxLayout()
        self.husk_save_btn = QPushButton('Save')
        self.husk_save_btn.setCursor(Qt.PointingHandCursor)
        self.husk_save_btn.clicked.connect(self._save_husk_path)
        husk_btn_row.addWidget(self.husk_save_btn)
        self.husk_detect_btn = QPushButton('Auto-Detect')
        self.husk_detect_btn.setCursor(Qt.PointingHandCursor)
        self.husk_detect_btn.clicked.connect(self._detect_husk)
        husk_btn_row.addWidget(self.husk_detect_btn)
        husk_btn_row.addStretch()
        husk_layout.addLayout(husk_btn_row)

        self.husk_status = QLabel('')
        self.husk_status.setWordWrap(True)
        self.husk_status.setObjectName('hint')
        husk_layout.addWidget(self.husk_status)

        husk_layout.addStretch()
        layout.addWidget(husk_group)

        yt_group = QGroupBox('YouTube Screensaver')
        yt_layout = QVBoxLayout(yt_group)

        yt_layout.addWidget(QLabel(
            'URL to open when the YT Screensaver button is clicked.'
        ))

        yt_url_row = QHBoxLayout()
        self.yt_url_input = QLineEdit()
        self.yt_url_input.setPlaceholderText('https://youtube.com/...')
        yt_url_row.addWidget(self.yt_url_input, 1)
        self.yt_save_btn = QPushButton('Save')
        self.yt_save_btn.setCursor(Qt.PointingHandCursor)
        self.yt_save_btn.clicked.connect(self._save_yt_url)
        yt_url_row.addWidget(self.yt_save_btn)
        yt_layout.addLayout(yt_url_row)

        self.yt_status = QLabel('')
        self.yt_status.setWordWrap(True)
        self.yt_status.setObjectName('hint')
        yt_layout.addWidget(self.yt_status)

        yt_layout.addStretch()
        layout.addWidget(yt_group)

        teams_group = QGroupBox('Teams Notifications')
        teams_layout = QVBoxLayout(teams_group)
        teams_layout.setSpacing(16)

        # — Render Notifications —
        render_label = QLabel('Render Channel')
        rf = QFont()
        rf.setBold(True)
        render_label.setFont(rf)
        teams_layout.addWidget(render_label)
        teams_layout.addWidget(QLabel(
            'Notifies when a render completes or fails.'
        ))
        teams_url_row = QHBoxLayout()
        self.teams_url_input = QLineEdit()
        self.teams_url_input.setPlaceholderText('https://outlook.office.com/webhook/...')
        teams_url_row.addWidget(self.teams_url_input, 1)
        self.teams_save_btn = QPushButton('Save')
        self.teams_save_btn.setCursor(Qt.PointingHandCursor)
        self.teams_save_btn.clicked.connect(self._save_teams_url)
        teams_url_row.addWidget(self.teams_save_btn)
        teams_layout.addLayout(teams_url_row)
        self.teams_status = QLabel('')
        self.teams_status.setWordWrap(True)
        self.teams_status.setObjectName('hint')
        teams_layout.addWidget(self.teams_status)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet('color: #444;')
        teams_layout.addWidget(sep1)

        # — Dailies Channel —
        dailies_label = QLabel('Dailies Channel')
        df = QFont()
        df.setBold(True)
        dailies_label.setFont(df)
        teams_layout.addWidget(dailies_label)
        teams_layout.addWidget(QLabel(
            'Used by Houdini playblast tools.'
        ))
        dailies_url_row = QHBoxLayout()
        self.dailies_url_input = QLineEdit()
        self.dailies_url_input.setPlaceholderText('https://outlook.office.com/webhook/...')
        dailies_url_row.addWidget(self.dailies_url_input, 1)
        self.dailies_save_btn = QPushButton('Save')
        self.dailies_save_btn.setCursor(Qt.PointingHandCursor)
        self.dailies_save_btn.clicked.connect(self._save_dailies_url)
        dailies_url_row.addWidget(self.dailies_save_btn)
        teams_layout.addLayout(dailies_url_row)
        self.dailies_status = QLabel('')
        self.dailies_status.setWordWrap(True)
        self.dailies_status.setObjectName('hint')
        teams_layout.addWidget(self.dailies_status)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet('color: #444;')
        teams_layout.addWidget(sep2)

        # — Production Tracking Channel —
        prod_label = QLabel('Production Tracking Channel')
        pf = QFont()
        pf.setBold(True)
        prod_label.setFont(pf)
        teams_layout.addWidget(prod_label)
        teams_layout.addWidget(QLabel(
            'Notifies when a task status is changed in the Production tab.'
        ))
        production_url_row = QHBoxLayout()
        self.production_url_input = QLineEdit()
        self.production_url_input.setPlaceholderText('https://outlook.office.com/webhook/...')
        production_url_row.addWidget(self.production_url_input, 1)
        self.production_save_btn = QPushButton('Save')
        self.production_save_btn.setCursor(Qt.PointingHandCursor)
        self.production_save_btn.clicked.connect(self._save_production_url)
        production_url_row.addWidget(self.production_save_btn)
        teams_layout.addLayout(production_url_row)
        self.production_status = QLabel('')
        self.production_status.setWordWrap(True)
        self.production_status.setObjectName('hint')
        teams_layout.addWidget(self.production_status)

        layout.addWidget(teams_group)

        group = QGroupBox('File Structure')
        group_layout = QVBoxLayout(group)

        group_layout.addWidget(QLabel(
            'Check the project directory structure and create any missing folders.'
        ))

        self.repair_btn = QPushButton('Repair File Structure')
        self.repair_btn.setMinimumHeight(36)
        self.repair_btn.setCursor(Qt.PointingHandCursor)
        self.repair_btn.clicked.connect(self._repair)
        group_layout.addWidget(self.repair_btn)

        self.repair_result = QLabel('')
        self.repair_result.setWordWrap(True)
        self.repair_result.setObjectName('hint')
        group_layout.addWidget(self.repair_result)

        group_layout.addStretch()
        layout.addWidget(group)
        layout.addStretch()

        self._load_husk_path()
        self._load_yt_url()
        self._load_teams_url()
        self._load_dailies_url()
        self._load_production_url()

    def _load_husk_path(self):
        from settings import get_setting, find_husk
        configured = get_setting('husk_path')
        if configured:
            self.husk_path_input.setText(configured)
        detected = find_husk()
        if configured:
            if configured == detected:
                self.husk_status.setText(f'OK: {detected}')
                self.husk_status.setStyleSheet('color: #00c853;')
            else:
                self.husk_status.setText(f'Saved: {configured}\nAuto-detected: {detected}')
                self.husk_status.setStyleSheet('')
        elif detected:
            self.husk_path_input.setText(detected)
            self.husk_status.setText(f'Auto-detected: {detected}')
            self.husk_status.setStyleSheet('color: #00c853;')
        else:
            self.husk_status.setText('husk not found. Install Houdini or set the path manually.')
            self.husk_status.setStyleSheet('color: #ff6b6b;')

    def _browse_husk(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select husk Binary', '',
            'All Files (*)' if platform.system() != 'Windows' else 'husk (*.exe);;All Files (*)'
        )
        if path:
            self.husk_path_input.setText(path)

    def _detect_husk(self):
        from settings import find_husk
        detected = find_husk()
        if detected:
            self.husk_path_input.setText(detected)
            self.husk_status.setText(f'Auto-detected: {detected}')
            self.husk_status.setStyleSheet('color: #00c853;')
        else:
            self.husk_status.setText('Could not auto-detect husk. Check your Houdini installation or HFS environment variable.')
            self.husk_status.setStyleSheet('color: #ff6b6b;')

    def _save_husk_path(self):
        from settings import set_setting
        path = self.husk_path_input.text().strip()
        if path and not Path(path).exists():
            self.husk_status.setText(f'Warning: File not found at {path}')
            self.husk_status.setStyleSheet('color: #ffa726;')
            return
        set_setting('husk_path', path)
        self._load_husk_path()

    def _save_yt_url(self):
        from settings import set_setting
        url = self.yt_url_input.text().strip()
        set_setting('yt_screensaver_url', url)
        if url:
            self.yt_status.setText(f'Saved: {url}')
            self.yt_status.setStyleSheet('color: #00c853;')
        else:
            self.yt_status.setText('URL cleared.')
            self.yt_status.setStyleSheet('')

    def _load_yt_url(self):
        from settings import get_setting
        url = get_setting('yt_screensaver_url', '')
        self.yt_url_input.setText(url)
        if url:
            self.yt_status.setText(f'Current: {url}')
            self.yt_status.setStyleSheet('')
        else:
            self.yt_status.setText('No URL configured.')
            self.yt_status.setStyleSheet('color: #ffa726;')

    def _save_teams_url(self):
        from settings import set_setting
        url = self.teams_url_input.text().strip()
        set_setting('teams_webhook_url', url)
        if url:
            self.teams_status.setText(f'Saved: {url}')
            self.teams_status.setStyleSheet('color: #00c853;')
        else:
            self.teams_status.setText('URL cleared.')
            self.teams_status.setStyleSheet('')

    def _load_teams_url(self):
        from settings import get_setting
        url = get_setting('teams_webhook_url', '')
        self.teams_url_input.setText(url)
        if url:
            self.teams_status.setText('')
            self.teams_status.setStyleSheet('')
        else:
            self.teams_status.setText('No webhook URL configured.')
            self.teams_status.setStyleSheet('color: #ffa726;')

    def _save_dailies_url(self):
        from settings import set_setting
        url = self.dailies_url_input.text().strip()
        set_setting('dailies_webhook_url', url)
        if url:
            self.dailies_status.setText(f'Saved: {url}')
            self.dailies_status.setStyleSheet('color: #00c853;')
        else:
            self.dailies_status.setText('URL cleared.')
            self.dailies_status.setStyleSheet('')

    def _load_dailies_url(self):
        from settings import get_setting
        url = get_setting('dailies_webhook_url', '')
        self.dailies_url_input.setText(url)
        if url:
            self.dailies_status.setText('')
            self.dailies_status.setStyleSheet('')
        else:
            self.dailies_status.setText('No webhook URL configured.')
            self.dailies_status.setStyleSheet('color: #ffa726;')

    def _save_production_url(self):
        from settings import set_setting
        url = self.production_url_input.text().strip()
        set_setting('production_webhook_url', url)
        if url:
            self.production_status.setText(f'Saved: {url}')
            self.production_status.setStyleSheet('color: #00c853;')
        else:
            self.production_status.setText('URL cleared.')
            self.production_status.setStyleSheet('')

    def _load_production_url(self):
        from settings import get_setting
        url = get_setting('production_webhook_url', '')
        self.production_url_input.setText(url)
        if url:
            self.production_status.setText('')
            self.production_status.setStyleSheet('')
        else:
            self.production_status.setText('No webhook URL configured.')
            self.production_status.setStyleSheet('color: #ffa726;')

    def _repair(self):
        from make_folders import repair_project_structure
        self.repair_btn.setEnabled(False)
        self.repair_btn.setText('Repairing...')
        self.repair_result.setText('')
        QApplication.processEvents()
        try:
            missing = repair_project_structure(self.project_root)
            if missing:
                lines = '\n'.join(f'  - {p}' for p in missing[:20])
                extra = f' (+{len(missing) - 20} more)' if len(missing) > 20 else ''
                self.repair_result.setText(f'Created {len(missing)} missing folder(s):\n{lines}{extra}')
            else:
                self.repair_result.setText('All project directories exist — nothing to repair.')
        except Exception as e:
            self.repair_result.setText(f'Error: {e}')
        finally:
            self.repair_btn.setEnabled(True)
            self.repair_btn.setText('Repair File Structure')


class MainWindow(QMainWindow):
    def __init__(self, project_root, env_vars, apps_config, pipeline_dir):
        super().__init__()
        self.project_root = project_root
        self.env_vars = env_vars
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._build()

    def _build(self):
        self.setWindowTitle(f'MazeHub Pipeline - {self.project_root.name}')
        self.setMinimumSize(960, 640)
        self.resize(1100, 720)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setObjectName('sidebar')
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(4)

        logo_label = QLabel('MAZEHUB')
        logo_label.setAlignment(Qt.AlignCenter)
        logo_font = QFont()
        logo_font.setPointSize(14)
        logo_font.setBold(True)
        logo_label.setFont(logo_font)
        logo_label.setObjectName('logo')
        sidebar_layout.addWidget(logo_label)

        proj_label = QLabel(self.project_root.name)
        proj_label.setAlignment(Qt.AlignCenter)
        proj_label.setObjectName('projectName')
        sidebar_layout.addWidget(proj_label)

        sidebar_layout.addSpacing(16)

        self.sidebar_buttons = []
        self.pages = QStackedWidget()

        page_classes = [DashboardPage, LaunchAppsPage, ShotExplorerPage,
                        LightRigsPage, AssetExplorerPage, ProductionPage,
                        RenderPage, PreviewPage,
                        EnvVarsPage, SettingsPage, LogPage, HelpPage]
        page_args = [
            (self.project_root, self.env_vars, self.apps_config, self.pipeline_dir),
            (self.apps_config, self.pipeline_dir, self.project_root),
            (self.project_root, self.apps_config, self.pipeline_dir),
            (self.project_root, self.apps_config, self.pipeline_dir),
            (self.project_root, self.apps_config, self.pipeline_dir),
            (self.project_root, self.pipeline_dir),
            (self.project_root, self.pipeline_dir),
            (self.project_root, self.pipeline_dir),
            (self.env_vars,),
            (self.project_root,),
            (),
            (),
        ]

        SIDEBAR_RENDER_IDX = 7
        for i, (label, tooltip) in enumerate(SIDEBAR_ITEMS):
            if label == 'Help':
                sidebar_layout.addStretch()
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet('color: #444; margin: 4px 12px;')
                sidebar_layout.addWidget(sep)
            btn = SidebarButton(label, tooltip)
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            self.sidebar_buttons.append(btn)
            sidebar_layout.addWidget(btn)

            if i == SIDEBAR_RENDER_IDX:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet('color: #444; margin: 4px 12px;')
                sidebar_layout.addWidget(sep)

            page = page_classes[i](*page_args[i])
            self.pages.addWidget(page)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.pages, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f'Project Root: {self.project_root}')

        version_label = QLabel(f'v{APP_VERSION}')
        version_label.setStyleSheet('color: #888; padding-right: 8px;')
        self.status_bar.addPermanentWidget(version_label)

        self.sidebar_buttons[0].setChecked(True)

    def _switch_page(self, idx):
        self.pages.setCurrentIndex(idx)
        for i, btn in enumerate(self.sidebar_buttons):
            btn.setChecked(i == idx)
        page = self.pages.currentWidget()
        if hasattr(page, '_refresh'):
            page._refresh()

    def show_status(self, message, ok=True):
        if ok:
            self.status_bar.showMessage(message, 5000)
        else:
            self.status_bar.showMessage(f'ERROR: {message}', 8000)


def _load_styles(app, styles_dir):
    qss_path = Path(styles_dir) / 'styles.qss'
    if qss_path.exists():
        with open(qss_path) as f:
            app.setStyleSheet(f.read())
    else:
        fallback = '''
            QMainWindow { background-color: #1a1a2e; }
            QLabel { color: #e0e0e8; }
            QPushButton {
                background-color: #0f3460; color: #e0e0e8;
                border: none; border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #1a5276; }
        '''
        app.setStyleSheet(fallback)


def main():
    project_root = find_project_root()
    pipeline_dir = project_root / 'pipeline'
    app_dir = _app_dir()

    env_vars = setup_environment(project_root)
    apps_config = load_apps_config()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    app = QApplication(sys.argv)
    app.setFont(QFont('Segoe UI', 10))
    icon_path = os.path.join(app_dir, 'icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    _load_styles(app, app_dir)

    log_stream = get_log_stream()
    sys.stdout = log_stream
    sys.stderr = log_stream

    window = MainWindow(project_root, env_vars, apps_config, pipeline_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
