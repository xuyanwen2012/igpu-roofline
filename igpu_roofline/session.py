"""One measurement session on one device.

Results are append-only: every configuration gets a key (name + hash of its full
config); an existing result is reused, an unfinished raw file stops the run rather
than being overwritten. That is what makes `run` resumable.
"""
import fcntl
import hashlib
import json
import shutil
import statistics
import tarfile
import time

from . import paths
from .device import utc_now
from .measure import accounting, differential, stats


class Session:
    def __init__(self, device, results_root, plan: str = "quick"):
        self.device = device
        self.plan = plan
        self.out = results_root / device.serial
        self.out.mkdir(parents=True, exist_ok=True)
        self._lock = (self.out / "owner.lock").open("w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"{device.serial}: another igpu-roofline process owns this device")
        self.manifest = json.loads(paths.SHADER_MANIFEST.read_text())
        self.runner_sha = paths.digest(paths.RUNNER)
        self.caps = None
        self.guard = None  # stages.Guard: thermal pacing and sentinel checks around run()
        cap_file = self.out / "capabilities.json"
        if cap_file.exists():
            self.caps = json.loads(cap_file.read_text())

    # --- setup --------------------------------------------------------------------
    def deploy(self):
        d = self.device
        d.shell(f"mkdir -p {d.remote}/shaders")
        for spv in sorted(paths.SHADER_OUT.glob("*.spv")):
            d.push(spv, f"{d.remote}/shaders/{spv.name}")
        for binary in (paths.RUNNER, paths.RUNNER_SUSTAINED, paths.INSPECT):
            d.push(binary, f"{d.remote}/{binary.name}")
            d.shell(f"chmod 755 {d.remote}/{binary.name}")
            if d.remote_sha256(f"{d.remote}/{binary.name}") != paths.digest(binary):
                raise RuntimeError(f"{binary.name}: on-device SHA-256 does not match the local build")

        manifest: dict = {str(p.relative_to(paths.REPO)): paths.digest(p)
                    for p in sorted(paths.REPO.glob("runner/src/*")) + sorted(paths.SHADER_SRC.glob("*.comp"))
                    + [paths.RUNNER, paths.SHADER_MANIFEST]}
        manifest["git_commit"] = paths.git_commit()
        # Earlier runners that produced results here stay valid; each row names its runner.
        old = self.out / "artifact-manifest.json"
        history = []
        if old.exists():
            prev = json.loads(old.read_text())
            history = prev.get("runner_history", [])
            prev_sha = prev.get("build/android/roofline")
            if prev_sha and prev_sha != self.runner_sha and prev_sha not in [h["sha256"] for h in history]:
                history.append(dict(sha256=prev_sha, git_commit=prev.get("git_commit"), replaced_utc=utc_now()))
        manifest["runner_history"] = history
        old.write_text(json.dumps(manifest, indent=2))

        # Keep the exact binary and sources that produced these results.
        archive = self.out / "artifacts" / self.runner_sha[:16]
        if not archive.exists():
            archive.mkdir(parents=True)
            shutil.copy2(paths.RUNNER, archive / "roofline")
            with tarfile.open(archive / "source.tar.gz", "w:gz") as tf:
                for p in ["runner", "shaders", "igpu_roofline"]:
                    tf.add(paths.REPO / p, arcname=p, filter=lambda t: None if "__pycache__" in t.name else t)
                tf.add(paths.SHADER_MANIFEST, arcname="build/shader-manifest.json")

    def capabilities(self) -> dict:
        d = self.device
        r = d.shell(f"{d.remote}/roofline capabilities")
        if r.returncode:
            raise RuntimeError(f"capabilities failed: {r.stderr}")
        caps = json.loads(next(line for line in r.stdout.splitlines() if line.startswith("{")))
        caps.update(serial=d.serial, backend=d.kind, device_properties=d.properties(), vkjson=d.vkjson(),
                    page_size=d.page_size(), clock_state=d.clock_state(), capture_utc=utc_now(),
                    performance_query_exposed="VK_KHR_performance_query" in caps["extensions"],
                    overrides=d.overrides)
        (self.out / "capabilities.json").write_text(json.dumps(caps, indent=2))
        self.caps = caps
        return caps

    # --- configuration helpers --------------------------------------------------------
    def variant(self, name: str) -> dict:
        return next(m for m in self.manifest if m["name"] == name)

    def variants(self, **match) -> list[dict]:
        return [m for m in self.manifest if all(m.get(k) == v for k, v in match.items())]

    def eligible(self, m: dict) -> bool:
        if m["family"] != "matrix":
            return True
        # VkComponentTypeKHR: float16=0, float32=1, sint8=3, sint32=5; scope 3 = subgroup.
        a = 3 if m["dtype"] == "int8" else 0
        acc = 5 if m["dtype"] == "int8" else 0 if m["dtype"] == "fp16" else 1
        return any(x["m"] == m["m"] and x["n"] == m["matrix_n"] and x["k"] == m["k"] and x["a"] == a
                   and x["b"] == a and x["c"] == acc and x["result"] == acc and x["scope"] == 3
                   for x in (self.caps or {}).get("matrix_shapes", []))

    def base(self, m: dict, warmup_seconds: float = 0.0) -> dict:
        c: dict = dict(m, wg=64, groups=256, n=1024, loops=128, samples=21, shared_count=1024, stride=1,
                 runner_sha256=self.runner_sha)
        if warmup_seconds:
            c["warmup_seconds"] = warmup_seconds
        if m["family"] == "matrix":
            c["wg"] = (self.caps or {})["subgroup"]
        return c

    # --- one measurement ----------------------------------------------------------------
    def run(self, c: dict, tag: str) -> dict:
        folder = self.out / tag
        folder.mkdir(parents=True, exist_ok=True)
        key = c["name"] + "_" + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:12]
        path, raw = folder / f"{key}.json", folder / f"{key}.jsonl"
        if path.exists():
            return json.loads(path.read_text())
        if raw.exists():
            raise RuntimeError(f"Unfinished raw file {raw} is kept for inspection; move it aside to re-measure")

        if self.guard:
            self.guard.before(tag)
        d = self.device
        (folder / f"{key}.config.json").write_text(json.dumps(c, indent=2))
        d.push(folder / f"{key}.config.json", f"{d.remote}/config.json")
        executable = c.get("executable", "roofline")
        before, fault_before, start = d.telemetry(), d.faults(), time.time()
        telemetry = [before]
        with raw.open("w") as out, raw.with_suffix(".stderr").open("w") as err:
            proc = d.popen(executable, out, err)
            limit = c.get("duration_seconds", 0) + c.get("warmup_seconds", 0) + 180
            try:
                while proc.poll() is None:
                    time.sleep(1)
                    if time.time() - start > limit:
                        d.kill(executable)
                        proc.kill()
                        raise TimeoutError(f"{key} exceeded {limit:.0f} s")
                    if time.time() - start >= len(telemetry) * 10:
                        telemetry.append(d.telemetry())
            finally:
                if proc.poll() is None:
                    proc.kill()
        rc = proc.returncode
        fault_after = d.faults()
        telemetry.append(d.telemetry())
        raw.with_suffix(".telemetry.json").write_text(json.dumps(telemetry, indent=2))

        events = [json.loads(x) for x in raw.read_text().splitlines() if x.startswith("{")]
        samples = [e for e in events if e.get("event") == "sample"]
        row: dict = dict(config=c, plan=self.plan, raw=str(raw.relative_to(self.out)), rc=rc,
                   fault_before=fault_before, fault_after=fault_after,
                   fault_delta=None if fault_before is None or fault_after is None else fault_after - fault_before,
                   wall_seconds=time.time() - start,
                   allocation=next((e for e in events if e.get("event") == "allocation"), None),
                   warmup=next((e for e in events if e.get("event") == "warmup"), None),
                   gpu_freq=[t.get("gpu_freq") for t in telemetry],
                   events=[e for e in events if e.get("event") not in ("sample", "sample_half")])
        # Exact results are required except for float reductions whose summation order
        # legitimately differs from the host (FMA chains, BabelStream Dot); those use the
        # runner's relative tolerance.
        float_reduction = c["family"] == "alu" or (c["family"] == "memory" and c.get("op") == 6)
        row["accepted"] = (rc == 0 and bool(samples) and row["fault_delta"] in (None, 0)
                           and all(s["validation"]["pass"] and (float_reduction or s["validation"]["max_abs_error"] == 0)
                                   for s in samples))
        if samples:
            row.update(stats([s["seconds"] for s in samples]))
            row["effective_loops"] = samples[0]["loops"]
            # Calibration may raise dispatches per sample when a loop count is capped
            # (bounded FP16 accumulation); account for the batch the runner actually used.
            batch = samples[0].get("batch_dispatches", c.get("batch_dispatches", 1))
            row["batch_dispatches"] = batch
            row["accounting"] = accounting(dict(c, batch_dispatches=batch), samples[0]["loops"])
            row["below_target_duration"] = row["median_seconds"] < 0.8 * c.get("target_seconds", 0.005)
            halves = {e["sample"]: e for e in events if e.get("event") == "sample_half"}
            if halves:
                row["differential"] = differential(samples, halves)
            if c.get("duration_seconds", 0) > 0:
                last = samples[-1]["elapsed_seconds"]
                tail = [s["seconds"] for s in samples if s["elapsed_seconds"] >= last - 60]
                row["last60"] = stats(tail)
                a, b = statistics.median(tail[: len(tail) // 2]), statistics.median(tail[len(tail) // 2:])
                row["steady_last60"] = abs(b / a - 1) <= 0.05 and row["last60"]["cv"] <= 0.1
                row["gpu_timestamp_duty_fraction"] = sum(s["seconds"] for s in samples) / last
        path.write_text(json.dumps(row, indent=2))

        stderr = raw.with_suffix(".stderr").read_text()
        if rc != 0 and ("vkQueueSubmit" in stderr or "vkWaitForFences" in stderr):
            raise RuntimeError(f"GPU submission/completion failed (device lost?); inspect {raw.with_suffix('.stderr')}")
        if row["fault_delta"]:
            raise RuntimeError(f"GPU fault counter increased during {key}; stop and investigate")
        status = "PASS" if row["accepted"] else "REJECT"
        print(f"{d.serial} {tag} {c['name']} {status} {row.get('median_seconds', 0) * 1e3:.4f} ms", flush=True)
        if self.guard:
            self.guard.after(tag)
        return row
