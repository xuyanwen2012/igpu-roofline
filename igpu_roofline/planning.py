"""Select configurations without running a GPU, and replay launch parameters."""

import json
from pathlib import Path


def config_identity(config: dict) -> str:
    # Confirmation adds these fields to the original sweep configuration.
    return json.dumps(
        {
            k: v
            for k, v in config.items()
            if k not in ("replicate", "confirm_key", "role", "confirmation_reps")
        },
        sort_keys=True,
    )


class Collector:
    """Use the existing stage generators without dispatching measurements."""

    def __init__(self, session):
        self.session = session
        self.rows = []

    def __getattr__(self, name):
        return getattr(self.session, name)

    def run(self, config, tag):
        self.rows.append((tag, config))


def configurations(session, plan, families=(), variants=(), stages=()):
    from .stages import SHORT_STAGES

    known_families = {m["family"] for m in session.manifest}
    known_variants = {m["name"] for m in session.manifest}
    for values, known, label in (
        (families, known_families, "family"),
        (variants, known_variants, "variant"),
    ):
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"Unknown {label}: {', '.join(sorted(unknown))}")
    selected = []
    for step in SHORT_STAGES:
        if stages and step.__name__ not in stages:
            continue
        collector = Collector(session)
        step(collector, plan)
        rows = [
            (tag, c)
            for tag, c in collector.rows
            if (not families or c["family"] in families)
            and (not variants or c["name"] in variants)
        ]
        if rows:
            selected.append((step.__name__, rows))
    if not selected:
        raise ValueError(
            "No configurations match this plan and selection; try another plan or selector"
        )
    return selected


# Only launch/data parameters cross build boundaries. Shader metadata and hashes
# always come from the current manifest; old executable paths are never replayed.
REPLAY_PARAMETERS = {
    "wg",
    "groups",
    "n",
    "loops",
    "shared_count",
    "stride",
    "replicas",
    "memory_mode",
    "role",
    "chain_stride_bytes",
    "chain_order",
    "page_size",
    "alpha",
    "beta",
}
ROOF_STAGES = {
    "alu": "sweep-compute",
    "dot": "sweep-compute",
    "matrix": "sweep-compute",
    "memory": "sweep-memory",
    "shared": "sweep-shared",
    "texture": "sweep-texture",
}


def load_replay(path):
    data: dict = json.loads(Path(path).expanduser().read_text())
    # Existing campaigns already have this report; no new discovery run is needed
    # merely to obtain a replay file. Ignore unconfirmed sweep maxima.
    if (
        isinstance(data, dict)
        and isinstance(data.get("short_run"), dict)
        and data.get("device")
    ):
        data = {
            "schema_version": 1,
            "gpu": data["device"],
            "configurations": [
                {"roof": key, "config": row["config"]}
                for key, row in data["short_run"].items()
                if isinstance(row, dict) and row.get("confirmed") and "config" in row
            ],
        }
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("configurations"), list)
    ):
        raise ValueError(
            "Replay requires best-configurations.json or a report/summary.json with confirmed roofs"
        )
    if not data["configurations"]:
        raise ValueError("Replay file has no configurations")
    for entry in data["configurations"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("config"), dict)
            or not isinstance(entry["config"].get("name"), str)
        ):
            raise ValueError("Each replay entry must contain a named config")
    return data


def replay_configurations(session, plan, data, families=(), variants=()):
    if data.get("gpu") != session.caps["gpu"]:
        raise ValueError(
            "Replay GPU does not match this device; discover configurations on this GPU first"
        )
    manifest = {m["name"]: m for m in session.manifest}
    for requested, known, label in (
        (families, {m["family"] for m in session.manifest}, "family"),
        (variants, set(manifest), "variant"),
    ):
        if set(requested) - known:
            raise ValueError(
                f"Unknown {label}: {', '.join(sorted(set(requested) - known))}"
            )
    rows = []
    for entry in data["configurations"]:
        old = entry["config"]
        if variants and old["name"] not in variants:
            continue
        if old["name"] not in manifest:
            raise ValueError(
                f"Replay variant is absent from the current build: {old['name']}"
            )
        m = manifest[old["name"]]
        if (families and m["family"] not in families) or (
            variants and m["name"] not in variants
        ):
            continue
        if not session.eligible(m):
            raise ValueError(
                f"Replay variant is unsupported by this device: {m['name']}"
            )
        c = session.base(m, plan["warmup_seconds"])
        c.update({k: v for k, v in old.items() if k in REPLAY_PARAMETERS})
        if c["family"] not in ROOF_STAGES:
            raise ValueError(f"Replay requires a roof configuration: {m['name']}")
        for field in (
            "wg",
            "groups",
            "n",
            "loops",
            "shared_count",
            "stride",
            "replicas",
        ):
            if field in c and (type(c[field]) is not int or c[field] <= 0):
                raise ValueError(f"Replay {field} must be a positive integer")
        if c["wg"] > session.caps["max_workgroup_invocations"]:
            raise ValueError("Replay workgroup exceeds the current device limit")
        if c["family"] == "matrix" and c["wg"] % session.caps["subgroup"]:
            raise ValueError(
                "Replay workgroup is incompatible with the current subgroup size"
            )
        if c["family"] == "shared":
            scalar = 2 if c["dtype"] == "fp16" else 4
            if (
                c["shared_count"] * c["width"] * scalar
                > session.caps["max_shared_bytes"]
            ):
                raise ValueError(
                    "Replay shared allocation exceeds the current device limit"
                )
        tag = (
            "sweep-cache"
            if c.get("role", "confirmation_reps") == "cache"
            else "sweep-matrix-feed"
            if c["family"] == "matrix" and c.get("feed")
            else ROOF_STAGES[c["family"]]
        )
        rows.append((tag, c))
    if not rows:
        raise ValueError("No replay configurations match the selection")
    return [("replay", rows)]


def export_best(session, winners):
    payload = {
        "schema_version": 1,
        "gpu": session.caps["gpu"],
        "driver_version": session.caps.get("driver_version"),
        "serial": session.device.serial,
        "runner_sha256": session.runner_sha,
        "configurations": [
            {"roof": key, "config": row["config"]}
            for key, row in sorted(winners.items())
            if not session.exclusion_reasons(row)
        ],
    }
    (session.out / "best-configurations.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
