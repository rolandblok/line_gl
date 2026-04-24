#pragma once
#include <cmath>

struct Vec2 {
    double x, y;
    Vec2(double x = 0, double y = 0) : x(x), y(y) {}
    Vec2 operator+(const Vec2& o) const { return {x+o.x, y+o.y}; }
    Vec2 operator-(const Vec2& o) const { return {x-o.x, y-o.y}; }
    Vec2 operator*(double t)        const { return {x*t,   y*t};   }
};

inline double cross2d(Vec2 a, Vec2 b) { return a.x*b.y - a.y*b.x; }

// Intersect segment AB with segment CD.
// On success sets t (parameter on AB) and s (parameter on CD), both in [0,1].
// Returns false if parallel or intersection falls outside either segment.
inline bool segment_intersect(Vec2 a, Vec2 b, Vec2 c, Vec2 d,
                               double& t, double& s) {
    Vec2  r     = b - a;
    Vec2  q     = d - c;
    double denom = cross2d(r, q);
    if (std::fabs(denom) < 1e-8f) return false;  // parallel
    Vec2  ac = c - a;
    t = cross2d(ac, q) / denom;
    s = cross2d(ac, r) / denom;
    return t >= 0.0f && t <= 1.0f && s >= 0.0f && s <= 1.0f;
}

// Returns true if p is inside or on the boundary of triangle (a, b, c).
// Works for both CW and CCW winding.
inline bool point_in_triangle_2d(Vec2 p, Vec2 a, Vec2 b, Vec2 c) {
    double d1 = cross2d(b - a, p - a);
    double d2 = cross2d(c - b, p - b);
    double d3 = cross2d(a - c, p - c);
    bool has_neg = (d1 < 0.0f) || (d2 < 0.0f) || (d3 < 0.0f);
    bool has_pos = (d1 > 0.0f) || (d2 > 0.0f) || (d3 > 0.0f);
    return !(has_neg && has_pos);
}




struct Vec3 {
    double x, y, z;
    Vec3(double x = 0, double y = 0, double z = 0) : x(x), y(y), z(z) {}
    Vec3 operator+(const Vec3& o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vec3 operator*(double t)        const { return {x*t,   y*t,   z*t};   }
    Vec3 operator/(double t)        const { return {x/t,   y/t,   z/t};   }
    Vec3 operator-()               const { return {-x,    -y,    -z};    }
    double dot(const Vec3& o)   const { return x*o.x + y*o.y + z*o.z; }
    Vec3  cross(const Vec3& o) const {
        return {y*o.z - z*o.y, z*o.x - x*o.z, x*o.y - y*o.x};
    }
    double length()     const { return std::sqrt(x*x + y*y + z*z); }
    Vec3  normalized() const { return *this / length(); }
    Vec2 xy() const { return {x, y}; }
};
inline Vec3 operator*(double t, const Vec3& v) { return v * t; }

struct Vec4 {
    double x, y, z, w;
    Vec4(double x = 0, double y = 0, double z = 0, double w = 1)
        : x(x), y(y), z(z), w(w) {}
    Vec4(const Vec3& v, double w = 1) : x(v.x), y(v.y), z(v.z), w(w) {}
    Vec3 xyz() const { return {x, y, z}; }
    Vec4 operator+(const Vec4& o) const { return {x+o.x, y+o.y, z+o.z, w+o.w}; }
    Vec4 operator*(double t)        const { return {x*t,   y*t,   z*t,   w*t};   }
    double dot(const Vec4& o) const { return x*o.x + y*o.y + z*o.z + w*o.w; }
};

// Column-major 4x4 matrix (OpenGL convention).
// m[col][row] — transform a column vector as: M * v
struct Mat4 {
    double m[4][4]{};

    static Mat4 identity() {
        Mat4 r;
        r.m[0][0] = r.m[1][1] = r.m[2][2] = r.m[3][3] = 1.0f;
        return r;
    }

    Mat4 operator*(const Mat4& b) const {
        Mat4 r;
        for (int col = 0; col < 4; ++col)
            for (int row = 0; row < 4; ++row)
                for (int k = 0; k < 4; ++k)
                    r.m[col][row] += m[k][row] * b.m[col][k];
        return r;
    }

    Vec4 operator*(const Vec4& v) const {
        return {
            m[0][0]*v.x + m[1][0]*v.y + m[2][0]*v.z + m[3][0]*v.w,
            m[0][1]*v.x + m[1][1]*v.y + m[2][1]*v.z + m[3][1]*v.w,
            m[0][2]*v.x + m[1][2]*v.y + m[2][2]*v.z + m[3][2]*v.w,
            m[0][3]*v.x + m[1][3]*v.y + m[2][3]*v.z + m[3][3]*v.w,
        };
    }

    Mat4 transposed() const {
        Mat4 r;
        for (int c = 0; c < 4; ++c)
            for (int row = 0; row < 4; ++row)
                r.m[row][c] = m[c][row];
        return r;
    }
};
