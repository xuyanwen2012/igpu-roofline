"""Sample statistics, differential (two-point) timing and work/byte accounting.

Accounting conventions (see docs/METHODOLOGY.md):
  * an FMA is 2 FLOP; a packed int8 dot4 is 8 integer OP; matrix multiply-add is 2*M*N*K;
  * address arithmetic, loop control and operand recurrences are not counted, so
    rates are conservative;
  * global-memory bytes follow BabelStream (read, write, copy, mul, add, triad, dot)
    and are shader-logical bytes, never physical DRAM traffic.
"""
import statistics

GLOBAL_OPS = ["read", "write", "copy", "scale", "add", "triad", "dot"]
ARRAYS_PER_OP = [1, 1, 2, 2, 3, 3, 2]       # arrays touched per element
FLOPS_PER_OP = [1, 0, 0, 1, 1, 2, 2]        # FLOP per element


def stats(xs: list[float]) -> dict:
    mean = statistics.mean(xs)
    sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
    ordered = sorted(xs)
    return dict(n=len(xs), median_seconds=statistics.median(xs), min_seconds=ordered[0],
                mean_seconds=mean, stddev_seconds=sd, cv=sd / mean if len(xs) > 1 else 0.0,
                p05_seconds=ordered[int(0.05 * (len(xs) - 1))],
                p95_seconds=ordered[int(0.95 * (len(xs) - 1))])


def differential(samples: list[dict], halves: dict) -> dict:
    """Two-point timing t(L) = F + L*c from interleaved runs at L and L/2 loops.

    The median of paired differences gives the per-loop cost c; F is the fixed
    per-dispatch cost (launch, fills, write-back) that plain t(L)/L would include.
    """
    pairs = [(s["seconds"], halves[s["sample"]]["seconds"]) for s in samples if s["sample"] in halves]
    loops = samples[0]["loops"]
    half = next(iter(halves.values()))["loops"]
    per_loop = statistics.median((a - b) / (loops - half) for a, b in pairs)
    full = statistics.median(a for a, _ in pairs)
    fixed = full - loops * per_loop
    return dict(loops=loops, half_loops=half, pairs=len(pairs), seconds_per_loop=per_loop,
                fixed_seconds=fixed, fixed_fraction=fixed / full,
                incremental_seconds_for_L=loops * per_loop,
                valid=per_loop > 0 and fixed >= -0.05 * full)


def accounting(c: dict, loops: int) -> dict:
    """Work and logical bytes of one timed sample of configuration `c`."""
    family = c["family"]
    threads = c["wg"] * c["groups"]
    width = c.get("width", 1)
    chains = c.get("chains", 1)
    n = c.get("n", 1024)
    a = dict(float_ops=0, integer_ops=0, logical_global_bytes=0, logical_shared_bytes=0,
             physical_dram_bytes=None, physical_cache_bytes=None)

    if family == "memory":
        op, rep = c["op"], c.get("replicas", 1)
        arrays = ARRAYS_PER_OP[op]
        a["logical_global_bytes"] = n * width * 4 * loops * arrays * rep
        if op == 0:  # the read kernel also writes one partial sum per thread
            a["logical_global_bytes"] += min(threads // rep, n) * rep * width * 4
        a["float_ops"] = n * width * loops * FLOPS_PER_OP[op] * rep
        a["working_set_bytes"] = n * width * 4 * arrays
    elif family == "copy":
        a["logical_global_bytes"] = n * width * 8
        a["working_set_bytes"] = n * width * 8
    elif family == "alu":
        a["float_ops"] = 2 * threads * width * chains * 16 * loops
        a["logical_global_bytes"] = threads * width * 4 * (2 + chains)
    elif family == "dot":
        dots = c.get("dots_per_step", 1)
        a["integer_ops"] = 8 * threads * chains * loops * dots
        a["logical_global_bytes"] = threads * 4 * (2 + chains)
    elif family == "shared":
        scalar = 2 if c["dtype"] == "fp16" else 4
        bw = c.get("kind") == "bw"
        per = c.get("accumulators", 1) if bw else 1
        op = c["op"]
        a["logical_shared_bytes"] = threads * width * scalar * loops * per * (1 if op in (0, 2) else 2)
        a["logical_global_bytes"] = c["groups"] * c["shared_count"] * width * 4 + threads * width * 4
        a["shared_initialization_bytes"] = c["groups"] * c["shared_count"] * width * scalar
        a["shared_final_read_bytes"] = threads * width * scalar if op else 0
        if bw and op == 2:  # pure-write test has no fill
            a["shared_initialization_bytes"] = 0
            a["logical_global_bytes"] = threads * width * 4
        a["logical_shared_bytes"] += a["shared_initialization_bytes"] + a["shared_final_read_bytes"]
        a["float_ops"] = threads * width * loops * per if op == 0 else 0
        a["barriers_per_workgroup"] = 1 if bw else 1 + (2 * loops if op else 0)
    elif family == "matrix":
        # Every subgroup of a workgroup runs its own chains (wg may hold several subgroups).
        subgroups = max(1, c["wg"] // c.get("subgroup", c["wg"]))
        ops = 2 * c["m"] * c["matrix_n"] * c["k"] * chains * c["groups"] * subgroups * loops
        a["integer_ops" if c["dtype"] == "int8" else "float_ops"] = ops
        ab_bytes = 1 if c["dtype"] == "int8" else 2
        acc_bytes = 2 if c["dtype"] == "fp16" else 4
        tile_bytes = (c["m"] * c["k"] + c["k"] * c["matrix_n"]) * ab_bytes
        a["logical_global_bytes"] = c["groups"] * (tile_bytes + c["m"] * c["matrix_n"] * chains * acc_bytes)
        loads = c["groups"] * subgroups * loops * tile_bytes  # one A+B pair per iteration per subgroup
        if c.get("feed") == "shared":
            a["shared_initialization_bytes"] = c["groups"] * c["tiles"] * tile_bytes
            a["logical_global_bytes"] += c["groups"] * c["tiles"] * tile_bytes
            a["logical_shared_bytes"] = loads + a["shared_initialization_bytes"]
            a["matrix_load_bytes"] = loads
        elif c.get("feed") == "global":
            a["logical_global_bytes"] += loads
            a["matrix_load_bytes"] = loads
            a["working_set_bytes"] = n * tile_bytes
    elif family == "texture":
        texel = 8 if c["format"] == "rgba16f" else 16
        a["logical_global_bytes"] = n * texel * loops + threads * 16
        a["working_set_bytes"] = n * texel
        a["float_ops"] = n * 4 * loops
    elif family == "latency":
        a["dependent_loads"] = 16 * loops
        a["working_set_bytes"] = n * 4
        a["chain_stride_bytes"] = c.get("chain_stride_bytes", 64)
        a["chain_order"] = c.get("chain_order", "random")
    elif family == "ert":
        flops = c["flops_per_element"]
        a["float_ops"] = 2 * flops * 4 * n * loops
        a["logical_global_bytes"] = n * 16 * 2 * loops
        a["working_set_bytes"] = n * 16 * 2

    batch = c.get("batch_dispatches", 1)
    for key in ("float_ops", "integer_ops", "logical_global_bytes", "logical_shared_bytes",
                "shared_initialization_bytes", "shared_final_read_bytes", "barriers_per_workgroup", "matrix_load_bytes",
                "dependent_loads"):
        if key in a:
            a[key] *= batch
    return a
