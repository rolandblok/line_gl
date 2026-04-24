#include <iostream>
#include <cmath>
#include "vec_math.h"
#include "scene.h"
#include "transform.h"
#include "project.h"
#include "camera.h"
#include "interval.h"

#include "depth.h"
#include "occlusion.h"
#include "hidden_line.h"

static int passed = 0, failed = 0;

static void check(const char* name, bool ok) {
    if (ok) { std::cout << "  PASS  " << name << "\n"; ++passed; }
    else     { std::cout << "  FAIL  " << name << "\n"; ++failed; }
}

static bool near(double a, double b) { return std::fabs(a - b) < 1e-5f; }

int main() {
    std::cout << "=== Math ===\n";

    Vec3 a{1,0,0}, b{0,1,0};
    Vec3 c = a.cross(b);
    check("cross(x,y)==z",  near(c.x,0) && near(c.y,0) && near(c.z,1));
    check("dot(x,y)==0",    near(a.dot(b), 0));
    check("length(x)==1",   near(a.length(), 1));
    check("normalized",     near(Vec3{3,0,0}.normalized().x, 1));

    Mat4 I = Mat4::identity();
    Vec4 v{1,2,3,1};
    Vec4 r = I * v;
    check("identity*v==v",  near(r.x,1) && near(r.y,2) && near(r.z,3) && near(r.w,1));

    Mat4 A = Mat4::identity(); A.m[3][0] = 5.0f; // translate x+5
    Mat4 B = Mat4::identity(); B.m[3][1] = 3.0f; // translate y+3
    Vec4 p{0,0,0,1};
    Vec4 r1 = (A * B) * p;
    Vec4 r2 = A * (B * p);
    check("(A*B)*p x==5",   near(r1.x, 5) && near(r1.y, 3));
    check("A*(B*p) x==5",   near(r2.x, 5) && near(r2.y, 3));

    Mat4 T = A.transposed();
    check("transpose",      near(T.m[0][3], 5.0f));

    std::cout << "\n=== Scene ===\n";

    Triangle3D tri{{1,0,0},{0,1,0},{0,0,0}};
    Vec3 n = tri.normal();
    check("triangle normal z==1", near(n.x, 0) && near(n.y, 0) && near(n.z, 1));

    Scene scene;
    scene.add_line({0,0,0}, {1,1,1});
    scene.add_triangle({1,0,0}, {0,1,0}, {0,0,0});
    check("scene line count",     scene.lines.size() == 1);
    check("scene triangle count", scene.triangles.size() == 1);

    std::cout << "\n=== Transform ===\n";

    // Translation
    Vec4 origin{0,0,0,1};
    Vec4 t = make_translation({1,2,3}) * origin;
    check("translation",        near(t.x,1) && near(t.y,2) && near(t.z,3));

    // Scale
    Vec4 s = make_scale({2,3,4}) * Vec4{1,1,1,1};
    check("scale",              near(s.x,2) && near(s.y,3) && near(s.z,4));

    // Rotation X by 90°: (0,1,0) → (0,0,1)
    const double pi2 = 3.14159265f * 0.5f;
    Vec4 rx = make_rotation_x(pi2) * Vec4{0,1,0,0};
    check("rotation_x 90°",    near(rx.x,0) && near(rx.y,0) && near(rx.z,1));

    // Rotation Y by 90°: (1,0,0) → (0,0,-1)
    Vec4 ry = make_rotation_y(pi2) * Vec4{1,0,0,0};
    check("rotation_y 90°",    near(ry.x,0) && near(ry.y,0) && near(ry.z,-1));

    // Rotation Z by 90°: (1,0,0) → (0,1,0)
    Vec4 rz = make_rotation_z(pi2) * Vec4{1,0,0,0};
    check("rotation_z 90°",    near(rz.x,0) && near(rz.y,1) && near(rz.z,0));

    // Look-at: eye at (0,0,5) looking at origin → origin maps to (0,0,-5) in camera space
    Mat4 view = make_look_at({0,0,5}, {0,0,0}, {0,1,0});
    Vec4 view_origin = view * Vec4{0,0,0,1};
    check("look_at origin z",  near(view_origin.x,0) && near(view_origin.y,0) && near(view_origin.z,-5));

    // Perspective: w component of a point at z=-near should be near
    Mat4 proj = make_perspective(3.14159265f * 0.5f, 1.0f, 1.0f, 100.0f);
    Vec4 clip  = proj * Vec4{0,0,-1,1};
    check("perspective w==1",  near(clip.w, 1.0f));

    std::cout << "\n=== Projection ===\n";

    // Origin through a camera at (0,0,5) looking at origin should land at screen center
    const double W = 800.0f, H = 600.0f;
    Mat4 pview = make_look_at({0,0,5}, {0,0,0}, {0,1,0});
    Mat4 pproj = make_perspective(3.14159265f * 0.5f, W / H, 0.1f, 100.0f);
    Mat4 mvp   = pproj * pview;
    auto origin_p = project_vertex({0,0,0}, mvp, W, H);
    check("origin projects ok",      origin_p.has_value());
    check("origin projects to cx",   near(origin_p->x, W * 0.5f));
    check("origin projects to cy",   near(origin_p->y, H * 0.5f));

    // A point behind the camera should be rejected
    auto behind = project_vertex({0,0,10}, mvp, W, H);
    check("behind camera rejected",  !behind.has_value());

    // project_scene: 2 lines, both in front → 2 Line2D results
    Scene ps;
    ps.add_line({-1,0,-3}, {1,0,-3});
    ps.add_line({0,-1,-3}, {0,1,-3});
    Mat4 ident_mvp = make_perspective(3.14159265f * 0.5f, 1.0f, 0.1f, 100.0f);
    auto lines2d = project_scene(ps, ident_mvp, W, H);
    check("project_scene line count", lines2d.size() == 2);

    std::cout << "\n=== Camera ===\n";

    // Default camera at (0,0,5) looking at origin: origin should hit screen center
    Camera cam;
    auto hit = project_vertex({0,0,0}, cam.mvp(W/H), W, H);
    check("camera origin projects ok",  hit.has_value());
    check("camera origin at cx",        near(hit->x, W * 0.5f));
    check("camera origin at cy",        near(hit->y, H * 0.5f));

    // A point directly above target should appear above center (smaller y in SVG = higher)
    auto above = project_vertex({0,1,0}, cam.mvp(W/H), W, H);
    check("above target is above cy",   above && above->y < H * 0.5f);

    // Orbit 180° in yaw should flip the camera to the other side of the target
    Camera cam2;
    cam2.position = {0, 0, 5};
    cam2.orbit(3.14159265f, 0.0f);
    check("orbit 180° flips z",        cam2.position.z < 0.0f);

    std::cout << "\n=== IntervalSet ===\n";

    // Starts as [0,1]
    IntervalSet iv;
    check("initial one interval",   iv.intervals().size() == 1);

    // Subtract middle [0.3, 0.7] → [0,0.3] and [0.7,1]
    iv.subtract(0.3f, 0.7f);
    check("subtract middle: 2 intervals",  iv.intervals().size() == 2);
    check("left lo==0",    near(iv.intervals()[0].lo, 0.0f));
    check("left hi==0.3",  near(iv.intervals()[0].hi, 0.3f));
    check("right lo==0.7", near(iv.intervals()[1].lo, 0.7f));
    check("right hi==1",   near(iv.intervals()[1].hi, 1.0f));

    // Subtract [0, 0.15] → removes left piece partly → [0.15,0.3] and [0.7,1]
    iv.subtract(0.0f, 0.15f);
    check("subtract left: still 2",  iv.intervals().size() == 2);
    check("new left lo==0.15", near(iv.intervals()[0].lo, 0.15f));

    // Subtract entire remaining range → empty
    iv.subtract(0.0f, 1.0f);
    check("fully subtracted: empty", iv.empty());

    // Non-overlapping subtract leaves interval intact
    IntervalSet iv2;
    iv2.subtract(1.5f, 2.0f);  // outside [0,1]
    check("non-overlapping subtract: unchanged", iv2.intervals().size() == 1);

    std::cout << "\n=== Geom2D ===\n";

    // Perpendicular segments crossing at (0.5, 0): t=0.5, s=0.5
    {
        double t, s;
        bool hit = segment_intersect_2D({0,0},{1,0}, {0.5,-0.5},{0.5,0.5}, t, s);
        check("perpendicular hit",       hit);
        check("t==0.5",                  near(t, 0.5));
        check("s==0.5",                  near(s, 0.5));
    }

    // Parallel segments — no intersection
    {
        double t, s;
        bool hit = segment_intersect_2D({0,0},{1,0}, {0,1},{1,1}, t, s);
        check("parallel no hit",         !hit);
    }

    // Segments that would intersect if extended, but don't overlap
    {
        double t, s;
        bool hit = segment_intersect_2D({0,0},{0.4,0}, {0.5,-0.5},{0.5,0.5}, t, s);
        check("short segment no hit",    !hit);
    }

    // Point inside triangle
    Vec3 ta{0,0}, tb{1,0}, tc{0,1};
    check("inside triangle",             point_in_triangle_2D({0.25,0.25}, ta, tb, tc));
    check("outside triangle",           !point_in_triangle_2D({0.75,0.75}, ta, tb, tc));
    check("on edge counts as inside",    point_in_triangle_2D({0.5,0.0},   ta, tb, tc));
    check("at vertex counts as inside",  point_in_triangle_2D({0,0},       ta, tb, tc));

    std::cout << "\n=== Depth ===\n";

    // Camera at (0,0,5) looking at origin, point at origin
    Camera dcam;
    Mat4 dmvp = dcam.mvp(1.0f);

    // project_vertex z = NDC depth, in (-1, 1) for points inside frustum
    auto pv0 = project_vertex({0,0,0}, dmvp, 1.0, 1.0);
    check("origin depth in NDC range", pv0 && pv0->z > -1.0 && pv0->z < 1.0);

    // Point behind camera returns nullopt
    auto pv_behind = project_vertex({0,0,10}, dmvp, 1.0, 1.0);
    check("behind camera no depth",    !pv_behind.has_value());

    // depth interpolation: z lerps linearly between projected endpoints
    auto pv_start = project_vertex({0,0,0},  dmvp, 1.0, 1.0);
    auto pv_end   = project_vertex({0,0,-2}, dmvp, 1.0, 1.0);
    double dt = pv_start->z + (pv_end->z - pv_start->z) * 0.5;
    check("depth interpolation at t=0.5", near(dt, (pv_start->z + pv_end->z) * 0.5));

    // barycentric_2D: centroid has coords (1/3, 1/3, 1/3)
    Vec3 ba{0,0}, bb{1,0}, bc{0,1};
    Vec3 centroid{1.0/3.0, 1.0/3.0};
    double bu, bv, bw;
    bool bary_ok = barycentric_2D(centroid, ba, bb, bc, bu, bv, bw);
    check("barycentric centroid ok",   bary_ok);
    check("barycentric u==1/3",        near(bu, 1.0/3.0));
    check("barycentric v==1/3",        near(bv, 1.0/3.0));
    check("barycentric w==1/3",        near(bw, 1.0/3.0));

    // triangle_depth_at: at vertex a the depth should equal da
    double tri_d = triangle_depth_at(ba, Vec3{ba.x, ba.y, 0.2}, Vec3{bb.x, bb.y, 0.5}, Vec3{bc.x, bc.y, 0.8});
    check("depth at vertex a == da",   near(tri_d, 0.2));

    std::cout << "\n=== Occlusion ===\n";

    // Setup: camera at (0,0,5) looking at origin, 800x600 viewport
    const double OW = 800.0f, OH = 600.0f;
    Camera ocam;
    Mat4 omvp = ocam.mvp(OW / OH);

    // Large triangle at z=0 (closer to camera than the line below)
    Triangle3D big_tri{{-5,-5,0},{5,-5,0},{0,5,0}};

    // Line at z=-2 (behind the triangle) passing through the triangle center
    Vec3 LP{-1, 0, -2}, LQ{1, 0, -2};
    Line3D line_PQ{LP, LQ};
    auto occ = triangle_occlusion(line_PQ, big_tri, omvp, OW, OH);
    check("behind triangle: occluded",          !occ.empty());

    // Same line but now the triangle is at z=-4 (behind the line) — no occlusion
    Triangle3D far_tri{{-5,-5,-4},{5,-5,-4},{0,5,-4}};
    auto occ2 = triangle_occlusion(line_PQ, far_tri, omvp, OW, OH);
    check("triangle behind line: not occluded", occ2.empty());

    // Line entirely to the side of the big triangle — no occlusion
    Vec3 SP{-10, 0, -2}, SQ{-8, 0, -2};
    Line3D line_SQ{SP, SQ};
    auto occ3 = triangle_occlusion(line_SQ, big_tri, omvp, OW, OH);
    check("line beside triangle: not occluded", occ3.empty());

    // Partially occluded: line crosses triangle boundary
    Vec3 HP{-10, 0, -2}, HQ{0, 0, -2};  // starts outside, ends at center
    Line3D line_HQ{HP, HQ};
    auto occ4 = triangle_occlusion(line_HQ, big_tri, omvp, OW, OH);
    check("partial occlusion: interval found",  !occ4.empty());
    if (!occ4.empty()) {
        check("partial: t0 > 0",  occ4[0].t0 > 0.0f);
        check("partial: t1 == 1", near(occ4[0].t1, 1.0f));
    }

    std::cout << "\n=== Hidden Line Removal ===\n";

    const double HW = 800.0f, HH = 600.0f;
    Camera hcam;
    Mat4 hmvp = hcam.mvp(HW / HH);

    // Scene: one line behind a large triangle that fully covers it
    Scene hs;
    hs.add_line({-1, 0, -2}, {1, 0, -2});
    hs.add_triangle({-5,-5,0},{5,-5,0},{0,5,0});

    auto fully_hidden = hidden_line_removal(hs, hmvp, HW, HH);
    check("fully hidden: no segments",  fully_hidden.empty());

    // Scene: one line in front of a triangle — fully visible
    Scene hs2;
    hs2.add_line({-1, 0, 2}, {1, 0, 2});
    hs2.add_triangle({-5,-5,0},{5,-5,0},{0,5,0});

    auto fully_visible = hidden_line_removal(hs2, hmvp, HW, HH);
    check("fully visible: one segment", fully_visible.size() == 1);

    // Scene: no triangles — all lines pass through unchanged
    Scene hs3;
    hs3.add_line({-1, 0, 0}, {1, 0, 0});
    hs3.add_line({0, -1, 0}, {0, 1, 0});
    auto no_occluders = hidden_line_removal(hs3, hmvp, HW, HH);
    check("no occluders: 2 segments",   no_occluders.size() == 2);

    std::cout << "\n" << passed << " passed, " << failed << " failed.\n";
    return failed ? 1 : 0;
}
