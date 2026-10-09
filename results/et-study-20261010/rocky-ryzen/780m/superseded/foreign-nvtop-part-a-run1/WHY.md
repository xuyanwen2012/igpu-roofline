First part A run (fast plan, 2026-10-09 17:49 to 18:12 UTC), kept for comparison (owner decision 19:05 UTC).

A foreign `nvtop` (the owner's idle monitor) attached to the GPU at 18:03:05 UTC. Measured after that moment:
the last 11 confirmation rows (texture family), two sentinel readings, and the three 120 s sustained runs.
All sweeps and all confirmation repeats of the matrix, fed-matrix, shared, memory, FMA and dot roofs ended
before it (`timings.jsonl`). Under rule 5 of the task the run was repeated once; the repeat is the study's part A.
The driver disassembly in `pipeline-inspection/` was captured at 17:49 UTC (compile only) and is what `isa/roofline/`
was first copied from; the repeat's capture is compared with it in `isa/README.md`.
