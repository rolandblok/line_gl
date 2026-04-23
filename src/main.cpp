#include <cmath>
#include "scene.h"
#include "camera.h"
#include "project.h"
#include "svg.h"

static Scene make_cube() {
    Scene s;
    Vec3 v[8] = {
        {-1,-1,-1}, { 1,-1,-1}, { 1, 1,-1}, {-1, 1,-1},
        {-1,-1, 1}, { 1,-1, 1}, { 1, 1, 1}, {-1, 1, 1},
    };
    int edges[12][2] = {
        {0,1},{1,2},{2,3},{3,0},  // back face
        {4,5},{5,6},{6,7},{7,4},  // front face
        {0,4},{1,5},{2,6},{3,7},  // connecting edges
    };
    for (auto& e : edges)
        s.add_line(v[e[0]], v[e[1]]);

    // 6 faces × 2 triangles, CCW winding = outward normal
    int faces[12][3] = {
        {0,2,1},{0,3,2},  // back   (z=-1, normal 0,0,-1)
        {4,5,6},{4,6,7},  // front  (z=+1, normal 0,0,+1)
        {0,1,5},{0,5,4},  // bottom (y=-1, normal 0,-1,0)
        {3,6,2},{3,7,6},  // top    (y=+1, normal 0,+1,0)
        {0,4,7},{0,7,3},  // left   (x=-1, normal -1,0,0)
        {1,2,6},{1,6,5},  // right  (x=+1, normal +1,0,0)
    };
    for (auto& f : faces)
        s.add_triangle(v[f[0]], v[f[1]], v[f[2]]);

    return s;
}

int main() {
    const float W = 800.0f, H = 600.0f;

    Scene scene = make_cube();

    Camera cam;
    cam.position = {3.0f, 2.5f, 5.0f};
    cam.target   = {0, 0, 0};
    cam.fov      = 3.14159265f / 3.0f;
    Mat4 mvp = cam.mvp(W / H);

    auto lines2d = project_scene(scene, mvp, W, H);

    SvgWriter svg("output.svg", W, H);
    svg.add_lines(lines2d, "black", 1.5f);

    return 0;
}
