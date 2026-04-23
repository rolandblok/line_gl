#pragma once
#include <cmath>
#include "lgl_math.h"
#include "geom2d.h"

// NDC z depth of a single 3D point. Returns 1.0 (far) if behind camera.
inline float ndc_depth(const Vec3& p, const Mat4& mvp) {
    Vec4 clip = mvp * Vec4(p, 1.0f);
    if (clip.w <= 0.0f) return 1.0f;
    return clip.z / clip.w;
}

// NDC z depth at parameter t along segment PQ.
inline float depth_at_t(const Vec3& P, const Vec3& Q, float t, const Mat4& mvp) {
    return ndc_depth(P + (Q - P) * t, mvp);
}

// Barycentric coordinates (u, v, w) of point p inside 2D triangle (a, b, c).
// u is the weight for a, v for b, w for c.
// Returns false if the triangle is degenerate.
inline bool barycentric_2d(Vec2 p, Vec2 a, Vec2 b, Vec2 c,
                            float& u, float& v, float& w) {
    float denom = cross2d(b - a, c - a);
    if (std::fabs(denom) < 1e-8f) return false;
    u = cross2d(b - p, c - p) / denom;
    v = cross2d(c - p, a - p) / denom;
    w = 1.0f - u - v;
    return true;
}

// NDC z of a triangle at a given 2D screen point, via barycentric interpolation.
// da, db, dc are the NDC z depths of the three projected triangle vertices.
// Returns 1.0 (far) if barycentric coords cannot be computed.
inline float triangle_depth_at(Vec2 p,
                                Vec2 a, Vec2 b, Vec2 c,
                                float da, float db, float dc) {
    float u, v, w;
    if (!barycentric_2d(p, a, b, c, u, v, w)) return 1.0f;
    return u * da + v * db + w * dc;
}
