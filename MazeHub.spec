# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('.pipeline_mirror\\pipeline', 'pipeline'), ('make_folders.py', '.'), ('.venv\\Lib\\site-packages\\Imath.py', '.')]
binaries = [('.venv\\Lib\\site-packages\\OpenEXR.cp312-win_amd64.pyd', '.')]
hiddenimports = ['pipeline_gui', 'pipeline_app', 'recent_files', 'OpenEXR', 'Imath', 'numpy']
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:\\users\\Dominic\\Projects\\Uni\\mazehub_ai\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MazeHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\users\\Dominic\\Projects\\Uni\\mazehub_ai\\MazeHub_Logo.ico'],
)
