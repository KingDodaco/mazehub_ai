import os
import sys
import subprocess
import platform
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QStackedWidget, QTextEdit, QFrame,
    QHeaderView, QTreeWidget, QTreeWidgetItem, QStatusBar, QGroupBox,
    QFormLayout, QGridLayout, QScrollArea, QSplitter, QDialog, QTabWidget,
    QMenu, QCheckBox,
)

from pipeline_app import (
    find_project_root, setup_environment, load_apps_config,
    read_shot_meta, write_shot_meta, APP_FILE_EXTENSIONS,
    build_context_env, _app_dir,
)

from recent_files import add_recent_file, get_recent_files as load_recent_files, clear_recent_files


SIDEBAR_ITEMS = [
    ('Home', 'Dashboard with project info and quick launch'),
    ('Launch Apps', 'Launch VFX applications'),
    ('Shot Explorer', 'Browse existing shots and create new ones'),
    ('Asset Explorer', 'Browse existing assets and create new ones'),
    ('Env Vars', 'View environment variables'),
    ('Settings', 'Repair file structure and configure options'),
]


class SidebarButton(QPushButton):
    def __init__(self, text, tooltip):
        super().__init__(text)
        self.setToolTip(tooltip)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)


class AppLauncherThread(QThread):
    finished = Signal(str, bool)

    def __init__(self, config, pipeline_dir, project_root=None, context=None):
        super().__init__()
        self.config = config
        self.pipeline_dir = pipeline_dir
        self.project_root = project_root
        self.context = context

    def run(self):
        try:
            exec_path = self.pipeline_dir / self.config['subdir'] / self.config['executable']
            if not exec_path.exists():
                self.finished.emit(f'Executable not found: {exec_path}', False)
                return

            launch_env = os.environ.copy()
            if self.context and self.project_root:
                ctx = dict(self.context, app_name=self.config.get('_key', ''))
                ctx_env = build_context_env(ctx, self.project_root)
                launch_env.update(ctx_env)

            if platform.system() == 'Windows':
                subprocess.Popen([str(exec_path)], shell=True, env=launch_env)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(exec_path)], env=launch_env)
            else:
                subprocess.Popen([str(exec_path)], shell=True, env=launch_env)
            self.finished.emit(f'Launched {self.config["display_name"]}', True)
        except Exception as e:
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
        try:
            exec_path = self.pipeline_dir / self.config['subdir'] / self.config['executable']

            launch_env = os.environ.copy()
            if self.context and self.project_root:
                ctx = dict(self.context, app_name=self.config.get('_key', ''))
                ctx_env = build_context_env(ctx, self.project_root)
                launch_env.update(ctx_env)

            if platform.system() == 'Windows':
                subprocess.Popen([str(exec_path), str(self.file_path)], shell=True, env=launch_env)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(self.file_path)], env=launch_env)
            else:
                subprocess.Popen([str(exec_path), str(self.file_path)], shell=True, env=launch_env)
            self.finished.emit(f'Opened {self.file_path.name} with {self.config["display_name"]}', True)
        except Exception as e:
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
            display = cfg.get('display_name', app_name)
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
                if app_name == 'USD':
                    self._launch_usdview(fp)
                    ctx_type = self._current_context.get('type', '') if self._current_context else ''
                    ctx_name = self._current_context.get('name', '') if self._current_context else ''
                    ctx_cat = self._current_context.get('category', '') if self._current_context else ''
                    add_recent_file(fp, 'usdview', ctx_type, ctx_name, ctx_cat)
                    return
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
                add_recent_file(fp, cfg.get('display_name', app_name), ctx_type, ctx_name, ctx_cat)
                return

    def _launch_usdview(self, fp):
        import shutil
        usdview = shutil.which('usdview')
        if not usdview:
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status('usdview not found on PATH', False)
            return
        subprocess.Popen([usdview, str(fp)])

    def _result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


