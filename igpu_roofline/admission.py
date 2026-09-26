"""Shared build, validation and quality admission for every result consumer."""

import json
import statistics

from . import paths

QUALITY = {"max_median_se": 0.03, "max_fixed_fraction": 0.10, "max_drift": 0.05}
MAX_REPEAT_SPREAD = 0.05


def median_se(row):
    n = row.get("n") or 0
    return 1.2533 * row.get("cv", 1) / n**0.5 if n > 1 else 1.0


def quality(row):
    why = []
    if not row.get("accepted"):
        why.append("rejected")
    if median_se(row) > QUALITY["max_median_se"]:
        why.append("noisy_median")
    if row.get("below_target_duration"):
        why.append("short")
    d = row.get("differential")
    if d and (
        not d.get("valid") or d.get("fixed_fraction", 0) > QUALITY["max_fixed_fraction"]
    ):
        why.append("fixed_cost")
    if (row.get("warmup") or {}).get("steady") is False:
        why.append("warmup_unsteady")
    if abs(row.get("sample_drift", 0)) > QUALITY["max_drift"]:
        why.append("drifting")
    return why


def build_reasons(row, runner, shaders, sustained_runner=None):
    c = row.get("config", {})
    why = []
    if c.get("executable") == "roofline_sustained" or c.get("duration_seconds", 0) > 0:
        if not sustained_runner or c.get("runner_sha256") != sustained_runner:
            why.append("stale_sustained_runner")
        actual = c.get("reference_runner_sha256")
    else:
        actual = c.get("runner_sha256")
    if not runner or actual != runner:
        why.append("stale_runner")
    want = shaders.get(c.get("name"))
    if not want or c.get("spirv_sha256") != want:
        why.append("stale_shader")
    return why


def validation_reasons(row):
    why = []
    if row.get("schema_version") != 2 or row.get("validation_scope") != "pre_and_post":
        why.append("historical_validation_coverage")
    c = row.get("config", {})
    approximate = c.get("family") == "alu" or (
        c.get("family") == "memory" and c.get("op") == 6
    )
    for phase in ("pre", "post"):
        event = row.get(f"validation_{phase}")
        if not event:
            why.append(f"missing_{phase}_validation")
            continue
        v = event.get("validation", {})
        if (
            not v.get("pass")
            or not v.get("checked")
            or (not approximate and v.get("max_abs_error") != 0)
        ):
            why.append(f"failed_{phase}_validation")
    if row.get("rc") != 0:
        why.append("abnormal_exit")
    if row.get("fault_delta") not in (None, 0):
        why.append("gpu_fault")
    if not row.get("n"):
        why.append("no_samples")
    return why


def reasons(row, runner, shaders, sustained_runner=None):
    why = build_reasons(row, runner, shaders, sustained_runner) + validation_reasons(
        row
    )
    if row.get("config", {}).get("duration_seconds", 0) > 0:
        if not row.get("accepted"):
            why.append("rejected")
        if not row.get("steady_last60"):
            why.append("sustained_unsteady")
    else:
        why += quality(row)
    return list(dict.fromkeys(why))


def confirmed_groups(rows, eligible, rate, diagnostics=None):
    """Keep all repeat attempts in the denominator; require the planned repeat count."""
    groups = {}
    for r in rows:
        c = r["config"]
        key = c.get("confirm_key")
        if not key:
            continue
        ident = json.dumps(
            {k: v for k, v in c.items() if k != "replicate"}, sort_keys=True
        )
        groups.setdefault((key, ident), {})[c.get("replicate")] = r
    winners: dict[str, dict] = {}
    for (key, _), repeats in groups.items():
        rs = list(repeats.values())
        required = max(
            r["config"].get(
                "confirmation_reps", 5 if r.get("plan") in ("standard", "gold") else 3
            )
            for r in rs
        )
        ok = [r for r in rs if eligible(r)]
        values = [rate(r) for r in ok]
        med = statistics.median(values) if values else 0
        spread = (max(values) - min(values)) / med if med > 0 else None
        reasons = []
        if len(rs) < required:
            reasons.append("insufficient_repeats")
        if len(ok) < max(2, len(rs) - 1):
            reasons.append("insufficient_quality_repeats")
        if spread is None or spread > MAX_REPEAT_SPREAD:
            reasons.append("repeat_unstable")
        if diagnostics is not None:
            diagnostics.append(
                {
                    "roof": key,
                    "config": rs[0]["config"],
                    "attempts": len(rs),
                    "eligible_repeats": len(ok),
                    "repeat_values": values,
                    "repeat_spread": spread,
                    "reasons": reasons,
                }
            )
        if reasons:
            continue
        representative = min(ok, key=lambda r: abs(rate(r) - med))
        if key not in winners or med > winners[key]["median"]:
            winners[key] = {"row": representative, "median": med, "rows": ok}
    return winners


def build_context(folder):
    """Read deployed build identities once per report consumer, failing closed."""
    manifest_path = folder / "artifact-manifest.json"
    shader_path = folder / "shader-shas.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    shaders = json.loads(shader_path.read_text()) if shader_path.exists() else {}
    return (
        paths.manifest_runner(manifest),
        shaders,
        manifest.get("sustained_runner_sha256"),
    )


def sustained_reference_matches(config, reference):
    """A reference token cannot hide different shader/launch/data parameters."""
    from .planning import config_identity

    runtime = {
        "loops",
        "batch_dispatches",
        "calibrate",
        "warmup_seconds",
        "replicate",
        "confirm_key",
        "confirmation_reps",
        "runner_sha256",
        "executable",
        "duration_seconds",
        "reference_runner_sha256",
        "reference_config_identity",
        "sustained_roof",
    }
    signature = lambda c: {k: v for k, v in c.items() if k not in runtime}
    return config.get("reference_config_identity") == config_identity(
        reference
    ) and signature(config) == signature(reference)
