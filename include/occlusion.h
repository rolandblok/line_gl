#pragma once
#include <vector>
#include <algorithm>
#include <iostream>
#include <cmath>
#include "vec_math.h"
#include "depth.h"
#include "project.h"

struct OccludedInterval { double t0, t1; };

// Returns the sub-intervals of PQ that the projected triangle occludes.
//
// All inputs are pre-projected (xy = screen, z = view-space depth, larger = closer to camera).
//
// Strategy:
//  1. Find the 2D interval [ta, tb] where the line overlaps the triangle in screen space.
//     Track z_tri at each boundary point via edge interpolation (using the 's' param from
//     segment_intersect_2D) or barycentric (for endpoint-inside cases).
//  2. Compute delta = z_line - z_tri at ta and tb.
//     delta < 0 → line is farther from camera (occluded).
//  3. If delta has opposite signs at ta and tb, find the crossover t analytically (linear).
//  4. Emit the sub-intervals where delta < -kDepthBias.
inline std::vector<OccludedInterval>
triangle_occlusion(const Line2D& line_PQ,
                   const ProjectedTriangle& tri_ABC,
                   bool debug = false,
                   std::vector<Vec3>* crossings = nullptr) {

    const Vec3& P = line_PQ.a;
    const Vec3& Q = line_PQ.b;
    const Vec3& A = tri_ABC.a;
    const Vec3& B = tri_ABC.b;
    const Vec3& C = tri_ABC.c;

    if (debug) std::cerr << "      tri 2D: A(" << A.x << "," << A.y
                         << ") B(" << B.x << "," << B.y
                         << ") C(" << C.x << "," << C.y << ")\n";

    // --- Step 1: find all 2D overlap boundary points ---
    // Each point records t (on PQ) and z_tri (triangle's view-space depth at that screen point).
    struct BoundaryPt { double t; double z_tri; };
    BoundaryPt pts[5];
    int n = 0;

    double t, s;
    // Edge crossings: s gives exact position on the triangle edge → interpolate z_tri along edge.
    auto hit_xy = [&](double ti) -> std::pair<double,double> {
        return { P.x + (Q.x - P.x) * ti, P.y + (Q.y - P.y) * ti };
    };

    if (segment_intersect_2D(P, Q, A, B, t, s)) {
        auto [hx, hy] = hit_xy(t);
        if (debug) std::cerr << "      edge AB hit t=" << t << " s=" << s
                             << "  xy=(" << hx << "," << hy << ")\n";
        pts[n++] = {t, A.z + (B.z - A.z) * s};
        if (crossings) crossings->push_back(P + (Q - P) * t);
    }
    if (segment_intersect_2D(P, Q, B, C, t, s)) {
        auto [hx, hy] = hit_xy(t);
        if (debug) std::cerr << "      edge BC hit t=" << t << " s=" << s
                             << "  xy=(" << hx << "," << hy << ")\n";
        pts[n++] = {t, B.z + (C.z - B.z) * s};
        if (crossings) crossings->push_back(P + (Q - P) * t);
    }
    if (segment_intersect_2D(P, Q, C, A, t, s)) {
        auto [hx, hy] = hit_xy(t);
        if (debug) std::cerr << "      edge CA hit t=" << t << " s=" << s
                             << "  xy=(" << hx << "," << hy << ")\n";
        pts[n++] = {t, C.z + (A.z - C.z) * s};
        if (crossings) crossings->push_back(P + (Q - P) * t);
    }

    // Endpoint-inside: use barycentric to get z_tri at P or Q.
    bool p0_in = point_in_triangle_2D(P, A, B, C);
    bool p1_in = point_in_triangle_2D(Q, A, B, C);
    if (debug) std::cerr << "      P in tri=" << (p0_in ? "true" : "false")
                         << "  Q in tri=" << (p1_in ? "true" : "false") << "\n";
    if (p0_in) pts[n++] = {0.0, triangle_depth_at(P, A, B, C)};
    if (p1_in) pts[n++] = {1.0, triangle_depth_at(Q, A, B, C)};

    if (debug) std::cerr << "      n=" << n << "\n";
    if (n < 2) return {};

    // Find ta (min t) and tb (max t) with their z_tri values.
    int ia = 0, ib = 0;
    for (int i = 1; i < n; i++) {
        if (pts[i].t < pts[ia].t) ia = i;
        if (pts[i].t > pts[ib].t) ib = i;
    }
    double ta = pts[ia].t, tb = pts[ib].t;
    if (tb - ta < 1e-6) return {};

    // --- Step 2: depth delta at both interval endpoints ---
    // delta = z_line - z_tri;  delta < 0 → line is farther from camera (occluded).
    double delta_a = (P.z + (Q.z - P.z) * ta) - pts[ia].z_tri;
    double delta_b = (P.z + (Q.z - P.z) * tb) - pts[ib].z_tri;

    if (debug) std::cerr << "      2D interval [" << ta << ", " << tb << "]"
                         << "  delta_a=" << delta_a << "  delta_b=" << delta_b << "\n";

    // --- Step 3 & 4: classify and emit ---
    // z = clip.w: larger = farther from camera. Line is occluded when z_line > z_tri.
    // delta = z_line - z_tri > 0 means line is farther (behind) the triangle.
    constexpr double kDepthBias = 0.001;
    std::vector<OccludedInterval> result;

    bool a_behind = delta_a > kDepthBias;
    bool b_behind = delta_b > kDepthBias;

    if (a_behind && b_behind) {
        // Fully behind triangle → whole interval occluded.
        result.push_back({ta, tb});
    } else if (!a_behind && !b_behind) {
        // Fully in front (or coplanar) → nothing occluded.
    } else {
        // Depth crossover within the interval — find it analytically.
        double denom = delta_a - delta_b;
        if (std::fabs(denom) < 1e-10) return result;
        double t_cross = ta + (tb - ta) * delta_a / denom;
        t_cross = std::clamp(t_cross, ta, tb);
        if (debug) std::cerr << "      depth crossover at t=" << t_cross << "\n";
        if (crossings) crossings->push_back(P + (Q - P) * t_cross);
        if (a_behind) result.push_back({ta,      t_cross});
        else          result.push_back({t_cross, tb     });
    }

    return result;
}

