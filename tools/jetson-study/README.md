# Jetson roof-guided ExecuTorch study

Target: gpu-lab `orin-naughty`, UUID `b49259c9-868c-5b7c-b6f1-65a2bf4b63be`.
The isolated ExecuTorch branch is `yanwen/release14-quant-shaders-jetson`, based on
`0270403ba`; build with the [cross recipe](../jetson-cross/README.md).

`run-device.py` consumes a JSON campaign on stdin on Jetson. Stage it in
`~/.cache/et-jetson-study/`. Each job has `name`, `argv`, optional `env`,
`timeout_seconds`, `memory_limited`, and `requires` (a successful preceding job).
`@ROOT@` and `@OUT@` expand to the device campaign root and per-job directory.
The top-level keys are `campaign`, `budget_seconds`, and `jobs`.

The controller takes gpu-lab's native lock, checks for existing GPU workloads,
clears inherited ET Vulkan toggles, preserves existing results, and records
commands, binary hash, exit status, memory, clocks and temperatures. Large-model
jobs use a systemd user scope with a memory limit and no swap allowance, plus a
watchdog reserving 1 GiB system memory. GPU allocations may not all be charged to
the scope; both protections are needed. A failed prerequisite skips its dependent
job. A timeout or memory stop is a failed measurement, never a timing sample.
For a strict model-fit attempt, set job `max_swap_growth_kb: 0` and campaign
`stop_on_memory_pressure: true`: any additional system swap stops the job and
the campaign, even if the memory reserve subsequently recovers. Existing swapped
pages are recorded, not cleared or treated as new growth.

No clocks, power modes, system libraries, services or global swap settings change.
Roofline takes its own lock in addition to the controller's gpu-lab lock.

Example from the Fedora checkout (SSH uses the existing trusted host alias):

```sh
ssh -o BatchMode=yes -o HostKeyAlias=duck-naughty -o UpdateHostKeys=no \
  doremy@duck-naughty.tail031559.ts.net \
  'python3 ~/.cache/et-jetson-study/run-device.py' \
  < out/jetson-study/baseline-spec.json
```

The local artifact root is `out/jetson-study/`: preserved baseline bundle,
baseline/candidate specs, source patches, numerical-check logs, pipeline statistics,
roofline reports, clean model timings and separate trace evidence. Sync completed
remote campaign folders before running `summarize.py <campaign-folder>`.
The summary retains each repetition and uses the median shader time; an operator
comparison must use the separately recorded operator time. Exclude failed numeric
checks and unstable cells from validated speedup claims.

The screen has ten 4w tiles (including fp32 accumulation for large K) and eight
8da4w tiles. Only finalists passing production checks and repeated confirmation
may become defaults. Archive the full screen patch before removing unused variants.

Linear quantization group size is **128**, verified from the actual PTE delegate
metadata and the benchmark's runtime header. Embedding group32 is separate.
Pass `--group-size=128` explicitly in screens. Offline pipeline statistics must
also use matching specialization values (`K4_per_group=32`, `num_groups=K/128`);
a group32 inspection is not representative, and makes k64 variants invalid.

`build-version.sh VERSION` syncs tracked changes from the isolated Jetson worktree
into the disposable cross-build snapshot, archives the patch and produces separate
trace-enabled and clean timing runners under `out/jetson-study/builds/VERSION`.
The restored SDPA files are already applied by the underlying cross recipe.
Existing version directories are preserved. `measure-rss.py` captures child peak
RSS without requiring the optional GNU time package on Jetson; RSS does not claim
to account for every GPU allocation. `summarize-models.py` records failed model
attempts as well as successful observer timings.

`analyze-roofline.py <study-root>` writes a CSV and figure relating original
matrix throughput to the measured short-run roofs. Its byte count is modeled
compulsory tensor traffic, not a DRAM counter. `compare-models.py <campaign>`
consumes `summarize-models.py` output and compares matched token counts, reporting
all repeat times and spreads. Single-run screens remain provisional.

The initial M256 candidates do not align with the small correctness harness's
M128 cases. A fallback in that test is not a numerical verdict: validate the
actual candidate at aligned production shapes. Likewise, the microbenchmark's
texture dispatch expectation must match the runtime's default-on texture path;
the final Jetson source fixes the previous presence-only environment check.

The controller caps cumulative recorded job wall time across this dedicated root
at 5400 seconds; compilation, transfer and idle time are excluded. Start a new
explicit study root to authorize a new budget, rather than deleting old results.
