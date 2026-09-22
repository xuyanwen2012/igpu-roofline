"""Offline vendor-compiler ISA checks (no device needed; tools are optional).

* Mali: Arm Mali Offline Compiler (`malioc`, part of Arm Performance Studio) gives
  work registers, spills and occupancy. Its static cycle counts are stored but not
  used as a "bound" verdict: they are not loop-weighted.
* AMD RDNA (e.g. Samsung Xclipse): Radeon GPU Analyzer (`rga`) gives ISA text and
  VGPR/SGPR/LDS/scratch use. The AMD compiler differs from a vendor driver's, so
  this is an architecture-level approximation; driver-returned ISA (collected by
  the pipeline_stats stage) is preferred when available.
* Other GPUs (e.g. Adreno): no public offline Vulkan compiler; driver statistics only.

Tools are found via $MALIOC / $RGA or PATH. Missing tools are skipped, not errors.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import paths


def _tool(env: str, name: str) -> str | None:
    return os.environ.get(env) or shutil.which(name)


def target(gpu: str) -> tuple[str | None, str | None]:
    if "Mali-G710" in gpu:
        return "malioc", "Mali-G710"
    if "Mali-G1" in gpu:
        return "malioc", "Mali G1"
    m = re.search(r"Mali-(G\d+)", gpu)
    if m:
        return "malioc", f"Mali-{m[1]}"
    if "Xclipse" in gpu or "Radeon" in gpu:
        return "rga", os.environ.get("RGA_ASIC", "gfx1103")
    return None, None


def fma_equivalents(isa: str) -> int:
    """Scalar FMAs in AMD ISA text (dual-issue VOPD and packed f16 carry two)."""
    n = 0
    for line in isa.splitlines():
        op = line.strip().split(" ")[0] if line.strip() else ""
        if op.startswith("v_dual_"):
            n += sum(1 for part in re.findall(r"v_dual_(\w+)", line) if "fma" in part)
        elif op == "v_pk_fma_f16":
            n += 2
        elif re.fullmatch(r"v_fma(c|k|mk|ak)?_(f32|f16)(_e32|_e64)?", op):
            n += 1
    return n


def expected_scalar_fma(m: dict) -> int | None:
    if m["family"] == "alu":
        return 16 * m["chains"] * m["width"]
    if m["family"] == "ert":
        return 4 * 4 * m["flops_per_element"]
    return None


def isa_summary(isa: str, m: dict) -> dict:
    ops = [line.strip().split()[0] for line in isa.splitlines()
           if re.match(r"\s+(v_|s_|ds_|buffer_|global_|scratch_|flat_)", line)]
    fma, exp = fma_equivalents(isa), expected_scalar_fma(m)
    header = dict(re.findall(r"(vgpr_count|sgpr_count|wave_size)\((\d+)\)", isa))
    return dict(fma_scalar_equivalent=fma, expected_scalar_fma=exp, fma_matches_design=None if exp is None else fma == exp,
                dot=sum(1 for o in ops if "dot4" in o or "dot2" in o),
                lds_load=sum(1 for o in ops if o.startswith(("ds_load", "ds_read"))),
                lds_store=sum(1 for o in ops if o.startswith(("ds_store", "ds_write"))),
                scratch=sum(1 for o in ops if o.startswith("scratch_")), header=header)


def _malioc(tool: str, core: str, spv: Path) -> dict:
    p = subprocess.run([tool, "-c", core, "--vulkan", "--compute", "-S", "0=64", "--format", "json", str(spv)],
                       capture_output=True, text=True)
    if p.returncode:
        return dict(ok=False, error=p.stderr.strip()[-400:])
    v = json.loads(p.stdout)["shaders"][0]["variants"][0]
    props = {x["name"]: x["value"] for x in v["properties"]}
    perf = v["performance"]
    return dict(ok=True, tool="malioc", core=core, properties=props,
                total_cycles=dict(zip(perf["pipelines"], perf["total_cycles"]["cycle_count"])),
                spills=props.get("stack_spill_bytes", 0) > 0,
                summary=f"regs {props.get('work_registers_used')}, occupancy {props.get('thread_occupancy')}%, "
                        f"spill {props.get('stack_spill_bytes', 0)} B")


def _rga(tool: str, asic: str, spv: Path, m: dict, out: Path) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([tool, "-s", "vk-spv-offline", "-c", asic, "--comp", str(spv),
                            "--isa", f"{d}/isa.txt", "-a", f"{d}/stats.csv"], capture_output=True, text=True)
        isa_files, stat_files = list(Path(d).glob("*isa*")), list(Path(d).glob("*stats*"))
        if p.returncode or not isa_files:
            return dict(ok=False, error=(p.stdout + p.stderr).strip()[-400:])
        isa = isa_files[0].read_text()
        st = next(csv.DictReader(stat_files[0].open())) if stat_files else {}
    (out / f"{m['name']}.isa.txt").write_text(isa)
    summary = isa_summary(isa, m)
    spill = int(st.get("VGPR_SPILLS") or 0) + int(st.get("SGPR_SPILLS") or 0)
    check = "" if summary["expected_scalar_fma"] is None else (" (matches design)" if summary["fma_matches_design"]
                                                                 else f" (design {summary['expected_scalar_fma']})")
    return dict(ok=True, tool="rga", asic=asic, approximation="AMD RDNA compiler, not the device driver's",
                stats=st, counts=summary, spills=spill > 0,
                summary=f"VGPR {st.get('USED_VGPRs')}, LDS {st.get('USED_LDS_BYTES')} B, spills {spill}, "
                        f"ISA FMA {summary['fma_scalar_equivalent']}{check}")


def run(session) -> None:
    out = session.out / "offline-isa"
    out.mkdir(exist_ok=True)
    tool_name, tgt = target(session.caps["gpu"])
    tool = _tool("MALIOC" if tool_name == "malioc" else "RGA", tool_name) if tool_name else None
    if not tool:
        reason = "no public offline compiler for this GPU" if not tool_name else f"{tool_name} not found (set ${tool_name.upper()} or PATH)"
        (out / "unavailable.json").write_text(json.dumps(dict(gpu=session.caps["gpu"], reason=reason)))
        print(f"  offline ISA skipped: {reason}", flush=True)
        return
    for m in session.manifest:
        path = out / f"{m['name']}.json"
        if path.exists() or not session.eligible(m):
            continue
        spv = paths.SHADER_OUT / f"{m['name']}.spv"
        res = _malioc(tool, tgt, spv) if tool_name == "malioc" else _rga(tool, tgt, spv, m, out)
        res["shader"] = m["name"]
        path.write_text(json.dumps(res, indent=2))
