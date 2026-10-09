import json
from typing import Any

import pytest

from igpu_roofline import cli, workload


def roof(value, unit, spread=0.01, confirmed=True):
    return {
        "value": value,
        "unit": unit,
        "confirmed": confirmed,
        "repeat_spread": spread,
    }


SUMMARY: dict[str, Any] = {
    "device": "Test GPU",
    "short_run": {
        "matrix_fp16": roof(200.0, "TFLOP/s"),
        "matrix_fp16_feed_shared": roof(150.0, "TFLOP/s"),
        "matrix_int8": roof(400.0, "TOP/s", spread=0.08),
        "dot_int8": roof(40.0, "TOP/s"),
        "alu_fp16": roof(30.0, "TFLOP/s", confirmed=False),
        "global_read": roof(500.0, "GB/s"),
    },
}


def case(**kw):
    base = {
        "suite": "linear",
        "model": "llama-1b",
        "op": "wq_wo",
        "storage": "buffer",
        "variant": "coopmat",
        "ok": True,
    }
    return base | kw


def et_json(tmp_path, cases):
    path = tmp_path / "et.json"
    path.write_text(
        json.dumps(
            {
                "schema": workload.SCHEMA,
                "device": "Test GPU",
                "group_size": 128,
                "cases": cases,
            }
        )
    )
    return path


def test_prefill_wmma_is_compute_bound_against_hand_computed_roof():
    c = case(
        scheme="4w",
        regime="prefill",
        kernel="linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half",
        M=2048,
        K=2048,
        N=2048,
        kernel_median_us=100.0,
    )
    usable, _ = workload.usable_roofs(SUMMARY)
    row = workload.place(c, 128, usable)
    ops = 2 * 2048**3
    nbytes = 2048 * 2048 // 2 + 16 * 2048 * 2 + 2 * 2048 * 2048 * 2
    assert workload.compulsory_bytes(c, 128) == nbytes
    assert row["compute_roof"] == "matrix_fp16"
    assert row["bound"] == "compute"
    assert row["roof_fraction"] == pytest.approx(ops / 100e-6 / 200e12)
    assert row["feed_fraction"] == pytest.approx(ops / 100e-6 / 150e12)
    assert row["intensity_ops_per_byte"] == pytest.approx(ops / nbytes)


def test_decode_is_memory_bound_and_unusable_roofs_are_never_ceilings():
    usable, rejected = workload.usable_roofs(SUMMARY)
    assert "matrix_int8" not in usable and "spread" in rejected["matrix_int8"]
    assert rejected["alu_fp16"] == "unconfirmed"
    tiled = case(
        scheme="8da4w",
        regime="decode",
        kernel="linear_dq8ca_q4gsw_tiled_buffer_texture2d_half",
        M=1,
        K=2048,
        N=2048,
        kernel_median_us=20.0,
    )
    row = workload.place(tiled, 128, usable)
    assert row["compute_roof"] == "dot_int8"
    assert row["bound"] == "memory"
    nbytes = 2048 * 2048 // 2 + 16 * 2048 * 2 + 2048 + 8 + 2048 * 4 + 2048 * 2
    assert row["achieved_gbps"] == pytest.approx(nbytes / 20e-6 / 1e9)
    assert row["roof_fraction"] == pytest.approx(nbytes / 20e-6 / 500e9)
    wmma = workload.place(
        tiled | {"kernel": "linear_dq8ca_q4gsw_coopmat_x", "regime": "prefill"},
        128,
        usable,
    )
    assert wmma["compute_roof"] is None  # matrix_int8 spread too wide
    tiled4w = workload.place(tiled | {"scheme": "4w"}, 128, usable)
    assert tiled4w["compute_roof"] is None  # alu_fp16 unconfirmed


def test_workload_cli_writes_report_and_skips_failed_cases(tmp_path):
    dev = tmp_path / "gpu"
    (dev / "report").mkdir(parents=True)
    (dev / "report" / "summary.json").write_text(json.dumps(SUMMARY))
    good = case(
        scheme="4w",
        regime="prefill",
        kernel="linear_q4gsw_coopmat_x",
        M=2048,
        K=2048,
        N=2048,
        kernel_median_us=100.0,
    )
    path = et_json(
        tmp_path,
        [
            good,
            good | {"ok": False},
            good | {"suite": "correctness"},
            good | {"kernel_median_us": None},
            good | {"suite": "sdpa"},
        ],
    )
    cli.main(
        [
            "--results",
            str(tmp_path),
            "workload",
            "--device",
            "gpu",
            "--et-json",
            str(path),
        ]
    )
    out = json.loads((dev / "report" / "workload-et.json").read_text())
    assert len(out["rows"]) == 1
    assert set(out["roofs_used"]) == {
        "matrix_fp16",
        "matrix_fp16_feed_shared",
        "global_read",
    }
    md = (dev / "report" / "WORKLOAD-et.md").read_text()
    assert "linear_q4gsw_coopmat_x" in md


def test_wrong_schema_is_rejected(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"schema": "other", "cases": []}))
    with pytest.raises(ValueError):
        workload.load_cases(path)


def test_fp32_accumulate_4w_kernel_uses_fp16_fp32_matrix_roof():
    summary = dict(
        SUMMARY,
        short_run=dict(SUMMARY["short_run"], matrix_fp16_fp32=roof(300.0, "TFLOP/s")),
    )
    usable, _ = workload.usable_roofs(summary)
    c = case(
        scheme="4w",
        regime="prefill",
        kernel="linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k32g42s32f32c_texture3d_texture2d_half",
        M=2048,
        K=2048,
        N=2048,
        kernel_median_us=100.0,
    )
    assert workload.place(c, 128, usable)["compute_roof"] == "matrix_fp16_fp32"
    plain = c | {
        "kernel": "linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k32g42s32_buffer_texture2d_half"
    }
    assert workload.place(plain, 128, usable)["compute_roof"] == "matrix_fp16"
