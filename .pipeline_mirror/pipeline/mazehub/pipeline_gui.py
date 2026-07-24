import os
import sys
import subprocess
import platform
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QStackedWidget, QTextEdit, QFrame,
    QHeaderView, QTreeWidget, QTreeWidgetItem, QStatusBar, QGroupBox,
    QFormLayout, QGridLayout, QScrollArea, QSplitter,
)

from pipeline_app import (
    find_project_root, setup_environment, load_apps_config,
    find_project_files, read_shot_meta, write_shot_meta,
)


SIDEBAR_ITEMS = [
    ('Home', 'Dashboard with project info and quick launch'),
    ('Launch Apps', 'Launch VFX applications'),
    ('Shot Explorer', 'Browse existing shots and create new ones'),
    ('Asset Explorer', 'Browse existing assets and create new ones'),
    ('Browse Files', 'Find and open project files'),
    ('Env Vars', 'View environment variables'),
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

    def __init__(self, config, pipeline_dir):
        super().__init__()
        self.config = config
        self.pipeline_dir = pipeline_dir

    def run(self):
        try:
            exec_path = self.pipeline_dir / self.config['subdir'] / self.config['executable']
            if not exec_path.exists():
                self.finished.emit(f'Executable not found: {exec_path}', False)
                return
            if platform.system() == 'Windows':
                subprocess.Popen([str(exec_path)], shell=True)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(exec_path)])
            else:
                subprocess.Popen(['xdg-open', str(exec_path)])
            self.finished.emit(f'Launched {self.config["display_name"]}', True)
        except Exception as e:
            self.finished.emit(f'Failed: {e}', False)


