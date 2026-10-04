"""Thread-safe, atomic JSON persistence for one local application process."""
import copy
import json
import os
import tempfile
import threading
from pathlib import Path

class JsonStore:
    def __init__(self, path, default, validator=None):
        self.path = Path(path)
        self.default = default
        self.validator = validator
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists():
            return copy.deepcopy(self.default)
        with self.path.open(encoding="utf-8") as f:
            data = json.load(f)
        return self.validator(data) if self.validator else data

    def _write(self, data):
        data = self.validator(data) if self.validator else data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".json-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def read(self):
        with self.lock:
            return self._read()

    def write(self, data):
        with self.lock:
            self._write(data)

    def update(self, fn):
        with self.lock:
            data = self._read()
            result = fn(data)
            self._write(data)
            return result
