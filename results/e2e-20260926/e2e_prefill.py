#!/usr/bin/env python3
"""End-to-end 2048-token prefill tok/s, tiled vs tuned linear kernels, on the tuned GPUs.

Adapted from ../../vulkan_llama_prefill_2048/fleet_prefill.py (same llama_main invocation,
PyTorchObserver parsing and fdinfo device proof). Differences:
  - one bundle per GPU branch (bundles/<gpu>/{llama_main,libllama_runner.so}), copied to
    ~/.cache/et-e2e/<gpu> on the GPU's host;
  - modes: tiled (ET_VK_FORCE_TILED_LINEAR=1) and tuned (branch defaults), same binary,
    interleaved repeats;
  - every run holds the gpu-lab lock and records other compute processes and clocks before
    and after; a run with another compute process on the GPU is marked contended;
  - --check: greedy 32-token generation on a short prompt in both modes (correctness sanity).

Usage: e2e_prefill.py GPU [GPU ...] [--sizes 1b,3b,8b] [--quants 4w,8da4w] [--reps 3] [--check]
Writes out/<gpu>/... and appends to out/runs.jsonl (or out/checks.jsonl).
"""

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FLEET_DIR = HERE.parent.parent / "vulkan_llama_prefill_2048"
MODELS = "/mnt/linux-share/models"
SSH_DOMAIN = "tail031559.ts.net"
MODEL_DIRS = {"1b": ("llama-3.2-1b", "llama3_2-1b"), "3b": ("llama-3.2-3b", "llama3_2-3b"),
              "8b": ("llama-3.1-8b", "llama3_1-8b")}
TARGETS = {
    "4070tis": dict(kind="ssh", host="gpu-dev-4004", lock="81a511a2-de7e-c3c8-f641-3562c315ffa7", nvidia=True),
    "b70-0": dict(kind="ssh", host="fedora-gpu-eval", lock="868023e2-0000-0000-0100-000000000000"),
    "b580": dict(kind="local", lock="86800be2-0000-0000-0300-000000000000"),
    "780m": dict(kind="ssh", host="rocky-ryzen", lock="00000000-c400-0000-0000-000000000000"),
}
MODES = {"tiled": "ET_VK_FORCE_TILED_LINEAR=1", "tuned": ""}
RUN_TIMEOUT = 1500
REMOTE = "$HOME/.cache/et-e2e"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ssh_cmd(host):
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", f"HostKeyAlias={host}",
            f"doremy@{host}.{SSH_DOMAIN}"]


def sh(t, script, timeout=RUN_TIMEOUT):
    cmd = ["bash", "-s"] if t["kind"] == "local" else [*ssh_cmd(t["host"]), "bash -s"]
    return subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=timeout)


def deploy(gpu, t):
    """Copy the bundle + prompts to ~/.cache/et-e2e/<gpu> on the host."""
    src = HERE / "bundles" / gpu
    files = [src / "llama_main", src / "libllama_runner.so", FLEET_DIR / "prompt_2048.txt",
             HERE / "prompt_check.txt"]
    dest = f"{REMOTE}/{gpu}".replace("$HOME", "~")
    if t["kind"] == "local":
        d = Path(dest.replace("~", str(Path.home())))
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", *map(str, files), str(d)], check=True)
    else:
        subprocess.run([*ssh_cmd(t["host"]), f"mkdir -p {dest}"], check=True)
        subprocess.run(["rsync", "-a", "-e", " ".join(ssh_cmd(t["host"])[:-1]), *map(str, files),
                        f"doremy@{t['host']}.{SSH_DOMAIN}:{dest.replace('~/', '')}/"], check=True)


