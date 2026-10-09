"""Build the supplementary shape snapshot for GPUs outside gpu-lab's 2026-09-26 query.

Same schema as gpu-lab/docs/data/cooperative-matrices-*.json (KHR entries only).
Sources: the 7900 XTX and S26 agents' roofline campaigns (contrib/*/roofline.json, 2026-09-27)
and docs/COOPMAT-SHAPES.md (Xclipse M51 and Mali-G1 historical snapshots).
"""

import json
import re
from pathlib import Path

T = {"f16": 0, "f32": 1, "s8": 3, "s32": 5, "u8": 7, "u32": 9}
CONTRIB = Path(
    "../sarc-acl/dev/1.5/executorch/openspec/changes/sarc-1.5-e2e-benchmark/contrib"
)


def from_roofline(path, key):
    g = json.loads(Path(path).read_text())["gpus"][key]
    out = []
    for s in g["coopmat_shapes"]:
        m = re.fullmatch(r"(\d+)x(\d+)x(\d+) (\w+)x(\w+)\+(\w+)->(\w+)( sat)?", s)
        if m is None:
            raise ValueError(f"unrecognised coopmat shape: {s!r}")
        M, N, K, a, b, c, r, sat = m.groups()
        out.append(
            {
                "m": int(M),
                "n": int(N),
                "k": int(K),
                "a": T[a],
                "b": T[b],
                "c": T[c],
                "result": T[r],
                "saturating": int(bool(sat)),
                "scope": 3,
                "workgroup_invocations": 0,
            }
        )
    return g, out


def from_doc(heading):
    text = Path("docs/COOPMAT-SHAPES.md").read_text()
    sec = text[text.index(heading) :]
    sec = sec[: sec.index("\n## ", 1)] if "\n## " in sec[1:] else sec
    out = []
    for line in sec.splitlines():
        m = re.match(
            r"\| (\d+)×(\d+)×(\d+) \| (\w+) \| (\w+) \| (\w+) \| (\w+) \| subgroup \| (yes|no) \|",
            line,
        )
        if m:
            M, N, K, a, b, c, r, sat = m.groups()
            out.append(
                {
                    "m": int(M),
                    "n": int(N),
                    "k": int(K),
                    "a": T[a],
                    "b": T[b],
                    "c": T[c],
                    "result": T[r],
                    "saturating": int(sat == "yes"),
                    "scope": 3,
                    "workgroup_invocations": 0,
                }
            )
    return out


def dev(id_, host, name, driver, info, sg, src, khr):
    return {
        "id": id_,
        "host": host,
        "name": name,
        "driver": driver,
        "driver_info": info,
        "api": "",
        "subgroup_size": sg,
        "matrix_extensions": ["VK_KHR_cooperative_matrix"],
        "khr_feature": 1,
        "khr": khr,
        "flexible_dimensions_feature": 0,
        "workgroup_scope_feature": 0,
        "source": src,
    }


x, xk = from_roofline(CONTRIB / "7900xtx/roofline.json", "7900xtx")
s, sk = from_roofline(CONTRIB / "s26/roofline.json", "s26")
r7, r7k = from_roofline(CONTRIB / "rx7600/roofline.json", "rx7600")
gpus = [
    dev(
        "7900xtx",
        "host-7900xtx",
        "AMD Radeon RX 7900 XTX",
        "AMDVLK",
        f"driver {x['driver_version']}",
        x["subgroup_default"],
        "igpu-roofline campaign by the 7900 XTX agent, 2026-09-27 (contrib/7900xtx/roofline.json)",
        xk,
    ),
    dev(
        "rx7600",
        "host-ws1",
        "AMD Radeon RX 7600",
        "RADV",
        f"Mesa 26.2.3 (driver {r7['driver_version']})",
        r7["subgroup_default"],
        "igpu-roofline campaign by the RX 7600 agent, 2026-09-28 (contrib/rx7600/roofline.json)",
        r7k,
    ),
    dev(
        "s26",
        "Galaxy S26 Ultra (adb)",
        "Qualcomm Adreno 840",
        "Qualcomm",
        f"driver {s['driver_version']}",
        s["subgroup_default"],
        "igpu-roofline campaign by the S26 agent, 2026-09-27 (contrib/s26/roofline.json)",
        sk,
    ),
    dev(
        "m51",
        "internal device",
        "Samsung Xclipse (M51)",
        "Samsung",
        "internal driver build (not published)",
        None,
        "owner-provided shapes (docs/COOPMAT-SHAPES.md)",
        from_doc("## Samsung Xclipse (M51"),
    ),
    dev(
        "mali-g1",
        "vivo V2502A (adb)",
        "Arm Mali-G1-Ultra MC12",
        "Arm",
        "r54p1",
        16,
        "docs/COOPMAT-SHAPES.md, probed 2026-09-22; to be re-probed",
        from_doc("## Mali-G1-Ultra"),
    ),
]
for g in gpus:
    assert g["khr"], g["id"]
out = Path("docs/reports/data/cooperative-matrices-extra-2026-09-28.json")
out.write_text(
    json.dumps(
        {
            "compiled_at": "2026-09-28",
            "interface": "KHR fixed entries only; see each source",
            "gpus": gpus,
        },
        indent=1,
    )
)
print(out, [(g["id"], len(g["khr"])) for g in gpus])
