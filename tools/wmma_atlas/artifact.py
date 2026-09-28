"""Turn docs/reports/wmma-shape-atlas.html into a claude.ai Artifact page (no print/download; skeleton-free)."""

import re
import sys
from pathlib import Path

src = Path("docs/reports/wmma-shape-atlas.html").read_text()
out = Path(sys.argv[1])
s = src
s = re.sub(
    r'^<!doctype html>\s*<html[^>]*><head><meta charset="utf-8"><meta name="viewport"[^>]*>',
    "",
    s,
)
s = s.replace(
    "<title>Matrix Geometry — Homelab WMMA Atlas</title>",
    "<title>WMMA Shape Atlas</title>",
)
s = s.replace("</head><body>", "")
s = s.replace("</body></html>", "")
s = s.replace(
    '<button class="print-button" onclick="window.print()">Print / Save PDF</button>',
    "",
)
# The page commits to one light paper look: pin the scheme and ground explicitly.
s = s.replace("<style>\n:root{", "<style>\n:root{color-scheme:light;", 1)
s = s.replace(
    "main{max-width:1240px;margin:auto;padding:48px 48px 32px}",
    "main{max-width:1240px;margin:auto;padding:48px 48px 32px;min-width:0}.figure{overflow-x:auto}",
)
# Downloads are inert in the artifact viewer; offer a copy instead.
s = s.replace(
    '<button id="download">Download source snapshot</button>',
    '<button id="download" type="button">Copy source snapshot (JSON)</button>',
)
s = re.sub(
    r"document\.getElementById\('download'\)\.addEventListener\('click',\(\)=>\{.*?\}\);\n",
    "document.getElementById('download').addEventListener('click',e=>{const b=e.currentTarget,t=document.getElementById('snapshot').textContent;navigator.clipboard.writeText(t).then(()=>{b.textContent='Copied';},()=>{const r=document.createRange();r.selectNodeContents(document.getElementById('raw'));document.querySelector('details').open=true;getSelection().removeAllRanges();getSelection().addRange(r);b.textContent='Selected below: press Ctrl+C';});});\n",
    s,
    flags=re.S,
)
assert "window.print" not in s and "a.download" not in s
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(s)
print(out, len(s))
