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
triangle_occlusion(const Line3D& line_PQ, 
                   const Triangle3D& tri_ABC,
                   const Mat4& mvp,
                   double width, double height,
                   bool debug = false) {

    // --- Step 0: project everything to camera space and check for early outs ---
    auto P_cam = project_vertex(line_PQ.a,     mvp, width, height);
    auto Q_cam = project_vertex(line_PQ.b,     mvp, width, height);
    auto A_cam = project_vertex(tri_ABC.a, mvp, width, height);
    auto B_cam = project_vertex(tri_ABC.b, mvp, width, height);
    auto C_cam = project_vertex(tri_ABC.c, mvp, width, height);
    if (!P_cam || !Q_cam || !A_cam || !B_cam || !C_cam) return {};

    if (debug) std::cerr << "      tri 2D: A(" << A_cam->x << "," << A_cam->y
                         << ") B(" << B_cam->x << "," << B_cam->y
                         << ") C(" << C_cam->x << "," << C_cam->y << ")\n";

    // --- Step 1: find all 2D intervals ---
    double t_vals[5]; // at most 5 t values: 3 edge hits + 2 endpoints
    int   n = 0;
    double t, s;
    if (segment_intersect_2D(*P_cam, *Q_cam, *A_cam, *B_cam, t, s)) { if (debug) std::cerr << "      edge AB hit t=" << t << "\n"; t_vals[n++] = t; }
    if (segment_intersect_2D(*P_cam, *Q_cam, *B_cam, *C_cam, t, s)) { if (debug) std::cerr << "      edge BC hit t=" << t << "\n"; t_vals[n++] = t; }
    if (segment_intersect_2D(*P_cam, *Q_cam, *C_cam, *A_cam, t, s)) { if (debug) std::cerr << "      edge CA hit t=" << t << "\n"; t_vals[n++] = t; }

    // Check if endpoints are inside the triangle (counts as an intersection at t=0 or t=1).
    bool p0_in = point_in_triangle_2D(*P_cam, *A_cam, *B_cam, *C_cam);
    bool p1_in = point_in_triangle_2D(*Q_cam, *A_cam, *B_cam, *C_cam);
    if (debug) std::cerr << "      P_cam in tri=" << (p0_in ? "true" : "false") << "  Q_cam in tri=" << (p1_in ? "true" : "false") << "\n";
    if (p0_in) t_vals[n++] = 0.0f;
    if (p1_in) t_vals[n++] = 1.0f;

    if (debug) std::cerr << "      n=" << n << "\n";
    if (n < 2) return {};

    // find the min/max to get the full interval [ta, tb] of overlap.
    double ta = *std::min_element(t_vals, t_vals + n);
    double tb = *std::max_element(t_vals, t_vals + n);
    if (tb - ta < 1e-6f) return {};

    // --- Step 2: find t_triangle (line crosses triangle plane in 3D) ---
    Vec3  N     = tri_ABC.normal();
    Vec3  PQ    = line_PQ.b - line_PQ.a;
    double denom = N.dot(PQ);
    double t_triangle = (std::fabs(denom) < MIN_DOUBLE) ? -1.0f  // segment parallel to plane
                                                : N.dot(tri_ABC.a - line_PQ.a) / denom;

    if (debug) std::cerr << "      t_triangle=" << t_triangle
                         << "  2D interval [" << ta << ", " << tb << "]\n";

    // --- Step 3 & 4: split at t_triangle and depth-check each piece ---
    constexpr double kDepthBias = 1e-4;

    std::vector<OccludedInterval> result;

    // Helper to test a piece of the line segment for occlusion. If the line is behind the triangle, add it to the result.
    auto test_piece = [&](double a, double b) {
        if (b - a < 1e-6) return;
        double tmid      = (a + b) * 0.5;
        Vec3   pmid      = *P_cam + (*Q_cam - *P_cam) * tmid;
        double line_depth = P_cam->z + (Q_cam->z - P_cam->z) * tmid;
        double tri_depth  = triangle_depth_at(pmid, *A_cam, *B_cam, *C_cam);
        if (debug) std::cerr << "      piece [" << a << "," << b << "]"
                             << " line_depth=" << line_depth
                             << " tri_depth=" << tri_depth << "\n";
        if (line_depth > tri_depth + kDepthBias)
            result.push_back({a, b});
    };

    // If the triangle intersects the line segment, we have two pieces to test: [ta, t_triangle] and [t_triangle, tb].
    if (t_triangle > ta && t_triangle < tb) {
        test_piece(ta, t_triangle);
        test_piece(t_triangle, tb);
    } else {
        test_piece(ta, tb);
    }

    return result;
}
