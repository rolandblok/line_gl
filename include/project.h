#pragma once
#include <vector>
#include "lgl_math.h"
#include "scene.h"

struct Line2D {
    float x0, y0, x1, y1;
};

// Returns false if the point is behind the camera (w <= 0)
inline bool project_vertex(const Vec3& v, const Mat4& mvp,
                            float width, float height,
                            float& out_x, float& out_y) {
    Vec4 clip = mvp * Vec4(v, 1.0f);
    if (clip.w <= 0.0f) return false;
    float nx = clip.x / clip.w;
    float ny = clip.y / clip.w;
    out_x =  (nx + 1.0f) * 0.5f * width;
    out_y =  (1.0f - (ny + 1.0f) * 0.5f) * height;  // Y-flip for SVG
    return true;
}

// Projects all lines in a scene through MVP into 2D screen space.
// Lines with either endpoint behind the camera are dropped.
inline std::vector<Line2D> project_scene(const Scene& scene, const Mat4& mvp,
                                          float width, float height) {
    std::vector<Line2D> result;
    for (const auto& line : scene.lines) {
        float x0, y0, x1, y1;
        if (project_vertex(line.a, mvp, width, height, x0, y0) &&
            project_vertex(line.b, mvp, width, height, x1, y1))
            result.push_back({x0, y0, x1, y1});
    }
    return result;
}
