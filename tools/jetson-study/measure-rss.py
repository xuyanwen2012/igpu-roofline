"""Portable-to-Jetson replacement for /usr/bin/time when that package is absent."""

import resource
import subprocess
import sys

result = subprocess.run(sys.argv[1:])
# Linux reports ru_maxrss in KiB. This fresh wrapper runs exactly one child.
print(
    f"JETSON_MAX_RSS_KB={resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}",
    flush=True,
)
raise SystemExit(
    result.returncode if result.returncode >= 0 else 128 - result.returncode
)
