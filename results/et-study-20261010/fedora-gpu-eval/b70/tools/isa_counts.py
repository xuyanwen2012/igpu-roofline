#!/usr/bin/env python3
"""isa_counts.py <out.csv> <label=file>...: static counts from Mesa's GEN assembly listings.

Inputs are INTEL_DEBUG=cs dumps (several shaders per file, each introduced by "Native code for ...") or the
roofline tool's pipeline-inspection/<variant>.compute.GEN_Assembly.txt (one shader, no header; the statistics
then come from <variant>.json beside it). One row per distinct listing (a dump repeats a shader once per
pipeline creation; duplicates are counted in `copies`).

Columns: whole-shader counts, then the same counts inside the hottest loop = the innermost label..while range
that contains the most dpas instructions ("loop_*"). SLM = shared local memory messages (send.slm), split by the
message description the disassembler prints; bytes per message = lanes x data size x vector length.
All counts are static (per listing), not dynamic."""
import collections, csv, json, os, re, sys

HEAD = re.compile(r"SIMD(\d+) shader: (\d+) instructions\. (\d+) loops\. (\d+) cycles\. (\d+):(\d+) spills:fills, (\d+) sends, scheduled with mode ([\w-]+)\..*?GRF registers: (\d+)")
INS = re.compile(r"^(?:\(\S+\)\s+)?([a-z][\w.]*)\s+\((\d+)\)")
DATA = {"d8u32": 1, "d16u32": 2, "d32": 4, "d64": 8}


def msg_bytes(desc, lanes):
    m = re.search(r"\.(d8u32|d16u32|d32|d64)(?:x(\d+))?t?\.", desc + ".")
    return lanes * DATA[m[1]] * int(m[2] or 1) if m else 0


def count(lines):
    c = collections.Counter()
    for l in lines:
        m = INS.match(l.strip())
        if not m:
            continue
        op, lanes = m[1], int(m[2])
        c["instructions"] += 1
        desc = l.split(";")[-1].strip() if "//" in l else ""
        if op.startswith("dpas"):
            c["dpas"] += 1; c["dpas_" + op.split(".")[1] + "_w%d" % lanes] += 1
        elif op == "send.slm":
            kind = "load" if desc.startswith("load") else "store" if desc.startswith("store") else "fence" if desc.startswith("fence") else "other"
            c["slm_" + kind] += 1; c["slm_%s_bytes" % kind] += msg_bytes(desc, lanes)
            if kind == "load":
                c["slm_load_msgs:" + re.sub(r"\.a32.*", "", desc) + "(%d)" % lanes] += 1
        elif op in ("send.ugm", "send.tgm", "send.smpl", "send.gtwy"):
            kind = op.split(".")[1]
            if kind == "gtwy":
                kind = "barrier" if "barrier" in desc else "gtwy_other"
            elif kind == "ugm":
                kind = "ugm_load" if desc.startswith("load") else "ugm_store"
            elif kind == "tgm":
                kind = "tgm_load" if desc.startswith("load") else "tgm_store"
            c[kind] += 1
        elif op.startswith("sync"):
            c[op.replace(".", "_")] += 1
        elif op in ("while", "if", "else", "endif", "break", "jmpi"):
            c["flow"] += 1
    return c


def hot_loop(lines):
    labels, best = {}, None
    for i, l in enumerate(lines):
        m = re.match(r"^(L\d+):", l.strip())
        if m:
            labels[m[1]] = i
        m = re.match(r"^(?:\(\S+\)\s+)?while\s+\(\d+\)\s+(L\d+)", l.strip())
        if m and m[1] in labels:
            body = lines[labels[m[1]]:i + 1]
            n = sum(1 for x in body if "dpas" in x)
            if best is None or n > best[0] or (n == best[0] and len(body) < len(best[1])):
                best = (n, body)
    return best[1] if best else []


NIR = {}


def nir_facts(text):
    """workgroup size, shared memory size and subgroup size of the last NIR header in `text`"""
    f = []
    for k in ("workgroup_size", "shared_size", "api_subgroup_size", "min_subgroup_size", "max_subgroup_size"):
        m = re.findall(r"^%s: (.*)$" % k, text, re.M)
        if m:
            f.append("%s=%s" % (k, m[-1].replace(", ", "x")))
    return " ".join(f)


def listings(path):
    text = open(path, errors="replace").read()
    if "Native code for" not in text:
        stats = {}
        j = path.replace(".compute.GEN_Assembly.txt", ".json")
        if os.path.exists(j):
            for e in json.load(open(j))["records"][0].get("executables", []):
                for s in e.get("statistics", []):
                    stats[s["name"]] = s["value"]
                stats["_desc"] = e.get("description", "") + " " + e.get("name", "")
        n = path.replace("GEN_Assembly", "Final_NIR")
        stats["_nir"] = nir_facts(open(n).read()) if os.path.exists(n) else ""
        yield "", stats, text.splitlines()
        return
    parts = text.split("Native code for ")
    for prev, part in zip(parts, parts[1:]):
        NIR[re.search(r"blake3 (\w+)", part)[1][:16]] = nir_facts(prev)
        ls = part.splitlines()
        h = HEAD.search(ls[1])
        body = []
        for l in ls[2:]:
            if l.startswith("NIR ") or l.startswith("shader: ") or l.startswith("Native code"):
                break
            body.append(l)
        yield re.search(r"blake3 (\w+)", ls[0])[1][:16], h, body


COLS = ["dpas", "slm_load", "slm_load_bytes", "slm_store", "slm_store_bytes", "slm_fence", "barrier", "ugm_load", "ugm_store", "tgm_load", "tgm_store", "smpl", "sync_nop", "instructions"]
out = csv.writer(open(sys.argv[1], "w", newline=""))
out.writerow(["label", "listing", "copies", "simd_width", "instructions_reported", "loops", "cycles", "spills", "fills", "sends", "sched_mode", "grf", "nir_header"]
             + ["all_" + c for c in COLS] + ["dpas_forms"] + ["loop_" + c for c in COLS] + ["loop_slm_load_messages"])
for arg in sys.argv[2:]:
    label, path = arg.split("=", 1)
    seen = collections.OrderedDict()
    for ident, h, body in listings(path):
        key = ident or label
        if key in seen:
            seen[key][0] += 1; continue
        seen[key] = [1, h, body]
    for key, (copies, h, body) in seen.items():
        a, lp = count(body), count(hot_loop(body))
        if isinstance(h, dict):
            lanes = collections.Counter(int(m[2]) for m in (INS.match(l.strip()) for l in body) if m)
            meta = [max(lanes, key=lanes.get) if lanes else "", h.get("Instructions", ""), h.get("Loops", ""), h.get("Cycles", ""), h.get("Spills", ""), h.get("Fills", ""), h.get("SENDs", ""), "", h.get("GRF registers", ""), h.get("_nir", "")]
        else:
            meta = [h[1], h[2], h[3], h[4], h[5], h[6], h[7], h[8], h[9], NIR.get(key, "")]
        out.writerow([label, key, copies] + meta + [a[c] for c in COLS]
                     + [" ".join("%s:%d" % (k[5:], v) for k, v in sorted(a.items()) if k.startswith("dpas_"))]
                     + [lp[c] for c in COLS] + [" ".join("%s x%d" % (k[14:], v) for k, v in sorted(lp.items()) if k.startswith("slm_load_msgs:"))])