class FileOpenThread(QThread):
    finished = Signal(str, bool)

    def __init__(self, app_config, pipeline_dir, file_path):
        super().__init__()
        self.config = app_config
        self.pipeline_dir = pipeline_dir
        self.file_path = file_path

    def run(self):
        try:
            exec_path = self.pipeline_dir / self.config['subdir'] / self.config['executable']
            if platform.system() == 'Windows':
                subprocess.Popen([str(exec_path), str(self.file_path)], shell=True)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(self.file_path)])
            else:
                subprocess.Popen([str(exec_path), str(self.file_path)], shell=True)
            self.finished.emit(f'Opened {self.file_path.name} with {self.config["display_name"]}', True)
        except Exception as e:
            self.finished.emit(f'Failed: {e}', False)


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
    def __init__(self, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(12)

        if self.apps_config:
            for name, cfg in self.apps_config.items():
                card = QFrame()
                card.setFrameShape(QFrame.StyledPanel)
                card_layout = QHBoxLayout(card)

                info_layout = QVBoxLayout()
                app_name_label = QLabel(cfg['display_name'])
                app_name_label.setFont(QFont(app_name_label.font().family(), 11, QFont.Bold))
                info_layout.addWidget(app_name_label)

                exec_path = self.pipeline_dir / cfg['subdir'] / cfg['executable']
                info_layout.addWidget(QLabel(f'Executable: {exec_path}'))
                info_layout.addWidget(QLabel(f'Exists: {exec_path.exists()}'))

                card_layout.addLayout(info_layout)
                card_layout.addStretch()

                launch_btn = QPushButton('Launch')
                launch_btn.setMinimumWidth(100)
                launch_btn.setMinimumHeight(36)
                launch_btn.setCursor(Qt.PointingHandCursor)
                launch_btn.clicked.connect(lambda checked, c=cfg: self._launch(c))
                card_layout.addWidget(launch_btn)

                container_layout.addWidget(card)
        else:
            container_layout.addWidget(QLabel('No applications configured.'))

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _launch(self, cfg):
        self.thread = AppLauncherThread(cfg, self.pipeline_dir)
        self.thread.finished.connect(lambda msg, ok: self._result(msg, ok))
        self.thread.start()

    def _result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


class ShotExplorerPage(QWidget):
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._editing_shot = None
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

        splitter = QSplitter(Qt.Vertical)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.edit_btn = QPushButton('Edit Selected')
        self.edit_btn.setMinimumHeight(32)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._load_selected)
        toolbar.addWidget(self.edit_btn)
        toolbar.addStretch()
        top_layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ['Shot', 'Path', 'Frame Range', 'Frame Rate', 'Resolution', 'Description', 'Working Dirs']
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(
            lambda: self.edit_btn.setEnabled(bool(self.table.selectedItems()))
        )
        top_layout.addWidget(self.table)
        splitter.addWidget(top_widget)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 8, 0, 0)

        self.form_group = QGroupBox('Create New Shot')
        form_layout = QVBoxLayout(self.form_group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel('Shot Name:'), 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('e.g. SH010')
        r1.addWidget(self.name_edit, 1)
        form_layout.addLayout(r1)

        meta_grid = QGridLayout()
        meta_grid.addWidget(QLabel('Frame Range:'), 0, 0)
        self.fr_edit = QLineEdit()
        self.fr_edit.setPlaceholderText('e.g. 1001-1100')
        meta_grid.addWidget(self.fr_edit, 0, 1)
        meta_grid.addWidget(QLabel('Frame Rate:'), 0, 2)
        self.fps_edit = QLineEdit()
        self.fps_edit.setPlaceholderText('e.g. 24')
        meta_grid.addWidget(self.fps_edit, 0, 3)
        meta_grid.addWidget(QLabel('Resolution:'), 0, 4)
        self.res_edit = QLineEdit()
        self.res_edit.setPlaceholderText('e.g. 1920x1080')
        meta_grid.addWidget(self.res_edit, 0, 5)
        form_layout.addLayout(meta_grid)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel('Description:'), 0)
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText('e.g. Establishing wide shot')
        r3.addWidget(self.desc_edit, 1)
        form_layout.addLayout(r3)

        btn_row = QHBoxLayout()
        self.create_btn = QPushButton('Create Shot')
        self.create_btn.setMinimumHeight(36)
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.clicked.connect(self._save)
        btn_row.addWidget(self.create_btn)

        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_edit)
        btn_row.addWidget(self.cancel_btn)

        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(70)
        form_layout.addWidget(self.result_text)

        bottom_layout.addWidget(self.form_group)
        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self._refresh()

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
            self.table.setItem(i, 4, QTableWidgetItem(meta['resolution']))
            self.table.setItem(i, 5, QTableWidgetItem(meta['description']))
            self.table.setItem(i, 6, QTableWidgetItem(f'{working_count} dirs'))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(self.table.columnWidth(1), 200))
        self.table.setColumnWidth(5, max(self.table.columnWidth(5), 200))
        self.table.horizontalHeader().setStretchLastSection(False)

    def _load_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        shot_name = self.table.item(row, 0).text()
        shot_path = self.project_root / 'sequence' / shot_name
        meta = read_shot_meta(shot_path)

        self._editing_shot = shot_name
        self.name_edit.setText(shot_name)
        self.fr_edit.setText(meta['frame_range'])
        self.fps_edit.setText(meta['frame_rate'])
        self.res_edit.setText(meta['resolution'])
        self.desc_edit.setText(meta['description'])
        self.form_group.setTitle(f'Edit Shot: {shot_name}')
        self.create_btn.setText('Save Metadata')
        self.cancel_btn.setVisible(True)

    def _cancel_edit(self):
        self._editing_shot = None
        self.name_edit.clear()
        self.fr_edit.clear()
        self.fps_edit.clear()
        self.res_edit.clear()
        self.desc_edit.clear()
        self.form_group.setTitle('Create New Shot')
        self.create_btn.setText('Create Shot')
        self.cancel_btn.setVisible(False)

    def _validate_meta(self):
        errors = []
        if not self.fr_edit.text().strip():
            errors.append('Frame Range')
        if not self.fps_edit.text().strip():
            errors.append('Frame Rate')
        if not self.res_edit.text().strip():
            errors.append('Resolution')
        return errors

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            self.result_text.setText('Please enter a shot name.')
            return

        missing = self._validate_meta()
        if missing:
            self.result_text.setText(f'Required fields missing: {", ".join(missing)}')
            return

        from make_folders import make_working_directory

        shot_path = self.project_root / 'sequence' / name
        meta = {
            'frame_range': self.fr_edit.text().strip(),
            'frame_rate': self.fps_edit.text().strip(),
            'resolution': self.res_edit.text().strip(),
            'description': self.desc_edit.text().strip(),
        }

        if self._editing_shot:
            if not shot_path.exists():
                self._cancel_edit()
                self._refresh()
                self.result_text.setText(f'Shot no longer exists: {name}')
                return
            write_shot_meta(shot_path, meta)
            self._cancel_edit()
            self._refresh()
            self.result_text.setText(f'Metadata saved for: {name}')
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status(f'Metadata updated: {name}', True)
            return

        if shot_path.exists():
            self.result_text.setText(f'Shot already exists: {name}')
            return

        try:
            make_working_directory(str(shot_path))
            write_shot_meta(shot_path, meta)
            self._cancel_edit()
            self._refresh()
            self.result_text.setText(f'Created shot: {name}\nLocation: {shot_path}')
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status(f'Shot created: {name}', True)
        except Exception as e:
            self.result_text.setText(f'Error: {e}')


