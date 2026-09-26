#include "calibration.h"
#include <cassert>
#include <string>
#include <vector>

int main() {
  auto run = [](uint32_t loops, uint32_t batch, uint32_t limit, double cost, double overhead) {
    int rounds = 0, samples = 0;
    std::string stop;
    calibrateTiming(
        loops, batch, limit, .005, true,
        [&](uint32_t l, uint32_t b) {
          ++samples;
          return b * (overhead + l * cost);
        },
        [&](int, uint32_t l, uint32_t b, double seconds, double fixed, uint32_t nl, uint32_t nb,
            const std::string &reason, bool done) {
          ++rounds;
          assert(nl >= 2 && nl <= limit && nb >= 1 && nb <= 256);
          assert(double(nl) / l >= .125 && double(nl) / l <= 8);
          assert(double(nb) / b >= .125 && double(nb) / b <= 8);
          if (done) {
            stop = reason;
            if (reason == "target_reached")
              assert(seconds >= .005 && seconds <= .0075 && fixed <= .10);
          }
        });
    assert(rounds <= 10 && samples == rounds * 6 && !stop.empty());
    return stop;
  };
  assert(run(1024, 1, 16384, .00005, .000001) == "target_reached"); // too long
  assert(run(2, 1, 16384, .000001, .000001) == "target_reached");   // too short
  assert(run(128, 64, 16384, .00005, .000001) == "target_reached"); // remove batches
  assert(run(2, 1, 64, .00000001, 0) == "workload_limit");          // both upper limits
  assert(run(2, 1, 64, .01, 0) == "workload_limit");                // lower loop limit
  assert(run(4, 1, 64, .000001, .01) == "fixed_cost_limit");        // fixed cost dominates
  assert(run(2, 1, 16384, .000001, .003) == "fixed_cost_limit");
  assert(run(128, 1, 16384, .00057, .0037) == "quality_floor_reached"); // Pixel regression
  uint32_t loops = 128, batch = 1;
  int rounds = 0;
  std::string stop;
  calibrateTiming(
      loops, batch, 16384, .005, false, [&](uint32_t, uint32_t) { return rounds % 2 ? .001 : .1; },
      [&](int, uint32_t, uint32_t, double, double, uint32_t, uint32_t, const std::string &reason,
          bool done) {
        ++rounds;
        if (done)
          stop = reason;
      });
  assert(rounds == 10 && stop == "iteration_limit");
  // A single outlier in each triplet must not move an already calibrated workload.
  uint32_t stableLoops = 128, stableBatch = 1;
  int calls = 0;
  calibrateTiming(
      stableLoops, stableBatch, 16384, .005, false,
      [&](uint32_t, uint32_t) { return ++calls % 3 == 0 ? 1.0 : .006; },
      [&](int round, uint32_t, uint32_t, double sec, double, uint32_t, uint32_t,
          const std::string &reason,
          bool done) { assert(round == 0 && sec == .006 && done && reason == "target_reached"); });
  assert(calls == 3 && stableLoops == 128 && stableBatch == 1);
}
