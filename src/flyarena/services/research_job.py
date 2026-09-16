"""Isolated whole-trial worker entry point; never runs in an HTTP handler."""
from __future__ import annotations
from pathlib import Path
import sys
import threading
from ..common import DATA
from ..compiler import Compiler
from ..connectome import Connectome
from ..store import Store
from .research_service import ResearchService


def main():
    root, ident, lease, generation = sys.argv[1:5]
    generation = int(generation)
    store = Store(Path(root))
    compiler = Compiler(Connectome(data=DATA))
    service = ResearchService(store,lambda:compiler)
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(30):
            try:
                service.repository.heartbeat(ident,lease,generation)
            except RuntimeError:
                return
    thread = threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    try:
        service.execute_claim((ident,lease,generation))
    finally:
        stop.set(); thread.join(timeout=1)


if __name__ == '__main__':
    main()
