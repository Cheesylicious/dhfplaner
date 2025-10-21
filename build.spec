# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

# Da die Datenbank-Zugangsdaten hartkodiert sind und Tkinter jetzt korrekt funktioniert,
# ist diese Liste für Deine Assets vorgesehen (z.B. Icons).
added_files = [
    # Kopiere das gesamte 'gui'-Verzeichnis in den 'gui'-Unterordner des Bundles.
    ('gui', 'gui'),
    # Kopiere das gesamte 'database'-Verzeichnis in den 'database'-Unterordner des Bundles.
    ('database', 'database'),

    # WICHTIG: main.py MUSS wieder extern sein.
    ('main.py', '.'),

    # Die Datenbank-Datei planer.db in den 'database' Ordner kopieren.
    ('planer.db', 'database'),

]

# --- ENDE DER DATEN-DEFINITION ---

# ERSTELLEN DER BINARIES-LISTE MIT PFADEN (KOMPLETT AUTOMATISIERT)
# ------------------------------------------------------------------
# Die Liste ist LEER. PyInstaller findet die DLLs aus der Conda-Umgebung selbst.
binaries_to_add = []

# ------------------------------------------------------------------


a = Analysis(
    # KORREKTUR: Der Bootloader ist der einzige Code, der in die EXE kommt.
    ['boot_loader.py'],

    # Pathex ist der Pfad zum Projektordner
    pathex=['C:\\Python313\\Projekte\\DHF Planer'],
    # Leere Binärliste
    binaries=binaries_to_add,

    datas=added_files,

    # Versteckte Imports (alle Fixes beibehalten)
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
    # WICHTIG: Die Pakete 'database' und 'gui' MÜSSEN EXCLUDED werden!
    excludes=['database', 'gui'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

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

    # WICHTIG: Konsole ANLASSEN, um den Fehler beim Laden der externen main.py zu sehen.
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DHF-Planer',
)