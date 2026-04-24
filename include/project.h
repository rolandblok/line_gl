#pragma once
#include <optional>
#include <vector>
#include "vec_math.h"
#include "scene.h"

struct Line2D {
    Vec3 a, b;
};

// Returns nullopt if the point is behind the camera (w <= 0).
// xy = screen-space position, z = NDC depth in [-1, 1].
inline std::optional<Vec3> project_vertex(const Vec3& v, const Mat4& mvp,
                                           double width, double height) {
    Vec4 clip = mvp * Vec4(v, 1.0);
    if (clip.w <= 0.0) return std::nullopt;
    double nx = clip.x / clip.w;
    double ny = clip.y / clip.w;
    return Vec3{
        (nx + 1.0) * 0.5 * width,
        (1.0 - (ny + 1.0) * 0.5) * height,  // Y-flip for SVG
        clip.z / clip.w                       // NDC depth in [-1, 1]
    };
}

// Projects all lines in a scene through MVP into 2D screen space.
// Lines with either endpoint behind the camera are dropped.
inline std::vector<Line2D> project_scene(const Scene& scene, const Mat4& mvp,
                                          double width, double height) {
    std::vector<Line2D> result;
    for (const auto& line : scene.lines) {
        auto a = project_vertex(line.a, mvp, width, height);
        auto b = project_vertex(line.b, mvp, width, height);
        if (a && b)
            result.push_back({*a, *b});
    }
    return result;
}
