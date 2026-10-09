# Radeon 780M: roofs against the tuned linear kernels (campaign et-study-20261010)

## State

- 2026-10-09 19:06 UTC: RUNNING on the device: the part B/C timing run (`tools/run-et-microbench.sh`, detached,
  campaign lock held, status in `status.txt` of its output folder on the device host). Next: the repeat of
  part A. The owner ended the foreign `nvtop` at 19:05 UTC (decision in the task file, option a).
- First part A run (17:49 to 18:12 UTC): kept for comparison, see "Decision" below for what in it was
  measured with the `nvtop` attached.

## Decision asked 2026-10-09 18:35 UTC, answered 19:05 UTC: option (a), the owner ended the `nvtop` (kept as written)

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
