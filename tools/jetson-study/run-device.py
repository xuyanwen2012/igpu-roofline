"""Run a bounded Jetson campaign under the shared GPU lock; preserve every attempt."""

import atexit
import contextlib
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

spec = json.load(sys.stdin)
root = Path.home() / ".cache/et-jetson-study"
root.mkdir(exist_ok=True)
lockpath = Path.home() / ".cache/gpu-lab/lock-b49259c9-868c-5b7c-b6f1-65a2bf4b63be"
lock = lockpath.open("a+")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
active = subprocess.check_output(["ps", "-eo", "comm="], text=True).splitlines()
if any(
    x.strip().startswith(("roofline", "llama_main", "test_llama_", "llama-server"))
    for x in active
):
    raise SystemExit("Another GPU workload is active")
spent = 0.0
for previous in root.glob("*/*/result.json"):
    spent += json.loads(previous.read_text()).get("wall_seconds", 0.0)
spec["budget_seconds"] = min(spec.get("budget_seconds", 5400), max(0, 5400 - spent))
print("device budget remaining seconds:", round(5400 - spent, 1), flush=True)
start = time.monotonic()


def memory():
    d = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        d[key] = int(value.split()[0])
    return d


def temperatures(paths):
    values = {}
    for path in paths:
        # Some Orin thermal zones report ENODATA when powered down.
        with contextlib.suppress(OSError, ValueError):
            values[path.parent.name] = int(path.read_text())
    return values


def cleanup_owned():
    process = globals().get("p")
    if process is None or process.poll() is not None:
        return
    scope = globals().get("unit")
    if scope:
        subprocess.run(["systemctl", "--user", "stop", scope + ".scope"], timeout=10)
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


atexit.register(cleanup_owned)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))


for job in spec["jobs"]:
    name = job["name"]
    out = root / spec["campaign"] / name
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "result.json"
    if meta.exists():
        print(name, "preserved existing result", flush=True)
        continue
    if (out / "stdout.log").exists():
        raise SystemExit(f"Preserving incomplete attempt: {out}; use a new campaign")
    required = job.get("requires")
    if required:
        prior = root / spec["campaign"] / required / "result.json"
        if not prior.exists() or json.loads(prior.read_text())["rc"] != 0:
            meta.write_text(
                json.dumps({"rc": 125, "stop_reason": "prerequisite_failed"})
            )
            print(name, "skipped: prerequisite failed", flush=True)
            continue
    if time.monotonic() - start >= spec.get("budget_seconds", 5400):
        print("campaign budget exhausted", flush=True)
        break
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ET_VK_", "ETVK_"))}
    env.update(ETVK_DEVICE_INDEX="0", LD_LIBRARY_PATH=str(root / "bin"))
    env.update(job.get("env", {}))
    argv = [
        a.replace("@ROOT@", str(root)).replace("@OUT@", str(out)) for a in job["argv"]
    ]
    before = memory()
    info = {
        "argv": argv,
        "env": {k: v for k, v in env.items() if k.startswith(("ET_VK_", "ETVK_"))},
        "memory_before_kb": before,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "max_swap_growth_kb": job.get("max_swap_growth_kb", 65536),
    }
    binary = Path(job.get("executable", argv[0]).replace("@ROOT@", str(root)))
    if binary.is_file():
        info["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    unit = None
    if job.get("memory_limited"):
        unit = "et-jetson-" + str(os.getpid()) + "-" + str(time.monotonic_ns())
        limit = max(512 * 1024, before["MemAvailable"] - 1024 * 1024) * 1024
        info["memory_max_bytes"] = limit
        argv = [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            "--unit=" + unit,
            "-p",
            "MemoryMax=" + str(limit),
            "-p",
            "MemorySwapMax=0",
            *argv,
        ]
    thermal_paths = list(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    then = time.monotonic()
    reason = None
    samples = []
    with (out / "stdout.log").open("w") as log:
        p = subprocess.Popen(
            argv,
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        while p.poll() is None:
            mem = memory()
            try:
                clock = int(
                    Path("/sys/class/devfreq/17000000.gpu/cur_freq").read_text()
                )
            except OSError:
                clock = None
            samples.append(
                {
                    "elapsed": time.monotonic() - then,
                    "available_kb": mem["MemAvailable"],
                    "swap_used_kb": mem["SwapTotal"] - mem["SwapFree"],
                    "gpu_hz": clock,
                    "thermal_millic": temperatures(thermal_paths),
                }
            )
            if mem["MemAvailable"] < 1024 * 1024:
                reason = "system_memory_reserve"
            if mem["SwapFree"] < before["SwapFree"] - info["max_swap_growth_kb"]:
                reason = "swap_growth"
            if time.monotonic() - then > job.get("timeout_seconds", 180):
                reason = "job_timeout"
            if time.monotonic() - start > spec.get("budget_seconds", 5400):
                reason = "campaign_budget"
            if reason:
                if unit:
                    subprocess.run(
                        ["systemctl", "--user", "stop", unit + ".scope"], timeout=10
                    )
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                break
            time.sleep(0.1)
        info.update(
            rc=p.wait(),
            stop_reason=reason,
            wall_seconds=time.monotonic() - then,
            memory_after_kb=memory(),
        )
    (out / "telemetry.json").write_text(json.dumps(samples))
    meta.write_text(json.dumps(info, indent=2))
    print(name, info["rc"], reason, round(info["wall_seconds"], 2), flush=True)
    if reason == "campaign_budget":
        break
    if reason in ("system_memory_reserve", "swap_growth"):
        if spec.get("stop_on_memory_pressure", False):
            break
        # Let allocations unwind; never continue if the reserve remains depleted.
        time.sleep(2)
        if memory()["MemAvailable"] < 1024 * 1024:
            break
