#include <cmath>
#include <iostream>
#include "scene.h"
#include "camera.h"
#include "project.h"
#include "hidden_line.h"
#include "intersect.h"
#include "svg.h"
#include "vec_math.h"

[[maybe_unused]] static Scene make_xyz_axis_scene() {
    Scene s;
    s.add_line({0,0,0}, {0.5,0,0}, color{255,0,0});
    s.add_line({0,0,0}, {0,0.5,0}, color{0,255,0});
    s.add_line({0,0,0}, {0,0,0.5}, color{0,0,255});
    return s;
}

// Simple test scene: one triangle in the XY plane, one line passing through it from behind.
// Expected result: the line is split into two visible segments on either side of the triangle.
[[maybe_unused]] static Scene make_test_scene() {
    Scene s;

    Vec3 ta{0,0,0}, tb{2,0,0}, tc{0,2,0};
    s.add_triangle(ta, tb, tc);

    // Triangle edges (coplanar with the face; depth bias prevents self-occlusion)
    s.add_line(ta, tb);
    s.add_line(tb, tc);
    s.add_line(tc, ta);

    // Line at z=-1 (behind the triangle), crossing through its projected area at y=0.25
    s.add_line({1, 1, -2}, {1,1, 2});
    s.add_line({0.5, 1, -2}, {1, 0.5, 2});
    s.add_line({1, 0.4, -2}, {1, 0.4, 0.4});

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

// Two triangles that half-cross each other:
//   - Triangle A is tilted so its left half is in front, right half behind triangle B.
//   - Triangle B is tilted the opposite way.
// Each triangle's edges should be visible on the half that sticks out in front.
[[maybe_unused]] static Scene make_crossing_triangles() {
    Scene s;

    // Triangle A: 
    Vec3 A0{ 1.5,  0,  0};
    Vec3 A1{ 0.0,  1.5, 0};
    Vec3 A2{ 0,  0.0, 1.5};
    s.add_triangle(A0, A1, A2);
    s.add_line(A0, A1, color{255,0,0});
    s.add_line(A1, A2, color{0,255,0});
    s.add_line(A2, A0, color{0,0,255});

    // Triangle B: 
    Vec3 B0{2.0, 0, 1.0};
    Vec3 B1{ -2.0, 0,  0};
    Vec3 B2{ -2.0,    1,  0.0};
    s.add_triangle(B0, B1, B2);
    s.add_line(B0, B1, color{255,0,0});
    s.add_line(B1, B2, color{0,255,0});
    s.add_line(B2, B0, color{0,0,255});

    return s;
}

int main() {
    const double W = 800.0f, H = 600.0f;

    Camera cam_persp;
    cam_persp.position   = {2.0f, 1.5f, 3.0f};
    cam_persp.target     = {0.0f, 0.0f, 0.0f};
    cam_persp.fov        = 3.14159265f / 3.0f;
    cam_persp.proj_mode  = ProjectionMode::Perspective;

    Camera cam_ortho;
    cam_ortho.position      = {2.0f, 1.5f, 3.0f};
    cam_ortho.target        = {0.0f, 0.0f, 0.0f};
    cam_ortho.proj_mode     = ProjectionMode::Orthographic;
    cam_ortho.ortho_height  = 2.5;

    // ── switch projection here ──────────────────────────────
    Camera& cam = cam_ortho;
    // ────────────────────────────────────────────────────────

    Mat4 view = cam.view();
    const Mat4* view_mat = (cam.proj_mode == ProjectionMode::Orthographic) ? &view : nullptr;
    Mat4 mvp = cam.mvp(W / H);

    Scene xyz = make_xyz_axis_scene();
    auto xyz_p = project_scene_full(xyz, mvp, W, H, view_mat);

    auto render = [&](Scene& scene, const char* out, const char* out_raw, bool debug = false) {
        std::vector<Vec3> crossings;
        auto pscene  = project_scene_full(scene, mvp, W, H, view_mat);
        add_triangle_intersection_lines(pscene);
        auto lines2d = hidden_line_removal(pscene, debug, &crossings);
        std::cout << out << ": " << lines2d.size() << " segments\n";

        SvgWriter svg(out, W, H);
        svg.add_lines(lines2d, 1.0f, false);
        svg.add_lines(xyz_p.lines, 2.0f, false);
        for (const auto& p : crossings)
            svg.add_dot(p, 4.0, "orange");

        SvgWriter svg_raw(out_raw, W, H);
        svg_raw.add_lines(project_scene(scene, mvp, W, H, view_mat), 1.5);
    };

    auto s1 = make_test_scene();
    render(s1, "output.svg",          "output_non_occlude.svg", false);

    auto s2 = make_cube();
    render(s2, "output_cube.svg",     "output_cube_raw.svg");

    auto s3 = make_crossing_triangles();
    render(s3, "output_crossing.svg", "output_crossing_raw.svg", true);

    return 0;
}
