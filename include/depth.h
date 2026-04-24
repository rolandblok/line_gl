#pragma once
#include <cmath>
#include "vec_math.h"

// Barycentric coordinates (u, v, w) of point p inside 2D triangle (a, b, c).
// u is the weight for a, v for b, w for c.
// Returns false if the triangle is degenerate.
inline bool barycentric_2D(Vec3 p, Vec3 a, Vec3 b, Vec3 c,
                            double& u, double& v, double& w) {
    double denom = cross2D(b - a, c - a);
    if (std::fabs(denom) < 1e-8) return false;
    u = cross2D(b - p, c - p) / denom;
    v = cross2D(c - p, a - p) / denom;
    w = 1.0 - u - v;
    return true;
}

// NDC z of a triangle at a given 2D screen point, via barycentric interpolation.
// a, b, c are projected vertices: xy = screen position, z = NDC depth.
// Returns 1.0 (far) if the triangle is degenerate.
inline double triangle_depth_at(Vec3 p2, Vec3 a, Vec3 b, Vec3 c) {
    double u, v, w;
    if (!barycentric_2D(p2, a, b, c, u, v, w)) return 1.0;
    return u * a.z + v * b.z + w * c.z;
}