class AssetExplorerPage(QWidget):
    def __init__(self, project_root, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._build()

    def _build(self):
        from make_folders import NEW_ASSET_CATEGORY_LIST

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel('Asset Explorer')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addSpacing(8)

        splitter = QSplitter(Qt.Vertical)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel('Category:'))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['All'] + list(NEW_ASSET_CATEGORY_LIST))
        self.filter_combo.currentTextChanged.connect(self._refresh)
        filter_row.addWidget(self.filter_combo)
        filter_row.addStretch()
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        filter_row.addWidget(self.refresh_btn)
        top_layout.addLayout(filter_row)
        top_layout.addSpacing(4)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['Asset', 'Category', 'Path', 'Working Dirs'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        top_layout.addWidget(self.table)
        splitter.addWidget(top_widget)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 8, 0, 0)

        form_group = QGroupBox('Create New Asset')
        form_layout = QVBoxLayout(form_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel('Category:'), 0)
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(NEW_ASSET_CATEGORY_LIST)
        row1.addWidget(self.cat_combo, 1)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel('Asset Name:'), 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('e.g. MainCharacter')
        row2.addWidget(self.name_edit, 1)
        form_layout.addLayout(row2)

        btn_row = QHBoxLayout()
        self.create_btn = QPushButton('Create Asset')
        self.create_btn.setMinimumHeight(36)
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.clicked.connect(self._create)
        btn_row.addWidget(self.create_btn)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(80)
        form_layout.addWidget(self.result_text)

        bottom_layout.addWidget(form_group)
        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self._refresh()

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

    def _create(self):
        category = self.cat_combo.currentText()
        name = self.name_edit.text().strip()
        if not name:
            self.result_text.setText('Please enter an asset name.')
            return

        from make_folders import make_working_directory

        asset_path = self.project_root / 'asset' / category / name
        if asset_path.exists():
            self.result_text.setText(f'Asset already exists: {category}/{name}')
            return

        try:
            make_working_directory(str(asset_path))
            self.result_text.setText(f'Created asset: {category}/{name}\nLocation: {asset_path}')
            self.name_edit.clear()
            self._refresh()
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status(f'Asset created: {category}/{name}', True)
        except Exception as e:
            self.result_text.setText(f'Error: {e}')


