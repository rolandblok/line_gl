#pragma once
#include <cmath>

struct Vec2 {
    float x, y;
    Vec2(float x = 0, float y = 0) : x(x), y(y) {}
    Vec2 operator+(const Vec2& o) const { return {x+o.x, y+o.y}; }
    Vec2 operator-(const Vec2& o) const { return {x-o.x, y-o.y}; }
    Vec2 operator*(float t)        const { return {x*t,   y*t};   }
};

inline float cross2d(Vec2 a, Vec2 b) { return a.x*b.y - a.y*b.x; }

// Intersect segment AB with segment CD.
// On success sets t (parameter on AB) and s (parameter on CD), both in [0,1].
// Returns false if parallel or intersection falls outside either segment.
inline bool segment_intersect(Vec2 a, Vec2 b, Vec2 c, Vec2 d,
                               float& t, float& s) {
    Vec2  r     = b - a;
    Vec2  q     = d - c;
    float denom = cross2d(r, q);
    if (std::fabs(denom) < 1e-8f) return false;  // parallel
    Vec2  ac = c - a;
    t = cross2d(ac, q) / denom;
    s = cross2d(ac, r) / denom;
    return t >= 0.0f && t <= 1.0f && s >= 0.0f && s <= 1.0f;
}

// Returns true if p is inside or on the boundary of triangle (a, b, c).
// Works for both CW and CCW winding.
inline bool point_in_triangle_2d(Vec2 p, Vec2 a, Vec2 b, Vec2 c) {
    float d1 = cross2d(b - a, p - a);
    float d2 = cross2d(c - b, p - b);
    float d3 = cross2d(a - c, p - c);
    bool has_neg = (d1 < 0.0f) || (d2 < 0.0f) || (d3 < 0.0f);
    bool has_pos = (d1 > 0.0f) || (d2 > 0.0f) || (d3 > 0.0f);
    return !(has_neg && has_pos);
}
