#pragma once
#include <cmath>
#include "vec_math.h"

inline Mat4 make_translation(const Vec3& t) {
    Mat4 m = Mat4::identity();
    m.m[3][0] = t.x;
    m.m[3][1] = t.y;
    m.m[3][2] = t.z;
    return m;
}

inline Mat4 make_scale(const Vec3& s) {
    Mat4 m = Mat4::identity();
    m.m[0][0] = s.x;
    m.m[1][1] = s.y;
    m.m[2][2] = s.z;
    return m;
}

inline Mat4 make_rotation_x(double rad) {
    Mat4 m = Mat4::identity();
    double c = std::cos(rad), s = std::sin(rad);
    m.m[1][1] =  c;  m.m[2][1] = -s;
    m.m[1][2] =  s;  m.m[2][2] =  c;
    return m;
}

inline Mat4 make_rotation_y(double rad) {
    Mat4 m = Mat4::identity();
    double c = std::cos(rad), s = std::sin(rad);
    m.m[0][0] =  c;  m.m[2][0] =  s;
    m.m[0][2] = -s;  m.m[2][2] =  c;
    return m;
}

inline Mat4 make_rotation_z(double rad) {
    Mat4 m = Mat4::identity();
    double c = std::cos(rad), s = std::sin(rad);
    m.m[0][0] =  c;  m.m[1][0] = -s;
    m.m[0][1] =  s;  m.m[1][1] =  c;
    return m;
}

// fov_y in radians, aspect = width/height, OpenGL NDC convention (z in [-1,1])
inline Mat4 make_perspective(double fov_y, double aspect, double near, double far) {
    Mat4 m{};
    double f = 1.0f / std::tan(fov_y * 0.5f);
    m.m[0][0] = f / aspect;
    m.m[1][1] = f;
    m.m[2][2] = (far + near) / (near - far);
    m.m[2][3] = -1.0f;
    m.m[3][2] = (2.0f * far * near) / (near - far);
    return m;
}

// View matrix: world → camera space
inline Mat4 make_look_at(const Vec3& eye, const Vec3& center, const Vec3& up) {
    Vec3 f = (center - eye).normalized();
    Vec3 r = f.cross(up).normalized();
    Vec3 u = r.cross(f);

    Mat4 m{};
    m.m[0][0] =  r.x;  m.m[1][0] =  r.y;  m.m[2][0] =  r.z;  m.m[3][0] = -r.dot(eye);
    m.m[0][1] =  u.x;  m.m[1][1] =  u.y;  m.m[2][1] =  u.z;  m.m[3][1] = -u.dot(eye);
    m.m[0][2] = -f.x;  m.m[1][2] = -f.y;  m.m[2][2] = -f.z;  m.m[3][2] =  f.dot(eye);
    m.m[3][3] =  1.0f;
    return m;
}
