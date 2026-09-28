from pathlib import Path

p = Path("docs/reports/wmma-shape-atlas.html")
s = p.read_text()
css = """
.shape-key{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:26px 0}.shape-key article{border-top:4px solid var(--green);background:#edf1e9;padding:18px}.shape-key b{font:36px Georgia,serif;display:block}.shape-key p{margin:6px 0 0;font-size:14px}.shape-key article:nth-child(2){border-color:var(--blue)}.shape-key article:nth-child(3){border-color:var(--orange)}.math-line{font:clamp(20px,3vw,32px)/1.5 Georgia,serif;text-align:center;padding:20px;background:#edf1e9;margin:20px 0}.math-line span{white-space:nowrap}.lesson{margin:32px 0}.lesson h3{font:26px Georgia,serif}.walkthrough{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:22px 0}.step-card{border:1px solid var(--line);border-top:4px solid var(--green);padding:20px}.step-card b{display:block;font:24px Georgia,serif;margin:12px 0}.step-card p{font-size:14px;margin-bottom:0}.step-card.active{background:#edf1e9;outline:2px solid var(--green)}.step-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.step-controls button[aria-pressed=true]{background:var(--green);color:white}.step-status{padding:18px;background:#edf1e9;margin-top:16px;min-height:100px}.annotated{overflow-x:auto}.annotated svg{min-width:640px}.lesson-note{font-size:14px;color:var(--muted)}.equation-highlight{color:var(--orange);font-weight:700}.matrix-labels{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.matrix-labels p{font-size:14px;margin:0}.matrix-labels b{display:block;font-size:17px}.explainer-summary{margin:16px 0;font-size:15px;padding:14px;border-left:3px solid var(--green)}
@media(max-width:650px){.shape-key{gap:8px}.shape-key article{padding:12px}.walkthrough{grid-template-columns:1fr}.matrix-labels{grid-template-columns:repeat(2,1fr)}.legend{flex-wrap:wrap}.shape-key b{font-size:28px}}@media print{.shape-key,.walkthrough,.matrix-labels{break-inside:avoid}.annotated{overflow:visible}.annotated svg{min-width:0}.lesson{break-inside:avoid}.step-controls,.step-status{display:none}.step-card.active{outline:none;background:transparent}}
"""
s = s.replace("</style>", css + "</style>")
# Draw individual cells and highlight one row/column/accumulator/output element.
svg = '<svg viewBox="0 0 1100 350" role="img" aria-label="An 8 by 16 A matrix with row zero highlighted, a 16 by 16 B matrix with column zero highlighted, and 8 by 16 C and D matrices with element zero zero highlighted.">'
for x, h, w, label, col, kind in [
    (30, 8, 16, "A", "#17685f", "row"),
    (310, 16, 16, "B", "#3b6591", "col"),
    (590, 8, 16, "C", "#b95e30", "cell"),
    (870, 8, 16, "D", "#b95e30", "cell"),
]:
    y = 190 - h * 6
    svg += f'<text x="{x + 96}" y="40" text-anchor="middle" font-size="23" fill="{col}" font-weight="600">{label}</text>'
    for r in range(h):
        for c in range(w):
            hi = r == 0 if kind == "row" else c == 0 if kind == "col" else r == c == 0
            svg += f'<rect x="{x + c * 12}" y="{y + r * 12}" width="11" height="11" fill="{col}" opacity="{1 if hi else 0.12}"/>'
    svg += f'<text x="{x + 96}" y="310" text-anchor="middle" font-size="18" fill="#192f35">{h} rows × {w} columns</text>'
for x, op in [(266, "×"), (546, "+"), (826, "=")]:
    svg += f'<text x="{x}" y="196" text-anchor="middle" font-size="30" fill="#192f35">{op}</text>'
