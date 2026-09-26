"""Admission, isolation and sentinel regressions; no GPU required."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from igpu_roofline import admission, paths, report, stages
from igpu_roofline.device import LocalDevice, run_owned
from igpu_roofline.locking import DeviceLock
from igpu_roofline.measure import accounting
from igpu_roofline.planning import config_identity
from igpu_roofline.session import Session
from igpu_roofline.shaders import _matrix_source, catalogue


def trusted() -> dict:
    v = {"validation": {"pass": True, "checked": 128, "max_abs_error": 0}}
    return {
        "schema_version": 2,
        "validation_scope": "pre_and_post",
        "rc": 0,
        "validation_pre": copy.deepcopy(v),
        "validation_post": copy.deepcopy(v),
        "accepted": True,
        "n": 21,
        "cv": 0.01,
        "median_seconds": 0.006,
        "min_seconds": 0.0059,
        "accounting": {"float_ops": 600, "integer_ops": 0},
        "config": {
            "name": "alu",
            "family": "alu",
            "dtype": "fp32",
            "runner_sha256": "R",
            "spirv_sha256": "S",
        },
    }


def test_matrix_output_and_bytes_cover_all_subgroups():
    c = {
        "family": "matrix",
        "dtype": "fp16_fp32",
        "m": 8,
        "matrix_n": 16,
        "k": 16,
        "chains": 4,
        "groups": 32,
        "wg": 64,
        "subgroup": 16,
    }
    a = accounting(c, 8)
    assert a["logical_global_bytes"] == 32 * 4 * (
        (8 * 16 + 16 * 16) * 2 + 8 * 16 * 4 * 4
    )
    assert a["float_ops"] == 2 * 8 * 16 * 16 * 4 * 32 * 4 * 8
    with pytest.raises(ValueError, match="whole subgroups"):
        accounting(dict(c, wg=17), 8)
    source = _matrix_source(
        (paths.SHADER_SRC / "matrix.comp").read_text(), 4, "fp16_fp32"
    )
    assert source.count("(gl_WorkGroupID.x*gl_NumSubgroups+gl_SubgroupID)*CHAINS+") == 4
    names = {job[0] for job in catalogue()}
    assert {
        "matrix_fp16_8x16x16_c4",
        "matrix_fp16_fp32_8x16x16_c4",
        "matrix_int8_8x16x32_c4",
    } <= names
    caps = {
        "subgroup": 16,
        "max_workgroup_invocations": 1024,
        "max_storage_buffer_range": 1024**2,
    }
    assert all(
        g * (wg // 16) * 4 * 8 * 16 * 4 <= 1024**2
        for wg, g in stages.matrix_grid(c, caps, False)
    )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"schema_version": 1}, "historical_validation_coverage"),
        ({"validation_post": None}, "missing_post_validation"),
        (
            {"validation_post": {"validation": {"pass": False}}},
            "failed_post_validation",
        ),
        ({"rc": -9}, "abnormal_exit"),
        ({"sample_drift": 0.1}, "drifting"),
        ({"below_target_duration": True}, "short"),
    ],
)
def test_admission_rejects_incomplete_and_low_quality(mutation, reason):
    row = trusted()
    row.update(mutation)
    assert reason in admission.reasons(row, "R", {"alu": "S"})


@pytest.mark.parametrize("field", ["runner_sha256", "spirv_sha256"])
def test_missing_hash_never_matches(field):
    row = trusted()
    del row["config"][field]
    assert admission.build_reasons(row, "R", {"alu": "S"})
    assert admission.build_reasons(trusted(), None, {})


def test_sustained_requires_both_builds():
    row = trusted()
    row["config"].update(
        executable="roofline_sustained", runner_sha256="T", reference_runner_sha256="R"
    )
    assert admission.build_reasons(row, "R", {"alu": "S"}, "T") == []
    assert admission.build_reasons(row, "R", {"alu": "S"}, "old") == [
        "stale_sustained_runner"
    ]
    assert admission.build_reasons(row, "old", {"alu": "S"}, "T") == ["stale_runner"]


def test_confirmation_preserves_attempts_and_requires_planned_repeats():
    rows: list[dict] = [
        dict(
            trusted(),
            config=dict(trusted()["config"], confirm_key="alu_fp32", replicate=i),
        )
        for i in range(3)
    ]
    admit = lambda r: not admission.reasons(r, "R", {"alu": "S"})
    assert not admission.confirmed_groups(rows[:2], admit, stages.rate)
    rows[2]["validation_post"] = None
    assert admission.confirmed_groups(rows, admit, stages.rate)
    rows[1]["sample_drift"] = 0.2
    assert not admission.confirmed_groups(rows, admit, stages.rate)


@pytest.mark.parametrize(
    "post,rc,accepted", [(True, 0, True), (False, 0, False), (True, 2, False)]
)
def test_session_requires_real_post_event(tmp_path, post, rc, accepted):
    s = Session.__new__(Session)
    s.out, s.plan, s.guard, s.runner_sha = tmp_path, "quick", None, "R"
    s.manifest = [{"name": "alu", "spirv_sha256": "S"}]
    s.device = SimpleNamespace(
        remote="unused",
        serial="fake",
        stop=lambda proc: proc.wait(),
        push=lambda *a: None,
        telemetry=lambda: {},
        faults=lambda: None,
    )
    events = [
        {"event": "schema", "schema_version": 2, "validation_scope": "pre_and_post"},
        dict(event="validation_pre", **trusted()["validation_pre"]),
    ]
    events += [
        {
            "event": "sample",
            "sample": i,
            "loops": 4,
            "seconds": 0.006,
            "elapsed_seconds": (i + 1) * 0.006,
        }
        for i in range(3)
    ]
    if post:
        events.append(
            dict(
                event="validation_post",
                sample=2,
                loops=4,
                **trusted()["validation_post"],
            )
        )
    script = (
        "import sys; print("
        + repr("\n".join(json.dumps(e) for e in events))
        + f"); sys.exit({rc})"
    )
    s.device.popen = lambda exe, out, err: subprocess.Popen(
        [sys.executable, "-c", script], stdout=out, stderr=err
    )
    c = dict(trusted()["config"], wg=64, groups=32, width=1, chains=4)
    result = s.run(c, "sweep-compute")
    assert result["accepted"] is accepted
    assert (tmp_path / result["raw"]).exists()


def test_device_lock_is_independent_of_results_and_stage(tmp_path):
    identity = "test-device:" + str(tmp_path)
    with DeviceLock(identity):
        code = (
            "from igpu_roofline.locking import DeviceLock; DeviceLock("
            + repr(identity)
            + ")"
        )
        child = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        assert child.returncode != 0
        assert str(os.getpid()) in child.stderr and "occupied" in child.stderr
        with DeviceLock(identity + "-second-gpu"):
            pass
    with DeviceLock(identity):
        pass
    with (
        DeviceLock("gpu-one", path=tmp_path / "owner.lock"),
        pytest.raises(RuntimeError, match="occupied"),
    ):
        DeviceLock("gpu-two", path=tmp_path / "owner.lock")


def test_timeout_kills_only_owned_process(tmp_path):
    device = LocalDevice.__new__(LocalDevice)
    device.remote, device.env = str(tmp_path), os.environ.copy()
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    (tmp_path / "sleeper.py").write_text("import time; time.sleep(30)")
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            run_owned(device, sys.executable, "sleeper.py", 0.03)
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait()


def guard(tmp_path, monkeypatch):
    s = SimpleNamespace(
        out=tmp_path,
        runner_sha="R",
        _shader_shas={"alu": "S"},
        device=SimpleNamespace(identity="GPU", serial="gpu", gpu_temp_c=lambda: None),
    )
    g = stages.Guard(s, {})
    counter = []

    def probe(*args):
        counter.append(args[1])
        row: dict = dict(trusted(), raw=f"probe/{len(counter)}.jsonl")
        row["config"]["runner_sha256"] = s.runner_sha
        return row

    monkeypatch.setattr(stages, "probe", probe)
    return g, counter


def test_sentinel_reuse_preserves_baseline_and_quarantine_boundary(
    tmp_path, monkeypatch
):
    g, calls = guard(tmp_path, monkeypatch)
    g.check("replay_start")
    g.check("replay_end")
    previous = g.last_good_utc
    g.check("confirm_start")
    assert len(calls) == len(g.readings) == 2
    assert g.last_good_utc == previous
    g.check("confirm_end")
    assert len(calls) == 3
    records = [
        json.loads(x)
        for x in (tmp_path / "sentinel-checks.jsonl").read_text().splitlines()
    ]
    assert records[2]["reused"] and records[2]["source"] == records[1]["source"]


@pytest.mark.parametrize(
    "interruption",
    ["expiry", "measurement", "cooldown", "error", "device", "build", "periodic"],
)
def test_sentinel_reuse_invalidations(tmp_path, monkeypatch, interruption):
    g, calls = guard(tmp_path, monkeypatch)
    g.check("first_end")
    if interruption == "expiry":
        g._reusable["completed"] -= 6
    elif interruption == "measurement":
        g.before("validate")
    elif interruption == "cooldown":
        temperatures = iter([90, 40])
        g.s.device.gpu_temp_c = lambda: next(temperatures)
        monkeypatch.setattr(stages.time, "sleep", lambda *_: None)
        g.before("sweep-compute")
    elif interruption == "error":
        monkeypatch.setattr(
            stages, "probe", lambda *a: (_ for _ in ()).throw(RuntimeError("failed"))
        )
        with pytest.raises(RuntimeError):
            g.check("interrupted")
        assert g._reusable is None
        return
    elif interruption == "device":
        g.s.device.identity = "other"
    elif interruption == "build":
        g.s.runner_sha = "new"
    else:
        g.count = 19
        g.after("sweep-compute")
    g.check("second_start")
    assert len(calls) == (3 if interruption == "periodic" else 2)


def test_reports_share_admission_and_do_not_mix_sustained(tmp_path, monkeypatch):
    (tmp_path / "capabilities.json").write_text(
        json.dumps({"gpu": "fake", "serial": "fake"})
    )
    (tmp_path / "artifact-manifest.json").write_text(
        json.dumps({"runner_sha256": "R", "sustained_runner_sha256": "T"})
    )
    (tmp_path / "shader-shas.json").write_text(json.dumps({"alu": "S"}))
    rows = []
    for i in range(3):
        row = trusted()
        row["config"].update(confirm_key="alu_fp32", replicate=i)
        row["source"] = f"confirm/{i}.json"
        rows.append(row)
    ref = config_identity(rows[0]["config"])
    for i in range(3):
        row = trusted()
        row["config"].update(
            duration_seconds=60,
            executable="roofline_sustained",
            runner_sha256="T",
            reference_runner_sha256="R",
            reference_config_identity=ref,
            sustained_roof="alu_fp32",
        )
        row.update(
            source=f"sustain-{i}/x.json",
            steady_last60=True,
            last60={"median_seconds": 0.006},
        )
        rows.append(row)
    bad = trusted()
    bad.update(
        source="sweep-compute/bad.json",
        median_seconds=0.000001,
        below_target_duration=True,
    )
    rows.append(bad)
    for fn in (
        "write_report_md",
        "plot_rooflines",
        "plot_working_set",
        "plot_shared_stride",
        "write_sustained",
    ):
        monkeypatch.setattr(report, fn, lambda *a: None)
    from igpu_roofline import insights

    seen = []
    monkeypatch.setattr(
        insights, "write_all", lambda f, r, valid, c, s: seen.append(valid)
    )
    monkeypatch.setattr(report, "load_rows", lambda _: copy.deepcopy(rows))
    summary = report.analyze(tmp_path)
    assert summary["roof_basis"] == "sustained"
    assert summary["short_run"]["alu_fp32"]["value"] == 1e-7
    assert all(r["source"] != bad["source"] for r in seen[-1])
    assert "short" in (tmp_path / "report/all-configurations.csv").read_text()
    rows[5]["steady_last60"] = False
    assert report.analyze(tmp_path)["roof_basis"] == "short-run"
    rows[5]["steady_last60"] = True
    rows[5]["config"]["duration_seconds"] = 120
    assert report.analyze(tmp_path)["sustained"]["alu_fp32"]["batches"] == 2
    rows[5]["config"]["duration_seconds"] = 60
    rows[5]["config"]["reference_config_identity"] = "other configuration"
    assert report.analyze(tmp_path)["sustained"]["alu_fp32"]["batches"] == 2
    rows[5]["config"]["reference_config_identity"] = ref
    rows[5]["config"]["wg"] = 512
    assert report.analyze(tmp_path)["sustained"]["alu_fp32"]["batches"] == 2
    del rows[5]["config"]["wg"]
    rows[5]["config"]["loops"] = 123
    assert report.analyze(tmp_path)["sustained"]["alu_fp32"]["batches"] == 2
    del rows[5]["config"]["loops"]
    rows[5]["source"] = "sustain-1/duplicate.json"
    assert report.analyze(tmp_path)["sustained"]["alu_fp32"]["batches"] == 2


def test_native_calibration_policy(tmp_path):
    source = Path(__file__).with_name("calibration_test.cpp")
    binary = tmp_path / "calibration"
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(paths.REPO / "runner/src"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_local_identity_does_not_depend_on_name_or_stage(tmp_path, monkeypatch):
    from igpu_roofline import device

    uuid = "123456789abcdef0123456789abcdef0"
    calls = []

    def identity(command, **kw):
        calls.append(command)
        return SimpleNamespace(
            stdout=json.dumps({"device_uuid": uuid, "gpu": "same name"})
        )

    monkeypatch.setattr(device.subprocess, "run", identity)
    monkeypatch.setenv("IGPU_ROOFLINE_STAGE", str(tmp_path / "first"))
    first = LocalDevice("first-alias")
    monkeypatch.setenv("IGPU_ROOFLINE_STAGE", str(tmp_path / "second"))
    second = LocalDevice("second-alias")
    assert first.identity == second.identity == "vulkan:" + uuid
    assert first.remote != second.remote
    assert Path(first.remote).name == Path(second.remote).name == uuid
    assert first.env["IGPU_ROOFLINE_UUID"] == uuid
    assert calls == [[str(paths.RUNNER), "identity"]] * 2
    assert not (tmp_path / "first").exists()  # construction is read-only


def test_shapes_lock_precedes_deployment(tmp_path):
    from igpu_roofline.shapes import probe

    device = SimpleNamespace(identity=f"shape-lock:{tmp_path}")
    with DeviceLock(device.identity), pytest.raises(RuntimeError, match="occupied"):
        probe(
            device, Path("unused")
        )  # no transport method is even needed before locking


def test_adb_stop_uses_unique_pid_and_start_time(monkeypatch):
    from igpu_roofline.device import AdbDevice

    commands = []
    device = AdbDevice("serial")
    monkeypatch.setattr(
        device,
        "shell",
        lambda command, **kw: commands.append(command) or SimpleNamespace(returncode=0),
    )
    actions = []
    proc = SimpleNamespace(
        remote_pidfile="/data/local/tmp/process-unique.pid",
        kill=lambda: actions.append("kill"),
        wait=lambda: actions.append("wait"),
    )
    device.stop(proc)
    command = commands[0]
    assert proc.remote_pidfile in command and ".cancel" in command
    assert "started" in command and "current" in command and "while" in command
    assert "pkill" not in command and "pidof" not in command
    assert actions == ["kill", "wait"]


def test_sentinel_degradation_after_reuse_keeps_original_boundary(
    tmp_path, monkeypatch
):
    g, _ = guard(tmp_path, monkeypatch)
    g.check("first_end")
    boundary = g.last_good_utc
    g.check("second_start")
    row = trusted()
    row["accounting"]["float_ops"] = 100
    monkeypatch.setattr(stages, "probe", lambda *a: row)
    quarantined = []
    monkeypatch.setattr(g, "quarantine", lambda since: quarantined.append(since) or 0)
    with pytest.raises(stages.DeviceDegraded):
        g.check("second_end")
    assert quarantined == [boundary]
    assert len(g.readings) == 1 and g._reusable is None


def test_failed_sweep_without_samples_is_diagnostic_not_a_candidate(tmp_path):
    s = Session.__new__(Session)
    s.out, s.runner_sha = tmp_path, "R"
    s.manifest = [{"name": "alu", "spirv_sha256": "S"}]
    row = trusted()
    row.update(accepted=False, rc=2, n=0, validation_post=None)
    del row["accounting"]
    del row["median_seconds"]
    (tmp_path / "sweep-compute").mkdir()
    (tmp_path / "sweep-compute/failed.json").write_text(json.dumps(row))
    assert stages.candidates(s, 1) == {}
    excluded = json.loads((tmp_path / "roof-candidates.json").read_text())["excluded"][
        "alu_fp32"
    ]
    assert excluded[0]["rate"] is None and "no_samples" in excluded[0]["why"]


def test_insights_direct_entry_uses_shared_admission(tmp_path, monkeypatch):
    from igpu_roofline import insights

    (tmp_path / "artifact-manifest.json").write_text(json.dumps({"runner_sha256": "R"}))
    (tmp_path / "shader-shas.json").write_text(json.dumps({"alu": "S"}))
    good = trusted()
    old = dict(trusted(), validation_post=None)
    noisy = dict(trusted(), cv=0.8)
    seen = []
    monkeypatch.setattr(
        insights, "write_supplement", lambda p, rows, caps: seen.append(rows)
    )
    monkeypatch.setattr(
        insights, "write_tuning", lambda f, p, rows, caps: seen.append(rows)
    )
    monkeypatch.setattr(insights, "write_isa_check", lambda *a: None)
    insights.write_all(tmp_path, tmp_path, [good, old, noisy], {}, {})
    assert seen == [[good], [good]]


def test_unstable_confirmation_is_not_a_roof():
    rows = [
        dict(
            trusted(),
            median_seconds=t,
            config=dict(trusted()["config"], confirm_key="alu_fp32", replicate=i),
        )
        for i, t in enumerate([0.006, 0.006, 0.009])
    ]
    diagnostics = []
    assert not admission.confirmed_groups(
        rows, lambda r: True, stages.rate, diagnostics
    )
    assert diagnostics[0]["reasons"] == ["repeat_unstable"]
    assert len(diagnostics[0]["repeat_values"]) == 3


def test_invalid_probe_does_not_imply_degradation(tmp_path, monkeypatch):
    g, _ = guard(tmp_path, monkeypatch)
    g.check("initial")
    boundary = g.last_good_utc
    row = trusted()
    row["differential"] = {"valid": True, "fixed_fraction": 0.43}
    monkeypatch.setattr(stages, "probe", lambda *a: row)
    moved = []
    monkeypatch.setattr(g, "quarantine", lambda since: moved.append(since) or 0)
    with pytest.raises(stages.ProbeInvalid):
        g.check("after")
    assert moved == [boundary] and len(g.readings) == 1
    assert g.last_good_utc == boundary and g._reusable is None


def test_probe_freezes_only_quality_passing_workload(tmp_path, monkeypatch):
    g, _ = guard(tmp_path, monkeypatch)
    bad = dict(
        trusted(),
        effective_loops=10,
        batch_dispatches=1,
        differential={"valid": True, "fixed_fraction": 0.43},
    )
    good = dict(trusted(), effective_loops=57, batch_dispatches=2)
    seq = iter([bad, good])
    monkeypatch.setattr(stages, "probe", lambda *a: next(seq))
    g.check("initial")
    assert g.s.probe_workload == {"loops": 57, "batch_dispatches": 2}
    assert len(g.readings) == 1
