# utils/threading_utils.py
import threading
import queue
from typing import Callable, Any


class WorkerThread(threading.Thread):
    """
    Führt eine zeitaufwändige Funktion in einem separaten Thread aus
    und meldet das Ergebnis über eine Queue zurück.

    Dieser Thread ist als 'daemon' konfiguriert, was bedeutet, dass er
    automatisch beendet wird, wenn die Hauptanwendung geschlossen wird.
    """

    def __init__(self, target_func: Callable, *args, **kwargs):
        """
        Initialisiert den Worker-Thread.

        Args:
            target_func: Die Funktion, die im Hintergrund ausgeführt werden soll
                         (z.B. eine Datenbankabfrage).
            *args, **kwargs: Argumente, die an die target_func übergeben werden.
        """
        super().__init__()
        self.target_func = target_func
        self.args = args
        self.kwargs = kwargs
        self.result_queue = queue.Queue()
        # Daemon-Threads verhindern, dass die Anwendung offen bleibt,
        # nur weil noch ein Hintergrund-Thread läuft.
        self.daemon = True

    def run(self):
        """
        Die Hauptmethode des Threads.
        Führt die Zielfunktion aus und speichert das Ergebnis (oder einen Fehler)
        sicher in der Queue.
        """
        try:
            # Führe die eigentliche (blockierende) Arbeit aus
            result = self.target_func(*self.args, **self.kwargs)
            # Speichere das Ergebnis für den Haupt-Thread
            self.result_queue.put((result, None))
        except Exception as e:
            # Speichere den Fehler, falls einer auftritt
            self.result_queue.put((None, e))


class ThreadManager:
    """
    Verwaltet das Starten von WorkerThreads und die sichere Kommunikation
    mit dem Haupt-Thread (GUI) unter Verwendung von tkinter's .after() Mechanismus (Polling).
    """

    def __init__(self, root: Any):
        """
        Initialisiert den ThreadManager.

        Args:
            root: Ein tkinter-Widget (z.B. das Hauptfenster, ctk.CTk, tk.Toplevel),
                  das die .after()-Methode bereitstellt, um Callbacks sicher
                  im GUI-Thread auszuführen.
        """
        self.root = root
        # Liste, um laufende Worker und ihre zugehörigen Callback-Funktionen zu speichern
        self.active_workers = []
        # Stellt sicher, dass der Checker-Loop nur einmal gestartet wird
        self.checker_running = False

    def start_worker(self, target_func: Callable, on_complete: Callable, *args, **kwargs):
        """
        Startet eine Funktion (target_func) in einem neuen Worker-Thread.

        Wenn die Funktion abgeschlossen ist, wird on_complete im GUI-Thread aufgerufen.

        Args:
            target_func: Die auszuführende Funktion (z.B. db_core.get_data).
            on_complete: Die Callback-Funktion, die im GUI-Thread aufgerufen werden soll.
                         Sie muss zwei Argumente akzeptieren: (result, error).
            *args, **kwargs: Argumente, die an die target_func übergeben werden.
        """
        # Erstelle einen neuen Worker
        worker = WorkerThread(target_func, *args, **kwargs)
        # Füge den Worker und seinen Callback zur Liste der aktiven Worker hinzu
        self.active_workers.append((worker, on_complete))

        # Starte den Thread (ruft worker.run() auf)
        worker.start()

        # Starte den Polling-Check-Loop, falls er nicht schon läuft
        if not self.checker_running:
            self.checker_running = True
            self._check_workers()

    def _check_workers(self):
        """
        [LÄUFT IM GUI-THREAD]
        Überprüft periodisch (alle 100ms) alle aktiven Worker, ob sie Ergebnisse haben.
        Dies ist der Kernmechanismus, um Daten sicher aus Threads zurück
        in die GUI zu bringen.
        """
        still_running = []

        # Gehe durch alle Worker, die wir gestartet haben
        for worker, on_complete in self.active_workers:
            try:
                # Prüft nicht-blockierend (get_nowait), ob etwas in der Queue ist
                result, error = worker.result_queue.get_nowait()

                # Wenn wir hier sind, ist der Thread fertig.
                # Rufe den Callback sicher im GUI-Thread auf.
                try:
                    on_complete(result, error)
                except Exception as e_callback:
                    # Fängt Fehler im Callback selbst ab
                    print(f"[ThreadManager] Fehler im 'on_complete' Callback: {e_callback}")

            except queue.Empty:
                # Die Queue ist leer, d.h. der Thread läuft noch.
                # Behalte ihn in der Liste für den nächsten Check.
                still_running.append((worker, on_complete))
            except Exception as e_queue:
                # Unerwarteter Fehler beim Abrufen aus der Queue
                print(f"[ThreadManager] Fehler beim Abrufen des Worker-Ergebnisses: {e_queue}")

        # Aktualisiere die Liste der aktiven Worker
        self.active_workers = still_running

        # Wenn noch Worker laufen, plane den nächsten Check
        if self.active_workers:
            self.root.after(100, self._check_workers)
        else:
            # Keine Worker mehr aktiv, der Checker kann pausieren.
            self.checker_running = False