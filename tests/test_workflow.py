"""Development workflows: exercise the real planner and selection without a GPU."""

import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from igpu_roofline import cli, stages
from igpu_roofline.measure import accounting
from igpu_roofline.planning import configurations, load_replay, replay_configurations
from igpu_roofline.session import Session, wait_for_runner
from igpu_roofline.shaders import catalogue
from igpu_roofline.timing import record_timing


class FakeSession(Session):
    def __init__(self, folder):
        self.out = folder
        self.plan = "quick"
        self.runner_sha = "current-runner"
        self.manifest = [
            dict(job[3], spirv_sha256="current-shader") for job in catalogue()
        ]
        self.caps = {
            "gpu": "test-gpu",
            "driver_version": 1,
            "subgroup": 32,
            "max_shared_bytes": 32768,
            "max_workgroup_invocations": 1024,
            "max_storage_buffer_range": 512 * 1024**2,
            "page_size": 4096,
            "matrix_shapes": [],
            "extensions": [],
        }
        self.device = SimpleNamespace(serial="test-device")
        self.calls = []
        self.guard = None

    def deploy(self):
        self.calls.append(("deploy", None))

    def capabilities(self):
        return self.caps

    def run(self, c, tag):
        self.calls.append((tag, c))
        folder = self.out / tag
        folder.mkdir(exist_ok=True)
        key = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:12]
        row = {
            "config": c,
            "accepted": True,
            "schema_version": 2,
            "validation_scope": "pre_and_post",
            "rc": 0,
            "validation_pre": {
                "validation": {"pass": True, "checked": 1, "max_abs_error": 0}
            },
            "validation_post": {
                "validation": {"pass": True, "checked": 1, "max_abs_error": 0}
            },
            "n": 21,
            "cv": 0.01,
            "median_seconds": 0.006,
            "min_seconds": 0.0059,
            "effective_loops": c["loops"],
            "batch_dispatches": 1,
            "accounting": accounting(c, c["loops"]),
            "raw": f"{tag}/{key}.jsonl",
        }
        (folder / f"{key}.json").write_text(json.dumps(row))
        return row


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stages, "Guard", lambda *args: SimpleNamespace(check=lambda *args: None)
    )
    monkeypatch.setattr(stages, "pipeline_stats", lambda *args: None)
    monkeypatch.setattr(stages, "offline_isa", lambda *args: None)
    return FakeSession(tmp_path)


def test_full_plan_preserves_configuration_counts(session):
    expected = {"quick": 234, "fast": 301, "standard": 1832}
    for plan, count in expected.items():
        selected = configurations(session, stages.PLANS[plan])
        assert sum(len(rows) for _, rows in selected) == count
    assert session.calls == []
    assert list(session.out.iterdir()) == []


def test_filters_intersect_and_do_not_silently_fall_back(session):
    selected = configurations(
        session,
        stages.PLANS["quick"],
        families=["alu"],
        variants=["alu_fp32_v4_c4"],
        stages=["compute"],
    )
    assert [name for name, _ in selected] == ["compute"]
    assert len(selected[0][1]) == 1
    with pytest.raises(ValueError, match="Unknown variant"):
        configurations(session, stages.PLANS["quick"], variants=["typo"])
    with pytest.raises(ValueError, match="No configurations"):
        configurations(
            session, stages.PLANS["quick"], families=["alu"], stages=["memory"]
        )


def test_focused_confirmation_excludes_unrelated_existing_rows(session):
    # An earlier, faster roof in the same result directory must not be confirmed.
    unrelated = session.base(session.variant("alu_fp32_v4_c16"), 0.25)
    unrelated.update(wg=256, groups=8192)
    session.run(unrelated, "sweep-compute")
    session.calls.clear()
    stages.run_plan(session, "quick", variants=["alu_fp32_v4_c4"], stages=["compute"])
    measured = [(tag, c) for tag, c in session.calls if c is not None]
    assert len(measured) == 4  # one sweep + three confirmations
    assert {c["name"] for _, c in measured} == {"alu_fp32_v4_c4"}
    exported = load_replay(session.out / "best-configurations.json")
    assert [r["roof"] for r in exported["configurations"]] == ["alu_fp32"]
    assert "alu_fp32_v4_c16" in session.inspection_names  # sentinel remains inspectable
    assert "ert_f1" not in session.inspection_names


