"""Unit tests for accounting, timing, SPIR-V auditing and report logic (no GPU needed)."""
import pytest

from igpu_roofline.isa_offline import expected_scalar_fma, fma_equivalents
from igpu_roofline.measure import accounting, differential
from igpu_roofline.report import choose_roofs, hierarchical_ridges, is_control, metric
from igpu_roofline.spirv_audit import check, ledger
from igpu_roofline.stages import PLANS, is_control as config_is_control
from igpu_roofline.volatile_workgroup import annotate


# --- accounting ------------------------------------------------------------------------
def test_batch_multiplies_traffic_not_capacity():
    c = dict(family="memory", op=2, n=1024, width=4, wg=64, groups=16)
    single, batch = accounting(c, 3), accounting(dict(c, batch_dispatches=8), 3)
    assert batch["logical_global_bytes"] == single["logical_global_bytes"] * 8
    assert batch["working_set_bytes"] == single["working_set_bytes"]


def test_copy_counts_both_directions():
    assert accounting(dict(family="memory", op=2, n=1024, width=4, wg=64, groups=16), 3)["logical_global_bytes"] == 1024 * 16 * 2 * 3


def test_replicas_are_not_capacity():
    a = accounting(dict(family="memory", op=0, n=1024, width=1, wg=64, groups=64, replicas=4), 10)
    assert a["working_set_bytes"] == 4096
    assert a["logical_global_bytes"] == 4096 * 4 * 10 + 4096 * 4


def test_babelstream_dot():
    a = accounting(dict(family="memory", op=6, n=1024, width=4, wg=64, groups=16), 2)
    assert a["logical_global_bytes"] == 1024 * 16 * 2 * 2
    assert a["float_ops"] == 1024 * 4 * 2 * 2


def test_matrix_integer_ops_are_not_flops():
    a = accounting(dict(family="matrix", dtype="int8", m=64, matrix_n=16, k=32, chains=4, wg=64, groups=512), 128)
    assert a["float_ops"] == 0
    assert a["integer_ops"] == 2 * 64 * 16 * 32 * 4 * 512 * 128


def test_dot8_counts_every_dot():
    assert accounting(dict(family="dot", chains=4, wg=64, groups=8, dots_per_step=8), 10)["integer_ops"] == 8 * 64 * 8 * 4 * 10 * 8


def test_shared_read_counts_accumulators_and_fill():
    c = dict(family="shared", kind="bw", op=0, dtype="fp32", width=4, wg=64, groups=2, shared_count=256, accumulators=8)
    a = accounting(c, 16)
    assert a["logical_shared_bytes"] == 128 * 16 * 16 * 8 + 2 * 256 * 16
    assert a["barriers_per_workgroup"] == 1


def test_shared_write_has_no_fill():
    c = dict(family="shared", kind="bw", op=2, dtype="fp16", width=2, wg=64, groups=2, shared_count=256, accumulators=8)
    a = accounting(c, 16)
    assert a["shared_initialization_bytes"] == 0
    assert a["logical_shared_bytes"] == 128 * 4 * 16 * 8 + 128 * 4
    assert a["logical_global_bytes"] == 128 * 2 * 4


def test_ert_intensity():
    a = accounting(dict(family="ert", flops_per_element=64, n=1000, wg=64, groups=4), 3)
    assert a["float_ops"] / a["logical_global_bytes"] == pytest.approx(64 * 8 / 32)


def test_latency_loads():
    a = accounting(dict(family="latency", n=4096, wg=1, groups=1, chain_stride_bytes=64), 100)
    assert (a["dependent_loads"], a["working_set_bytes"]) == (1600, 16384)


# --- timing ----------------------------------------------------------------------------
def test_differential_removes_fixed_cost():
    fixed, per_loop, L, H = 0.001, 0.0001, 100, 50
    samples = [dict(sample=i, loops=L, seconds=fixed + L * per_loop + (i % 3) * 1e-6) for i in range(9)]
    halves = {i: dict(sample=i, loops=H, seconds=fixed + H * per_loop + (i % 3) * 1e-6) for i in range(9)}
    d = differential(samples, halves)
    assert d["seconds_per_loop"] == pytest.approx(per_loop, abs=1e-9)
    assert d["fixed_seconds"] == pytest.approx(fixed, abs=1e-5)
    assert d["valid"]


def test_differential_rejects_negative_overhead():
    d = differential([dict(sample=0, loops=100, seconds=0.010)], {0: dict(sample=0, loops=50, seconds=0.004)})
    assert not d["valid"]


