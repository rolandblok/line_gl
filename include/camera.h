#pragma once
#include "lgl_math.h"
#include "transform.h"

struct Camera {
    Vec3  position = {0, 0, 5};
    Vec3  target   = {0, 0, 0};
    Vec3  up       = {0, 1, 0};
    float fov      = 3.14159265f / 3.0f;  // 60° vertical, in radians
    float near     = 0.1f;
    float far      = 100.0f;

    Mat4 view() const {
        return make_look_at(position, target, up);
    }

    Mat4 projection(float aspect) const {
        return make_perspective(fov, aspect, near, far);
    }

    Mat4 mvp(float aspect, const Mat4& model = Mat4::identity()) const {
        return projection(aspect) * view() * model;
    }

    // Orbit around the target by yaw (Y axis) and pitch (X axis), in radians
    void orbit(float yaw, float pitch) {
        Vec3 offset = position - target;

        Mat4 ry = make_rotation_y(yaw);
        Vec4 rotated = ry * Vec4(offset, 0.0f);
        offset = rotated.xyz();

        Vec3 right = offset.cross(up).normalized();
        Mat4 rx = make_rotation_around(right, pitch);
        rotated = rx * Vec4(offset, 0.0f);
        offset = rotated.xyz();

        position = target + offset;
    }

private:
    static Mat4 make_rotation_around(const Vec3& axis, float rad) {
        float c = std::cos(rad), s = std::sin(rad), t = 1.0f - c;
        float x = axis.x, y = axis.y, z = axis.z;
        Mat4 m{};
        m.m[0][0] = t*x*x + c;    m.m[1][0] = t*x*y - s*z; m.m[2][0] = t*x*z + s*y;
        m.m[0][1] = t*x*y + s*z;  m.m[1][1] = t*y*y + c;   m.m[2][1] = t*y*z - s*x;
        m.m[0][2] = t*x*z - s*y;  m.m[1][2] = t*y*z + s*x; m.m[2][2] = t*z*z + c;
        m.m[3][3] = 1.0f;
        return m;
    }
};
