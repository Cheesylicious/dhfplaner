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