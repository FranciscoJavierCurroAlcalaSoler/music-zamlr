# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['serve.py'],
    pathex=[],
    binaries=[],
    # The revisions are read from disk by path and never imported, so no
    # import graph leads to them and nothing but this line puts them in the
    # bundle. A build without it starts, finds a script directory with no
    # revisions in it, and gives a new installation a database with no
    # tables. The two entries have to land where alembic.ini's
    # script_location expects them: the ini file at the top of _internal,
    # the directory beside it, and %(here)s resolving between the two.
    datas=[("alembic.ini", "."), ("alembic", "alembic")],
    # Empty, and that is a measured answer rather than an omission. Uvicorn
    # names its protocol, loop and lifespan classes in strings, and SQLAlchemy
    # resolves its dialect the same way, so neither can be followed by an
    # import graph. Both are covered already: pyinstaller-hooks-contrib ships
    # hook-uvicorn.py, which calls collect_submodules on the whole package,
    # and PyInstaller itself ships hook-sqlalchemy.py. A build with this list
    # emptied passes every test in tests/test_packaged_backend.py, which is
    # also what would fail if a later release of those hooks stopped.
    #
    # A list that changes nothing is worse than no list: it reads as
    # load-bearing, and the next person adds to it rather than measuring.
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The backend never reads from a terminal. readline arrives only because
    # modules such as pdb import it, and they carry on without it. On Linux
    # it brings libreadline, which is GPL-3, so shipping it would oblige the
    # release to carry readline's source as well.
    excludes=["readline"],
    noarchive=False,
    optimize=0,
)
# Left to the system. Every machine that can install the Linux package has
# both, because WebKitGTK, a declared dependency, needs them. Bundled, they
# are GPL-3 libraries whose runtime exception would have to be argued. No
# Windows file has these names.
a.binaries = [
    entry
    for entry in a.binaries
    if not entry[0].startswith(("libstdc++.so", "libgcc_s.so"))
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='music-zamlr-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='music-zamlr-backend',
)
