#pragma once
#include <optional>
#include <vector>
#include <algorithm>
#include <iostream>
#include "vec_math.h"
#include "scene.h"
#include "depth.h"
#include "project.h"

struct OccludedInterval { double t0, t1; };

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
                   double width, double height,
                   bool debug = false) {

    // --- Step 0: project everything to 2D and check for early outs ---
    auto P_2D = project_vertex(P,     mvp, width, height);
    auto Q_2D = project_vertex(Q,     mvp, width, height);
    auto A_2D    = project_vertex(tri.a, mvp, width, height);
    auto B_2D    = project_vertex(tri.b, mvp, width, height);
    auto C_2D    = project_vertex(tri.c, mvp, width, height);
    if (!P_2D || !Q_2D || !A_2D || !B_2D || !C_2D) return {};

    if (debug) std::cerr << "      tri 2D: A(" << A_2D->x << "," << A_2D->y
                         << ") B(" << B_2D->x << "," << B_2D->y
                         << ") C(" << C_2D->x << "," << C_2D->y << ")\n";

    // --- Step 1: find all 2D intervals ---
    double t_vals[5]; // at most 5 t values: 3 edge hits + 2 endpoints
    int   n = 0;
    double t, s;
    if (segment_intersect(P_2D->xy(), Q_2D->xy(), A_2D->xy(), B_2D->xy(), t, s)) { if (debug) std::cerr << "      edge AB hit t=" << t << "\n"; t_vals[n++] = t; }
    if (segment_intersect(P_2D->xy(), Q_2D->xy(), B_2D->xy(), C_2D->xy(), t, s)) { if (debug) std::cerr << "      edge BC hit t=" << t << "\n"; t_vals[n++] = t; }
    if (segment_intersect(P_2D->xy(), Q_2D->xy(), C_2D->xy(), A_2D->xy(), t, s)) { if (debug) std::cerr << "      edge CA hit t=" << t << "\n"; t_vals[n++] = t; }

    bool p0_in = point_in_triangle_2d(P_2D->xy(), A_2D->xy(), B_2D->xy(), C_2D->xy());
    bool p1_in = point_in_triangle_2d(Q_2D->xy(), A_2D->xy(), B_2D->xy(), C_2D->xy());
    if (debug) std::cerr << "      P_2D in tri=" << p0_in << "  Q_2D in tri=" << p1_in << "\n";
    if (p0_in) t_vals[n++] = 0.0f;
    if (p1_in) t_vals[n++] = 1.0f;

    if (debug) std::cerr << "      n=" << n << "\n";
    if (n < 2) return {};

    double ta = *std::min_element(t_vals, t_vals + n);
    double tb = *std::max_element(t_vals, t_vals + n);
    if (tb - ta < 1e-6f) return {};

    // --- Step 2: find t_plane (line crosses triangle plane in 3D) ---
    Vec3  N     = tri.normal();
    Vec3  PQ    = Q - P;
    double denom = N.dot(PQ);
    double t_plane = (std::fabs(denom) < 1e-8f) ? -1.0f  // segment parallel to plane
                                                : N.dot(tri.a - P) / denom;

    if (debug) std::cerr << "      t_plane=" << t_plane
                         << "  2D interval [" << ta << ", " << tb << "]\n";

    // --- Step 3 & 4: split at t_plane and depth-check each piece ---
    constexpr double kDepthBias = 1e-4;

    std::vector<OccludedInterval> result;

    auto test_piece = [&](double a, double b) {
        if (b - a < 1e-6) return;
        double tmid      = (a + b) * 0.5;
        Vec2   pmid      = P_2D->xy() + (Q_2D->xy() - P_2D->xy()) * tmid;
        double line_depth = P_2D->z + (Q_2D->z - P_2D->z) * tmid;
        double tri_depth  = triangle_depth_at(pmid, *A_2D, *B_2D, *C_2D);
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
