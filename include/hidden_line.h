#pragma once
#include <vector>
#include <iostream>
#include "scene.h"
#include "lgl_math.h"
#include "project.h"
#include "interval.h"
#include "occlusion.h"

// debug helpers — print Vec2 / NDC depth
static inline void dbg_vec2(const char* label, float x, float y) {
    std::cerr << "    " << label << " (" << x << ", " << y << ")\n";
}

inline std::vector<Line2D>
hidden_line_removal(const Scene& scene, const Mat4& mvp,
                    float width, float height, bool debug = false) {
    std::vector<Line2D> result;
    int line_idx = 0;

    for (const auto& line : scene.lines) {
        float lx0 = 0, ly0 = 0, lx1 = 0, ly1 = 0;
        bool a_ok = project_vertex(line.a, mvp, width, height, lx0, ly0);
        bool b_ok = project_vertex(line.b, mvp, width, height, lx1, ly1);

        if (debug) {
            std::cerr << "\n[line " << line_idx << "]"
                      << " 3D (" << line.a.x << "," << line.a.y << "," << line.a.z << ")"
                      << " -> (" << line.b.x << "," << line.b.y << "," << line.b.z << ")\n";
            if (!a_ok) std::cerr << "  endpoint A behind camera — skip\n";
            if (!b_ok) std::cerr << "  endpoint B behind camera — skip\n";
        }
        ++line_idx;
        if (!a_ok || !b_ok) continue;

        if (debug) {
            dbg_vec2("  2D A:", lx0, ly0);
            dbg_vec2("  2D B:", lx1, ly1);
            float dx = lx1 - lx0, dy = ly1 - ly0;
            std::cerr << "  2D length: " << std::sqrt(dx*dx + dy*dy) << "\n";
        }

        IntervalSet visible;

        int tri_idx = 0;
        for (const auto& tri : scene.triangles) {
            auto occs = triangle_occlusion(line.a, line.b, tri, mvp, width, height, debug);
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
            float x0, y0, x1, y1;
            if (project_vertex(Pa, mvp, width, height, x0, y0) &&
                project_vertex(Pb, mvp, width, height, x1, y1))
                result.push_back({x0, y0, x1, y1});
        }
    }

    return result;
}
