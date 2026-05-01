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
// Returns nullopt if the point is behind the camera.
// xy = screen-space position, z = depth (positive, larger = farther from camera).
// For orthographic projection, pass the view matrix as view_mat so that
// correct view-space depth (-z_view) is used instead of clip.w.
inline std::optional<Vec3> project_vertex(const Vec3& v, const Mat4& mvp,
                                           double width, double height,
                                           const Mat4* view_mat = nullptr) {
    Vec4 clip = mvp * Vec4(v, 1.0);
    double depth;
    if (view_mat) {
        // Orthographic: clip.w = 1; derive depth from view-space z.
        Vec4 vp = *view_mat * Vec4(v, 1.0);
        if (vp.z >= 0.0) return std::nullopt;  // behind or on camera plane
        depth = -vp.z;  // positive; larger = farther from camera
    } else {
        if (clip.w <= 0.0) return std::nullopt;
        depth = clip.w;
    }
    double nx = clip.x / clip.w;
    double ny = clip.y / clip.w;
    return Vec3{
        (nx + 1.0) * 0.5 * width,
        (1.0 - (ny + 1.0) * 0.5) * height,  // Y-flip for SVG
        depth
    };
}

// Projects the full scene to screen space once.
// Lines or triangles with any vertex behind the camera are dropped.
// For orthographic, pass the view matrix as view_mat for correct depth.
inline ProjectedScene project_scene_full(const Scene& scene, const Mat4& mvp,
                                          double width, double height,
                                          const Mat4* view_mat = nullptr) {
    ProjectedScene ps;
    for (const auto& line : scene.lines) {
        auto a = project_vertex(line.a, mvp, width, height, view_mat);
        auto b = project_vertex(line.b, mvp, width, height, view_mat);
        if (a && b) ps.lines.push_back({*a, *b, line.col});
    }
    for (const auto& tri : scene.triangles) {
        auto a = project_vertex(tri.a, mvp, width, height, view_mat);
        auto b = project_vertex(tri.b, mvp, width, height, view_mat);
        auto c = project_vertex(tri.c, mvp, width, height, view_mat);
        if (a && b && c) ps.triangles.push_back({*a, *b, *c});
    }
    return ps;
}

// Projects only the lines (for a raw unoccluded view).
// For orthographic, pass the view matrix as view_mat for correct depth.
inline std::vector<Line2D> project_scene(const Scene& scene, const Mat4& mvp,
                                          double width, double height,
                                          const Mat4* view_mat = nullptr) {
    std::vector<Line2D> result;
    for (const auto& line : scene.lines) {
        auto a = project_vertex(line.a, mvp, width, height, view_mat);
        auto b = project_vertex(line.b, mvp, width, height, view_mat);
        if (a && b) result.push_back({*a, *b, line.col});
    }
    return result;
}
