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
hidden_line_removal(const Scene& scene, const Mat4& mvp,
                    double width, double height, bool debug = false,
                    std::vector<Vec3>* crossings = nullptr) {
    std::vector<Line2D> result;
    int line_idx = 0;

    for (const auto& line : scene.lines) {

        // Project endpoints to 2D. If either is behind the camera, skip the line.
        auto line_a_2d = project_vertex(line.a, mvp, width, height);
        auto line_b_2d = project_vertex(line.b, mvp, width, height);

        if (debug) {
            std::cerr << "\n[line " << line_idx << "]"
                      << " 3D (" << line.a.x << "," << line.a.y << "," << line.a.z << ")"
                      << " -> (" << line.b.x << "," << line.b.y << "," << line.b.z << ")\n";
            if (!line_a_2d) std::cerr << "  endpoint A behind camera — skip\n";
            if (!line_b_2d) std::cerr << "  endpoint B behind camera — skip\n";
        }
        ++line_idx;
        if (!line_a_2d || !line_b_2d) continue;

        if (debug) {
            dbg_vec2("  2D A:", line_a_2d->x, line_a_2d->y);
            dbg_vec2("  2D B:", line_b_2d->x, line_b_2d->y);
            double dx = line_b_2d->x - line_a_2d->x, dy = line_b_2d->y - line_a_2d->y;
            std::cerr << "  2D length: " << std::sqrt(dx*dx + dy*dy) << "\n";
        }

        // Start with the whole line visible, then punch out occluded pieces.
        IntervalSet visible;

        int tri_idx = 0;
        for (const auto& tri : scene.triangles) {
            auto occs = triangle_occlusion(line, tri, mvp, width, height, debug, crossings);
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
            Vec3 Pa = *line_a_2d + (*line_b_2d - *line_a_2d) * iv.lo;
            Vec3 Pb = *line_a_2d + (*line_b_2d - *line_a_2d) * iv.hi;
            result.push_back({Pa, Pb});
        }
    }

    return result;
}


