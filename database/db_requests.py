# database/db_requests.py
# REFAKTORIERT: Diese Datei wurde aufgeteilt.
# Sie importiert jetzt nur noch die Funktionen aus den neuen Modulen,
# um die Abwärtskompatibilität für den Rest der Anwendung sicherzustellen.

import warnings

# --- 1. Import von Urlaubsanträgen ---
try:
    from .db_vacation_requests import *
except ImportError as e:
    warnings.warn(f"Konnte db_vacation_requests nicht importieren: {e}")

# --- 2. Import von Wunschfrei-Anträgen ---
try:
    from .db_wunschfrei_requests import *

    # Spezifische Überschreibungen, falls Namen kollidieren
    # (z.B. get_all_requests_by_user)
    # HINWEIS: In db_vacation_requests heißt die User-Funktion
    # 'get_requests_by_user',
    # in db_wunschfrei_requests heißt sie 'get_all_requests_by_user'.
    # Daher ist keine explizite Umbenennung (import ... as ...) nötig.

    # Die Hilfsfunktion 'get_user_info_for_notification' wird
    # redundant importiert, was Python aber handhaben sollte.

except ImportError as e:
    warnings.warn(f"Konnte db_wunschfrei_requests nicht importieren: {e}")