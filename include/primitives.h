#pragma once
#include "vec_math.h"

inline double cross2Dxy(Vec3 v1, Vec3 v2) {
    return v1.x * v2.y - v1.y * v2.x;
}

struct Line3D {
    Vec3 a, b;
    color col;
    int  parent_tri = -1;   // index into Scene::triangles; -1 = none
    Line3D() = default;
    Line3D(const Vec3& a, const Vec3& b, color col = color{}) : a(a), b(b), col(col) {}
    Vec3 lerp(double t) const { return a + (b - a) * t; }
    inline double cross2Dxy() { return a.x*b.y - a.y*b.x; }

};

struct Triangle3D {
    Vec3 a, b, c;
    int  id       = -1;   // index into Scene::triangles, assigned when added
    int  group_id = -1;   // shared by all triangles from the same primitive (block/rectangle); -1 = ungrouped
    Vec3 normal() const { return (b - a).cross(c - a).normalized(); }
};


// Intersect of 2D line segment AB with 2D line segment CD.
// On success sets t (parameter on AB) and s (parameter on CD), both in [0,1].
// Returns false if parallel or intersection falls outside either segment.
inline bool segment_intersect_2D(Vec3 a, Vec3 b, Vec3 c, Vec3 d,
                               double& t, double& s) {
    Vec3  r     = b - a;
    Vec3  q     = d - c;
    double denom = cross2Dxy(r, q);
    if (std::fabs(denom) < MIN_DOUBLE) return false;  // parallel
    Vec3  ac = c - a;
    t = cross2Dxy(ac, q) / denom;
    s = cross2Dxy(ac, r) / denom;
    return t > -MIN_DOUBLE && t < (1.0f+MIN_DOUBLE) && s > -MIN_DOUBLE && s < (1.0f+MIN_DOUBLE);
}

// Returns true if 2D point p is inside or on the boundary of 2D triangle (a, b, c).
// Works for both CW and CCW winding.
inline bool point_in_triangle_2D(Vec3 p, Vec3 a, Vec3 b, Vec3 c) {
    double d1 = cross2Dxy(b - a, p - a);
    double d2 = cross2Dxy(c - b, p - b);
    double d3 = cross2Dxy(a - c, p - c);
    bool has_neg = (d1 < 0.0f) || (d2 < 0.0f) || (d3 < 0.0f);
    bool has_pos = (d1 > 0.0f) || (d2 > 0.0f) || (d3 > 0.0f);
    return !(has_neg && has_pos);
}

