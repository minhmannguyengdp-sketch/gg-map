# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

BASE_DIR = Path(os.getcwd()).resolve()
ENTRY_SCRIPT = Path(os.environ.get("GG_MAP_ENTRY_SCRIPT", str(BASE_DIR / "ui_cao_map.py"))).resolve()

datas = []
hiddenimports = []
datas += collect_data_files("playwright")
datas += collect_data_files("bs4")
hiddenimports += collect_submodules("tkinter")
hiddenimports += [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.simpledialog",
    "tkinter.ttk",
]
hiddenimports += collect_submodules("playwright")
hiddenimports += collect_submodules("bs4")
hiddenimports += collect_submodules("pandas")
hiddenimports += collect_submodules("openpyxl")


a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(BASE_DIR), str(ENTRY_SCRIPT.parent)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(BASE_DIR / "runtime_tk_hook.py"),
        str(BASE_DIR / "runtime_utf8_hook.py"),
    ],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GG_map_7.9_new",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GG_map_7.9_new",
)
