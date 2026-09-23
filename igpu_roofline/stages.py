"""Measurement stages and plans.

A plan is an ordered list of stages. Every stage is idempotent (finished
configurations are skipped), so re-running the same plan resumes it.
"""
import datetime
import json
import math
import statistics
import time

from . import paths
from .device import utc_now
from .measure import ARRAYS_PER_OP

MiB = 1024 ** 2

PLANS = {
    # Every family once at its most informative settings; roofs confirmed by 3 repeats
    # of the best candidate; no sustained runs.
    "quick": dict(level="quick", warmup_seconds=0.25, confirm=dict(top=1, reps=3), sustain=None),
    # Only what shader tuning needs (~35-45 min on a phone): compute, WMMA register +
    # fed roofs, DRAM/cache/shared/texture bandwidth, latency levels; top 2 x 3
    # confirmation; 120 s sustained runs of three representative roofs.
    "fast": dict(level="fast", warmup_seconds=0.5, confirm=dict(top=2, reps=3),
                 sustain=dict(batches=1, duration=120, cooldown=60,
                              keys=[["alu_fp16"], ["matrix_fp16_fp32", "matrix_fp16", "matrix_int8"], ["memory_fp32_0"]])),
    # All sweeps, top-3 candidates x 5 repeats per roof, one 300 s sustained run per roof.
    "standard": dict(level="full", warmup_seconds=1.0, confirm=dict(top=3, reps=5),
                     sustain=dict(batches=1, duration=300, cooldown=90)),
    # As standard, with three sustained batches for batch-to-batch repeatability.
    "gold": dict(level="full", warmup_seconds=1.0, confirm=dict(top=3, reps=5),
                 sustain=dict(batches=3, duration=300, cooldown=90)),
}

# A result may define a roof only if its median is precise, its samples are long enough
# and it is not dominated by fixed dispatch cost (see quality()). The gate is on the
# standard error of the median (~1.2533 * CV / sqrt(n)), not on per-sample CV: DRAM and
# shared-memory samples on phones scatter 6-14 % while a 21-sample median stays ~3 %.
QUALITY = dict(max_median_se=0.03, max_fixed_fraction=0.10, max_drift=0.05)


def median_se(r: dict) -> float:
    """Relative standard error of the sample median (normal approximation)."""
    n = r.get("n") or 0
    return 1.2533 * r.get("cv", 1) / n ** 0.5 if n > 1 else 1.0


def is_control(c: dict) -> bool:
    """Comparison variants that never define a roof."""
    return bool(c.get("volatile_global") or c.get("memory_mode", "device_local") != "device_local"
                or (c["family"] == "shared" and c.get("kind") != "bw"))


# --- setup ---------------------------------------------------------------------------
def deploy(s, plan):
    s.deploy()


def capabilities(s, plan):
    s.capabilities()


# --- short-run stages ------------------------------------------------------------------
def validate(s, plan):
    """Small correctness runs of one variant per family (no warm-up)."""
    names = ["mem_read_v4", "mem_write_v4", "mem_copy_v4", "mem_scale_v4", "mem_add_v4", "mem_triad_v4",
             "mem_dot_v4", "mem_copy_v4_volatile", "alu_fp32_v1_c4", "alu_fp32_v4_c4", "alu_fp16_v2_c4",
             "sharedbw_fp32_v4_op0", "sharedbw_fp16_v4_op0", "sharedbw_fp32_v4_op2", "sharedbw_fp16_v1_op2",
             "shared_fp32_v4_op0_xlanes_volatile", "shared_fp32_v4_op1_xlanes_volatile",
             "dot8_c4", "pchase", "ert_f1", "ert_f64"]
    names += [m["name"] for m in s.variants(family="matrix", chains=1) if s.eligible(m)]
    for name in names:
        c = s.base(s.variant(name))
        c.update(groups=32, loops=32, samples=3, calibrate=False)
        if c["family"] == "latency":
            c.update(wg=1, groups=1, n=1 << 16, chain_stride_bytes=64, chain_order="random")
        s.run(c, "validate")
        if name == "mem_copy_v4":
            s.run(dict(c, memory_mode="host_coherent"), "validate")


