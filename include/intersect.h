#pragma once
#include <cmath>
#include <cstdlib>
#include "project.h"
#include "vec_math.h"
#include "primitives.h" 

// ---------------------------------------------------------------------------
// projected_triangle_intersection
//
// Finds the line segment where two projected triangles intersect in (x,y,z)
// space (xy = screen coords, z = clip.w depth).
//
// Algorithm:
//   1. Fit a plane through each triangle's three (x,y,z) points.
//   2. The intersection of the two planes is a 3-D line  P(t) = P0 + t*D.
//   3. Clip that line in 2D (xy only) to the interior of both triangles
//      using the Cyrus-Beck algorithm, yielding parameter interval [t0,t1].
//   4. Return the resulting segment.
//
// Returns false when the planes are parallel or the clipped interval is empty.
// ---------------------------------------------------------------------------
inline bool projected_triangle_intersection(
    const ProjectedTriangle& A,
    const ProjectedTriangle& B,
    Line3D& out)
{
    // ---- plane normals and offsets ----------------------------------------
    Vec3 nA = (A.b - A.a).cross(A.c - A.a);
    Vec3 nB = (B.b - B.a).cross(B.c - B.a);
    double dA = nA.dot(A.a);
    double dB = nB.dot(B.a);

    // ---- intersection line direction D = nA × nB --------------------------
    Vec3 D = nA.cross(nB);
    double Dlen2 = D.dot(D);
    if (Dlen2 < 1e-10) return false;   // parallel / near-parallel planes

    // ---- find one point P0 on both planes ----------------------------------
    // Fix the component of D with largest magnitude to zero and solve the
    // remaining 2×2 system for maximum numerical stability.
    double ax = std::abs(D.x), ay = std::abs(D.y), az = std::abs(D.z);
    Vec3 P0{};
    if (az >= ax && az >= ay) {
        // fix z = 0
        double det = nA.x * nB.y - nA.y * nB.x;
        if (std::abs(det) < 1e-12) return false;
        P0.x = (dA * nB.y - dB * nA.y) / det;
        P0.y = (nA.x * dB - nB.x * dA) / det;
        P0.z = 0.0;
    } else if (ay >= ax) {
        // fix y = 0
        double det = nA.x * nB.z - nA.z * nB.x;
        if (std::abs(det) < 1e-12) return false;
        P0.x = (dA * nB.z - dB * nA.z) / det;
        P0.z = (nA.x * dB - nB.x * dA) / det;
        P0.y = 0.0;
    } else {
        // fix x = 0
        double det = nA.y * nB.z - nA.z * nB.y;
        if (std::abs(det) < 1e-12) return false;
        P0.y = (dA * nB.z - dB * nA.z) / det;
        P0.z = (nA.y * dB - nB.y * dA) / det;
        P0.x = 0.0;
    }

    // ---- Cyrus-Beck clip P(t) = P0 + t*D to a triangle in 2D (xy) ---------
    //
    // For each edge (Vi → Vj) we require:
    //   cross2D(Vj-Vi, P(t)-Vi)  >=  0  (for CCW winding)
    //  →  c + t*k  >=  0
    //     c = cross2D(edge, P0 - Vi)
    //     k = cross2D(edge, D)
    //
    // For CW-wound triangles the signed area is negative; we flip the sign so
    // the same inequality stays "inside".
    // -------------------------------------------------------------------------
    double t_min = -1e18, t_max = 1e18;

    auto clip_to_tri = [&](const ProjectedTriangle& T) -> bool {
        double area2 = cross2Dxy(T.b - T.a, T.c - T.a);
        if (std::abs(area2) < 1e-10) return false;  // degenerate triangle
        double sgn = (area2 > 0) ? 1.0 : -1.0;

        const Vec3* v[3] = { &T.a, &T.b, &T.c };
        for (int i = 0; i < 3; ++i) {
            const Vec3& Vi = *v[i];
            const Vec3& Vj = *v[(i + 1) % 3];
            double ex = Vj.x - Vi.x, ey = Vj.y - Vi.y;
            double wx = P0.x - Vi.x, wy = P0.y - Vi.y;
            double c = sgn * (ex * wy - ey * wx);
            double k = sgn * (ex * D.y  - ey * D.x);

            if (std::abs(k) < 1e-10) {
                if (c < -1e-8) return false;     // line parallel & outside edge
            } else if (k > 0.0) {
                t_min = std::max(t_min, -c / k); // entering
            } else {
                t_max = std::min(t_max, -c / k); // exiting
            }
        }
        return t_min < t_max;
    };

    if (!clip_to_tri(A)) return false;
    if (!clip_to_tri(B)) return false;

    static constexpr double kMinLen2D = 0.5;  // pixels — skip degenerate segs
    Vec3 pa = P0 + D * t_min;
    Vec3 pb = P0 + D * t_max;
    double dx = pb.x - pa.x, dy = pb.y - pa.y;
    if (dx*dx + dy*dy < kMinLen2D * kMinLen2D) return false;

    out.a = pa;
    out.b = pb;
    return true;
}

// ---------------------------------------------------------------------------
// add_triangle_intersection_lines
//
// For every pair of triangles in the scene, computes their intersection
// segment and appends it to pscene.lines with the given color.
// Call this after project_scene_full() and before hidden_line_removal().
// ---------------------------------------------------------------------------
inline void add_triangle_intersection_lines(ProjectedScene& pscene,
                                             color col = color{})
{
    const std::size_t n = pscene.triangles.size();
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = i + 1; j < n; ++j) {
            Line3D seg;
            if (projected_triangle_intersection(
                    pscene.triangles[i], pscene.triangles[j], seg)) {
                seg.col = col;
                pscene.lines.push_back(seg);
            }
        }
    }
}
