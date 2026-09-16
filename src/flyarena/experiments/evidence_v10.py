"""Exclusive, fixed numeric evidence schema with exception-safe prefix retention.

The producer never passes caller-supplied keyword names into NumPy. A chunk's
field names live in a separately frozen schema; archives contain only values and
ticks. Invalid/failing states are separate from the initialized valid prefix.
"""
from __future__ import annotations
from pathlib import Path
import json
import time
import traceback
import numpy as np
from ..common import file_sha, write_json


class NumericEvidence:
    def __init__(self, root: Path, width: int, *, chunk_size=1000, metadata=None):
        root.mkdir(parents=True, exist_ok=False)
        self.root, self.width, self.chunk_size = root, width, chunk_size
        self.values = np.empty((chunk_size, width), dtype=np.float64)
        self.ticks = np.empty(chunk_size, dtype=np.int64)
        self.n = self.total = self.chunk = 0
        self.files = {}
        self.errors = []
        self.started = time.monotonic()
        write_json(root / "start.json", metadata or {})

    def append(self, tick, values):
        a = np.asarray(values)
        if a.shape != (self.width,) or a.dtype.kind not in "fiub" or not np.isfinite(a).all():
            raise ValueError("invalid/nonfinite scientific row")
        if type(tick) is not int or tick < 0:
            raise ValueError("invalid integer tick")
        if self.n == self.chunk_size:
            self.flush()
        self.values[self.n] = a
        self.ticks[self.n] = tick
        self.n += 1
        self.total += 1

    def flush(self):
        if not self.n:
            return
        path = self.root / f"chunk-{self.chunk:05d}.npz"
        with path.open("xb") as f:
            np.savez_compressed(f, ticks=self.ticks[:self.n], values=self.values[:self.n])
        self.files[path.name] = file_sha(path)
        self.chunk += 1
        self.n = 0

    def finish(self, error=None, *, failing_values=None, snapshot=None, extra=None):
        """Always attempt prefix, failure state and terminal independently.

        snapshot is an OPTIONAL terminal snapshot supplier, not a physics callback.
        Its failure cannot erase the prefix or the original exception.
        """
        primary = None if error is None else {"type": type(error).__name__, "message": str(error),
                    "traceback": "".join(traceback.format_exception(error))}
        try:
            try:
                self.flush()
            except BaseException as exc:
                self.errors.append({"stage": "prefix", "type": type(exc).__name__, "message": str(exc)})
                # Separate emergency numeric prefix if the regular chunk writer failed.
                try:
                    with (self.root / "emergency-prefix.npz").open("xb") as f:
                        np.savez(f, ticks=self.ticks[:self.n], values=self.values[:self.n])
                except BaseException as fallback:
                    self.errors.append({"stage": "emergency-prefix", "message": str(fallback)})
            if failing_values is not None:
                try:
                    a = np.asarray(failing_values, dtype=np.float64)
                    with (self.root / "failing-state.npz").open("xb") as f:
                        np.savez(f, values=a)
                    self.files["failing-state.npz"] = file_sha(self.root / "failing-state.npz")
                except BaseException as exc:
                    self.errors.append({"stage": "failing-state", "message": str(exc)})
            if snapshot is not None:
                try:
                    a = np.asarray(snapshot(), dtype=np.float64)
                    with (self.root / "terminal-state.npz").open("xb") as f:
                        np.savez(f, values=a)
                    self.files["terminal-state.npz"] = file_sha(self.root / "terminal-state.npz")
                except BaseException as exc:
                    self.errors.append({"stage": "optional-snapshot", "message": str(exc)})
        finally:
            write_json(self.root / "terminal.json", {
                "schema": "numeric-evidence-terminal/v10", "complete": primary is None and not self.errors,
                "primary_failure": primary, "retention_failures": self.errors,
                "initialized_rows": self.total, "files": self.files,
                "wall_seconds": time.monotonic() - self.started, "extra": extra or {}})
        return json.loads((self.root / "terminal.json").read_text())