def first_look(s, plan):
    """One representative configuration per family."""
    if plan["level"] == "fast":
        return  # smoke test only; the sweeps below cover it
    for m in s.manifest:
        f = m["family"]
        pick = ((f == "memory" and m["width"] == 4) or (f == "alu" and m["width"] == 4 and m["chains"] in (4, 8))
                or (f == "shared" and m["width"] == 4 and m.get("accumulators", 8) == 8)
                or (f == "dot" and m["chains"] == 4)
                or (f == "matrix" and not m.get("feed") and m["chains"] in (1, 4) and s.eligible(m)))
        if not pick:
            continue
        c = s.base(m, plan["warmup_seconds"])
        if f == "memory":
            c.update(n=4 * MiB, groups=4096, loops=1)
        if f == "matrix":
            c["groups"] = 512
        s.run(c, "first-look")


def cache(s, plan):
    """Read bandwidth vs working-set size (small sets use replicated workgroups)."""
    quick = plan["level"] in ("quick", "fast")
    for w in ((4,) if quick else (1, 2, 4)):
        m = s.variant(f"mem_read_v{w}")
        for exp in range(12, 30):
            size = 1 << exp
            if size > min(512 * MiB, s.caps["max_storage_buffer_range"]):
                continue
            n = size // (4 * w)
            for wg in ((128,) if quick else (64, 128, 256)):
                base_groups = min(4096, max(1, n // wg))
                rep = max(1, 256 // base_groups)
                c = s.base(m, plan["warmup_seconds"])
                c.update(wg=wg, n=n, groups=base_groups * rep, replicas=rep, loops=1)
                s.run(c, "sweep-cache")


def memory(s, plan):
    """BabelStream kernels over working sets up to 512 MiB (>=256 MiB defines the DRAM roof)."""
    quick = plan["level"] in ("quick", "fast")
    for m in s.manifest:
        if m["family"] != "memory" or m["width"] != 4 or (quick and m.get("volatile_global")):
            continue
        if plan["level"] == "fast" and m["op"] not in (0, 1, 2, 5):
            continue  # read, write, copy, triad
        for exp in ((28, 29) if quick else range(12, 30)):
            arrays = ARRAYS_PER_OP[m["op"]]
            n = (1 << exp) // (arrays * 16) // 64 * 64
            if n * 16 > s.caps["max_storage_buffer_range"]:
                continue
            c = s.base(m, plan["warmup_seconds"])
            c.update(n=n, groups=min(4096, max(1, n // 64)), loops=1)
            s.run(c, "sweep-memory")


def matrix_grid(m: dict, caps: dict, quick: bool) -> list[tuple[int, int]]:
    """(workgroup size, workgroups) points for one cooperative-matrix variant.

    Every data type gets the same grid. One 16-lane subgroup per workgroup and <= 512
    workgroups left Mali-G1 MC12 far from saturated (int8 4x16x16: 2.9 -> 5.3 TOP/s at
    16384 workgroups), so the grid reaches 16384 workgroups and 4 subgroups per group.
    Output is capped at 256 MiB.
    """
    sg = caps["subgroup"]
    out_bytes = m["chains"] * m["m"] * m["matrix_n"] * (2 if m["dtype"] == "fp16" else 4)
    wgs = [sg] if quick else [sg, 4 * sg]
    groups = (4096, 16384) if quick else (64, 512, 4096, 16384)
    return [(wg, g) for wg in wgs for g in groups
            if wg <= caps["max_workgroup_invocations"] and g * out_bytes <= 256 * MiB]


def matrix_coverage(s) -> list[dict]:
    """Device-supported subgroup shapes with no compiled variant (never skipped silently)."""
    names = {(0, 0, 0, 0): "fp16", (0, 0, 1, 1): "fp16_fp32", (3, 3, 5, 5): "int8"}
    have = {(m["m"], m["matrix_n"], m["k"], m["dtype"]) for m in s.variants(family="matrix")}
    missing = [x for x in s.caps.get("matrix_shapes", []) if x["scope"] == 3
               and (x["m"], x["n"], x["k"], names.get((x["a"], x["b"], x["c"], x["result"]))) not in have]
    (s.out / "matrix-coverage.json").write_text(json.dumps(dict(
        device_shapes=s.caps.get("matrix_shapes", []), not_compiled=missing,
        note="Only fp16, fp16->fp32 and int8 (s8 x s8 -> s32) variants are built; other type combinations are listed here."), indent=2))
    return missing


def compute(s, plan):
    """FMA / int8 dot / cooperative matrix over vector width, chains and launch size."""
    quick = plan["level"] in ("quick", "fast")
    missing = matrix_coverage(s)
    if missing:
        print(f"{s.device.serial} matrix shapes supported but not compiled: {len(missing)} (see matrix-coverage.json)", flush=True)
    for m in s.manifest:
        if m["family"] not in ("alu", "dot", "matrix") or not s.eligible(m) or m.get("feed"):
            continue
        if plan["level"] == "fast" and not (
                (m["family"] == "alu" and m["width"] == 4 and m["chains"] in (8, 16))
                or (m["family"] == "dot" and m["chains"] in (4, 8))
                or (m["family"] == "matrix" and m["chains"] in (4, 8))):
            continue  # the chain counts that reached the roof on every device so far
        if m["family"] == "matrix":
            points = matrix_grid(m, s.caps, quick)
        else:
            # 512 x 256 threads did not saturate Mali-G1 MC12 FP32; go to 8192 workgroups.
            points = [(wg, g) for wg in ([256] if quick else [64, 128, 256])
                      for g in ((2048, 8192) if plan["level"] == "fast" else (2048,) if quick
                                else (64, 512, 2048, 8192))]
        for wg, g in points:
            c = s.base(m, plan["warmup_seconds"])
            c.update(wg=wg, groups=g)
            s.run(c, "sweep-compute")


def matrix_feed(s, plan):
    """Cooperative matrix fed by coopMatLoad every iteration (the register-resident
    roof excludes loads): from workgroup memory, from a cache-resident buffer
    (~1 MiB of tiles) and from DRAM (>= 256 MiB of tiles, each tile read once).
    CHAINS = multiply-adds per loaded A/B pair, i.e. reuse per load."""
    quick = plan["level"] in ("quick", "fast")
    for m in s.manifest:
        if m["family"] != "matrix" or not m.get("feed") or not s.eligible(m):
            continue
        ab = 1 if m["dtype"] == "int8" else 2
        tile_bytes = (m["m"] * m["k"] + m["k"] * m["matrix_n"]) * ab
        if m["feed"] == "shared":
            sources = [m["tiles"]]
        else:
            biggest = s.caps["max_storage_buffer_range"] // (max(m["m"] * m["k"], m["k"] * m["matrix_n"]) * ab)
            sources = [max(1, MiB // tile_bytes), min(biggest, -(-256 * MiB // tile_bytes))]
        for tiles in sources:
            for wg, g in matrix_grid(m, s.caps, quick):
                if g < 4096 or (plan["level"] == "fast" and g < 16384):
                    continue  # small launches are covered by the compute sweep
                c = s.base(m, plan["warmup_seconds"])
                c.update(wg=wg, groups=g, n=tiles)
                s.run(c, "sweep-matrix-feed")


def texture(s, plan):
    """Texture vs storage-buffer read bandwidth on the same texels: storage buffer,
    2D and 3D sampled images (texelFetch), RGBA16F and RGBA32F, cache-resident
    (1 MiB) and DRAM-sized (256 MiB) working sets."""
    wgs = (256,) if plan["level"] in ("quick", "fast") else (64, 256)
    for m in s.variants(family="texture"):
        texel = 8 if m["format"] == "rgba16f" else 16
        for ws in (MiB, 256 * MiB):
            n = ws // texel
            if n * texel > s.caps["max_storage_buffer_range"]:
                continue
            for wg in wgs:
                c = s.base(m, plan["warmup_seconds"])
                c.update(wg=wg, groups=4096, n=n, loops=1)
                s.run(c, "sweep-texture")


def shared(s, plan):
    """Workgroup memory: workgroup size, allocation size and stride (bank conflicts)."""
    quick = plan["level"] in ("quick", "fast")
    max_shared = s.caps["max_shared_bytes"]
    fast = plan["level"] == "fast"
    # fast: conflict-free, worst power-of-two and padded stride only.
    strides = (1, 32, 33) if fast else (1, 2, 4, 8, 16, 32, 33, 64, 65)
    for m in s.manifest:
        if m["family"] != "shared":
            continue
        if quick and not (m.get("kind") == "bw" and m["width"] == 4 and m["accumulators"] == 8):
            continue
        scalar = 2 if m["dtype"] == "fp16" else 4
        # Workgroup size and allocation size matter as much as stride (together up to 5x
        # on some GPUs: a small allocation keeps more workgroups resident), so the quick
        # plan sweeps both coarsely.
        points = {(64, max_shared, st) for st in strides}
        points |= {(wg, size, 1) for wg in ((64, 256) if fast else (64, 128, 256)) for size in (4096, max_shared)}
        if not quick:
            points |= {(wg, 4096, 1) for wg in (32, 64, 128, 256)}
            points |= {(64, size, 1) for size in (1024, 2048, 4096, 8192, 16384, max_shared)}
        for wg, size, stride in sorted(points):
            count = size // (m["width"] * scalar)
            if m["op"] and wg * stride > count:
                continue
            c = s.base(m, plan["warmup_seconds"])
            c.update(wg=wg, groups=256, shared_count=count, stride=stride)
            s.run(c, "sweep-shared")


def latency(s, plan):
    """Pointer chasing: capacity/levels, TLB reach and line size (Saavedra).

    Every dispatch walks the whole chain (at least 2^16 and at most 2^20 dependent
    loads): too few loads and fixed dispatch cost dominates; too many serial loads in
    one dispatch trip the driver's GPU watchdog (VK_ERROR_DEVICE_LOST).
    """
    quick = plan["level"] in ("quick", "fast")
    m = s.variants(family="latency")[0]
    limit = min(256 * MiB, s.caps["max_storage_buffer_range"])

    def chase(tag, size, stride, order, min_loops, **extra):
        nodes = size // stride
        # Two passes per dispatch for every order: the differential (L vs L/2 loops) is
        # then one warm pass. One pass per dispatch measured cold lines (Mali-G1: 474 ns
        # at 1 MiB in the line-size test vs 109 ns warm in the capacity test).
        passes = 2
        c = s.base(m, plan["warmup_seconds"])
        c.update(wg=1, groups=1, n=size // 4, calibrate=False, samples=9 if order == "random" else 5,
                 loops=max(min_loops, min(-(-passes * nodes // 16), 65536)),
                 chain_stride_bytes=stride, chain_order=order, **extra)
        s.run(c, tag)

    sizes = [1 << e for e in range(10, 29, 2)] if quick else sorted({x for e in range(10, 29) for x in (1 << e, 3 << (e - 1))})
    for size in sizes:
        if size <= limit:
            chase("latency-capacity", size, 64, "random", 4096)
    if quick:
        return
    page = s.caps.get("page_size", 4096)
    for exp in range(16, 29):
        size = 1 << exp
        if size <= limit and size // page >= 2:
            chase("latency-tlb", size, page, "random", 4096, page_size=page)
    for size in (MiB, 64 * MiB):  # first-level line, last-level/DRAM line
        for stride in (4, 8, 16, 32, 64, 128, 256, 512, 1024):
            chase("latency-stride", size, stride, "sequential", 2)


def ert(s, plan):
    """Empirical Roofline Toolkit sweep: arithmetic intensity 0.25..256 FLOP/byte."""
    if plan["level"] == "fast":
        return
    for m in s.variants(family="ert"):
        for wg in ((256,) if plan["level"] in ("quick", "fast") else (64, 256)):
            c = s.base(m, plan["warmup_seconds"])
            c.update(wg=wg, groups=4096, n=8 * MiB, loops=1)
            s.run(c, "ert")


def memory_type(s, plan):
    """A/B control: the same kernels with DEVICE_LOCAL vs host-visible coherent buffers."""
    if plan["level"] == "fast":
        return
    for rep in range(1 if plan["level"] == "quick" else 3):
        for name in ("mem_read_v4", "mem_write_v4", "mem_copy_v4", "mem_triad_v4"):
            m = s.variant(name)
            n = (256 * MiB) // (ARRAYS_PER_OP[m["op"]] * 16) // 64 * 64
            modes = ["device_local", "host_coherent"] if rep % 2 == 0 else ["host_coherent", "device_local"]
            for mode in modes:
                c = s.base(m, plan["warmup_seconds"])
                c.update(n=n, groups=4096, loops=1, memory_mode=mode, repeat=rep)
                s.run(c, "control-memory-type")


# --- device-state sentinel -------------------------------------------------------------
def probe(s, label: str, plan) -> dict:
    """Fixed FP32 FMA configuration used as a clock proxy.

    Without a readable GPU clock, a device can change state invisibly: on Mali-G1 the
    same binary and configuration fell from 3.48 to 2.2 TFLOP/s hours later at 35 C
    with the screen on. Measured before/after every stage; the report flags stages whose
    sentinel is < 85 % of the median reading (Guard stops the run on a confirmed drop).
    """
    c = s.base(s.variant("alu_fp32_v4_c16"), plan["warmup_seconds"])
    c.update(wg=256, groups=512, probe=label, probe_utc=utc_now())
    row = s.run(c, "probe")
    if row.get("accepted"):
        rate = row["accounting"]["float_ops"] / row["median_seconds"] / 1e12
        print(f"{s.device.serial} probe {label} {rate:.3f} TFLOP/s", flush=True)
    return row


class DeviceDegraded(RuntimeError):
    """The sentinel fell below the session reference: stop, reboot/cool, resume."""


# Thermal pacing for short-run stages: a Mali-G1 phone latched into a ~40 % slower
# state (until reboot) after its GPU reached 61-66 C under heavy cooperative-matrix
# load. Waiting for the GPU to cool before each configuration keeps short-run roofs
# in one device state. Sustained stages are not paced (heating is what they measure).
PACE = dict(start_above_c=50.0, resume_below_c=45.0, max_wait_s=600)
# The sentinel scatters ~+-6 % between processes in the fast state; the slow state is
# ~35 % lower. So the reference is the MEDIAN of earlier readings (not the max, which is
# an upper outlier), the threshold 85 %, and a trip is re-measured twice before acting.
SENTINEL = dict(every=20, degraded_below=0.85, confirm_readings=3)


class Guard:
    """Wraps Session.run: paces on GPU temperature, measures the sentinel every
    SENTINEL['every'] configurations and at stage boundaries, and on a drop moves the
    results measured since the last good sentinel to superseded/ and stops the plan."""

    UNGUARDED = ("probe", "validate")

    def __init__(self, s, plan):
        self.s, self.plan, self.count, self.busy = s, plan, 0, False
        self.last_good_utc = utc_now()
        runner = s.runner_sha
        vals = []
        for p in s.out.glob("probe/*.json"):
            if p.name.endswith((".config.json", ".telemetry.json")):
                continue
            r = json.loads(p.read_text())
            if r.get("accepted") and r.get("config", {}).get("runner_sha256") == runner and r.get("accounting"):
                vals.append(r["accounting"]["float_ops"] / r["median_seconds"] / 1e12)
        self.readings = vals  # every accepted sentinel of this runner on this device, any process

    @property
    def reference(self):
        return statistics.median(self.readings) if self.readings else None

    def _guarded(self, tag: str) -> bool:
        return not (self.busy or tag in self.UNGUARDED or tag.startswith("sustain"))

    def before(self, tag: str):
        if not self._guarded(tag):
            return
        d, waited, t0 = self.s.device, 0, time.time()
        pace = getattr(d, "pace", PACE)  # devices may set their own thresholds
        temp = d.gpu_temp_c()
        if temp is not None and temp > pace["start_above_c"]:
            while temp is not None and temp > pace["resume_below_c"] and time.time() - t0 < pace["max_wait_s"]:
                time.sleep(10)
                temp = d.gpu_temp_c()
            waited = time.time() - t0
            with (self.s.out / "pacing.jsonl").open("a") as f:
                f.write(json.dumps(dict(utc=utc_now(), tag=tag, waited_s=round(waited, 1), gpu_c=temp)) + "\n")

    def after(self, tag: str):
        if not self._guarded(tag):
            return
        self.count += 1
        if self.count % SENTINEL["every"] == 0:
            self.check(f"{tag}_{self.count}")

    def _read(self, label: str):
        self.busy = True
        try:
            row = probe(self.s, label, self.plan)
        finally:
            self.busy = False
        return row["accounting"]["float_ops"] / row["median_seconds"] / 1e12 if row.get("accepted") else None

    def check(self, label: str) -> float | None:
        started = utc_now()
        value = self._read(label)
        if value is None:
            return None
        ref = self.reference
        if ref is not None and value < SENTINEL["degraded_below"] * ref:
            # One low reading is not a state change: re-measure and decide on the median.
            more = [self._read(f"{label}_recheck{i}") for i in range(1, SENTINEL["confirm_readings"])]
            value = statistics.median([value] + [v for v in more if v is not None])
        if ref is not None and value < SENTINEL["degraded_below"] * ref:
            moved = self.quarantine(self.last_good_utc)
            raise DeviceDegraded(f"sentinel {value:.3f} < {SENTINEL['degraded_below']:.0%} of the median {ref:.3f} "
                                 f"TFLOP/s at {label}; {moved} result(s) since {self.last_good_utc} moved to superseded/. "
                                 "Reboot the device, let it cool, and rerun the same command to resume.")
        self.readings.append(value)
        self.last_good_utc = started
        return value

    def quarantine(self, since: str) -> int:
        """Move every non-probe result whose run started after `since` to superseded/."""
        dest = self.s.out / "superseded" / ("degraded-" + utc_now().replace(":", "-"))
        moved = 0
        for tele in self.s.out.glob("*/*.telemetry.json"):
            stage = tele.parent.name
            if stage in ("probe", "superseded") or stage.startswith("sustain"):
                continue
            if json.loads(tele.read_text())[0]["utc"] <= since:
                continue
            key = tele.name[: -len(".telemetry.json")]
            (dest / stage).mkdir(parents=True, exist_ok=True)
            for f in tele.parent.glob(key + ".*"):
                f.rename(dest / stage / f.name)
            moved += 1
        return moved


# --- roof selection: quality gates, then confirmation -----------------------------------
def quality(r: dict) -> list[str]:
    """Reasons a result may not define a roof (empty list = eligible)."""
    why = []
    if not r.get("accepted"):
        why.append("rejected")
    if median_se(r) > QUALITY["max_median_se"]:
        why.append("noisy_median")
    if r.get("below_target_duration"):
        why.append("short")
    d = r.get("differential")
    if d and (not d.get("valid") or d.get("fixed_fraction", 0) > QUALITY["max_fixed_fraction"]):
        why.append("fixed_cost")
    w = r.get("warmup") or {}
    if w.get("steady") is False:
        why.append("warmup_unsteady")
    if abs(r.get("sample_drift", 0)) > QUALITY["max_drift"]:
        why.append("drifting")
    return why


def roof_key(stage: str, r: dict):
    c, a = r.get("config", {}), r.get("accounting", {})
    if not c or c["family"] in ("latency", "ert", "copy") or is_control(c):
        return None
    f = c["family"]
    key = f + "_" + c.get("dtype", "") + (f"_{c['op']}" if f in ("memory", "shared") else "")
    if f == "matrix" and c.get("feed"):
        return matrix_feed_key(c, a)
    if f == "texture":
        return texture_key(c, a)
    if f == "memory":
        if stage == "sweep-cache" or c.get("role") == "cache":
            return "cache_read_effective" if 32768 <= a.get("working_set_bytes", 0) <= 4 * MiB else None
        if a.get("working_set_bytes", 0) < 256 * MiB:
            return None
    return key


def matrix_feed_key(c: dict, a: dict):
    """Roof key of a fed cooperative-matrix result: shared, cache-resident or DRAM."""
    base = f"matrix_{c['dtype']}_feed_"
    if c["feed"] == "shared":
        return base + "shared"
    ws = a.get("working_set_bytes", 0)
    return base + ("dram" if ws >= 256 * MiB else "cache" if ws <= 4 * MiB else "mid")


def texture_key(c: dict, a: dict):
    ws = a.get("working_set_bytes", 0)
    level = "dram" if ws >= 256 * MiB else "cache" if ws <= 4 * MiB else None
    return f"texture_{c['format']}_{c['mode']}_{level}" if level else None


def rate(r: dict) -> float:
    c, a = r["config"], r["accounting"]
    f = c["family"]
    work = (a.get("integer_ops", 0) + a.get("float_ops", 0) if f in ("alu", "dot", "matrix")
            else a["logical_shared_bytes"] if f == "shared" else a["logical_global_bytes"])
    return work / r["median_seconds"]


def candidates(s, top: int) -> dict:
    """Best `top` quality-gated sweep results per roof (first-look is a smoke test only)."""
    best, gated = {}, {}
    for p in s.out.glob("sweep-*/*.json"):
        if p.name.endswith((".config.json", ".telemetry.json")):
            continue
        r = json.loads(p.read_text())
        if not r.get("accepted") or not s.current(r):
            continue
        key = roof_key(p.parent.name, r)
        if not key:
            continue
        if p.parent.name == "sweep-cache":
            r["config"] = dict(r["config"], role="cache")
        why = quality(r)
        if why:
            gated.setdefault(key, []).append(dict(name=r["config"]["name"], rate=rate(r), why=why))
        else:
            best.setdefault(key, []).append(r)
    chosen = {k: sorted(v, key=rate, reverse=True)[:top] for k, v in best.items()}
    (s.out / "roof-candidates.json").write_text(json.dumps(dict(
        quality=QUALITY,
        selected={k: [dict(name=r["config"]["name"], rate=rate(r), raw=r["raw"]) for r in v] for k, v in chosen.items()},
        gated_but_faster={k: [g for g in v if k in chosen and g["rate"] > rate(chosen[k][0])] for k, v in gated.items()},
        roofs_without_quality_candidate=sorted(set(gated) - set(chosen))), indent=2))
    return chosen


def confirm(s, plan):
    """Winner's-curse control: re-measure the top candidates of every roof in fresh
    processes, round-robin, alternating direction each repeat so drift hits all alike."""
    cfg = plan["confirm"]
    work = [(k, r) for k, v in sorted(candidates(s, cfg["top"]).items()) for r in v]
    for i in range(cfg["reps"]):
        for n, (key, r) in enumerate(work if i % 2 == 0 else work[::-1]):
            c = dict(r["config"], replicate=i, confirm_key=key, calibrate=True,
                     loops=1 if r["config"]["family"] == "memory" else 128)
            s.run(c, "confirm")


def select_roofs(s) -> dict:
    """Per roof: the candidate with the best median over its confirmation repeats
    (at most one repeat may fail the quality gates); returns a representative row."""
    groups = {}
    for p in s.out.glob("confirm/*.json"):
        if p.name.endswith((".config.json", ".telemetry.json")):
            continue
        r = json.loads(p.read_text())
        c = r["config"]
        if not s.current(r):
            continue
        ident = json.dumps({k: v for k, v in c.items() if k != "replicate"}, sort_keys=True)
        groups.setdefault((c["confirm_key"], ident), []).append(r)
    winners = {}
    for (key, _), rows in groups.items():
        ok = [r for r in rows if not quality(r)]
        if len(ok) < max(2, len(rows) - 1):
            continue
        med = statistics.median(rate(r) for r in ok)
        pick = min(ok, key=lambda r: abs(rate(r) - med))
        if key not in winners or med > winners[key][0]:
            winners[key] = (med, pick)
    if not winners:
        raise RuntimeError("no confirmed roofs; run the confirm stage first")
    return {k: v[1] for k, v in winners.items()}


def sustain(s, plan):
    cfg = plan["sustain"]
    winners = select_roofs(s)
    (s.out / "sustained-selection.json").write_text(json.dumps(winners, indent=2))
    sustained_sha = paths.digest(paths.RUNNER_SUSTAINED)
    same = lambda d: {k: v for k, v in d.items() if k not in ("duration_seconds", "warmup_seconds")}
    if cfg.get("keys"):
        # Representative roofs only: the first available key of each group.
        picked = {}
        for group in cfg["keys"]:
            key = next((k for k in group if k in winners), None)
            if key:
                picked[key] = winners[key]
        winners = picked
    for batch in range(cfg["batches"]):
        probe(s, f"sustain_{batch}", plan)
        for key, r in sorted(winners.items()):
            base_batch = r.get("batch_dispatches", 1)
            c = dict(r["config"], loops=r["effective_loops"], calibrate=False, duration_seconds=cfg["duration"],
                     executable="roofline_sustained",
                     batch_dispatches=min(256, base_batch * max(1, math.ceil(0.005 / r["median_seconds"]))),
                     reference_runner_sha256=r["config"]["runner_sha256"], runner_sha256=sustained_sha)
            for k in ("warmup_seconds", "replicate", "confirm_key"):
                c.pop(k, None)
            done = [q for q in (s.out / f"sustain-{batch}").glob(c["name"] + "_*.json")
                    if not q.name.endswith((".config.json", ".telemetry.json"))
                    and (lambda x: x.get("accepted") and same(x["config"]) == same(c))(json.loads(q.read_text()))]
            if done:
                continue
            time.sleep(cfg["cooldown"])
            preflight = s.run(dict(c, duration_seconds=0, samples=5), f"sustain-preflight-{batch}")
            if not preflight["accepted"]:
                raise RuntimeError(f"sustained preflight failed for {key}")
            s.run(c, f"sustain-{batch}")


# --- driver statistics and offline ISA -----------------------------------------------
def pipeline_stats(s, plan):
    """VK_KHR_pipeline_executable_properties for every variant (+ driver ISA text if offered)."""
    out = s.out / "pipeline-inspection"
    out.mkdir(exist_ok=True)
    if "VK_KHR_pipeline_executable_properties" not in s.caps["extensions"]:
        (out / "unavailable.json").write_text(json.dumps({"reason": "extension not exposed"}))
        return
    d = s.device
    for m in s.manifest:
        path = out / f"{m['name']}.json"
        if not s.eligible(m) or path.exists():
            continue
        c = s.base(m)
        c.update(n=1024, groups=16)
        if m["family"] == "latency":
            c.update(wg=1, groups=1)
        (out / f"{m['name']}.config.json").write_text(json.dumps(c))
        d.push(out / f"{m['name']}.config.json", f"{d.remote}/inspect-config.json")
        r = d.shell(f"cd {d.remote} && ./inspect inspect-config.json", 120)
        records = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        for rec in records:
            for ex in rec.get("executables", []):
                for rep in ex.get("representations", []):
                    if rep.get("text") and rep["text"] != "binary representation":
                        name = f"{m['name']}.{ex['name']}.{rep['name']}".replace(" ", "_")
                        (out / f"{name}.txt").write_text(rep["text"])
        path.write_text(json.dumps(dict(rc=r.returncode, shader=m["name"], stderr=r.stderr[-2000:],
                                        inspector_sha256=paths.digest(paths.INSPECT), records=records), indent=2))


def offline_isa(s, plan):
    from . import isa_offline
    isa_offline.run(s)


# --- plan driver ---------------------------------------------------------------------
SHORT_STAGES = [validate, first_look, cache, memory, compute, matrix_feed, texture, shared, latency, ert, memory_type]


def run_plan(s, plan_name: str):
    plan = PLANS[plan_name]
    state = s.out / "workflow-state.json"

    def mark(phase, **extra):
        state.write_text(json.dumps(dict(phase=phase, plan=plan_name, utc=datetime.datetime.now(
            datetime.timezone.utc).isoformat(), **extra), indent=2))

    started = time.time()
    guard = None
    try:
        for step in [deploy, capabilities, pipeline_stats, offline_isa] + SHORT_STAGES + [confirm]:
            name = step.__name__
            mark(name)
            print(f"=== {s.device.serial} {name}", flush=True)
            measuring = step in SHORT_STAGES or step is confirm
            if measuring and guard is None:
                guard = s.guard = Guard(s, plan)
            if measuring:
                guard.check(f"{name}_start")
            step(s, plan)
            if measuring:
                guard.check(f"{name}_end")
    except DeviceDegraded as e:
        mark("paused_device_degraded", reason=str(e))
        raise SystemExit(f"{s.device.serial}: {e}")
    finally:
        s.guard = None
    if plan["sustain"]:
        mark("sustain")
        print(f"=== {s.device.serial} sustain", flush=True)
        sustain(s, plan)
    mark("finished", elapsed_hours=round((time.time() - started) / 3600, 2))