def test_timestamp_wrap_arithmetic():
    period = 52.08333206176758
    assert ((3 - ((1 << 48) - 2)) & ((1 << 48) - 1)) * period == pytest.approx(260.4166603088379)


# --- SPIR-V ------------------------------------------------------------------------------
ASM = """%pw = OpTypePointer Workgroup %float
%ps = OpTypePointer StorageBuffer %float
%data = OpVariable %pw Workgroup
%buf = OpVariable %ps StorageBuffer
%a = OpAccessChain %ps %buf %i
%x = OpLoad %float %a
%w = OpAccessChain %pw %data %i
OpStore %w %x Volatile
%y = OpExtInst %float %1 Fma %x %x %x
OpControlBarrier %uint_2 %uint_2 %uint_264
"""


def test_ledger_storage_classes():
    c = ledger(ASM)
    assert (c["load_StorageBuffer"], c["store_Workgroup"], c["fma"], c["control_barrier"], c["volatile"]) == (1, 1, 1, 1, 1)


def test_ledger_mismatch_is_reported():
    assert check(dict(family="alu", chains=1), {"fma": 15}) == {"fma": (16, 15)}


def test_volatile_only_on_workgroup_accesses():
    src = ("%pw = OpTypePointer Workgroup %float\n%pf = OpTypePointer Function %float\n%w = OpAccessChain %pw %data %i\n"
           "%f = OpVariable %pf Function\n%a = OpLoad %float %w\n%b = OpLoad %float %f\nOpStore %w %a\nOpStore %f %b\n")
    out, n = annotate(src)
    assert n == 2
    assert "OpLoad %float %w Volatile" in out and "OpLoad %float %f\n" in out and "OpStore %w %a Volatile" in out


def test_volatile_rejects_unknown_mask():
    with pytest.raises(AssertionError):
        annotate("%pw = OpTypePointer Workgroup %float\n%w = OpVariable %pw Workgroup\n%x = OpLoad %float %w Aligned 4\n")


def test_amd_isa_fma_counting():
    isa = "  v_fma_f32 v1, v2, v3, v4\n  v_fmac_f32 v1, v2, v3\n  v_pk_fma_f16 v1, v2, v3, v4\n  v_dual_fmac_f32 v1, v2, v3 :: v_dual_fmac_f32 v4, v5, v6\n"
    assert fma_equivalents(isa) == 1 + 1 + 2 + 2
    assert expected_scalar_fma(dict(family="alu", chains=16, width=4)) == 1024


# --- report logic -------------------------------------------------------------------------
def test_controls_never_define_roofs():
    base = {"accounting": {"logical_global_bytes": 1, "logical_shared_bytes": 1}}
    keys = [metric(dict(base, config=cfg))[0] for cfg in (
        dict(family="memory", op=2, volatile_global=True), dict(family="memory", op=1, memory_mode="host_coherent"),
        dict(family="shared", op=0, dtype="fp32"), dict(family="shared", kind="bw", op=0, dtype="fp32"))]
    assert keys == ["global_copy_volatile", "global_write_hostcoherent", "shared_fp32_read_1acc", "shared_fp32_read"]
    assert [is_control(k) for k in keys] == [True, True, True, False]
    assert config_is_control(dict(family="shared", op=0)) and not config_is_control(dict(family="shared", kind="bw", op=0))


def test_non_roof_families():
    assert metric({"config": {"family": "latency"}, "accounting": {}}) is None
    assert metric({"config": {"family": "ert"}, "accounting": {}}) is None


def test_partial_sustained_keeps_short_roofs():
    short = {"alu_fp32": {"value": 4, "unit": "TFLOP/s"}, "global_copy": {"value": 80, "unit": "GB/s"}}
    assert choose_roofs(short, {"alu_fp32": {"value": 3, "unit": "TFLOP/s", "batches": 1}}) == (short, "short-run")
    full = {k: dict(v, batches=3) for k, v in short.items()}
    assert choose_roofs(short, full) == (full, "sustained")
    assert hierarchical_ridges(short)["global"]["alu_fp32"] == 50


def test_plans():
    assert set(PLANS) == {"quick", "fast", "standard", "gold"}
    assert PLANS["fast"]["sustain"]["duration"] == 120 and PLANS["fast"]["confirm"] == dict(top=2, reps=3)
    assert PLANS["quick"]["sustain"] is None
    assert PLANS["gold"]["sustain"]["batches"] == 3
    assert all(p["warmup_seconds"] > 0 for p in PLANS.values())


