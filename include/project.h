#pragma once
#include <optional>
#include <vector>
#include "vec_math.h"
#include "scene.h"

struct Line2D {
    Vec3 a, b;
    color col{};  // optional color for SVG output; default black
};

struct ProjectedTriangle {
    Vec3 a, b, c;   // xy = screen position, z = view-space depth (clip.w: positive, larger = closer)
};

struct ProjectedScene {
    std::vector<Line2D>           lines;
    std::vector<ProjectedTriangle> triangles;
};

// Projects a 3D vertex through MVP.
// Returns nullopt if the point is behind the camera (w <= 0).
// xy = screen-space position, z = clip.w (view-space depth: positive, linear, larger = closer).
inline std::optional<Vec3> project_vertex(const Vec3& v, const Mat4& mvp,
                                           double width, double height) {
    Vec4 clip = mvp * Vec4(v, 1.0);
    if (clip.w <= 0.0) return std::nullopt;
    double nx = clip.x / clip.w;
    double ny = clip.y / clip.w;
    return Vec3{
        (nx + 1.0) * 0.5 * width,
        (1.0 - (ny + 1.0) * 0.5) * height,  // Y-flip for SVG
        clip.w                                // view-space depth: larger = closer to camera
    };
}

// Projects the full scene to screen space once.
// Lines or triangles with any vertex behind the camera are dropped.
inline ProjectedScene project_scene_full(const Scene& scene, const Mat4& mvp,
                                          double width, double height) {
    ProjectedScene ps;
    for (const auto& line : scene.lines) {
        auto a = project_vertex(line.a, mvp, width, height);
        auto b = project_vertex(line.b, mvp, width, height);
        if (a && b) ps.lines.push_back({*a, *b, line.col});
    }
    for (const auto& tri : scene.triangles) {
        auto a = project_vertex(tri.a, mvp, width, height);
        auto b = project_vertex(tri.b, mvp, width, height);
        auto c = project_vertex(tri.c, mvp, width, height);
        if (a && b && c) ps.triangles.push_back({*a, *b, *c});
    }
    return ps;
}

// Projects only the lines (for a raw unoccluded view).
inline std::vector<Line2D> project_scene(const Scene& scene, const Mat4& mvp,
                                          double width, double height) {
    std::vector<Line2D> result;
    for (const auto& line : scene.lines) {
        auto a = project_vertex(line.a, mvp, width, height);
        auto b = project_vertex(line.b, mvp, width, height);
        Line2D projected_line;
        projected_line.a = *a;
        projected_line.b = *b;
        projected_line.col = line.col;
        if (a && b) result.push_back(projected_line);
    }
    return result;
}
