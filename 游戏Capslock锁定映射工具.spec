# -*- mode: python ; coding: utf-8 -*-
import os

# PyInstaller provides SPECPATH while executing a spec file.
base_dir = globals().get("SPECPATH") or os.getcwd()
script_path = os.path.join(base_dir, "caps_lock_blocker.py")
manifest_path = os.path.join(base_dir, "app.manifest")

a = Analysis(
    [script_path],
    pathex=[base_dir],
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
pyz = PYZ(a.pure)

# onedir build: the executable runs directly from this folder.
# No self-extraction to %TEMP%, which avoids "Could not create temporary directory".
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GameCapslockMapper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    uac_admin=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest=manifest_path,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GameCapslockMapper',
)
