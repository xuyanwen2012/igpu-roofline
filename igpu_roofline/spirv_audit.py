"""Static SPIR-V instruction ledger for the microbenchmark shaders.

Counts come from `spirv-dis` text after `glslc -O` (which unrolls `[[unroll]]`
loops), so they are per-loop-body static counts, not dynamic instruction counts.
Loads and stores are attributed to a storage class through the pointer's type.

Every shader variant must match its design exactly (see `expected`); the build
fails otherwise. This catches a compiler, or an edit, silently changing what a
microbenchmark measures.
"""
import re

POINTER_PRODUCERS = ("OpVariable", "OpAccessChain", "OpInBoundsAccessChain",
                     "OpPtrAccessChain", "OpCopyObject")


def ledger(asm: str) -> dict:
    ptr_class = dict(re.findall(r"(%\w+) = OpTypePointer (\w+) ", asm))
    id_type = {}
    for m in re.finditer(r"(%\w+) = (\w+) (%\w+)", asm):
        if m[2] in POINTER_PRODUCERS:
            id_type[m[1]] = m[3]

    counts = {"fma": 0, "dot": 0, "coopmat_muladd": 0, "coopmat_load": 0, "control_barrier": 0, "volatile": 0}
    for line in asm.splitlines():
        s = line.strip()
        load = re.match(r"%\w+ = OpLoad %\w+ (%\w+)", s)
        store = re.match(r"OpStore (%\w+) ", s)
        m = load or store
        if m:
            storage = ptr_class.get(id_type.get(m[1]), "Unknown")
            key = ("load_" if load else "store_") + storage
            counts[key] = counts.get(key, 0) + 1
        if re.search(r"OpExtInst %\w+ %\w+ Fma ", s):
            counts["fma"] += 1
        if re.search(r"= Op(U|S|SU)Dot(AccSat)? ", s):
            counts["dot"] += 1
        if "OpCooperativeMatrixMulAddKHR" in s:
            counts["coopmat_muladd"] += 1
        if "OpCooperativeMatrixLoadKHR" in s:
            counts["coopmat_load"] += 1
        if s.startswith("OpControlBarrier"):
            counts["control_barrier"] += 1
        if re.search(r"\bVolatile\b", s):
            counts["volatile"] += 1
    return counts


def expected(meta: dict) -> dict:
    """Exact static counts a variant must show. Families not listed are unchecked."""
    family = meta["family"]
    if family == "alu":
        return {"fma": 16 * meta["chains"]}
    if family == "dot":
        return {"dot": meta["chains"] * meta.get("dots_per_step", 1)}
    if family == "matrix":
        # A and B once before the loop; fed variants load them again inside the loop.
        e = {"coopmat_muladd": meta["chains"], "coopmat_load": 4 if meta.get("feed") else 2}
        if meta.get("feed") == "shared":
            e["control_barrier"] = 1  # after staging the tiles
        return e
    if family == "memory":
        op = meta["op"]
        e = {"load_StorageBuffer": [1, 0, 1, 1, 2, 2, 2][op], "store_StorageBuffer": 1}
        if not meta.get("volatile_global"):
            e["volatile"] = 0
        if op == 6:  # BabelStream Dot: one barrier before and one inside the reduction
            e["control_barrier"] = 2
        return e
    if family == "shared" and meta.get("kind") == "bw":
        acc = meta["accumulators"]
        if meta["op"] == 0:
            return {"load_Workgroup": acc, "store_Workgroup": 1, "control_barrier": 1, "volatile": acc + 1}
        return {"load_Workgroup": 1, "store_Workgroup": acc, "control_barrier": 1, "volatile": acc + 1}
    if family == "latency":
        return {"load_StorageBuffer": 16, "store_StorageBuffer": 1}
    if family == "ert":
        # Bodies with F > 32 are chunked into 32 unrolled steps per loop trip unless
        # FULL_UNROLL; ELEMS independent elements (chains) per thread.
        flops, elems = meta["flops_per_element"], meta.get("elems", 4)
        steps = flops if flops <= 32 or meta.get("full_unroll") else 32
        return {"fma": elems * steps, "load_StorageBuffer": elems, "store_StorageBuffer": elems}
    return {}


def check(meta: dict, counts: dict) -> dict:
    """Return {key: (expected, actual)} for every mismatch; empty means OK."""
    return {k: (v, counts.get(k, 0)) for k, v in expected(meta).items() if counts.get(k, 0) != v}
