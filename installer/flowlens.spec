# -*- mode: python ; coding: utf-8 -*-
# PyInstaller specification for FlowLens Collector

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# uiautomation ships DLLs and comtypes generates wrappers at run time: take all of both.
extra_datas, extra_binaries, extra_hidden = [], [], []
for package in ('uiautomation', 'comtypes'):
    d, b, h = collect_all(package)
    extra_datas += d
    extra_binaries += b
    extra_hidden += h

a = Analysis(
    [os.path.join(ROOT, 'src', 'flowlens', '__main__.py')],
    pathex=[os.path.join(ROOT, 'src')],
    binaries=extra_binaries,
    datas=[(os.path.join(ROOT, 'LICENSE'), '.')] + extra_datas,
    hiddenimports=[
        'flowlens.windows.app',
        'flowlens.windows.shell',
        'flowlens.windows.watcher',
        'flowlens.windows.input_watcher',
        'flowlens.windows.past_import',
        'flowlens.windows.consent_dialog',
        'flowlens.windows.status_window',
        'flowlens.windows.settings_window',
        'flowlens.windows.autostart',
        'pyzipper',
        'psutil',
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'win32ts',
        'win32evtlog',
        'winreg',
    ] + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'requests',
        'httpx',
        'urllib3',
        'aiohttp',
        'fastapi',
        'flask',
        'uvicorn',
        'websockets',
        'openai',
        'anthropic',
        'ollama',
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
    name='flowlens',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='flowlens',
)
