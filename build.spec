# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

# Da die Datenbank-Zugangsdaten hartkodiert sind und Tkinter jetzt korrekt funktioniert,
# ist diese Liste für Deine Assets vorgesehen (z.B. Icons).
added_files = [
    # Hier nur zusätzliche Assets einfügen, falls vorhanden.
]

# --- ENDE DER DATEN-DEFINITION ---

a = Analysis(
    ['main.py'],
    # Passt den Pfad an Deine aktuelle Umgebung an:
    pathex=['E:\\Programme\\Python313\\DHF Planer'],
    binaries=[],
    datas=added_files,

    # Versteckte Imports sind jetzt komplett und beheben das leere Fenster
    hiddenimports=[
        'tkinter',
        'babel.numbers',
        'mysql.connector',
        'holidays.countries', # <-- DIESER IMPORT LÖST DEN FEHLER
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False, # <-- Für eine GUI-Anwendung (keine Konsole sichtbar)
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