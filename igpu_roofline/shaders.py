"""Shader variant catalogue and compiler.

Every variant is compiled with glslc, validated with spirv-val, disassembled, and
checked against its exact static instruction ledger (spirv_audit). Workgroup-
memory variants get SPIR-V `Volatile` added after compilation.
"""
import concurrent.futures
import hashlib
import json
import subprocess

from . import paths
from .spirv_audit import check, ledger
from .volatile_workgroup import annotate

GLSLC_TARGET = "vulkan1.3"


def _vec(dtype: str, width: int) -> tuple[str, str]:
    scalar = "float" if dtype == "fp32" else "float16_t"
    if width == 1:
        return scalar, scalar
    return ("vec" if dtype == "fp32" else "f16vec") + str(width), scalar


def catalogue() -> list[tuple[str, str, dict, dict]]:
    """(name, source file stem, -D defines, metadata) for every variant."""
    jobs = []

    def add(name, src, defines, meta):
        jobs.append((name, src, defines, dict(meta, name=name, shader="shaders/" + name + ".spv")))

    for w in (1, 2, 4):
        # Global memory, BabelStream set. Primary variants are not volatile (stores keep
        # the loads live); `_volatile` variants are a control for compiler interference.
        for op, label in enumerate(["read", "write", "copy", "scale", "add", "triad", "dot"]):
            add(f"mem_{label}_v{w}", "memory", dict(WIDTH=w, OP=op),
                dict(family="memory", op=op, width=w, dtype="fp32"))
        if w == 4:
            for op, label in enumerate(["read", "write", "copy", "scale", "add", "triad"]):
                add(f"mem_{label}_v{w}_volatile", "memory", dict(WIDTH=w, OP=op, VOLATILE="volatile"),
                    dict(family="memory", op=op, width=w, dtype="fp32", volatile_global=True))

        for dtype in ("fp32", "fp16"):
            vec, scalar = _vec(dtype, w)
            # FMA throughput: `chains` independent dependency chains per invocation.
            for chains in (1, 2, 4, 8, 16):
                add(f"alu_{dtype}_v{w}_c{chains}", "alu", dict(WIDTH=w, T=vec, S=scalar, CHAINS=chains),
                    dict(family="alu", width=w, chains=chains, dtype=dtype))
            # Workgroup memory, textbook form: 8 independent accumulators (read) / pure writes.
            for op in (0, 2):
                add(f"sharedbw_{dtype}_v{w}_op{op}", "shared_bw", dict(WIDTH=w, T=vec, S=scalar, OP=op, ACC=8),
                    dict(family="shared", kind="bw", width=w, op=op, dtype=dtype, accumulators=8,
                         cross_lane_producer=True, volatile_workgroup=True))
            # Accumulator sweep for the read test (is shared memory saturated?).
            for acc in (4, 16, 32):
                add(f"sharedbw_{dtype}_v{w}_op0_acc{acc}", "shared_bw", dict(WIDTH=w, T=vec, S=scalar, OP=0, ACC=acc),
                    dict(family="shared", kind="bw", width=w, op=0, dtype=dtype, accumulators=acc,
                         cross_lane_producer=True, volatile_workgroup=True))
            # Controls: single accumulator read, and read/write with two barriers per step.
            for op in (0, 1):
                add(f"shared_{dtype}_v{w}_op{op}_xlanes_volatile", "shared_crosslane",
                    dict(WIDTH=w, T=vec, S=scalar, OP=op),
                    dict(family="shared", width=w, op=op, dtype=dtype,
                         cross_lane_producer=True, volatile_workgroup=True))

    # int8 dot4: the operand recurrence is shared by 8 independent dots.
    for chains in (1, 2, 4, 8):
        add(f"dot8_c{chains}", "dot8", dict(CHAINS=chains, DOTS=8),
            dict(family="dot", width=1, chains=chains, dtype="int8", dots_per_step=8))

    add("pchase", "pchase", {}, dict(family="latency", width=1, dtype="uint32"))
    for flops in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024):
        add(f"ert_f{flops}", "ert", dict(FLOPS=flops),
            dict(family="ert", width=4, dtype="fp32", flops_per_element=flops))

    # Cooperative matrix. Only shapes the device reports are run (see Session.eligible).
    shapes = ([(64, n, 16, "fp16") for n in (16, 32, 64)] + [(64, n, 32, "int8") for n in (16, 32, 64)]
              + [(4, 8, 8, "fp16"), (16, 32, 32, "fp16"), (4, 16, 16, "int8"),
                 (4, 8, 8, "fp16_fp32"), (16, 32, 32, "fp16_fp32"),
                 (16, 16, 16, "fp16"), (16, 16, 16, "fp16_fp32"), (16, 16, 32, "int8")])
    for m, n, k, dtype in shapes:
        a_type = "int8_t" if dtype == "int8" else "float16_t"
        c_type = "int32_t" if dtype == "int8" else "float16_t" if dtype == "fp16" else "float"
        for chains in (1, 2, 4, 8):
            add(f"matrix_{dtype}_{m}x{n}x{k}_c{chains}", "matrix",
                dict(M=m, N=n, K=k, AT=a_type, CT=c_type, CHAINS=chains),
                dict(family="matrix", dtype=dtype, m=m, matrix_n=n, k=k, chains=chains, width=1))
    return jobs