class BrowseFilesPage(QWidget):
    def __init__(self, project_root, apps_config, pipeline_dir, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.apps_config = apps_config
        self.pipeline_dir = pipeline_dir
        self._file_map = {}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel('Browse Project Files')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        layout.addSpacing(8)

        search_layout = QHBoxLayout()
        self.search_btn = QPushButton('Search for Project Files')
        self.search_btn.setMinimumHeight(36)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.clicked.connect(self._search)
        search_layout.addWidget(self.search_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)
        layout.addSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['#', 'Application', 'File', 'Path'])
        self.tree.setColumnWidth(0, 40)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(2, 200)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        self.tree.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        self.open_btn = QPushButton('Open Selected')
        self.open_btn.setMinimumHeight(36)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self._open_selected)
        self.open_btn.setEnabled(False)
        btn_layout.addWidget(self.open_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.tree.itemSelectionChanged.connect(
            lambda: self.open_btn.setEnabled(bool(self.tree.selectedItems()))
        )

    def _search(self):
        self.tree.clear()
        self._file_map.clear()
        self.search_btn.setEnabled(False)
        self.search_btn.setText('Searching...')

        results = find_project_files(self.project_root, self.apps_config)

        self.search_btn.setText('Search for Project Files')
        self.search_btn.setEnabled(True)

        idx = 1
        for app_name in sorted(results):
            for fp in results[app_name]:
                rel = fp.relative_to(self.project_root)
                item = QTreeWidgetItem([
                    str(idx), app_name, fp.name, str(rel.parent)
                ])
                self.tree.addTopLevelItem(item)
                self._file_map[idx] = (app_name, fp, rel, item)
                idx += 1

        if idx == 1:
            item = QTreeWidgetItem(['', '', 'No project files found.', ''])
            self.tree.addTopLevelItem(item)

    def _open_selected(self):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        num_text = item.text(0)
        if not num_text.isdigit():
            return
        num = int(num_text)
        if num not in self._file_map:
            return

        app_name, file_path, rel, _ = self._file_map[num]
        cfg = self.apps_config.get(app_name)
        if not cfg:
            window = self.window()
            if hasattr(window, 'show_status'):
                window.show_status(f'No config for {app_name}', False)
            return

        self.thread = FileOpenThread(cfg, self.pipeline_dir, file_path)
        self.thread.finished.connect(lambda msg, ok: self._result(msg, ok))
        self.thread.start()

    def _result(self, msg, ok):
        window = self.window()
        if hasattr(window, 'show_status'):
            window.show_status(msg, ok)


class EnvVarsPage(QWidget):
    def __init__(self, env_vars, parent=None):
        super().__init__(parent)
        self.env_vars = env_vars
        self._build()

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
            'Each value references MAZE_PROJECT_ROOT as the base path. '
            'Absolute paths are also set in the OS environment for tool compatibility.'
        )
        note.setWordWrap(True)
        note.setObjectName('hint')
        layout.addWidget(note)
        layout.addSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['Variable', 'Value'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        self.table.setRowCount(len(self.env_vars))
        for i, (key, value) in enumerate(sorted(self.env_vars.items())):
            self.table.setItem(i, 0, QTableWidgetItem(key))
            self.table.setItem(i, 1, QTableWidgetItem(value))

        self.table.resizeColumnToContents(0)
        layout.addWidget(self.table)


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
                        AssetExplorerPage, BrowseFilesPage, EnvVarsPage]
        page_args = [
            (self.project_root, self.env_vars, self.apps_config, self.pipeline_dir),
            (self.apps_config, self.pipeline_dir),
            (self.project_root,),
            (self.project_root,),
            (self.project_root, self.apps_config, self.pipeline_dir),
            (self.env_vars,),
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
    script_dir = Path(__file__).resolve().parent

    env_vars = setup_environment(project_root)
    apps_config = load_apps_config()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    app = QApplication(sys.argv)
    app.setFont(QFont('Segoe UI', 10))
    _load_styles(app, script_dir)

    window = MainWindow(project_root, env_vars, apps_config, pipeline_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
