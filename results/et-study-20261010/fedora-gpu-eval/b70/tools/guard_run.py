#!/usr/bin/env python3
"""guard_run.py <out prefix> <command...>: run one GPU job of this study and watch the cards while it runs.

Every 2 s, one line in <out prefix>.samples.tsv:
  epoch  act_freq_MHz  cur_freq_MHz  throttle_status  throttle_reasons  pkg_temp_mC  energy_uJ  foreign
`foreign` lists GPU work this job did not start ("-" when none):
  drm:<pid>:<comm>:<pdev>:<engine cycles>   a DRM client of either B70 whose fdinfo is readable and whose pid
                                            is not a descendant of this guard
  name:<pid>:<comm>                         a process whose program name (for python: its script path) names a
                                            known GPU workload (the fallback for other users' processes)
The job is stopped (SIGTERM to its process group, KILL after 20 s) and the exit status is 76 when a name match
appears, or a foreign DRM client shows engine cycles that advance or are non-zero when first seen. A foreign
DRM client with zero cycles (an idle monitor) is recorded and does not stop the job.
<out prefix>.status.json always says what is running. Reads procfs and sysfs only; changes nothing.
"""
import glob, json, os, re, signal, subprocess, sys, time

PDEV = "0000:01:00.0"
PDEVS = ("0000:01:00.0", "0000:02:00.0")
NAMES = re.compile(r"llama-server|ComfyUI|comfyui|comfy|ollama|vllm|nvtop|intel_gpu_top|llama_main|test_llama_microbench|roofline")  # matched against the program, never against arguments
P = "/sys/bus/pci/devices/" + PDEV
F = P + "/tile0/gt0/freq0"
H = glob.glob(P + "/hwmon/hwmon*")[0]
ME = os.getpid()


def rd(path):
    try:
        return open(path).read().strip().replace(" ", "+") or "-"
    except OSError:
        return "-"


def mine(pid):
    while pid > 1:
        if pid == ME:
            return True
        try:
            pid = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


def comm(pid):
    return rd(f"/proc/{pid}/comm")


def foreign(last):
    out, stop = [], False
    seen = set()
    for f in glob.glob("/proc/[0-9]*/fdinfo/*"):
        try:
            t = open(f).read()
        except OSError:
            continue
        if "drm-pdev" not in t:
            continue
        kv = dict(l.split(":", 1) for l in t.splitlines() if ":" in l)
        pdev = kv.get("drm-pdev", "").strip()
        cid = (pdev, kv.get("drm-client-id", "").strip())
        pid = int(f.split("/")[2])
        if pdev not in PDEVS or cid in seen or mine(pid):
            continue
        seen.add(cid)
        cyc = sum(int(v.split()[0]) for k, v in kv.items() if k.startswith("drm-cycles-"))
        if cyc > last.get(cid, 0):
            stop = True
        last[cid] = cyc
        out.append(f"drm:{pid}:{comm(pid)}:{pdev}:{cyc}")
    for d in glob.glob("/proc/[0-9]*"):
        pid = int(d.split("/")[2])
        try:
            a = open(d + "/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        a = [x.decode(errors="replace") for x in a if x]
        if not a or mine(pid) or pid == ME:
            continue
        if os.path.basename(a[0]) in ("bash", "sh", "dash", "zsh", "fish") and "-c" in a[1:3]:
            continue
        prog = [os.path.basename(a[0])] + ([a[1]] if os.path.basename(a[0]).startswith("python") and len(a) > 1 else [])
        if NAMES.search(" ".join(prog)):
            out.append(f"name:{pid}:{comm(pid)}")
            stop = True
    return out, stop


def main():
    prefix, cmd = sys.argv[1], sys.argv[2:]
    status = {"command": cmd, "guard_pid": ME, "started_utc": time.strftime("%FT%TZ", time.gmtime()), "state": "starting", "polls": 0}

    def write():
        tmp = prefix + ".status.json.tmp"
        json.dump(status, open(tmp, "w"), indent=1)
        os.replace(tmp, prefix + ".status.json")

    last = {}
    o, stop = foreign(last)
    if o and stop:
        status.update(state="not_started_foreign", foreign=o, rc=76)
        write()
        return 76
    proc = subprocess.Popen(cmd, start_new_session=True)
    status.update(state="running", job_pid=proc.pid)
    rc = None
    with open(prefix + ".samples.tsv", "a", buffering=1) as s:
        s.write("epoch\tact_mhz\tcur_mhz\tthrottle\treasons\tpkg_temp_mc\tenergy_uj\tforeign\n")
        while True:
            o, stop = foreign(last)
            s.write("\t".join([f"{time.time():.2f}", rd(F + "/act_freq"), rd(F + "/cur_freq"), rd(F + "/throttle/status"), rd(F + "/throttle/reasons"), rd(H + "/temp2_input"), rd(H + "/energy1_input"), ";".join(o) or "-"]) + "\n")
            status["polls"] += 1
            if stop and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                status.update(state="foreign_stopped", foreign=o, rc=76)
                rc = 76
                break
            if proc.poll() is not None:
                rc = 76 if stop else proc.returncode
                status.update(state="foreign_at_end" if stop else "finished", foreign=o, rc=rc, job_rc=proc.returncode)
                break
            write()
            time.sleep(2)
    status["ended_utc"] = time.strftime("%FT%TZ", time.gmtime())
    write()
    return rc


if __name__ == "__main__":
    sys.exit(main())
