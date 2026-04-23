#pragma once
#include <vector>
#include "lgl_math.h"

struct Line3D {
    Vec3 a, b;
};

struct Triangle3D {
    Vec3 a, b, c;
    Vec3 normal() const { return (b - a).cross(c - a).normalized(); }
};

struct Scene {
    std::vector<Line3D>     lines;
    std::vector<Triangle3D> triangles;

    void add_line(const Vec3& a, const Vec3& b)               { lines.push_back({a, b}); }
    void add_triangle(const Vec3& a, const Vec3& b, const Vec3& c) { triangles.push_back({a, b, c}); }
};
