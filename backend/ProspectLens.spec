# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Target 1: ProspectLens Engine (Tray UI + FastAPI backend)
datas_engine = [('icons', 'icons')]
binaries_engine = []
hiddenimports_engine = [
    'sqlmodel',
    'sqlalchemy.sql.functions',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.loops.auto',
    'uvicorn.lifespan.on',
    'pystray._win32'
]

tmp_ret = collect_all('google-genai')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]
tmp_ret = collect_all('playwright')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]
tmp_ret = collect_all('pystray')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]
tmp_ret = collect_all('sqlmodel')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]
tmp_ret = collect_all('uvicorn')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]
tmp_ret = collect_all('pandas')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]
tmp_ret = collect_all('openpyxl')
datas_engine += tmp_ret[0]; binaries_engine += tmp_ret[1]; hiddenimports_engine += tmp_ret[2]

a_engine = Analysis(
    ['tray_app.py'],
    pathex=[],
    binaries=binaries_engine,
    datas=datas_engine,
    hiddenimports=hiddenimports_engine,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas.tests', 'numpy.tests', 'PIL.tests', 'sqlalchemy.testing'],
    noarchive=False,
    optimize=0,
)
pyz_engine = PYZ(a_engine.pure)

exe_engine = EXE(
    pyz_engine,
    a_engine.scripts,
    [],
    exclude_binaries=True,
    name='ProspectLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='icons/app.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Target 2: Native Messaging Host launcher_host
a_launcher = Analysis(
    ['launcher_host.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz_launcher = PYZ(a_launcher.pure)

exe_launcher = EXE(
    pyz_launcher,
    a_launcher.scripts,
    [],
    exclude_binaries=True,
    name='launcher_host',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon='icons/app.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_engine,
    a_engine.binaries,
    a_engine.datas,
    exe_launcher,
    a_launcher.binaries,
    a_launcher.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ProspectLens',
)
