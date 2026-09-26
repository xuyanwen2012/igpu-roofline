#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

// Pure timing policy, also exercised with deterministic clocks in the native tests.
// measure(loops, batch) returns GPU seconds; emit records each measured candidate.
template <class Measure, class Emit>
static void calibrateTiming(uint32_t &loops, uint32_t &batch, uint32_t limit, double target,
                            bool differential, Measure measure, Emit emit) {
  const uint32_t minimum = differential ? 2 : 1;
  loops = std::clamp(loops, minimum, limit);
  batch = std::clamp(batch, 1u, 256u);
  auto median = [&](uint32_t l) {
    double times[3] = {measure(l, batch), measure(l, batch), measure(l, batch)};
    std::sort(times, times + 3);
    return times[1];
  };
  for (int round = 0; round < 10; ++round) {
    double seconds = median(loops);
    double fixed = 0;
    if (differential) {
      double half = median(loops / 2);
      fixed = (seconds - loops * (seconds - half) / (loops - loops / 2)) / seconds;
    }
    uint32_t nextLoops = loops, nextBatch = batch;
    std::string reason;
    double factor = std::clamp(target * 1.2 / seconds, 0.125, 8.0);
    if (fixed > 0.10) {
      // Batching cannot remove per-dispatch overhead: grow the loop body first.
      factor = std::clamp(fixed / 0.08, 1.125, 8.0);
      nextLoops = std::min(limit, uint32_t(std::ceil(loops * factor)));
      reason = nextLoops == loops ? "fixed_cost_limit" : "increase_for_fixed_cost";
    } else if (seconds >= target && seconds <= 1.5 * target) {
      reason = "target_reached";
    } else if (seconds > 1.5 * target) {
      if (batch > 1) {
        nextBatch = std::max(1u, uint32_t(std::ceil(batch * factor)));
        if (nextBatch == batch)
          --nextBatch;
        reason = "reduce_batch";
      } else {
        nextLoops = std::max(minimum, uint32_t(std::ceil(loops * factor)));
        if (nextLoops == loops && loops > minimum)
          --nextLoops;
        reason = "reduce_loops";
      }
    } else {
      nextLoops = std::min(limit, std::max(loops + 1, uint32_t(std::ceil(loops * factor))));
      if (nextLoops == loops) {
        nextBatch = std::min(256u, std::max(batch + 1, uint32_t(std::ceil(batch * factor))));
        reason = "increase_batch";
      } else
        reason = "increase_loops";
    }
    bool stop = nextLoops == loops && nextBatch == batch;
    if (stop && reason != "target_reached" && reason != "fixed_cost_limit")
      reason = "workload_limit";
    if (!stop && round == 9) {
      stop = true;
      reason = "iteration_limit";
    }
    emit(round, loops, batch, seconds, fixed, nextLoops, nextBatch, reason, stop);
    if (stop)
      return;
    loops = nextLoops;
    batch = nextBatch;
  }
}
