#pragma once
#include <vector>

// Represents the visible portions of a line segment parameterized over [0, 1].
// Stored as a sorted list of disjoint intervals.
struct IntervalSet {
    struct Interval { float lo, hi; };

    IntervalSet() : _intervals{{0.0f, 1.0f}} {}

    // Punch out [lo, hi] from the visible set.
    void subtract(float lo, float hi) {
        if (lo >= hi) return;
        std::vector<Interval> result;
        for (const auto& iv : _intervals) {
            if (hi <= iv.lo || lo >= iv.hi) {
                result.push_back(iv);              // no overlap — keep whole interval
            } else {
                if (iv.lo < lo)  result.push_back({iv.lo, lo});  // left remnant
                if (iv.hi > hi)  result.push_back({hi, iv.hi});  // right remnant
            }
        }
        _intervals = result;
    }

    const std::vector<Interval>& intervals() const { return _intervals; }
    bool empty() const { return _intervals.empty(); }

private:
    std::vector<Interval> _intervals;
};