@pytest.mark.parametrize(
    "focused,override,expected",
    [
        (False, None, True),
        (False, False, False),
        (True, None, False),
        (True, True, True),
    ],
)
def test_sustained_defaults_preserve_full_plans(
    session, monkeypatch, focused, override, expected
):
    # Limit the synthetic full plan to one generator to keep this orchestration test small.
    monkeypatch.setattr(stages, "SHORT_STAGES", [stages.compute])
    sustained = []
    monkeypatch.setattr(stages, "sustain", lambda *args: sustained.append(True))
    stages.run_plan(
        session, "fast", families=["alu"] if focused else (), sustained=override
    )
    assert bool(sustained) is expected


def test_replay_uses_current_artifacts_and_standard_validation(session):
    old = dict(
        session.base(session.variant("alu_fp32_v4_c4")),
        groups=8192,
        runner_sha256="old-runner",
        spirv_sha256="old-shader",
        shader="old.spv",
        executable="old-runner",
        samples=1,
        calibrate=False,
        differential=False,
        duration_seconds=300,
        replicate=4,
        confirm_key="alu_fp32",
        batch_dispatches=256,
    )
    data = {"schema_version": 1, "gpu": "test-gpu", "configurations": [{"config": old}]}
    c = replay_configurations(session, stages.PLANS["quick"], data)[0][1][0][1]
    assert c["groups"] == 8192
    assert (
        c["runner_sha256"] == "current-runner" and c["spirv_sha256"] == "current-shader"
    )
    assert c["shader"] != "old.spv" and c["samples"] == 21
    assert c["warmup_seconds"] == 0.25
    assert (
        not {
            "executable",
            "calibrate",
            "differential",
            "duration_seconds",
            "replicate",
            "batch_dispatches",
        }
        & c.keys()
    )
    with pytest.raises(ValueError, match="GPU does not match"):
        replay_configurations(
            session, stages.PLANS["quick"], dict(data, gpu="other-gpu")
        )


def test_replay_runs_only_exported_configurations(session):
    stages.run_plan(session, "quick", variants=["alu_fp32_v4_c4"], stages=["compute"])
    data = load_replay(session.out / "best-configurations.json")
    session.calls.clear()
    session.runner_sha = "rebuilt-runner"
    stages.run_plan(session, "quick", replay=data)
    measured = [(tag, c) for tag, c in session.calls if c is not None]
    assert len(measured) == 4
    assert {c["runner_sha256"] for _, c in measured} == {"rebuilt-runner"}
    assert json.loads((session.out / "run-selection.json").read_text())["stages"] == [
        {"name": "replay", "configurations": 1}
    ]


def test_replay_accepts_existing_report_but_only_confirmed_roofs(session):
    c = session.base(session.variant("alu_fp32_v4_c4"))
    path = session.out / "summary.json"
    path.write_text(
        json.dumps(
            {
                "device": "test-gpu",
                "short_run": {
                    "alu_fp32": {"confirmed": True, "config": c},
                    "alu_fp16": {"config": dict(c, name="alu_fp16_v4_c4")},
                },
            }
        )
    )
    data = load_replay(path)
    assert [r["roof"] for r in data["configurations"]] == ["alu_fp32"]


def test_wait_collects_telemetry_and_enforces_timeout(monkeypatch):
    import igpu_roofline.session as module

    elapsed = [0]
    monkeypatch.setattr(module.time, "monotonic", lambda: elapsed[0])
    killed = []

    class Process:
        done = False

        def poll(self):
            return -9 if self.done else None

        def wait(self, timeout=None):
            if self.done:
                return -9
            assert timeout is not None
            elapsed[0] += timeout
            raise subprocess.TimeoutExpired("runner", timeout)

        def kill(self):
            self.done = True

    device = SimpleNamespace(
        stop=lambda proc: (killed.append(proc), proc.kill(), proc.wait()),
        telemetry=lambda: {"sample": True},
    )
    telemetry = []
    with pytest.raises(TimeoutError):
        process = Process()
        wait_for_runner(process, device, "roofline", 12, telemetry)
    assert telemetry == [{"sample": True}]
    assert killed == [process]


