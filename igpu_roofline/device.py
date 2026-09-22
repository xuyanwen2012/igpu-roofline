"""Device backends.

`AdbDevice` runs the runner on an Android device through adb. `LocalDevice` runs
it on the host's own GPU (e.g. a Linux iGPU); the interface is the same so the
stages do not care where the GPU is.

Nothing here changes device settings: clocks are only read. Pin clocks yourself
beforehand if you want (see tools/pin_gpu_clock.sh); the results record whether
they were pinned.
"""
import datetime
import glob
import hashlib
import json
import os
import pathlib
import re
import shutil
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
    """The host's own GPU (Linux iGPU such as Radeon 780M), same interface as AdbDevice.

    "Remote" paths are a local staging directory; commands run through bash. GPU
    clocks, busy % and temperature come from amdgpu sysfs when present (read only).
    """
    kind = "local"
    # Thermal pacing thresholds (see stages.PACE): a mini PC's iGPU idles near 45 C,
    # so the phone thresholds would stall every configuration.
    pace = dict(start_above_c=85.0, resume_below_c=75.0, max_wait_s=600)

    def __init__(self, name: str | None = None, overrides: dict | None = None):
        import socket
        self.overrides = overrides or {}
        self.card = self._amdgpu_card()
        gpu = (self._read(f"{self.card}/device/product_name") if self.card else "") or "gpu"
        self.serial = name or f"{socket.gethostname()}-{re.sub(r'[^A-Za-z0-9]+', '-', gpu).strip('-').lower() or 'gpu'}"
        self.remote = str(pathlib.Path(os.environ.get("IGPU_ROOFLINE_STAGE", "~/.cache/igpu-roofline/stage")).expanduser())
        pathlib.Path(self.remote).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read(path: str) -> str:
        try:
            return pathlib.Path(path).read_text().strip()
        except OSError:
            return ""

    @staticmethod
    def _amdgpu_card() -> str | None:
        for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
            if pathlib.Path(card, "device/pp_dpm_sclk").exists():
                return card
        return None

    # --- transport -------------------------------------------------------------
    def shell(self, command: str, timeout=90):
        return subprocess.run(["bash", "-c", command], capture_output=True, text=True, timeout=timeout)

    def push(self, local: pathlib.Path, remote: str):
        shutil.copy2(local, remote)

    def remote_sha256(self, remote: str) -> str:
        return hashlib.sha256(pathlib.Path(remote).read_bytes()).hexdigest()

    def popen(self, executable: str, stdout, stderr):
        return subprocess.Popen(["bash", "-c", f"cd {self.remote} && ./{executable} config.json"], stdout=stdout, stderr=stderr)

    def kill(self, executable: str):
        subprocess.run(["pkill", "-x", executable], capture_output=True)

    # --- device facts ------------------------------------------------------------
    def properties(self) -> dict:
        osr = dict(line.split("=", 1) for line in self._read("/etc/os-release").splitlines() if "=" in line)
        cpu = next((line.split(":", 1)[1].strip() for line in self._read("/proc/cpuinfo").splitlines()
                    if line.startswith("model name")), "")
        # Same keys as Android so the report header works unchanged.
        return {"ro.product.manufacturer": "host", "ro.product.model": cpu,
                "ro.build.version.release": osr.get("PRETTY_NAME", "").strip('"'),
                "ro.soc.model": cpu, "kernel": os.uname().release,
                "gpu_product": self._read(f"{self.card}/device/product_name") if self.card else ""}

    def vkjson(self) -> dict | None:
        return None

    def page_size(self) -> int:
        return os.sysconf("SC_PAGE_SIZE")

    def _dpm(self, name: str) -> tuple[list[int], int | None]:
        levels, cur = [], None
        for line in self._read(f"{self.card}/device/{name}").splitlines():
            m = re.match(r"\s*\d+:\s*(\d+)Mhz(\s*\*)?", line)
            if m:
                levels.append(int(m[1]))
                if m[2]:
                    cur = int(m[1])
        return levels, cur

    def clock_state(self) -> dict:
        domains = {}
        if self.card:
            level = self._read(f"{self.card}/device/power_dpm_force_performance_level")
            for name in ("pp_dpm_sclk", "pp_dpm_mclk"):
                levels, cur = self._dpm(name)
                if levels:
                    domains[f"{self.card}/device/{name}"] = dict(governor=level, min=str(min(levels) * 10**6),
                                                                max=str(max(levels) * 10**6),
                                                                cur=str(cur * 10**6) if cur else None)
        # amdgpu is pinned only with a manual/peak performance level (needs root).
        pinned = [p for p, d in domains.items() if d["governor"] in ("profile_peak", "manual")]
        return dict(domains=domains, pinned_domains=pinned, captured_utc=utc_now())

    def gpu_freq(self) -> dict:
        out = {}
        for name in ("pp_dpm_sclk", "pp_dpm_mclk"):
            _, cur = self._dpm(name) if self.card else ([], None)
            if cur:
                out[f"{self.card}/device/{name}"] = str(cur * 10**6)
        return out

    def faults(self) -> int | None:
        return None

    def _temps(self) -> dict:
        temps = {}
        for hw in glob.glob("/sys/class/hwmon/hwmon*"):
            name = self._read(f"{hw}/name")
            for t in glob.glob(f"{hw}/temp*_input"):
                label = self._read(t.replace("_input", "_label")) or pathlib.Path(t).name
                try:
                    temps[f"{name}:{label}"] = int(self._read(t)) / 1000
                except ValueError:
                    pass
        return temps

    def gpu_temp_c(self) -> float | None:
        vals = [v for k, v in self._temps().items() if k.startswith("amdgpu")]
        return max(vals) if vals else None

    def telemetry(self) -> dict:
        temps = self._temps()
        busy = self._read(f"{self.card}/device/gpu_busy_percent") if self.card else ""
        text = "\n".join([f"{k} {v}" for k, v in sorted(temps.items())] + [f"gpu_busy_percent {busy}",
                          "loadavg " + self._read("/proc/loadavg")])
        return dict(utc=utc_now(), temperatures_c=temps, gpu_freq=self.gpu_freq(), gpu_busy_percent=busy, text=text)
