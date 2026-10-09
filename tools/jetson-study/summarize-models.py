"""Extract clean whole-model timing observations and memory outcomes."""

import argparse
import hashlib
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("campaign", type=Path)
p.add_argument("--additional-campaign", type=Path, action="append", default=[])
a = p.parse_args()
rows = []
metadata = [
    meta
    for campaign in [a.campaign, *a.additional_campaign]
    for meta in sorted(campaign.glob("*/result.json"))
]
for meta in metadata:
    d = json.loads(meta.read_text())
    log = (meta.parent / "stdout.log").read_text(errors="replace")
    observations = re.findall(r"PyTorchObserver (\{[^\n]+\})", log)
    row = {
        "job": meta.parent.name,
        "campaign": str(meta.parent.parent),
        "rc": d["rc"],
        "stop_reason": d.get("stop_reason"),
        "process_wall_seconds": d.get("wall_seconds"),
    }
    if observations:
        stat = json.loads(observations[-1])
        row.update(stat)
        row["prefill_ms"] = stat["prompt_eval_end_ms"] - stat["inference_start_ms"]
        row["load_ms"] = stat["model_load_end_ms"] - stat["model_load_start_ms"]
        # Preserve text for review; matching hashes are not numerical proof.
        text = log.split("PyTorchObserver")[0]
        row["text_prefix_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    rss = re.search(r"JETSON_MAX_RSS_KB=(\d+)", log)
    if rss:
        row["max_rss_kb"] = int(rss[1])
    memory = meta.parent / "memory.txt"
    if memory.exists():
        match = re.search(
            r"Maximum resident set size \(kbytes\): (\d+)", memory.read_text()
        )
        if match:
            row["max_rss_kb"] = int(match[1])
    rows.append(row)
    print(
        row["job"],
        row["rc"],
        row.get("stop_reason"),
        row.get("prefill_token_per_sec"),
        row.get("decode_token_per_sec"),
        row.get("max_rss_kb"),
    )
(a.campaign / "summary.json").write_text(json.dumps(rows, indent=2))
