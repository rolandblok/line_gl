#pragma once
#include <optional>
#include <vector>
#include <algorithm>
#include <iostream>
#include "lgl_math.h"
#include "scene.h"
#include "geom2d.h"
#include "depth.h"
#include "project.h"

struct OccludedInterval { float t0, t1; };

// Returns the sub-intervals of PQ that the triangle occludes (0, 1, or 2 pieces).
//
// Strategy:
//  1. Find the 2D interval [ta, tb] where the projected segment overlaps the projected triangle.
//  2. Find t_plane: where the segment crosses the triangle's plane in 3D.
//  3. Split [ta, tb] at t_plane — each piece is either entirely in front or behind.
//  4. Keep only the pieces where the segment is behind the triangle (larger NDC z).
inline std::vector<OccludedInterval>
triangle_occlusion(const Vec3& P, const Vec3& Q,
                   const Triangle3D& tri,
                   const Mat4& mvp,
                   float width, float height,
                   bool debug = false) {
    // Project segment endpoints
    float lx0, ly0, lx1, ly1;
    if (!project_vertex(P, mvp, width, height, lx0, ly0)) return {};
    if (!project_vertex(Q, mvp, width, height, lx1, ly1)) return {};
    Vec2 L0{lx0, ly0}, L1{lx1, ly1};

    // Project triangle vertices
    float ax, ay, bx, by, cx, cy;
    if (!project_vertex(tri.a, mvp, width, height, ax, ay)) return {};
    if (!project_vertex(tri.b, mvp, width, height, bx, by)) return {};
    if (!project_vertex(tri.c, mvp, width, height, cx, cy)) return {};
    Vec2 A{ax, ay}, B{bx, by}, C{cx, cy};

    if (debug) std::cerr << "      tri 2D: A(" << ax << "," << ay
                         << ") B(" << bx << "," << by
                         << ") C(" << cx << "," << cy << ")\n";

    // --- Step 1: find 2D interval ---
    float t_vals[5];
    int   n = 0;
    float t, s;
    if (segment_intersect(L0, L1, A, B, t, s)) { if (debug) std::cerr << "      edge AB hit t=" << t << "\n"; t_vals[n++] = t; }
    if (segment_intersect(L0, L1, B, C, t, s)) { if (debug) std::cerr << "      edge BC hit t=" << t << "\n"; t_vals[n++] = t; }
    if (segment_intersect(L0, L1, C, A, t, s)) { if (debug) std::cerr << "      edge CA hit t=" << t << "\n"; t_vals[n++] = t; }

    bool p0_in = point_in_triangle_2d(L0, A, B, C);
    bool p1_in = point_in_triangle_2d(L1, A, B, C);
    if (debug) std::cerr << "      L0 in tri=" << p0_in << "  L1 in tri=" << p1_in << "\n";
    if (p0_in) t_vals[n++] = 0.0f;
    if (p1_in) t_vals[n++] = 1.0f;

    if (debug) std::cerr << "      n=" << n << "\n";
    if (n < 2) return {};

    float ta = *std::min_element(t_vals, t_vals + n);
    float tb = *std::max_element(t_vals, t_vals + n);
    if (tb - ta < 1e-6f) return {};

    // --- Step 2: find t_plane (line crosses triangle plane in 3D) ---
    Vec3  N     = tri.normal();
    Vec3  PQ    = Q - P;
    float denom = N.dot(PQ);
    float t_plane = (std::fabs(denom) < 1e-8f) ? -1.0f  // segment parallel to plane
                                                : N.dot(tri.a - P) / denom;

    if (debug) std::cerr << "      t_plane=" << t_plane
                         << "  2D interval [" << ta << ", " << tb << "]\n";

    // --- Step 3 & 4: split at t_plane and depth-check each piece ---
    constexpr float kDepthBias = 1e-4f;
    float da = ndc_depth(tri.a, mvp);
    float db = ndc_depth(tri.b, mvp);
    float dc = ndc_depth(tri.c, mvp);

    std::vector<OccludedInterval> result;

    auto test_piece = [&](float a, float b) {
        if (b - a < 1e-6f) return;
        float tmid       = (a + b) * 0.5f;
        Vec2  pmid       = L0 + (L1 - L0) * tmid;
        float line_depth = depth_at_t(P, Q, tmid, mvp);
        float tri_depth  = triangle_depth_at(pmid, A, B, C, da, db, dc);
        if (debug) std::cerr << "      piece [" << a << "," << b << "]"
                             << " line_depth=" << line_depth
                             << " tri_depth=" << tri_depth << "\n";
        if (line_depth > tri_depth + kDepthBias)
            result.push_back({a, b});
    };

    if (t_plane > ta && t_plane < tb) {
        test_piece(ta, t_plane);
        test_piece(t_plane, tb);
    } else {
        test_piece(ta, tb);
    }

    return result;
}
