# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for pyx2ctune GUI application.

Uses --onedir mode for fast startup (no temp extraction).
On macOS, also produces a .app bundle.
"""

import sys

block_cipher = None

a = Analysis(
    ['pyx2ctune/gui/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pyx2cscope',
        'pyx2cscope.x2cscope',
        'pyx2cscope.parser',
        'pyx2cscope.parser.elf_parser',
        'pyx2cscope.parser.generic_parser',
        'pyx2cscope.variable',
        'pyx2cscope.variable.variable',
        'pyx2cscope.utils',
        'mchplnet',
        'pyelftools',
        'elftools',
        'elftools.elf',
        'elftools.elf.elffile',
        'elftools.dwarf',
        'elftools.dwarf.dwarfinfo',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'lark',
        'matplotlib.backends.backend_qt5agg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'test',
        'pyx2cscope.gui',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pyx2ctune',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == 'darwin',
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pyx2ctune',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='pyx2ctune.app',
        icon=None,
        bundle_identifier='com.microchip.pyx2ctune',
        info_plist={
            'CFBundleShortVersionString': '0.1.0',
            'NSHighResolutionCapable': True,
        },
    )
