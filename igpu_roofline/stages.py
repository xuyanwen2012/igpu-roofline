"""Measurement stages and plans.

A plan is an ordered list of stages. Every stage is idempotent (finished
configurations are skipped), so re-running the same plan resumes it.
"""
import datetime
import json
import math
import time

from . import paths
from .measure import ARRAYS_PER_OP

MiB = 1024 ** 2

PLANS = {
    # ~15-20 min: every family once at its most informative settings, no sustained runs.
    "quick": dict(level="quick", warmup_seconds=0.25, sustain=None),
    # All sweeps + one 300 s sustained run per roof.
    "standard": dict(level="full", warmup_seconds=1.0, sustain=dict(batches=1, duration=300, cooldown=90)),
    # As standard, with three sustained batches for batch-to-batch repeatability.
    "gold": dict(level="full", warmup_seconds=1.0, sustain=dict(batches=3, duration=300, cooldown=90)),
}


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
    for m in s.manifest:
        f = m["family"]
        pick = ((f == "memory" and m["width"] == 4) or (f == "alu" and m["width"] == 4 and m["chains"] in (4, 8))
                or (f == "shared" and m["width"] == 4 and m.get("accumulators", 8) == 8)
                or (f == "dot" and m["chains"] == 4) or (f == "matrix" and m["chains"] in (1, 4) and s.eligible(m)))
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
    quick = plan["level"] == "quick"
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
    quick = plan["level"] == "quick"
    for m in s.manifest:
        if m["family"] != "memory" or m["width"] != 4 or (quick and m.get("volatile_global")):
            continue
        for exp in ((28, 29) if quick else range(12, 30)):
            arrays = ARRAYS_PER_OP[m["op"]]
            n = (1 << exp) // (arrays * 16) // 64 * 64
            if n * 16 > s.caps["max_storage_buffer_range"]:
                continue
            c = s.base(m, plan["warmup_seconds"])
            c.update(n=n, groups=min(4096, max(1, n // 64)), loops=1)
            s.run(c, "sweep-memory")


def compute(s, plan):
    """FMA / int8 dot / cooperative matrix over vector width, chains and launch size."""
    quick = plan["level"] == "quick"
    for m in s.manifest:
        if m["family"] not in ("alu", "dot", "matrix") or not s.eligible(m):
            continue
        wgs = [s.caps["subgroup"]] if m["family"] == "matrix" else ([256] if quick else [64, 128, 256])
        groups = [512] if quick else ([64, 512, 4096] if m["family"] == "matrix" and m["dtype"] == "fp16" else [64, 512])
        for wg in wgs:
            for g in groups:
                c = s.base(m, plan["warmup_seconds"])
                c.update(wg=wg, groups=g)
                s.run(c, "sweep-compute")


def shared(s, plan):
    """Workgroup memory: workgroup size, allocation size and stride (bank conflicts)."""
    quick = plan["level"] == "quick"
    max_shared = s.caps["max_shared_bytes"]
    strides = (1, 2, 4, 8, 16, 32, 33, 64, 65)
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
        points |= {(wg, size, 1) for wg in (64, 128, 256) for size in (4096, max_shared)}
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
    quick = plan["level"] == "quick"
    m = s.variants(family="latency")[0]
    limit = min(256 * MiB, s.caps["max_storage_buffer_range"])

    def chase(tag, size, stride, order, min_loops, **extra):
        nodes = size // stride
        passes = 2 if order == "random" else 1
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
            chase("latency-stride", size, stride, "sequential", 1)


def ert(s, plan):
    """Empirical Roofline Toolkit sweep: arithmetic intensity 0.25..256 FLOP/byte."""
    for m in s.variants(family="ert"):
        for wg in ((256,) if plan["level"] == "quick" else (64, 256)):
            c = s.base(m, plan["warmup_seconds"])
            c.update(wg=wg, groups=4096, n=8 * MiB, loops=1)
            s.run(c, "ert")


def memory_type(s, plan):
    """A/B control: the same kernels with DEVICE_LOCAL vs host-visible coherent buffers."""
    for rep in range(1 if plan["level"] == "quick" else 3):
        for name in ("mem_read_v4", "mem_write_v4", "mem_copy_v4", "mem_triad_v4"):
            m = s.variant(name)
            n = (256 * MiB) // (ARRAYS_PER_OP[m["op"]] * 16) // 64 * 64
            modes = ["device_local", "host_coherent"] if rep % 2 == 0 else ["host_coherent", "device_local"]
            for mode in modes:
                c = s.base(m, plan["warmup_seconds"])
                c.update(n=n, groups=4096, loops=1, memory_mode=mode, repeat=rep)
                s.run(c, "control-memory-type")


# --- sustained -----------------------------------------------------------------------
def select_roofs(s) -> dict:
    """Fastest accepted configuration per roof, from the short-run sweeps."""
    winners = {}
    for p in list(s.out.glob("sweep-*/*.json")) + list(s.out.glob("first-look/*.json")):
        if p.name.endswith((".config.json", ".telemetry.json")):
            continue
        r = json.loads(p.read_text())
        c, a = r.get("config", {}), r.get("accounting", {})
        if not r.get("accepted") or c["family"] in ("latency", "ert") or is_control(c):
            continue
        f = c["family"]
        key = f + "_" + c.get("dtype", "") + (f"_{c['op']}" if f in ("memory", "shared") else "")
        if f == "memory":
            if p.parent.name == "sweep-cache":
                if not 32768 <= a.get("working_set_bytes", 0) <= 4 * MiB:
                    continue
                key = "cache_read_effective"
                r["config"] = dict(c, role="cache")
            elif a.get("working_set_bytes", 0) < 256 * MiB:
                continue
        work = (a.get("integer_ops", 0) + a.get("float_ops", 0) if f in ("alu", "dot", "matrix")
                else a["logical_shared_bytes"] if f == "shared" else a["logical_global_bytes"])
        rate = work / r["median_seconds"]
        if key not in winners or rate > winners[key][0]:
            winners[key] = (rate, r)
    return {k: v[1] for k, v in winners.items()}


def sustain(s, plan):
    cfg = plan["sustain"]
    winners = select_roofs(s)
    (s.out / "sustained-selection.json").write_text(json.dumps(winners, indent=2))
    sustained_sha = paths.digest(paths.RUNNER_SUSTAINED)
    same = lambda d: {k: v for k, v in d.items() if k not in ("duration_seconds", "warmup_seconds")}
    for batch in range(cfg["batches"]):
        for key, r in sorted(winners.items()):
            c = dict(r["config"], loops=r["effective_loops"], calibrate=False, duration_seconds=cfg["duration"],
                     executable="roofline_sustained",
                     batch_dispatches=min(128, max(1, math.ceil(0.005 / r["median_seconds"]))),
                     reference_runner_sha256=r["config"]["runner_sha256"], runner_sha256=sustained_sha)
            c.pop("warmup_seconds", None)
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
SHORT_STAGES = [validate, first_look, cache, memory, compute, shared, latency, ert, memory_type]


def run_plan(s, plan_name: str):
    plan = PLANS[plan_name]
    state = s.out / "workflow-state.json"

    def mark(phase, **extra):
        state.write_text(json.dumps(dict(phase=phase, plan=plan_name, utc=datetime.datetime.now(
            datetime.timezone.utc).isoformat(), **extra), indent=2))

    started = time.time()
    for step in [deploy, capabilities, pipeline_stats, offline_isa] + SHORT_STAGES:
        name = step.__name__
        mark(name)
        print(f"=== {s.device.serial} {name}", flush=True)
        step(s, plan)
    if plan["sustain"]:
        mark("sustain")
        print(f"=== {s.device.serial} sustain", flush=True)
        sustain(s, plan)
    mark("finished", elapsed_hours=round((time.time() - started) / 3600, 2))
