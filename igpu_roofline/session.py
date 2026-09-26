"""One measurement session on one device.

Results are append-only: every configuration gets a key (name + hash of its full
config); an existing result is reused, an unfinished raw file stops the run rather
than being overwritten. That is what makes `run` resumable.
"""

import hashlib
import json
import shutil
import statistics
import subprocess
import tarfile
import time

from . import admission, paths
from .device import run_owned, utc_now
from .locking import DeviceLock
from .measure import accounting, differential, stats
from .timing import record_timing


def wait_for_runner(proc, device, executable, limit, telemetry):
    """Wake on process exit, a telemetry deadline, or the timeout (no 1 s polling)."""
    started = time.monotonic()
    next_telemetry = started + 10
    while proc.poll() is None:
        now = time.monotonic()
        remaining = limit - (now - started)
        if remaining <= 0:
            device.stop(proc)
            raise TimeoutError(f"{executable} exceeded {limit:.0f} s")
        try:
            proc.wait(timeout=min(remaining, max(0.001, next_telemetry - now)))
        except subprocess.TimeoutExpired:
            if time.monotonic() >= next_telemetry:
                telemetry.append(device.telemetry())
                next_telemetry = time.monotonic() + 10


class Session:
    def __init__(self, device, results_root, plan: str = "quick"):
        self.device = device
        self.plan = plan
        self._device_lock = DeviceLock(device.identity)
        try:
            self.out = results_root / device.serial
            self.out.mkdir(parents=True, exist_ok=True)
            self._lock = DeviceLock(str(self.out), path=self.out / "owner.lock")
        except BaseException:
            self._device_lock.close()
            raise
        try:
            self.manifest = json.loads(paths.SHADER_MANIFEST.read_text())
            self.runner_sha = paths.digest(paths.RUNNER)
            self.sustained_sha = paths.digest(paths.RUNNER_SUSTAINED)
            self.caps = None
            self.guard = (
                None  # stages.Guard: thermal pacing and sentinel checks around run()
            )
            cap_file = self.out / "capabilities.json"
            if cap_file.exists():
                self.caps = json.loads(cap_file.read_text())
            if self.caps and device.kind == "local":
                previous = self.caps.get("device_uuid")
                if previous and device.identity != f"vulkan:{previous}":
                    raise ValueError(
                        "Results directory belongs to another GPU UUID; use a new results directory"
                    )
        except BaseException:
            self.close()
            raise

    def close(self):
        self._lock.close()
        self._device_lock.close()

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
                raise RuntimeError(
                    f"{binary.name}: on-device SHA-256 does not match the local build"
                )

        manifest: dict = {
            str(p.relative_to(paths.REPO)): paths.digest(p)
            for p in sorted(paths.REPO.glob("runner/src/*"))
            + sorted(paths.SHADER_SRC.glob("*.comp"))
            + [paths.RUNNER, paths.SHADER_MANIFEST]
        }
        manifest["git_commit"] = paths.git_commit()
        manifest["runner_sha256"] = self.runner_sha
        manifest["sustained_runner_sha256"] = self.sustained_sha
        # Earlier builds remain provenance, but cannot define current roofs.
        old = self.out / "artifact-manifest.json"
        history = []
        if old.exists():
            prev = json.loads(old.read_text())
            history = prev.get("runner_history", [])
            prev_sha = paths.manifest_runner(prev)
            if (
                prev_sha
                and prev_sha != self.runner_sha
                and prev_sha not in [h["sha256"] for h in history]
            ):
                history.append(
                    {
                        "sha256": prev_sha,
                        "git_commit": prev.get("git_commit"),
                        "replaced_utc": utc_now(),
                    }
                )
        manifest["runner_history"] = history
        old.write_text(json.dumps(manifest, indent=2))
        # SPIR-V SHA of every variant as deployed: rows measured with another build of a
        # shader are stale and never define a roof (see Session.current()).
        (self.out / "shader-shas.json").write_text(
            json.dumps(
                {m["name"]: m["spirv_sha256"] for m in self.manifest},
                indent=2,
                sort_keys=True,
            )
        )

        # Keep the exact binary and sources that produced these results.
        archive = self.out / "artifacts" / self.runner_sha[:16]
        if not archive.exists():
            archive.mkdir(parents=True)
            shutil.copy2(paths.RUNNER, archive / "roofline")
            with tarfile.open(archive / "source.tar.gz", "w:gz") as tf:
                for p in ["runner", "shaders", "igpu_roofline"]:
                    tf.add(
                        paths.REPO / p,
                        arcname=p,
                        filter=lambda t: None if "__pycache__" in t.name else t,
                    )
                tf.add(paths.SHADER_MANIFEST, arcname="build/shader-manifest.json")

    def capabilities(self) -> dict:
        d = self.device
        r = run_owned(d, "roofline", "capabilities", 90)
        if r.returncode:
            raise RuntimeError(f"capabilities failed: {r.stderr}")
        caps = json.loads(
            next(line for line in r.stdout.splitlines() if line.startswith("{"))
        )
        if hasattr(d, "bind_gpu"):
            d.bind_gpu(caps)
        caps.update(
            serial=d.serial,
            backend=d.kind,
            device_properties=d.properties(),
            vkjson=d.vkjson(),
            page_size=d.page_size(),
            clock_state=d.clock_state(),
            capture_utc=utc_now(),
            performance_query_exposed="VK_KHR_performance_query" in caps["extensions"],
            overrides=d.overrides,
        )
        (self.out / "capabilities.json").write_text(json.dumps(caps, indent=2))
        self.caps = caps
        return caps

    def current(self, r: dict) -> bool:
        """Row measured with the current runner and the current build of its shader."""
        return not admission.build_reasons(
            r, self.runner_sha, self._shader_shas, getattr(self, "sustained_sha", None)
        )

    def exclusion_reasons(self, row):
        return admission.reasons(
            row,
            self.runner_sha,
            self._shader_shas,
            getattr(self, "sustained_sha", None),
        )

    @property
    def _shader_shas(self) -> dict:
        if getattr(self, "_shas", None) is None:
            self._shas = {m["name"]: m["spirv_sha256"] for m in self.manifest}
        return self._shas

    # --- configuration helpers --------------------------------------------------------
    def variant(self, name: str) -> dict:
        return next(m for m in self.manifest if m["name"] == name)

    def variants(self, **match) -> list[dict]:
        return [
            m for m in self.manifest if all(m.get(k) == v for k, v in match.items())
        ]

    def eligible(self, m: dict) -> bool:
        if m["family"] != "matrix":
            return True
        # VkComponentTypeKHR: float16=0, float32=1, sint8=3, sint32=5; scope 3 = subgroup.
        a = 3 if m["dtype"] == "int8" else 0
        acc = 5 if m["dtype"] == "int8" else 0 if m["dtype"] == "fp16" else 1
        return any(
            x["m"] == m["m"]
            and x["n"] == m["matrix_n"]
            and x["k"] == m["k"]
            and x["a"] == a
            and x["b"] == a
            and x["c"] == acc
            and x["result"] == acc
            and x["scope"] == 3
            for x in (self.caps or {}).get("matrix_shapes", [])
        )

    def base(self, m: dict, warmup_seconds: float = 0.0) -> dict:
        c: dict = dict(
            m,
            wg=64,
            groups=256,
            n=1024,
            loops=128,
            samples=21,
            shared_count=1024,
            stride=1,
            runner_sha256=self.runner_sha,
            schema_version=2,
        )
        if warmup_seconds:
            c["warmup_seconds"] = warmup_seconds
        if m["family"] == "matrix":
            c["wg"] = c["subgroup"] = (self.caps or {})["subgroup"]
            if m.get("feed") == "shared":
                c["n"] = m["tiles"]  # buffer holds exactly the staged tile pairs
        return c

    # --- one measurement ----------------------------------------------------------------
    def run(self, c: dict, tag: str) -> dict:
        with record_timing(
            self.out, "configuration", c["name"], stage=tag, plan=self.plan
        ):
            try:
                return self._run(c, tag)
            except BaseException:
                if self.guard:
                    self.guard.invalidate()
                raise

    def _run(self, c: dict, tag: str) -> dict:
        phase_start = time.perf_counter()
        phase_seconds = {}

        def phase(name):
            nonlocal phase_start
            now = time.perf_counter()
            phase_seconds[name] = now - phase_start
            phase_start = now

        folder = self.out / tag
        folder.mkdir(parents=True, exist_ok=True)
        key = (
            c["name"]
            + "_"
            + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:12]
        )
        path, raw = folder / f"{key}.json", folder / f"{key}.jsonl"
        if path.exists():
            return json.loads(path.read_text())
        if raw.exists():
            raise RuntimeError(
                f"Unfinished raw file {raw} is kept for inspection; move it aside to re-measure"
            )

        if self.guard:
            self.guard.before(tag)
        phase("resume_and_guard")
        d = self.device
        (folder / f"{key}.config.json").write_text(json.dumps(c, indent=2))
        d.push(folder / f"{key}.config.json", f"{d.remote}/config.json")
        phase("config_upload")
        executable = c.get("executable", "roofline")
        before, fault_before, start = d.telemetry(), d.faults(), time.time()
        telemetry = [before]
        phase("telemetry_before")
        with raw.open("w") as out, raw.with_suffix(".stderr").open("w") as err:
            proc = d.popen(executable, out, err)
            limit = c.get("duration_seconds", 0) + c.get("warmup_seconds", 0) + 180
            try:
                wait_for_runner(proc, d, executable, limit, telemetry)
            finally:
                if proc.poll() is None or proc.returncode != 0:
                    d.stop(proc)
        phase("runner_process")
        rc = proc.returncode
        fault_after = d.faults()
        telemetry.append(d.telemetry())
        raw.with_suffix(".telemetry.json").write_text(json.dumps(telemetry, indent=2))
        phase("telemetry_after")

        events = [
            json.loads(x) for x in raw.read_text().splitlines() if x.startswith("{")
        ]
        samples = [e for e in events if e.get("event") == "sample"]
        row: dict = {
            "config": c,
            "plan": self.plan,
            "raw": str(raw.relative_to(self.out)),
            "rc": rc,
            "fault_before": fault_before,
            "fault_after": fault_after,
            "fault_delta": None
            if fault_before is None or fault_after is None
            else fault_after - fault_before,
            "wall_seconds": time.time() - start,
            "allocation": next(
                (e for e in events if e.get("event") == "allocation"), None
            ),
            # The pre-sampling warm-up (last one) decides steadiness; all are kept.
            "warmup": next(
                (e for e in reversed(events) if e.get("event") == "warmup"), None
            ),
            "warmups": [e for e in events if e.get("event") == "warmup"],
            "gpu_freq": [t.get("gpu_freq") for t in telemetry],
            "events": [
                e for e in events if e.get("event") not in ("sample", "sample_half")
            ],
        }
        schema = next((e for e in events if e.get("event") == "schema"), {})
        row.update(
            schema_version=schema.get("schema_version", 1),
            validation_scope=schema.get("validation_scope", "historical_pre_only"),
            n=len(samples),
        )
        for phase_name in ("pre", "post"):
            row[f"validation_{phase_name}"] = next(
                (e for e in events if e.get("event") == f"validation_{phase_name}"),
                None,
            )
        row["accepted"] = not admission.validation_reasons(row)
        # Require an ordered post event identifying the actual final sample.
        post = row["validation_post"]
        if samples and post:
            row["accepted"] = row["accepted"] and (
                post.get("sample") == samples[-1]["sample"]
                and post.get("loops") == samples[-1]["loops"]
                and events.index(post) > events.index(samples[-1])
                and events.index(row["validation_pre"]) < events.index(samples[0])
            )
        if samples:
            row.update(stats([s["seconds"] for s in samples]))
            row["effective_loops"] = samples[0]["loops"]
            # Calibration may raise dispatches per sample when a loop count is capped
            # (bounded FP16 accumulation); account for the batch the runner actually used.
            batch = samples[0].get("batch_dispatches", c.get("batch_dispatches", 1))
            row["batch_dispatches"] = batch
            row["accounting"] = accounting(
                dict(c, batch_dispatches=batch), samples[0]["loops"]
            )
            row["below_target_duration"] = row["median_seconds"] < 0.8 * c.get(
                "target_seconds", 0.005
            )
            # Drift within the sample series (a clock still ramping or throttling):
            # median of the last third relative to the first third.
            times = [s["seconds"] for s in samples]
            if len(times) >= 6 and not c.get("duration_seconds"):
                third = len(times) // 3
                row["sample_drift"] = (
                    statistics.median(times[:third]) / statistics.median(times[-third:])
                    - 1
                )
            halves = {e["sample"]: e for e in events if e.get("event") == "sample_half"}
            if halves:
                row["differential"] = differential(samples, halves)
            if c.get("duration_seconds", 0) > 0:
                last = samples[-1]["elapsed_seconds"]
                tail = [
                    s["seconds"] for s in samples if s["elapsed_seconds"] >= last - 60
                ]
                row["last60"] = stats(tail)
                a, b = (
                    statistics.median(tail[: max(1, len(tail) // 2)]),
                    statistics.median(tail[len(tail) // 2 :]),
                )
                row["steady_last60"] = (
                    len(tail) >= 2
                    and last >= c["duration_seconds"]
                    and abs(b / a - 1) <= 0.05
                    and row["last60"]["cv"] <= 0.1
                )
                row["gpu_timestamp_duty_fraction"] = (
                    sum(s["seconds"] for s in samples) / last
                )
        row["exclusion_reasons"] = self.exclusion_reasons(row)
        phase("analysis")
        row["phase_seconds"] = phase_seconds
        row["runner_observed_seconds"] = {
            "warmup_wall": sum(
                e.get("wall_seconds", 0) for e in events if e.get("event") == "warmup"
            ),
            "sampled_gpu": sum(
                e["seconds"]
                for e in events
                if e.get("event") in ("sample", "sample_half")
            ),
        }
        path.write_text(json.dumps(row, indent=2))

        stderr = raw.with_suffix(".stderr").read_text()
        if rc != 0 and ("vkQueueSubmit" in stderr or "vkWaitForFences" in stderr):
            raise RuntimeError(
                f"GPU submission/completion failed (device lost?); inspect {raw.with_suffix('.stderr')}"
            )
        if row["fault_delta"]:
            raise RuntimeError(
                f"GPU fault counter increased during {key}; stop and investigate"
            )
        status = "PASS" if row["accepted"] else "REJECT"
        print(
            f"{d.serial} {tag} {c['name']} {status} {row.get('median_seconds', 0) * 1e3:.4f} ms",
            flush=True,
        )
        if self.guard:
            self.guard.after(tag)
        return row