class ShotDialog(QDialog):
    def __init__(self, parent=None, shot_name='', frame_start='1001', frame_end='1240', frame_rate='24', description=''):
        super().__init__(parent)
        self.setWindowTitle('New Shot' if not shot_name else f'Edit Shot: {shot_name}')
        self.setMinimumWidth(500)
        self._result = None

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(shot_name)
        self.name_edit.setPlaceholderText('e.g. SH010')
        form.addRow('Shot Name:', self.name_edit)

        range_row = QHBoxLayout()
        self.fr_start = QLineEdit(str(frame_start))
        self.fr_start.setPlaceholderText('Start')
        range_row.addWidget(self.fr_start)
        range_row.addWidget(QLabel('—'))
        self.fr_end = QLineEdit(str(frame_end))
        self.fr_end.setPlaceholderText('End')
        range_row.addWidget(self.fr_end)
        form.addRow('Frame Range:', range_row)

        self.fps_edit = QLineEdit(str(frame_rate))
        self.fps_edit.setPlaceholderText('e.g. 24')
        form.addRow('Frame Rate:', self.fps_edit)

        self.desc_edit = QLineEdit(description)
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
        self._result = {
            'name': name,
            'frame_range': f'{start}-{end}',
            'frame_rate': fps,
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

        title = QLabel('Welcome to MazeHub Pipeline')
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel(f'Project: {self.project_root.name}')
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle.setFont(subtitle_font)
        layout.addWidget(subtitle)

        layout.addWidget(QLabel(f'Root: {self.project_root}'))
        layout.addSpacing(16)

        stats_layout = QHBoxLayout()
        seq_count = len(list((self.project_root / 'sequence').iterdir())) if (self.project_root / 'sequence').exists() else 0
        asset_count = 0
        asset_dir = self.project_root / 'asset'
        if asset_dir.exists():
            for cat_dir in asset_dir.iterdir():
                if cat_dir.is_dir():
                    asset_count += len([d for d in cat_dir.iterdir() if d.is_dir()])
        stats_layout.addWidget(self._stat_card('Shots', str(seq_count)))
        stats_layout.addWidget(self._stat_card('Assets', str(asset_count)))
        stats_layout.addWidget(self._stat_card('Apps', str(len(self.apps_config))))
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
        
        app_name = entry.get('app_name', '')
        cfg = self.apps_config.get(app_name)
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
            self._run_launch(cfg)

    def _run_launch(self, cfg):
        self.thread = AppLauncherThread(cfg, self.pipeline_dir)
        self.thread.finished.connect(lambda msg, ok: self._show_launch_result(msg, ok))
        self.thread.start()

    def _show_launch_result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


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

        title = QLabel('Launch Application')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addSpacing(8)

        ctx_group = QGroupBox('Context (optional)')
        ctx_layout = QVBoxLayout(ctx_group)

        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel('Context:'))
        self.ctx_combo = QComboBox()
        self.ctx_combo.addItems(['None', 'Shot', 'Asset'])
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

        if self.apps_config:
            row = 0
            col = 0
            for name, cfg in self.apps_config.items():
                cfg['_key'] = name
                launch_btn = QPushButton(cfg['display_name'])
                launch_btn.setMinimumHeight(48)
                launch_btn.setCursor(Qt.PointingHandCursor)
                launch_btn.setObjectName('appLaunchBtn')
                launch_btn.clicked.connect(lambda checked, c=cfg: self._launch(c))
                container_layout.addWidget(launch_btn, row, col)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1
        else:
            container_layout.addWidget(QLabel('No applications configured.'), 0, 0, 1, 2)

        container_layout.setRowStretch(row + 1, 1)
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
        if text == 'Asset':
            self._on_category_change(self.ctx_cat_combo.currentText())
        self._update_context()

    def _on_category_change(self, category):
        self.ctx_asset_combo.clear()
        asset_dir = self.project_root / 'asset' / category
        if asset_dir.exists():
            assets = sorted(d.name for d in asset_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
            self.ctx_asset_combo.addItems(assets)
        self._update_context()

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
        self.thread = AppLauncherThread(
            cfg, self.pipeline_dir,
            project_root=self.project_root, context=self._context,
        )
        self.thread.finished.connect(lambda msg, ok: self._result(msg, ok))
        self.thread.start()

    def _result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


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

        title = QLabel('Shot Explorer')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ['Shot', 'Path', 'Frame Range', 'Frame Rate', 'Description', 'Working Dirs']
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_change)
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
        dialog = ShotDialog(self)
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
        shot_name = self.table.item(row, 0).text()
        shot_path = self.project_root / 'sequence' / shot_name
        meta = read_shot_meta(shot_path)

        fr = meta.get('frame_range', '1001-1240')
        parts = fr.split('-')
        frame_start = parts[0] if parts else '1001'
        frame_end = parts[1] if len(parts) > 1 else parts[0]

        dialog = ShotDialog(
            self,
            shot_name=shot_name,
            frame_start=frame_start,
            frame_end=frame_end,
            frame_rate=meta.get('frame_rate', '24'),
            description=meta.get('description', ''),
        )
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()

        write_shot_meta(shot_path, {
            'frame_range': data['frame_range'],
            'frame_rate': data['frame_rate'],
            'description': data['description'],
        })
        self._refresh()
        self._status(f'Metadata updated: {shot_name}', True)

    def _on_selection_change(self):
        items = self.table.selectedItems()
        self.edit_btn.setEnabled(bool(items))
        if items:
            row = items[0].row()
            shot_name = self.table.item(row, 0).text()
            shot_path = self.project_root / 'sequence' / shot_name
            ctx = {'type': 'shot', 'name': shot_name, 'path': shot_path}
            self._file_panel.set_directory(shot_path, context=ctx)
            self.file_browser.setTitle(f'Files: {shot_name}')
            self.file_browser.setVisible(True)
        else:
            self._file_panel.clear()
            self.file_browser.setVisible(False)

    def _refresh(self):
        self.table.setRowCount(0)
        seq_dir = self.project_root / 'sequence'
        if not seq_dir.exists():
            return
        shots = sorted([d.name for d in seq_dir.iterdir() if d.is_dir() and not d.name.startswith('_')])
        self.table.setRowCount(len(shots))
        for i, name in enumerate(shots):
            shot_path = seq_dir / name
            meta = read_shot_meta(shot_path)
            working_count = sum(1 for d in shot_path.iterdir() if d.is_dir() and not d.name.startswith('_'))
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(str(shot_path.relative_to(self.project_root))))
            self.table.setItem(i, 2, QTableWidgetItem(meta['frame_range']))
            self.table.setItem(i, 3, QTableWidgetItem(meta['frame_rate']))
            self.table.setItem(i, 4, QTableWidgetItem(meta['description']))
            self.table.setItem(i, 5, QTableWidgetItem(f'{working_count} dirs'))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(self.table.columnWidth(1), 200))
        self.table.setColumnWidth(5, max(self.table.columnWidth(5), 200))
        self.table.horizontalHeader().setStretchLastSection(False)

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

        title = QLabel('Asset Explorer')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
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

        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        filter_row.addWidget(self.refresh_btn)
        toolbar.addLayout(filter_row)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['Asset', 'Category', 'Path', 'Working Dirs'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_change)
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
            asset_name = self.table.item(row, 0).text()
            cat = self.table.item(row, 1).text()
            asset_path = self.project_root / 'asset' / cat / asset_name
            ctx = {'type': 'asset', 'name': asset_name, 'path': asset_path, 'category': cat}
            self._file_panel.set_directory(asset_path, context=ctx)
            self.file_browser.setTitle(f'Files: {asset_name}')
            self.file_browser.setVisible(True)
        else:
            self._file_panel.clear()
            self.file_browser.setVisible(False)

    def _refresh(self):
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
                    working_count = sum(1 for d in asset.iterdir() if d.is_dir())
                    rows.append((asset.name, cat_dir.name, str(asset.relative_to(self.project_root)), f'{working_count} dirs'))
        self.table.setRowCount(len(rows))
        for i, (name, cat, path, count) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(cat))
            self.table.setItem(i, 2, QTableWidgetItem(path))
            self.table.setItem(i, 3, QTableWidgetItem(count))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(self.table.columnWidth(2), 300))

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


class SettingsPage(QWidget):
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel('Settings')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addSpacing(16)

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
                        AssetExplorerPage, EnvVarsPage, SettingsPage]
        page_args = [
            (self.project_root, self.env_vars, self.apps_config, self.pipeline_dir),
            (self.apps_config, self.pipeline_dir, self.project_root),
            (self.project_root, self.apps_config, self.pipeline_dir),
            (self.project_root, self.apps_config, self.pipeline_dir),
            (self.env_vars,),
            (self.project_root,),
        ]

        for i, (label, tooltip) in enumerate(SIDEBAR_ITEMS):
            btn = SidebarButton(label, tooltip)
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            self.sidebar_buttons.append(btn)
            sidebar_layout.addWidget(btn)

            page = page_classes[i](*page_args[i])
            self.pages.addWidget(page)

        sidebar_layout.addStretch()

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.pages, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f'Project Root: {self.project_root}')

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

    window = MainWindow(project_root, env_vars, apps_config, pipeline_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
