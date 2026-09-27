# -*- mode: python ; coding: utf-8 -*-
# PyInstaller specification for FlowLens Collector

block_cipher = None

a = Analysis(
    ['../src/flowlens/__main__.py'],
    pathex=['../src'],
    binaries=[],
    datas=[
        ('../LICENSE', '.'),
    ],
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
        'uiautomation',
        'psutil',
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'win32ts',
        'win32evtlog',
        'winreg',
    ],
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
        'google-genai',
        'google-generativeai',
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
