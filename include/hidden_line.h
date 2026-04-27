#pragma once
#include <vector>
#include <iostream>
#include "scene.h"
#include "vec_math.h"
#include "project.h"
#include "interval.h"
#include "occlusion.h"

// debug helpers — print Vec2 / NDC depth
static inline void dbg_vec2(const char* label, double x, double y) {
    std::cerr << "    " << label << " (" << x << ", " << y << ")\n";
}

inline std::vector<Line2D>
hidden_line_removal(const ProjectedScene& scene,
                    bool debug = false,
                    std::vector<Vec3>* crossings = nullptr) {
    std::vector<Line2D> result;
    int line_idx = 0;

    // For each line, find the 2D intervals where it's occluded by any triangle, then punch those out from the visible set.
    for (const auto& line : scene.lines) {

        if (debug) {
            std::cerr << "\n[line " << line_idx << "]"
                      << " 2D A(" << line.a.x << "," << line.a.y << ")"
                      << " -> B(" << line.b.x << "," << line.b.y << ")\n";
            dbg_vec2("  2D A:", line.a.x, line.a.y);
            dbg_vec2("  2D B:", line.b.x, line.b.y);
            double dx = line.b.x - line.a.x, dy = line.b.y - line.a.y;
            std::cerr << "  2D length: " << std::sqrt(dx*dx + dy*dy) << "\n";
        }
        ++line_idx;

        IntervalSet visible;

        int tri_idx = 0;
        for (const auto& tri : scene.triangles) {
            auto occs = triangle_occlusion(line, tri, debug, crossings);
            if (debug) {
                std::cerr << "  tri[" << tri_idx << "]: "
                          << occs.size() << " occluded piece(s)\n";
                for (const auto& occ : occs)
                    std::cerr << "    subtract [" << occ.t0 << ", " << occ.t1 << "]\n";
            }
            for (const auto& occ : occs) visible.subtract(occ.t0, occ.t1);
            ++tri_idx;
        }

        if (debug) {
            std::cerr << "  visible intervals: " << visible.intervals().size() << "\n";
            for (const auto& iv : visible.intervals())
                std::cerr << "    [" << iv.lo << ", " << iv.hi << "]\n";
        }

        for (const auto& iv : visible.intervals()) {
            Vec3 Pa = line.a + (line.b - line.a) * iv.lo;
            Vec3 Pb = line.a + (line.b - line.a) * iv.hi;
            Line2D visible_line;
            visible_line.a = Pa;
            visible_line.b = Pb;
            visible_line.col = line.col;
            result.push_back(visible_line);
        }
    }

    return result;
}


