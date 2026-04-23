#include <iostream>
#include <cmath>
#include "lgl_math.h"
#include "scene.h"
#include "transform.h"
#include "project.h"
#include "camera.h"
#include "interval.h"
#include "geom2d.h"

static int passed = 0, failed = 0;

static void check(const char* name, bool ok) {
    if (ok) { std::cout << "  PASS  " << name << "\n"; ++passed; }
    else     { std::cout << "  FAIL  " << name << "\n"; ++failed; }
}

static bool near(float a, float b) { return std::fabs(a - b) < 1e-5f; }

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
    const float pi2 = 3.14159265f * 0.5f;
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
    const float W = 800.0f, H = 600.0f;
    Mat4 pview = make_look_at({0,0,5}, {0,0,0}, {0,1,0});
    Mat4 pproj = make_perspective(3.14159265f * 0.5f, W / H, 0.1f, 100.0f);
    Mat4 mvp   = pproj * pview;
    float sx, sy;
    bool ok = project_vertex({0,0,0}, mvp, W, H, sx, sy);
    check("origin projects ok",      ok);
    check("origin projects to cx",   near(sx, W * 0.5f));
    check("origin projects to cy",   near(sy, H * 0.5f));

    // A point behind the camera should be rejected
    bool behind = project_vertex({0,0,10}, mvp, W, H, sx, sy);
    check("behind camera rejected",  !behind);

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
    float cx, cy;
    bool hit = project_vertex({0,0,0}, cam.mvp(W/H), W, H, cx, cy);
    check("camera origin projects ok",  hit);
    check("camera origin at cx",        near(cx, W * 0.5f));
    check("camera origin at cy",        near(cy, H * 0.5f));

    // A point directly above target should appear above center (smaller y in SVG = higher)
    float ax, ay;
    project_vertex({0,1,0}, cam.mvp(W/H), W, H, ax, ay);
    check("above target is above cy",   ay < H * 0.5f);

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
        float t, s;
        bool hit = segment_intersect({0,0},{1,0}, {0.5f,-0.5f},{0.5f,0.5f}, t, s);
        check("perpendicular hit",       hit);
        check("t==0.5",                  near(t, 0.5f));
        check("s==0.5",                  near(s, 0.5f));
    }

    // Parallel segments — no intersection
    {
        float t, s;
        bool hit = segment_intersect({0,0},{1,0}, {0,1},{1,1}, t, s);
        check("parallel no hit",         !hit);
    }

    // Segments that would intersect if extended, but don't overlap
    {
        float t, s;
        bool hit = segment_intersect({0,0},{0.4f,0}, {0.5f,-0.5f},{0.5f,0.5f}, t, s);
        check("short segment no hit",    !hit);
    }

    // Point inside triangle
    Vec2 ta{0,0}, tb{1,0}, tc{0,1};
    check("inside triangle",             point_in_triangle_2d({0.25f,0.25f}, ta, tb, tc));
    check("outside triangle",           !point_in_triangle_2d({0.75f,0.75f}, ta, tb, tc));
    check("on edge counts as inside",    point_in_triangle_2d({0.5f,0.0f},   ta, tb, tc));
    check("at vertex counts as inside",  point_in_triangle_2d({0,0},         ta, tb, tc));

    std::cout << "\n" << passed << " passed, " << failed << " failed.\n";
    return failed ? 1 : 0;
}
