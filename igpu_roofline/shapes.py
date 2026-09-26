"""List a device's cooperative-matrix (WMMA) shapes from the runner's capability query.

`igpu-roofline shapes --device <serial>` (or `--local`) prints one Markdown table row per
VkCooperativeMatrixPropertiesKHR entry, ready to paste into docs/COOPMAT-SHAPES.md.
"""

import json

from .device import run_owned
from .locking import DeviceLock

# VkComponentTypeKHR (core KHR values plus the bfloat16 / fp8 extensions).
COMPONENT = {
    0: "f16",
    1: "f32",
    2: "f64",
    3: "s8",
    4: "s16",
    5: "s32",
    6: "s64",
    7: "u8",
    8: "u16",
    9: "u32",
    10: "u64",
    1000141000: "bf16",
    1000491002: "e4m3",
    1000491003: "e5m2",
}
SCOPE = {1: "device", 2: "workgroup", 3: "subgroup", 4: "queue family"}


def table(caps: dict) -> str:
    """Markdown table of every reported shape (M x N x K, A/B/C/Result types, scope, saturating)."""
    t = lambda v: COMPONENT.get(v, str(v))
    rows = [
        "| M×N×K | A | B | C | Result | scope | saturating |",
        "|---|---|---|---|---|---|---|",
    ]
    for x in caps.get("matrix_shapes", []):
        rows.append(
            f"| {x['m']}×{x['n']}×{x['k']} | {t(x['a'])} | {t(x['b'])} | {t(x['c'])} | {t(x['result'])} "
            f"| {SCOPE.get(x['scope'], x['scope'])} | {'yes' if x.get('saturating') else 'no'} |"
        )
    if len(rows) == 2:
        rows.append("| (none: VK_KHR_cooperative_matrix not exposed) | | | | | | |")
    return "\n".join(rows)


def probe(device, runner) -> dict:
    """Copy the runner to the device and return its capability JSON (no measurement).

    Uses its own file name so it never replaces the `roofline` binary of a campaign
    that may be running or paused on the same device."""
    with DeviceLock(device.identity):
        exe = f"{device.remote}/roofline_shapes"
        device.shell(f"mkdir -p {device.remote}")
        device.push(runner, exe)
        device.shell(f"chmod 755 {exe}")
        r = run_owned(device, "roofline_shapes", "capabilities", 90)
        if r.returncode:
            raise SystemExit(f"capabilities failed: {r.stderr.strip()[-400:]}")
        return json.loads(
            next(line for line in r.stdout.splitlines() if line.startswith("{"))
        )
