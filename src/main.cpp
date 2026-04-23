#include <cmath>
#include <iostream>
#include "scene.h"
#include "camera.h"
#include "project.h"
#include "hidden_line.h"
#include "svg.h"

// Simple test scene: one triangle in the XY plane, one line passing through it from behind.
// Expected result: the line is split into two visible segments on either side of the triangle.
static Scene make_test_scene() {
    Scene s;

    Vec3 ta{0,0,0}, tb{1,0,0}, tc{0,1,0};
    s.add_triangle(ta, tb, tc);

    // Triangle edges (coplanar with the face; depth bias prevents self-occlusion)
    s.add_line(ta, tb);
    s.add_line(tb, tc);
    s.add_line(tc, ta);

    // Line at z=-1 (behind the triangle), crossing through its projected area at y=0.25
    s.add_line({0.5f, 0.5f, -1}, {0.5f, 0.5f, 1});

    return s;
}

[[maybe_unused]] static Scene make_cube() {
    Scene s;
    Vec3 v[8] = {
        {-1,-1,-1}, { 1,-1,-1}, { 1, 1,-1}, {-1, 1,-1},
        {-1,-1, 1}, { 1,-1, 1}, { 1, 1, 1}, {-1, 1, 1},
    };
    int edges[12][2] = {
        {0,1},{1,2},{2,3},{3,0},
        {4,5},{5,6},{6,7},{7,4},
        {0,4},{1,5},{2,6},{3,7},
    };
    for (auto& e : edges)
        s.add_line(v[e[0]], v[e[1]]);

    int faces[12][3] = {
        {0,2,1},{0,3,2},  // back
        {4,5,6},{4,6,7},  // front
        {0,1,5},{0,5,4},  // bottom
        {3,6,2},{3,7,6},  // top
        {0,4,7},{0,7,3},  // left
        {1,2,6},{1,6,5},  // right
    };
    for (auto& f : faces)
        s.add_triangle(v[f[0]], v[f[1]], v[f[2]]);

    return s;
}

int main() {
    const float W = 800.0f, H = 600.0f;

    Scene scene = make_test_scene();

    Camera cam;
    cam.position = {3.0f, 2.5f, 5.0f};
    cam.target   = {0.0f, 0.0f, 0.0f};
    cam.fov      = 3.14159265f / 3.0f;
    Mat4 mvp = cam.mvp(W / H);

    auto lines2d = hidden_line_removal(scene, mvp, W, H, /*debug=*/true);
    std::cout << "hidden-line segments : " << lines2d.size() << "\n";

    auto lines_raw = project_scene(scene, mvp, W, H);
    std::cout << "raw projected segments: " << lines_raw.size() << "\n";

    SvgWriter svg("output.svg", W, H);
    svg.add_lines(lines2d, "black", 1.5f);

    SvgWriter svg_raw("output_non_occlude.svg", W, H);
    svg_raw.add_lines(lines_raw, "black", 1.5f);

    return 0;
}
