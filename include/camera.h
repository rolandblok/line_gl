#pragma once
#include "vec_math.h"
#include "transform.h"

enum class ProjectionMode { Perspective, Orthographic };

struct Camera {
    Vec3  position = {0, 0, 5};
    Vec3  target   = {0, 0, 0};
    Vec3  up       = {0, 1, 0};
    double fov      = 3.14159265f / 3.0f;  // 60° vertical, in radians
    double near     = 0.1f;
    double far      = 100.0f;
    ProjectionMode proj_mode   = ProjectionMode::Perspective;
    double ortho_height        = 5.0;  // half-height of the ortho view volume

    Mat4 view() const {
        return make_look_at(position, target, up);
    }

    // Projection matrix for given aspect ratio (width/height)
    Mat4 projection(double aspect) const {
        if (proj_mode == ProjectionMode::Orthographic) {
            double h = ortho_height;
            return make_orthographic(-h * aspect, h * aspect, -h, h, near, far);
        }
        return make_perspective(fov, aspect, near, far);
    }

    // Model-View-Projection matrix for given aspect ratio and optional model transform
    Mat4 mvp(double aspect, const Mat4& model = Mat4::identity()) const {
        return projection(aspect) * view() * model;
    }

    // Orbit around the target by yaw (Y axis) and pitch (X axis), in radians
    void orbit(double yaw, double pitch) {
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
    static Mat4 make_rotation_around(const Vec3& axis, double rad) {
        double c = std::cos(rad), s = std::sin(rad), t = 1.0f - c;
        double x = axis.x, y = axis.y, z = axis.z;
        Mat4 m{};
        m.m[0][0] = t*x*x + c;    m.m[1][0] = t*x*y - s*z; m.m[2][0] = t*x*z + s*y;
        m.m[0][1] = t*x*y + s*z;  m.m[1][1] = t*y*y + c;   m.m[2][1] = t*y*z - s*x;
        m.m[0][2] = t*x*z - s*y;  m.m[1][2] = t*y*z + s*x; m.m[2][2] = t*z*z + c;
        m.m[3][3] = 1.0f;
        return m;
    }
};
