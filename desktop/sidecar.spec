# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for PromptPressure Desktop Sidecar
Bundles the Python backend as a standalone executable for Tauri.
Run from desktop/ directory: pyinstaller sidecar.spec
"""

import sys
from pathlib import Path

# Project paths (spec file is in desktop/, project root is parent)
PROJECT_ROOT = Path('.').resolve().parent
PROMPTPRESSURE_PKG = PROJECT_ROOT / 'promptpressure'

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / 'promptpressure' / 'api.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Include config files
        (str(PROJECT_ROOT / 'configs'), 'configs'),
        # Include any data files needed
        (str(PROJECT_ROOT / 'data'), 'data'),
    ],
    hiddenimports=[
        # FastAPI and dependencies
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        'sse_starlette',
        'pydantic',
        'pydantic_settings',
        # Database
        'sqlalchemy',
        'sqlalchemy.ext.asyncio',
        'aiosqlite',
        # HTTP client
        'httpx',
        # PromptPressure modules
        'promptpressure',
        'promptpressure.adapters',
        'promptpressure.adapters.ollama_adapter',
        'promptpressure.adapters.groq_adapter',
        'promptpressure.adapters.openrouter_adapter',
        'promptpressure.adapters.lmstudio_adapter',
        'promptpressure.adapters.mock_adapter',
        'promptpressure.config',
        'promptpressure.cli',
        'promptpressure.database',
        'promptpressure.rate_limit',
        'promptpressure.metrics',
        'promptpressure.reporting',
        'promptpressure.plugins',
        'promptpressure.plugins.core',
        # Other deps
        'dotenv',
        'yaml',
        'jinja2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'matplotlib',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='promptpressure-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console mode for sidecar (no GUI)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# For macOS, also create an app bundle (optional)
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='PromptPressure-Sidecar.app',
        icon=None,
        bundle_identifier='com.stresstestor.promptpressure.sidecar',
        info_plist={
            'LSBackgroundOnly': True,  # Background-only app
            'NSHighResolutionCapable': True,
        },
    )
