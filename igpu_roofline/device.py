"""Device backends.

`AdbDevice` runs the runner on an Android device through adb. `LocalDevice` (run
on the host's own GPU, e.g. a Linux iGPU) is a planned second backend; the
interface is the same so the stages do not care where the GPU is.

Nothing here changes device settings: clocks are only read. Pin clocks yourself
beforehand if you want (see tools/pin_gpu_clock.sh); the results record whether
they were pinned.
"""
import datetime
import json
import pathlib
import re
import subprocess

from . import paths

# GPU clock sources readable without root. Missing ones are skipped.
FREQ_GLOBS = ["/sys/class/kgsl/kgsl-3d0/devfreq", "/sys/class/devfreq/*",
              "/sys/class/misc/mali0/device"]
EXTRA_FREQ_FILES = ["/sys/kernel/gpu/gpu_clock", "/sys/kernel/gpu/gpu_max_clock", "/sys/kernel/gpu/gpu_min_clock"]


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def list_adb_devices() -> list[dict]:
    out = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True).stdout
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            info = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
            devices.append(dict(serial=parts[0], model=info.get("model", "?"), product=info.get("product", "?")))
    return devices


class AdbDevice:
    kind = "adb"

    def __init__(self, serial: str, overrides: dict | None = None):
        self.serial = serial
        self.overrides = overrides or {}
        self.adb = ["adb", "-s", serial]
        self.remote = paths.REMOTE_DIR

    # --- transport -------------------------------------------------------------
    def call(self, args, timeout=90):
        return subprocess.run(self.adb + args, capture_output=True, text=True, timeout=timeout)

    def shell(self, command: str, timeout=90):
        return self.call(["shell", command], timeout)

    def push(self, local: pathlib.Path, remote: str):
        r = self.call(["push", str(local), remote], timeout=600)
        if r.returncode:
            raise RuntimeError(f"adb push {local} failed: {r.stderr}")

    def remote_sha256(self, remote: str) -> str:
        return self.shell(f"sha256sum {remote}").stdout.split()[0]

    def popen(self, executable: str, stdout, stderr):
        cmd = f"cd {self.remote} && ./{executable} config.json"
        return subprocess.Popen(self.adb + ["shell", cmd], stdout=stdout, stderr=stderr)

    def kill(self, executable: str):
        pid = self.shell(f"pidof {executable}").stdout.strip()
        if pid:
            self.shell(f"kill {pid}")

    # --- device facts ------------------------------------------------------------
    def properties(self) -> dict:
        keys = ["ro.product.manufacturer", "ro.product.model", "ro.build.version.release",
                "ro.build.version.sdk", "ro.build.fingerprint", "ro.soc.manufacturer", "ro.soc.model"]
        return {k: self.shell(f"getprop {k}").stdout.strip() for k in keys}

    def vkjson(self) -> dict | None:
        try:
            return json.loads(self.shell("cmd gpu vkjson", 60).stdout)
        except ValueError:
            return None

    def page_size(self) -> int:
        return int(self.shell("getconf PAGE_SIZE").stdout.strip() or 4096)

    def clock_state(self) -> dict:
        """Every readable GPU clock domain with governor/min/max/cur; `pinned` when min == max."""
        script = ("for d in " + " ".join(FREQ_GLOBS) + "; do [ -r $d/cur_freq ] || continue; "
                  "echo \"$d|$(cat $d/governor 2>/dev/null)|$(cat $d/min_freq 2>/dev/null)|"
                  "$(cat $d/max_freq 2>/dev/null)|$(cat $d/cur_freq 2>/dev/null)|$(cat $d/name 2>/dev/null)\"; done; "
                  "for f in " + " ".join(EXTRA_FREQ_FILES) + "; do [ -r $f ] && echo \"$f|||||$(cat $f)\"; done")
        domains = {}
        for line in self.shell(script, 30).stdout.splitlines():
            path, governor, lo, hi, cur, *rest = (line.split("|") + [""] * 6)[:6]
            domains[path] = dict(governor=governor or None, min=lo or None, max=hi or None,
                                 cur=cur or (rest[0] if rest else None))
        pinned = [p for p, d in domains.items() if d["min"] and d["min"] == d["max"]]
        return dict(domains=domains, pinned_domains=pinned, captured_utc=utc_now())

    def gpu_freq(self) -> dict:
        paths_ = self.overrides.get("gpu_freq_files") or [g + "/cur_freq" for g in FREQ_GLOBS] + EXTRA_FREQ_FILES[:1]
        r = self.shell("for f in " + " ".join(paths_) + "; do [ -r $f ] && echo \"$f $(cat $f 2>/dev/null)\"; done", 30)
        return {l.split(" ", 1)[0]: l.split(" ", 1)[1] for l in r.stdout.splitlines() if " " in l}

    def faults(self) -> int | None:
        """Adreno GPU fault counter (kgsl); other vendors expose none without root."""
        text = self.shell("cat /sys/class/kgsl/kgsl-3d0/gpufaults 2>/dev/null").stdout.strip()
        try:
            return sum(map(int, text.split())) if text else None
        except ValueError:
            return None

    def gpu_temp_c(self) -> float | None:
        """Hottest current GPU sensor from the thermal HAL (None if the device reports none)."""
        text = self.shell("dumpsys thermalservice", 30).stdout
        current = text.split("Current temperatures from HAL:", 1)[-1].split("Current cooling", 1)[0]
        temps = [float(m[1]) for m in re.finditer(r"Temperature\{mValue=([-\d.]+), mType=\d+, mName=([^,]+),", current)
                 if "gpu" in m[2].lower()]
        return max(temps) if temps else None

    def telemetry(self) -> dict:
        r = self.shell("dumpsys thermalservice; dumpsys battery; cat /proc/meminfo; cat /proc/loadavg", 30)
        text = r.stdout
        # e.g. "Temperature{mValue=38.1, mType=0, mName=cpu0, mStatus=0}"; the last reading per name wins.
        temps = {m[2]: float(m[1]) for m in re.finditer(r"Temperature\{mValue=([-\d.]+), mType=\d+, mName=([^,]+),", text)}
        return dict(utc=utc_now(), temperatures_c=temps, gpu_freq=self.gpu_freq(), text=text)


class LocalDevice:
    """Run on the host's own GPU (Linux iGPU). Planned; see docs/HOW-TO-RUN.md."""
    kind = "local"

    def __init__(self, *_, **__):
        raise NotImplementedError("The local (host GPU) backend is not implemented yet; use an Android device.")
