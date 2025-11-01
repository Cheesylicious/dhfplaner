# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Alle Daten-Dateien und ihre Zielordner im fertigen Programm
# ('quelldatei', 'zielordner_im_bundle')
added_files = [
    ('gui', 'gui'),
    ('database', 'database'),
    ('main.py', '.'),
    ('planer.db', 'database'),
    ('update_manager.py', '.'),
    ('version.txt', '.'),
]

a = Analysis(
    ['boot_loader.py'],
    pathex=['C:\\Python313\\Projekte\\DHF Planer'], # Passe dies bei Bedarf an
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'tkinter.colorchooser',
        'tkinter.scrolledtext',
        'tkinter.tix',
        'tkcalendar',
        'calendar',
        'email.mime.text',
        'babel.numbers',
        'mysql.connector',
        'holidays.countries',
        'mysql.connector.locales',
        'mysql.connector.abstracts',
        'mysql.connector.plugins.mysql_native_password',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['database', 'gui'],
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
    name='DHF-Planer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True, # Konsole anlassen für die Fehlersuche
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DHF-Planer',
)

import sys
sys.setrecursionlimit(5000)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('database/planer.db', 'database'),
        ('resources/logo.ico', 'resources'),
        ('resources/logo_planer.png', 'resources'),
        ('resources/login_background.png', 'resources'),
        ('resources/icon_user.png', 'resources'),
        ('resources/icon_lock.png', 'resources'),
        ('resources/icon_visible.png', 'resources'),
        ('resources/icon_hidden.png', 'resources'),
        # --- HINZUGEFÜGT (Regel 1): Stellt sicher, dass das tkcalendar-Motiv eingebettet wird ---
        ('venv/Lib/site-packages/tkcalendar/images', 'tkcalendar/images'),
        ('venv/Lib/site-packages/sv_ttk/sv.tcl', 'sv_ttk'),
        ('venv/Lib/site-packages/sv_ttk/theme', 'sv_ttk/theme')
    ],
    hiddenimports=[
        'babel.numbers',
        'babel.dates',
        'tkcalendar',
        'sv_ttk',
        # --- HINZUGEFÜGT (Regel 1): Behebt "No module named 'PIL'" ---
        'PIL',
        'PIL._tkinter_finder'
        # --- ENDE HINZUGEFÜGT ---
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DHF-Planer',
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
    icon='resources/logo.ico',
)