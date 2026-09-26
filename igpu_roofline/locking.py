"""Host/user-wide device locks, independent of campaign and staging paths."""

import fcntl
import hashlib
import json
import os
from pathlib import Path


class DeviceLock:
    def __init__(self, identity, *, path=None):
        if path is None:
            root = Path(f"/tmp/igpu-roofline-locks-{os.getuid()}")
            root.mkdir(mode=0o700, exist_ok=True)
            path = root / (hashlib.sha256(identity.encode()).hexdigest() + ".lock")
        self.file = path.open("a+")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            self.file.seek(0)
            owner = self.file.read().strip()
            self.file.close()
            raise RuntimeError(
                f"{identity}: device/results lock occupied by {owner}"
            ) from e
        self.file.seek(0)
        self.file.truncate()
        self.file.write(json.dumps({"pid": os.getpid(), "device": identity}))
        self.file.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