svg += "</svg>"
start = s.index('<section><div class="section-top"><span class="section-no">01')
end = s.index('<section><div class="section-top"><span class="section-no">02', start)
section = (
    """<section><div class="section-top"><span class="section-no">01</span><div><h2>Read 8 × 16 × 16 as M × N × K</h2><p>A shape describes one small matrix operation. The first two numbers give the output’s size; the third tells you how many products are summed for each output element.</p></div></div>
<div class="shape-key"><article><span class="eyebrow">M · output height</span><b>8 rows</b><p>How many rows the result has.</p></article><article><span class="eyebrow">N · output width</span><b>16 columns</b><p>How many columns the result has.</p></article><article><span class="eyebrow">K · reduction length</span><b>16 products</b><p>How many pairs are multiplied and summed for each result element.</p></article></div>
<div class="math-line"><span>A<sub>8×16</sub> × B<sub>16×16</sub></span> <span>+ <strong class="equation-highlight">C<sub>8×16</sub></strong></span> <span>= D<sub>8×16</sub></span></div>
<figure class="figure annotated">"""
    + svg
    + """<figcaption class="caption">Figure 1. Each square is one matrix element. The highlighted row of A and column of B produce one dot product. Add the highlighted value in C to obtain the highlighted value in D. Repeat for all 8×16 = 128 output elements.</figcaption></figure>
<div class="matrix-labels"><p><b>A · left input</b>8 rows, each containing 16 values.</p><p><b>B · right input</b>16 columns, each containing 16 values.</p><p><b>C · sum so far</b>One existing value per output element.</p><p><b>D · updated result</b>The product plus the existing values.</p></div>
<div class="lesson"><h3>Follow one output element</h3><p>Take the first row of A and the first column of B. Multiply their matching values and sum the 16 products. Then add <code>C[0,0]</code>.</p><div class="math-line" style="font-size:20px"><span>D[0,0] = A[0,0]·B[0,0] + … + A[0,15]·B[15,0]</span> <span class="equation-highlight">+ C[0,0]</span></div><p class="lesson-note">If all 16 input pairs are 1×1, their sum is 16. With C[0,0] = 0, the result is 16. With C[0,0] = 10, the result is 26. The same rule applies independently at every output position.</p></div>
<div class="lesson"><h3>Why is there a C?</h3><p><b>C holds what you have already accumulated.</b> For a standalone multiplication, set every element of C to zero. For a larger multiplication, calculate the result in pieces and use the previous D as the next C.</p><p>For example, multiply an <b>8×48</b> matrix by a <b>48×16</b> matrix. Split the shared dimension, 48, into three chunks of 16. Each chunk uses the same <b>8×16×16</b> shape and contributes to the same 8×16 output.</p>
<div class="walkthrough"><article class="step-card" id="step-0"><span class="eyebrow">1 · first 16 products</span><b>D₁ = A₁B₁ + 0</b><p>Start with a zero C.<br>Example element: <strong>16 + 0 = 16</strong></p></article><article class="step-card" id="step-1"><span class="eyebrow">2 · next 16 products</span><b>D₂ = A₂B₂ + D₁</b><p>Previous result D₁ becomes C.<br>Example element: <strong>32 + 16 = 48</strong></p></article><article class="step-card" id="step-2"><span class="eyebrow">3 · final 16 products</span><b>D₃ = A₃B₃ + D₂</b><p>Previous result D₂ becomes C.<br>Example element: <strong>48 + 48 = 96</strong></p></article></div>
<p class="lesson-note">Numerical example: B contains ones; A contains ones in its first 16 columns, twos in the next 16, and threes in the final 16. Each output element is therefore 16×1 + 16×2 + 16×3 = 96. Every intermediate result remains 8×16.</p>
<div class="interactive"><div class="step-controls" role="group" aria-label="Explore accumulation steps"><span>Follow the running sum:</span><button type="button" id="chunk-0" aria-pressed="true">Chunk 1</button><button type="button" id="chunk-1" aria-pressed="false">Chunk 2</button><button type="button" id="chunk-2" aria-pressed="false">Chunk 3</button></div><div class="step-status" id="chunk-status" aria-live="polite"></div></div></div>
<div class="twocol"><div class="callout"><b>What does “FP16 → FP32” mean?</b><p style="margin:8px 0 0">A and B store FP16 inputs. C and D use FP32 for the accumulated values. The arrow describes numeric types; it does not change the matrix dimensions.</p></div><div class="callout"><b>Matrix dimensions are not thread counts.</b><p style="margin:8px 0 0">A cooperating group of GPU threads carries out the operation. An 8×16×16 shape does not mean 8 threads, 16 threads or 2,048 threads.</p></div></div>
<p class="caption">These equations explain the mathematical operation. Floating-point rounding depends on the arithmetic and implementation; tile shape alone does not establish accuracy or speed.</p></section>
"""
)
s = s[:start] + section + s[end:]
s = s.replace(
    '<div id="diagram" aria-live="polite"></div>',
    '<div id="tile-summary" class="explainer-summary" aria-live="polite"></div><div id="diagram"></div>',
)
s = s.replace(
    "document.getElementById('diagram').innerHTML=diagram(r.m,r.n,r.k);",
    "document.getElementById('diagram').innerHTML=diagram(r.m,r.n,r.k);document.getElementById('tile-summary').innerHTML=`<b>${shape(r)} means ${r.m} output rows, ${r.n} output columns, and ${r.k} products summed per output element.</b><br>A (${r.m}×${r.k}) × B (${r.k}×${r.n}) + C (${r.m}×${r.n}) = D (${r.m}×${r.n}). C is zero for a fresh multiplication, or the previous result when accumulating. A/B: ${types[r.a]}/${types[r.b]}; C/D: ${types[r.c]}/${types[r.result]}.`;",
)
s = s.replace(
    "function entries(){entry.replaceChildren",
    "function entries(){entry.replaceChildren",
)
# Begin with the exact Intel shape used in the opening explanation.
s = s.replace(
    "gpu.addEventListener('change',entries);entry.addEventListener('change',update);entries();",
    "gpu.selectedIndex=2;gpu.addEventListener('change',entries);entry.addEventListener('change',update);entries();",
)
extra = """
const chunkExamples=[{c:0,product:16,d:16},{c:16,product:32,d:48},{c:48,product:48,d:96}];
function showChunk(index){const v=chunkExamples[index];for(let i=0;i<3;i++){document.getElementById(`chunk-${i}`).setAttribute('aria-pressed',String(i===index));document.getElementById(`step-${i}`).classList.toggle('active',i===index);}document.getElementById('chunk-status').innerHTML=`<b>Chunk ${index+1}: C[0,0] = ${v.c} → add ${v.product} → D[0,0] = ${v.d}.</b><br>${index===0?'Start with zero: there is no earlier result.':`C now holds ${v.c}, the result from the previous chunk.`} ${index<2?`The result ${v.d} becomes C for the next chunk.`:'All 48 products have now been accumulated. The final output is still 8×16.'}`;}
for(let i=0;i<3;i++)document.getElementById(`chunk-${i}`).addEventListener('click',()=>showChunk(i));showChunk(0);
"""
s = s.replace("</script></body>", extra + "</script></body>")
p.write_text(s)
print("Updated", p)