def state_cmd(t):
    """Other compute processes + clocks, for contention and state records."""
    if t.get("nvidia"):
        return ("nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader; "
                "echo @@CLK; nvidia-smi --query-gpu=clocks.sm,clocks.mem,temperature.gpu,power.draw "
                "--format=csv,noheader")
    # Non-NVIDIA: per-process GPU engine counters from drm fdinfo (drm-engine-* ns on amdgpu,
    # drm-cycles-* on xe), summed; contention is judged from the pre->post delta, not presence.
    return ("for p in /proc/[0-9]*; do v=$(cat $p/fdinfo/* 2>/dev/null | awk '/^drm-engine-[a-z]*:/"
            "{s+=$2} /^drm-cycles-[a-z]*:/{s+=$2} END{printf \"%.0f\", s}'); [ \"${v:-0}\" != 0 ] && "
            "echo \"$(basename $p) $v $(tr '\\0' ' ' < $p/cmdline | cut -c1-60)\"; done | grep -v llama_main; "
            "echo @@CLK; cat /sys/class/drm/card*/device/tile0/gt0/freq0/act_freq 2>/dev/null | head -1; "
            "cat /sys/class/drm/card*/device/pp_dpm_sclk 2>/dev/null | grep '\\*' | head -1")


def run_script(gpu, t, mode, model_path, tok_path, prompt, ngen):
    env = f"ETVK_DEVICE_INDEX=0 {MODES[mode]}"
    d = f"{REMOTE}/{gpu}"
    lock = f"$HOME/.cache/gpu-lab/lock-{t['lock']}"
    return f"""set -u
cd {d}; mkdir -p out
exec 9>>{lock}; flock -w 900 9 || {{ echo "@@RC 75"; echo "@@LOG"; echo LOCK_BUSY; exit 0; }}
echo "@@PRE"; ( {state_cmd(t)} ) 2>/dev/null
{env} LD_LIBRARY_PATH=. ./llama_main --model_path {model_path} --tokenizer_path {tok_path} \\
  --prompt_file {prompt} --max_new_tokens {ngen} --temperature 0 --warmup < /dev/null > out/run.log 2>&1 9>&- &
pid=$!
while kill -0 $pid 2>/dev/null; do
  for f in /proc/$pid/fdinfo/*; do
    awk '/^drm-driver:/{{d=$2}} /^drm-pdev:/{{p=$2}} END{{if(p!="") print "pdev=" p, "driver=" d}}' "$f" 2>/dev/null
  done
  command -v nvidia-smi >/dev/null && nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader 2>/dev/null | grep -w "^$pid" | sed 's/^/nvidia-app: /'
  sleep 0.5
done | sort -u > out/drm.txt
wait $pid; rc=$?
echo "@@POST"; ( {state_cmd(t)} ) 2>/dev/null
echo "@@RC $rc"; echo "@@LOG"; cat out/run.log; echo "@@DRM"; cat out/drm.txt
"""


def parse(out):
    pre = out.partition("@@PRE\n")[2].partition("@@POST")[0] if "@@PRE" in out else ""
    post = out.partition("@@POST\n")[2].partition("@@RC")[0] if "@@POST" in out else ""
    rc, logtxt, drm = None, "", ""
    if "@@RC" in out:
        rest = out.partition("@@RC ")[2]
        rc_s, _, rest = rest.partition("\n")
        rc = int(rc_s.strip() or -1)
        logtxt, _, drm = rest.partition("@@LOG\n")[2].partition("@@DRM\n")
    obs = next((json.loads(l.split("PyTorchObserver ", 1)[1]) for l in logtxt.splitlines()
                if "PyTorchObserver" in l), None)
    return rc, logtxt, drm, obs, pre, post


def others(state_txt):
    procs = state_txt.partition("@@CLK")[0].strip().splitlines()
    return [p for p in procs if p.strip()]


# Engine-counter growth that counts as another tenant using the GPU during a run:
# 50 ms of engine time (amdgpu ns) or 1e8 cycles (xe; ~40 ms at 2.5 GHz).
BUSY_DELTA = 5e7


def busy_others(pre, post, nvidia):
    if nvidia:  # compute-apps list: any other process is a co-tenant
        return sorted(set(others(pre)) | set(others(post)))
    def counters(txt):
        out = {}
        for line in others(txt):
            f = line.split(None, 2)
            if len(f) >= 2 and f[1].isdigit():
                out[f[0]] = (int(f[1]), f[2] if len(f) > 2 else "")
        return out
    a, b = counters(pre), counters(post)
    return sorted(f"{pid} {name} +{v - a.get(pid, (v, ''))[0]:.3g}" for pid, (v, name) in b.items()
                  if v - a.get(pid, (v, ""))[0] > BUSY_DELTA)