# --- roof selection and hardening ---------------------------------------------------------
from igpu_roofline.spirv_audit import expected  # noqa: E402
from igpu_roofline.stages import QUALITY, matrix_grid, quality  # noqa: E402


def _row(**kw):
    r = dict(accepted=True, cv=0.01, n=21, below_target_duration=False, differential=dict(valid=True, fixed_fraction=0.02))
    r.update(kw)
    return r


def test_quality_gates():
    assert quality(_row()) == []
    assert quality(_row(cv=0.10)) == []                    # 10 % scatter, 21 samples: median SE ~2.7 %
    assert "noisy_median" in quality(_row(cv=0.53))        # the old int8 roof
    assert "noisy_median" in quality(_row(cv=0.10, n=5))
    assert "short" in quality(_row(below_target_duration=True))
    assert "fixed_cost" in quality(_row(differential=dict(valid=True, fixed_fraction=0.67)))
    assert "fixed_cost" in quality(_row(differential=dict(valid=False, fixed_fraction=0.0)))
    assert "rejected" in quality(_row(accepted=False))
    assert quality(_row(differential=None)) == []  # streaming kernels have no differential


def test_matrix_grid_reaches_large_launches_for_every_dtype():
    caps = dict(subgroup=16, max_workgroup_invocations=1024)
    small = dict(chains=8, m=4, matrix_n=16, dtype="int8")
    assert (16, 16384) in matrix_grid(small, caps, quick=True)
    assert {(16, 16384), (64, 16384), (64, 64)} <= set(matrix_grid(small, caps, quick=False))
    big = dict(chains=8, m=64, matrix_n=64, dtype="fp16_fp32")
    assert all(g * 8 * 64 * 64 * 4 <= 256 * 1024 ** 2 for _, g in matrix_grid(big, caps, quick=False))


def test_ert_ledger_chunking_and_ilp():
    assert expected(dict(family="ert", flops_per_element=16))["fma"] == 64
    assert expected(dict(family="ert", flops_per_element=1024))["fma"] == 4 * 32
    assert expected(dict(family="ert", flops_per_element=1024, elems=16))["fma"] == 16 * 32
    assert expected(dict(family="ert", flops_per_element=1024, full_unroll=True))["fma"] == 4096
    assert expected(dict(family="ert", flops_per_element=8, elems=8))["load_StorageBuffer"] == 8


def test_plans_confirm_roofs():
    assert PLANS["quick"]["confirm"] == dict(top=1, reps=3)
    assert all(PLANS[p]["confirm"] == dict(top=3, reps=5) for p in ("standard", "gold"))


# --- device-state guard -------------------------------------------------------------------
import json as _json  # noqa: E402
import types  # noqa: E402

from igpu_roofline.device import AdbDevice  # noqa: E402
from igpu_roofline.stages import Guard  # noqa: E402

THERMAL = """Cached temperatures:
\tTemperature{mValue=99.0, mType=1, mName=GPU, mStatus=0}
Current temperatures from HAL:
\tTemperature{mValue=37.5, mType=0, mName=CPU, mStatus=0}
\tTemperature{mValue=61.1, mType=1, mName=GPU, mStatus=0}
Current cooling devices from HAL:
"""


def test_gpu_temperature_reads_current_hal_section():
    dev = AdbDevice.__new__(AdbDevice)
    dev.shell = lambda *a, **k: types.SimpleNamespace(stdout=THERMAL)
    assert dev.gpu_temp_c() == 61.1


def test_quarantine_moves_only_results_after_last_good_sentinel(tmp_path):
    def result(stage, key, utc):
        d = tmp_path / stage
        d.mkdir(exist_ok=True)
        (d / f"{key}.telemetry.json").write_text(_json.dumps([dict(utc=utc)]))
        (d / f"{key}.json").write_text("{}")
        (d / f"{key}.jsonl").write_text("")
    result("sweep-compute", "early", "2026-01-01T00:00:00+00:00")
    result("sweep-compute", "late", "2026-01-01T00:10:00+00:00")
    result("probe", "sentinel", "2026-01-01T00:11:00+00:00")
    g = Guard.__new__(Guard)
    g.s = types.SimpleNamespace(out=tmp_path)
    assert g.quarantine("2026-01-01T00:05:00+00:00") == 1
    assert (tmp_path / "sweep-compute" / "early.json").exists()
    assert not (tmp_path / "sweep-compute" / "late.json").exists()
    assert (tmp_path / "probe" / "sentinel.json").exists()
    assert len(list((tmp_path / "superseded").glob("degraded-*/sweep-compute/late.*"))) == 3