def _matrix_source(text: str, chains: int, dtype: str) -> str:
    # GLSL cannot index an array of coopmat with a loop variable on every driver,
    # so the accumulator array is expanded into named variables.
    acc = "coopmat<CT,gl_ScopeSubgroup,M,N,gl_MatrixUseAccumulator>"
    text = text.replace(f"{acc} acc[CHAINS];", "\n".join(f"{acc} acc{c};" for c in range(chains)))
    text = text.replace(f"[[unroll]]for(uint c=0;c<CHAINS;c++)acc[c]={acc}(CT(c));",
                        "\n".join(f"acc{c}={acc}(CT({c if dtype == 'int8' else c / 16}));" for c in range(chains)))
    text = text.replace("[[unroll]]for(uint c=0;c<CHAINS;c++)acc[c]=coopMatMulAdd(ma,mb,acc[c]);",
                        "\n".join(f"acc{c}=coopMatMulAdd(ma,mb,acc{c});" for c in range(chains)))
    text = text.replace("[[unroll]]for(uint c=0;c<CHAINS;c++)coopMatStore(acc[c],d,(gl_WorkGroupID.x*CHAINS+c)*M*N,N,gl_CooperativeMatrixLayoutRowMajor);",
                        "\n".join(f"coopMatStore(acc{c},d,(gl_WorkGroupID.x*CHAINS+{c})*M*N,N,gl_CooperativeMatrixLayoutRowMajor);" for c in range(chains)))
    return text


def _build_one(job) -> dict:
    name, src, defines, meta = job
    out = paths.SHADER_OUT
    source = paths.SHADER_SRC / f"{src}.comp"
    if src == "matrix":
        expanded = out / f"{name}.comp"
        expanded.write_text(_matrix_source(source.read_text(), defines["CHAINS"], meta["dtype"]))
        source = expanded
    spv = out / f"{name}.spv"
    cmd = ["glslc", f"--target-env={GLSLC_TARGET}", "-O"] + [f"-D{k}={v}" for k, v in defines.items()] + [str(source), "-o", str(spv)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"{name}: glslc failed\n{p.stderr}")
    subprocess.run(["spirv-val", "--target-env", GLSLC_TARGET, str(spv)], check=True, capture_output=True)
    asm = subprocess.check_output(["spirv-dis", str(spv)], text=True)
    if meta.get("volatile_workgroup"):
        asm, meta["volatile_workgroup_accesses"] = annotate(asm)
        (out / f"{name}.spvasm").write_text(asm)
        subprocess.run(["spirv-as", "--target-env", GLSLC_TARGET, str(out / f"{name}.spvasm"), "-o", str(spv)],
                       check=True, capture_output=True)
        subprocess.run(["spirv-val", "--target-env", GLSLC_TARGET, str(spv)], check=True, capture_output=True)
    (out / f"{name}.spvasm").write_text(asm)
    counts = ledger(asm)
    bad = check(meta, counts)
    if bad:
        raise RuntimeError(f"{name}: static SPIR-V ledger mismatch (expected, actual): {bad}")
    meta["spirv_ledger"] = counts
    meta["spirv_sha256"] = hashlib.sha256(spv.read_bytes()).hexdigest()
    meta["compile_command"] = [str(x).replace(str(paths.REPO) + "/", "") for x in cmd]
    return meta


def build_all() -> list[dict]:
    paths.SHADER_OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_build_one, catalogue()))
    paths.SHADER_MANIFEST.write_text(json.dumps(results, indent=2) + "\n")
    return results