def run_one(gpu, t, size, quant, mode, rep, check):
    mdir, stem = MODEL_DIRS[size]
    pte = f"{MODELS}/{mdir}/exported/{stem}_vulkan_{quant}.pte"
    tok = f"{MODELS}/{mdir}/original/tokenizer.model"
    # --check: a 1973-token real-text prompt, prefill only (short prompts and decode take the "coop"
    # SDPA path, whose shader is missing on some branches); compare the generated token.
    prompt, ngen = ("prompt_check.txt", 1) if check else ("prompt_2048.txt", 1)
    name = f"{size}_{quant}_{mode}" + ("_check" if check else f"_r{rep}")
    t0 = time.time()
    try:
        p = sh(t, run_script(gpu, t, mode, pte, tok, prompt, ngen))
        rc, logtxt, drm, obs, pre, post = parse(p.stdout)
        if rc is None:
            logtxt = p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        rc, logtxt, drm, obs, pre, post = -9, "TIMEOUT", "", None, "", ""
    d = OUT / gpu
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.log").write_text(logtxt)
    (d / f"{name}.state").write_text(f"PRE\n{pre}\nPOST\n{post}\nDRM\n{drm}")
    contended = busy_others(pre, post, t.get("nvidia", False))
    r = dict(gpu=gpu, size=size, quant=quant, mode=mode, rep=rep, check=check, rc=rc,
             time=time.strftime("%Y-%m-%dT%H:%M:%S"), wall_s=round(time.time() - t0, 1),
             contended=contended, drm=sorted(set(drm.split("\n")) - {""}),
             clk_pre=pre.partition("@@CLK")[2].strip(), clk_post=post.partition("@@CLK")[2].strip())
    if obs:
        # Field names differ across runner versions (model_execution_* on main).
        start = obs.get("model_execution_start_ms", obs.get("inference_start_ms"))
        end = obs.get("model_execution_end_ms", obs.get("prompt_eval_end_ms"))
        r.update(prefill_ms=(end - start) if not check else None,
                 tok_s=obs["prefill_token_per_sec"], prompt_tokens=obs["prompt_tokens"],
                 generated_tokens=obs["generated_tokens"],
                 load_ms=obs["model_load_end_ms"] - obs["model_load_start_ms"])
    ok = rc == 0 and obs is not None and (check or obs.get("prompt_tokens") == 2048)
    r["status"] = ("ok" if not contended else "contended") if ok else "FAILED"
    if not ok:
        r["error_tail"] = logtxt.strip().splitlines()[-5:] if logtxt.strip() else []
    with open(OUT / ("checks.jsonl" if check else "runs.jsonl"), "a") as f:
        f.write(json.dumps(r) + "\n")
    log(f"{gpu} {name}: {r['status']} tok/s={r.get('tok_s')} contended={contended} drm={r['drm']}")
    return r


def run_gpu(gpu, sizes, quants, reps, check):
    t = TARGETS[gpu]
    deploy(gpu, t)
    for s in sizes:
        for q in quants:
            if check:
                for m in MODES:
                    run_one(gpu, t, s, q, m, 0, True)
                continue
            for rep in range(1, reps + 1):
                order = ["tiled", "tuned"] if rep % 2 else ["tuned", "tiled"]
                for m in order:
                    run_one(gpu, t, s, q, m, rep, False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gpus", nargs="+", choices=list(TARGETS))
    ap.add_argument("--sizes", default="1b,3b,8b")
    ap.add_argument("--quants", default="4w,8da4w")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    for g in a.gpus:
        run_gpu(g, a.sizes.split(","), a.quants.split(","), a.reps, a.check)
    log("DONE")


if __name__ == "__main__":
    sys.exit(main())
