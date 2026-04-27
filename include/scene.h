#pragma once
#include <vector>
#include "vec_math.h"

struct Line3D {
    Vec3 a, b;
    color col;
    Line3D(const Vec3& a, const Vec3& b, color col = color{}) : a(a), b(b), col(col) {}
};

struct Triangle3D {
    Vec3 a, b, c;
    Vec3 normal() const { return (b - a).cross(c - a).normalized(); }
};

struct Scene {
    std::vector<Line3D>     lines;
    std::vector<Triangle3D> triangles;

    void add_line(const Vec3& a, const Vec3& b, color col = color{}) 
                  { lines.push_back({a, b, col}); }
    void add_triangle(const Vec3& a, const Vec3& b, const Vec3& c) { triangles.push_back({a, b, c}); }
};
