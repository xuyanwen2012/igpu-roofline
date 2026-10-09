"""Average uniformly sampled Nsight metrics inside long Vulkan submissions."""

import argparse
import json
import sqlite3
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("campaign", type=Path)
a = p.parse_args()
result = {}
for path in a.campaign.glob("*/capture.sqlite"):
    c = sqlite3.connect(path)
    # Exclude transfer-sized submissions and 1 ms sampling boundary intervals.
    rows = c.execute("""SELECT names.metricName, AVG(m.value), COUNT(*)
        FROM GPU_METRICS m JOIN TARGET_INFO_GPU_METRICS names
        ON m.typeId=names.typeId AND m.metricId=names.metricId
        WHERE EXISTS (SELECT 1 FROM VULKAN_WORKLOAD w
          WHERE w.end-w.start>2000000
          AND m.timestamp>=w.start+1000000 AND m.timestamp<=w.end-1000000)
        GROUP BY m.typeId,m.metricId""").fetchall()
    result[path.parent.name] = {name: {"mean": v, "samples": n} for name, v, n in rows}
    c.close()
    print(
        path.parent.name,
        {
            k: round(v["mean"], 3)
            for k, v in result[path.parent.name].items()
            if any(
                t in k
                for t in (
                    "SM Issue",
                    "Tensor Active",
                    "Compute Warps in Flight [Throughput %]",
                )
            )
        },
    )
(a.campaign / "counter-summary.json").write_text(json.dumps(result, indent=2))
