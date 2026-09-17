from __future__ import annotations

import subprocess
import sys
import threading
import time

from .store import Store


class Worker:
    def __init__(self, store: Store):
        self.store = store
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="arena-worker", daemon=True)
        self.process = None
        from functools import lru_cache
        from .services.training import TrainingService
        @lru_cache(maxsize=1)
        def compiler():
            from .compiler import Compiler
            from .connectome import Connectome
            return Compiler(Connectome())
        self.training = TrainingService(store, compiler)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        # The child owns its lease; shutdown leaves it to finish its current match.

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.training.tick()
                from .services.experiments import ExperimentRepository
                research_claim = ExperimentRepository(self.store).claim()
                if research_claim:
                    ident, lease, generation = research_claim
                    folder = self.store.root / 'research' / 'runs' / ident / str(generation)
                    folder.mkdir(parents=True, exist_ok=True)
                    with (folder / 'worker.log').open('a') as log:
                        self.process = subprocess.Popen([sys.executable, '-m', 'flyarena.services.research_job',
                            str(self.store.root), ident, lease, str(generation)], stdout=log, stderr=subprocess.STDOUT)
                        while self.process.poll() is None and not self.stop_event.wait(.5):
                            pass
                    continue
                claim = self.store.claim()
                if claim:
                    ident, lease, generation = claim
                    folder = self.store.root / "runs" / ident / str(generation)
                    folder.mkdir(parents=True, exist_ok=True)
                    with (folder / "worker.log").open("w") as log:
                        self.process = subprocess.Popen([sys.executable, "-m", "flyarena.job", ident, lease, str(generation), str(self.store.root)],
                                                         stdout=log, stderr=subprocess.STDOUT)
                        while self.process.poll() is None and not self.stop_event.wait(.5):
                            pass
            except Exception:
                import traceback
                traceback.print_exc()
            self.stop_event.wait(.75)
