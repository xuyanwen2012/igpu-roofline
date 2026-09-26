"""Append-only wall-clock timings, including interrupted/failed stages."""

import json
import time
from contextlib import contextmanager

from .device import utc_now


@contextmanager
def record_timing(folder, kind, name, **metadata):
    started = time.perf_counter()
    utc = utc_now()
    status = "failed"
    try:
        yield
        status = "completed"
    finally:
        with (folder / "timings.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    dict(
                        utc=utc,
                        kind=kind,
                        name=name,
                        status=status,
                        wall_seconds=time.perf_counter() - started,
                        **metadata,
                    )
                )
                + "\n"
            )
