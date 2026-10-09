# WMMA shape atlas tools

Scripts that build `docs/reports/wmma-shape-atlas.html` and its supplementary
shape snapshot. Run everything from the repository root, with these sibling
checkouts present: `../gpu-lab` and `../sarc-acl` (path
`dev/1.5/executorch/openspec/changes/sarc-1.5-e2e-benchmark/contrib`).

## Run order

1. `extra_devices.py` reads the `contrib/*/roofline.json` files from the sibling
   sarc-acl checkout and the shape tables in `docs/COOPMAT-SHAPES.md`. It writes
   `docs/reports/data/cooperative-matrices-extra-2026-09-28.json`.
2. `build.py` reads `../gpu-lab/docs/data/cooperative-matrices-2026-09-26.json`
   plus the extra snapshot from step 1 and writes
   `docs/reports/wmma-shape-atlas.html` (needs matplotlib).
3. `improve.py` patches that HTML in place (adds CSS and rewrites section 01).
   It appends to the existing file, so run it once per `build.py` output; do not
   repeat it without rebuilding first.
4. Optional: `artifact.py <out.html>` converts the atlas into a
   skeleton-free page for publishing as an artifact. It does not modify the atlas.

Example: `python tools/wmma_atlas/extra_devices.py && python tools/wmma_atlas/build.py && python tools/wmma_atlas/improve.py`

## Unknowns

- The order above is inferred from the file reads and writes in the scripts; the
  scripts carry no usage header and it was not confirmed by running them.
- Whether `improve.py` is meant to stay a separate step or should be folded into
  `build.py` is not recorded.
- Input file names are hard-coded with dates; a new gpu-lab snapshot needs edits.

Device-specific evidence and verdicts are in
[MATRIX-ACCELERATION.md](../../docs/MATRIX-ACCELERATION.md).
