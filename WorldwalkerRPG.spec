# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=['backend'],
    binaries=[],
    # Music is copied beside the finished EXE by the release packaging step.
    # Frozen launcher.py deliberately reads that user-editable top-level folder;
    # embedding a second copy under _internal only doubled every release ZIP.
    datas=[
        ('frontend', 'frontend'),
        ('assets', 'assets'),
        # naruto_tactics is imported as a top-level frozen module, so its
        # adjacent authored move library must live at the _internal root.
        ('backend/naruto_tactical_moves.json', '.'),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='WorldwalkerRPG',
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
    icon=['assets/branding/worldwalker.ico'],
    version='version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorldwalkerRPG',
)
