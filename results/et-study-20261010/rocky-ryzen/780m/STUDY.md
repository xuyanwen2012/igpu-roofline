# Radeon 780M: roofs against the tuned linear kernels (campaign et-study-20261010)

## State

- 2026-10-09 18:20 UTC: NOTHING of this study is running on the device.
- Part A ran 17:49 to 18:12 UTC (fast plan, tool 84361ac unmodified, finished, all roofs confirmed, sentinel
  healthy). A foreign `nvtop` (interactive ssh session, not started by this study) attached to the GPU at
  18:03:05 UTC: 22 s before the end of the confirmation stage and during all three sustained runs. Under rule 5
  the run is to be repeated once when the GPU is free; the first run is kept for comparison.
- Part B/C timing run was started at 18:17 UTC, found the `nvtop`, and was stopped by me after 1 minute
  (output filed as superseded on the device host). Waiting for the `nvtop` to go (checked 18:19: still there);
  meanwhile the parts that need no GPU (SPIR-V accumulator types, roofline shader ISA counts) are being done.
