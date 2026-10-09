# Radeon 780M: roofs against the tuned linear kernels (campaign et-study-20261010)

## State

- 2026-10-09 18:35 UTC: NOTHING of this study is running on the device. Waiting for the GPU to be free
  (see "Decision needed from the owner"); the device is checked at most every 20 minutes.
- Part A ran 17:49 to 18:12 UTC (fast plan, tool 84361ac unmodified, finished; 36 of 36 roofs confirmed,
  sentinel healthy in all 35 readings). A foreign `nvtop` attached to the GPU at 18:03:05 UTC. Measured
  after that moment: the last 11 confirmation rows (all of the texture family), two sentinel readings and the
  three 120 s sustained runs. Every sweep and every confirmation repeat of the matrix, fed-matrix, shared,
  memory, FMA and dot roofs ended before it. Rule 5: the run is repeated once when the GPU is free.
- Part B/C timing run: started 18:17 UTC, met the `nvtop`, stopped by me after 1 minute; its output is filed
  as superseded on the device host and is used for nothing.
- Done without the GPU so far: accumulator types of the nine dispatched kernels from their SPIR-V
  (`isa/spirv-types.csv`), ISA counts of the roofline matrix shaders from the driver disassembly that part A
  captured (`isa/roofline/`), the table generator (`tools/make_efficiency.py`).

## Decision needed from the owner (written once, 2026-10-09 18:35 UTC)

An interactive `nvtop` (pid 415275, an ssh session opened 18:03:05 UTC from another machine, not started by
this study) is attached to the 780M and was still there at 18:33 UTC, 30 minutes on. Rule 5 and the tuning
campaign's own practice (round 3: sessions with an idle `nvtop` attached are "not the round's numbers") make
a timing run under it invalid, and it is not mine to close. Parts B (kernel times) and C (driver dump of the
kernels during a real dispatch) need the GPU: about 12 minutes of device time; the repeat of part A 23 minutes.

- (a) Close that `nvtop` session. I then run B and C and the repeat of A. Cost: 35 minutes of device time.
  This is what I do without further question as soon as the process is gone.
- (b) Tell me to measure with the idle `nvtop` attached. Same 35 minutes, every row flagged as taken with a
  foreign GPU client attached. The first part A run suggests the effect is below its resolution (sustained
  14.762 against short 14.764 TFLOP/s, 86.72 against 86.73 GB/s, both sustained runs entirely under `nvtop`),
  but that is one observation, not a validation.
- (c) Close the study without B and C on this device: part A and the SPIR-V types stand, `efficiency.csv`
  stays empty. No device time.