def test_guard_needs_confirmed_drop_against_median(monkeypatch):
    import igpu_roofline.stages as st
    g = Guard.__new__(Guard)
    g.s, g.plan, g.busy, g.readings, g.last_good_utc = None, None, False, [3.3, 3.4, 3.58], "t0"
    g.quarantine = lambda since: 0
    seq = iter([3.20, 2.2, 2.25, 2.21])  # one low outlier (passes), then a real drop
    monkeypatch.setattr(st, "probe", lambda s, label, plan: dict(
        accepted=True, accounting=dict(float_ops=next(seq) * 1e12), median_seconds=1.0))
    assert g.check("a") == 3.20            # 3.20 >= 0.85 * median(3.3, 3.4, 3.58)
    with pytest.raises(st.DeviceDegraded):
        g.check("b")                       # 2.2, rechecked 2.25 / 2.21 -> degraded


def test_manifest_runner_for_android_host_and_new_manifests():
    from igpu_roofline.paths import manifest_runner
    assert manifest_runner({"build/android/roofline": "a"}) == "a"
    assert manifest_runner({"build/host/roofline": "h"}) == "h"
    assert manifest_runner({"runner_sha256": "r", "build/host/roofline": "h"}) == "r"


def test_drifting_or_unsteady_rows_are_gated():
    assert "drifting" in quality(_row(sample_drift=2.4))       # 780M shared read: 15 -> 4.4 ms
    assert "warmup_unsteady" in quality(_row(warmup=dict(steady=False)))
    assert quality(_row(sample_drift=0.02, warmup=dict(steady=True))) == []


def test_only_current_runner_and_shader_rows_count():
    from igpu_roofline.session import Session
    s = Session.__new__(Session)
    s.runner_sha, s.manifest = "R2", [{"name": "matrix_x", "spirv_sha256": "S2"}]
    assert s.current({"config": {"name": "matrix_x", "runner_sha256": "R2", "spirv_sha256": "S2"}})
    assert not s.current({"config": {"name": "matrix_x", "runner_sha256": "R1", "spirv_sha256": "S2"}})  # old runner
    assert not s.current({"config": {"name": "matrix_x", "runner_sha256": "R2", "spirv_sha256": "S1"}})  # old shader


def test_shapes_table_names_types_and_scope():
    from igpu_roofline.shapes import table
    md = table({"matrix_shapes": [dict(m=16, n=16, k=16, a=3, b=7, c=5, result=5, scope=3, saturating=1)]})
    assert "| 16×16×16 | s8 | u8 | s32 | s32 | subgroup | yes |" in md
    assert "none" in table({"matrix_shapes": []})


def test_matrix_feed_accounting_and_keys():
    from igpu_roofline.stages import matrix_feed_key
    base = dict(family="matrix", dtype="fp16_fp32", m=16, matrix_n=16, k=16, chains=4, groups=100, wg=128, subgroup=64)
    plain = accounting(base, 10)
    assert plain["float_ops"] == 2 * 16 * 16 * 16 * 4 * 100 * 2 * 10          # 2 subgroups per workgroup
    tile = (16 * 16 + 16 * 16) * 2
    sh = accounting(dict(base, feed="shared", tiles=4, n=4), 10)
    assert sh["matrix_load_bytes"] == 100 * 2 * 10 * tile
    assert sh["logical_shared_bytes"] == sh["matrix_load_bytes"] + 100 * 4 * tile
    gm = accounting(dict(base, feed="global", n=1 << 20), 10)
    assert gm["working_set_bytes"] == (1 << 20) * tile
    assert matrix_feed_key(dict(base, feed="global"), gm) == "matrix_fp16_fp32_feed_dram"
    assert matrix_feed_key(dict(base, feed="global"), dict(working_set_bytes=1 << 20)) == "matrix_fp16_fp32_feed_cache"
    assert matrix_feed_key(dict(base, feed="shared"), sh) == "matrix_fp16_fp32_feed_shared"


def test_texture_accounting_and_keys():
    from igpu_roofline.stages import texture_key
    c = dict(family="texture", format="rgba16f", mode="tex3d", wg=256, groups=4096, n=1 << 25)
    a = accounting(c, 2)
    assert a["logical_global_bytes"] == (1 << 25) * 8 * 2 + 256 * 4096 * 16
    assert texture_key(c, a) == "texture_rgba16f_tex3d_dram"
    assert texture_key(c, dict(working_set_bytes=1 << 20)) == "texture_rgba16f_tex3d_cache"
    assert expected(dict(family="texture", tex_dim=3)) == {"image_fetch": 1, "store_StorageBuffer": 1}