def test_sustained_command_does_not_run_discovery_and_rejects_old_build(
    session, monkeypatch
):
    stages.run_plan(session, "quick", variants=["alu_fp32_v4_c4"], stages=["compute"])
    session.calls.clear()
    invoked = []
    monkeypatch.setattr(
        stages, "sustain", lambda s, plan, keys: invoked.append((plan, keys))
    )
    stages.run_sustained(
        session, roof_keys=["alu_fp32"], duration=120, batches=2, cooldown=0
    )
    assert session.calls == [("deploy", None)]
    assert invoked[0][0]["sustain"] == {"duration": 120, "batches": 2, "cooldown": 0}
    assert invoked[0][1] == ["alu_fp32"]
    session.runner_sha = "different-runner"
    with pytest.raises(RuntimeError, match="no confirmed roofs"):
        stages.run_sustained(session)


def test_non_roof_selection_completes_without_exporting_unrelated_roofs(session):
    stages.run_plan(session, "quick", stages=["latency"])
    data = json.loads((session.out / "best-configurations.json").read_text())
    assert data["configurations"] == []
    assert not any(tag == "confirm" for tag, _ in session.calls)


def test_stage_timing_records_failure(tmp_path):
    with pytest.raises(ValueError), record_timing(tmp_path, "stage", "example"):
        raise ValueError("test")
    row = json.loads((tmp_path / "timings.jsonl").read_text())
    assert row["status"] == "failed" and row["wall_seconds"] >= 0


def test_wait_returns_on_exit_without_sleeping(monkeypatch):
    import igpu_roofline.session as module

    monkeypatch.setattr(
        module.time, "sleep", lambda *args: pytest.fail("must not sleep")
    )

    class Process:
        done = False

        def poll(self):
            return 0 if self.done else None

        def wait(self, timeout=None):
            assert timeout is not None and 0 < timeout <= 10
            self.done = True

    proc = Process()
    wait_for_runner(proc, SimpleNamespace(), "roofline", 180, [])
    assert proc.done


def test_cli_selection_and_sustain_validation(monkeypatch):
    received = []
    monkeypatch.setattr(cli, "cmd_run", lambda args: received.append(args))
    cli.main(
        ["run", "--local", "--family", "alu", "--stage", "compute", "--no-sustain"]
    )
    assert received[0].family == ["alu"] and received[0].sustained is False
    cli.main(["run", "--local"])
    assert received[1].sustained is None
    with pytest.raises(SystemExit) as error:
        cli.main(["sustain", "--local", "--duration", "5"])
    assert error.value.code == 2
    with pytest.raises(SystemExit):
        cli.main(["run", "--local", "--replay", "file.json", "--stage", "compute"])


def test_local_telemetry_binds_to_selected_gpu_and_rejects_ambiguity(monkeypatch):
    from igpu_roofline import device

    local = device.LocalDevice.__new__(device.LocalDevice)
    cards = [
        "/sys/class/drm/card0",
        "/sys/class/drm/card1",
        "/sys/class/drm/card0-DP-1",
    ]
    files = {
        f"{cards[0]}/device/vendor": "0x8086",
        f"{cards[0]}/device/device": "0xe20b",
        f"{cards[1]}/device/vendor": "0x1002",
        f"{cards[1]}/device/device": "0x13c0",
    }
    monkeypatch.setattr(device.glob, "glob", lambda pattern: cards)
    monkeypatch.setattr(local, "_read", lambda path: files.get(path, ""))
    local.bind_gpu({"vendor_id": 0x8086, "device_id": 0xE20B})
    assert local.card == cards[0]
    local.bind_gpu({"vendor_id": 0x1002, "device_id": 0x13C0})
    assert local.card == cards[1]
    files[f"{cards[1]}/device/vendor"] = "0x8086"
    files[f"{cards[1]}/device/device"] = "0xe20b"
    local.bind_gpu({"vendor_id": 0x8086, "device_id": 0xE20B})
    assert local.card is None
    local.bind_gpu({})
    assert local.card is None


def test_gpu_thermal_guard_uses_only_selected_card(monkeypatch):
    from igpu_roofline.device import LocalDevice

    local = LocalDevice.__new__(LocalDevice)
    monkeypatch.setattr(
        local,
        "_temps",
        lambda selected_gpu=False: {"intel": 42} if selected_gpu else {"amdgpu": 90},
    )
    assert local.gpu_temp_c() == 42


def test_missing_clock_telemetry_is_not_reported_as_a_known_clock_state():
    from igpu_roofline.report import _clock_line

    assert "unavailable" in _clock_line(
        {"clock_state": {"domains": {}, "pinned_domains": []}}
    )
