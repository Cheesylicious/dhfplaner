# utils/threading_utils.py
import threading
from queue import Queue, Empty, LifoQueue  # LifoQueue hinzugefügt
import time


class ThreadManager:
    """
    Verwaltet einen Pool von Worker-Threads, um GUI-Blockaden zu verhindern.
    Verwendet einen GUI-Callback, um Ergebnisse sicher zurückzugeben.
    (DIESE KLASSE BLEIBT UNVERÄNDERT)
    """

    def __init__(self, root, max_workers=5):
        self.root = root
        self.task_queue = Queue()
        self.max_workers = max_workers
        self.workers = []
        self.running = True
        self._start_workers()

    def _start_workers(self):
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)

    def _worker_loop(self):
        while self.running:
            try:
                # Warte auf eine Aufgabe
                target_func, callback, args, kwargs = self.task_queue.get(timeout=1)
                if not self.running:
                    break

                try:
                    # Führe die Aufgabe aus
                    result = target_func(*args, **kwargs)
                    error = None
                except Exception as e:
                    result = None
                    error = e

                # Sende das Ergebnis an den GUI-Thread
                if callback:
                    self.root.after(0, callback, result, error)

                self.task_queue.task_done()

            except Empty:
                continue
            except Exception as e:
                print(f"[ThreadManager] Kritischer Fehler im Worker-Loop: {e}")

    def start_worker(self, target_func, callback, *args, **kwargs):
        """
        Fügt eine neue Aufgabe zur Queue hinzu.

        Args:
            target_func (callable): Die Funktion, die im Thread ausgeführt werden soll.
            callback (callable): Die Funktion, die im GUI-Thread mit (result, error) aufgerufen wird.
            *args: Argumente für target_func.
            **kwargs: Keyword-Argumente für target_func.
        """
        if not self.running:
            print("[ThreadManager] Hinzufügen von Task abgelehnt, Manager stoppt.")
            return

        print(f"[ThreadManager] Füge Task hinzu: {target_func.__name__}")
        self.task_queue.put((target_func, callback, args, kwargs))

    def stop(self):
        """Signalisiert allen Workern, sich zu beenden."""
        print("[ThreadManager] Stoppe alle Worker...")
        self.running = False
        # Leere die Queue, um blockierte Threads zu lösen
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except Empty:
                break

        # Warte auf das Beenden der Threads (optional, da daemon=True)
        # for worker in self.workers:
        #     worker.join(timeout=1)
        print("[ThreadManager] Gestoppt.")


# --- NEU: Fehlende Klassen für den PreloadingManager (behebt ImportError) ---

class Task:
    """
    Kapselt eine Zielfunktion und ihre Argumente für den ThreadPool.
    """

    def __init__(self, target_func, *args, **kwargs):
        self.target_func = target_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Führt die Task aus und fängt Fehler ab."""
        try:
            self.target_func(*self.args, **self.kwargs)
        except Exception as e:
            print(f"[Task] Fehler bei Ausführung von {self.target_func.__name__}: {e}")
            import traceback
            traceback.print_exc()


class ThreadPool:
    """
    Ein dedizierter Thread-Pool für den PreloadingManager.
    Nutzt max_workers=1 (Standard), um DB-Anfragen zu serialisieren (Regel 2).
    Nutzt eine LIFO-Queue, damit P4 (Blättern) Vorrang vor P2/P3 (Tab-Laden) hat.
    """

    def __init__(self, max_workers=1, thread_name_prefix="PreloadWorker"):
        self.max_workers = max_workers
        # LIFO (Last-In, First-Out) priorisiert die neuesten Aufgaben (P4).
        self.task_queue = LifoQueue()
        self.workers = []
        self.running = False
        self.thread_name_prefix = thread_name_prefix

    def start(self):
        """Startet die Worker-Threads."""
        if self.running:
            return
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.name = f"{self.thread_name_prefix}-{i}"
            worker.start()
            self.workers.append(worker)

    def _worker_loop(self):
        """Die Hauptschleife für jeden Worker-Thread."""
        while self.running:
            try:
                # Warte auf eine Task
                task = self.task_queue.get(timeout=1)
                if task:
                    task.run()
                    self.task_queue.task_done()
            except Empty:
                if not self.running:
                    break
            except Exception as e:
                print(f"[ThreadPool {threading.current_thread().name}] Fehler: {e}")

    def add_task(self, task: Task):
        """Fügt eine Task zur LIFO-Queue hinzu."""
        if self.running:
            self.task_queue.put(task)

    def stop(self):
        """Stoppt alle Worker-Threads."""
        self.running = False
        # Leere Queue, um Worker zu beenden
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except Empty:
                break
        print(f"[ThreadPool {self.thread_name_prefix}] Gestoppt.")

# --- ENDE NEU ---