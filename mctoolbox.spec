# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for mctoolbox GUI application.

Uses --onedir mode for fast startup (no temp extraction).
On macOS, also produces a .app bundle.
"""

import sys

block_cipher = None

a = Analysis(
    ['mctoolbox/gui/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pymcaf',
        'pymcaf.backend',
        'pymcaf.connection',
        'pymcaf.constants',
        'pymcaf.motor',
        'pymcaf.parameters',
        'pymcaf.scope',
        'pymcaf.test_harness',
        'pymcaf.types',
        'pymcaf.backends',
        'pymcaf.backends.x2cscope',
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
    name='mctoolbox',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mctoolbox',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='mctoolbox.app',
        icon=None,
        bundle_identifier='com.microchip.mctoolbox',
        info_plist={
            'CFBundleShortVersionString': '0.1.0',
            'NSHighResolutionCapable': True,
        },
    )
