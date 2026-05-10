#pragma once
#include <cmath>
#include <algorithm>
#include "vec_math.h"
#include "scene.h"

// Clips a 3D ray (origin + t*dir) against three half-spaces defined by the
// triangle edges. The line is assumed coplanar with the triangle.
// Updates t_min and t_max. Returns false if the ray is fully outside.
inline bool clip_ray_to_triangle_3d(
    const Vec3& origin, const Vec3& dir,
    const Vec3& A, const Vec3& B, const Vec3& C, const Vec3& face_normal,
    double& t_min, double& t_max)
{
    const Vec3 verts[3] = { A, B, C };
    t_min = -1e18;
    t_max =  1e18;

    for (int i = 0; i < 3; ++i) {
        const Vec3& V0 = verts[i];
        const Vec3& V1 = verts[(i + 1) % 3];
        // Inward-facing edge normal (lies in the triangle plane)
        Vec3 edge_normal = face_normal.cross(V1 - V0).normalized();
        double denom = edge_normal.dot(dir);
        double dist  = edge_normal.dot(origin - V0);
        if (std::fabs(denom) < 1e-10) {
            // Ray is parallel to this edge plane — outside if dist < 0
            if (dist < -1e-8) return false;
        } else {
            double t = -dist / denom;
            if (denom > 0) t_min = std::max(t_min, t);   // entering
            else           t_max = std::min(t_max, t);   // leaving
        }
        if (t_min > t_max + 1e-10) return false;
    }
    return t_min <= t_max + 1e-10;
}

// Adds hatch lines for all triangles in `scene` based on their shading
// relative to scene.light_direction. Parameters are read from scene.hatch.
inline void add_hatching(Scene& scene)
{
    const double max_spacing  = scene.hatch.max_spacing;
    const double min_spacing  = scene.hatch.min_spacing;
    const double shade_cutoff = scene.hatch.shade_cutoff;
    const double epsilon      = scene.hatch.epsilon;
    const color  hatch_col    = scene.hatch.hatch_col;
    Vec3 light = scene.light_direction.normalized();

    for (const auto& tri : scene.triangles) {
        Vec3 n = tri.normal();

        // Back-face cull: skip triangles facing away from the camera
        Vec3 view_vec = (scene.cam.proj_mode == ProjectionMode::Perspective)
            ? (scene.cam.position - tri.a)
            : (scene.cam.position - scene.cam.target);
        if (n.dot(view_vec) <= 0.0) continue;

        // Shade: 0 = fully dark, 1 = fully lit
        double shade = std::clamp(-n.dot(light), 0.0, 1.0);

        if (shade >= shade_cutoff) continue;  // bright enough — no hatching

        // Spacing proportional to shade: dark → dense, bright → sparse
        double spacing = min_spacing + (max_spacing - min_spacing) * shade;

        // Hatch direction: perpendicular to light projected onto face plane,
        // lying within the face.
        Vec3 light_proj = (light - n * n.dot(light));
        if (light_proj.length() < 1e-8)
            light_proj = n.cross(Vec3{0,1,0});  // degenerate: light head-on
        Vec3 hatch_dir = light_proj.normalized();
        Vec3 sweep_dir = n.cross(hatch_dir).normalized();

        // Compute extent of triangle along sweep_dir
        const Vec3 verts[3] = { tri.a, tri.b, tri.c };
        double s_min =  1e18, s_max = -1e18;
        for (const auto& v : verts) {
            double s = sweep_dir.dot(v);
            s_min = std::min(s_min, s);
            s_max = std::max(s_max, s);
        }

        // Snap start to a grid aligned to origin so different triangles align
        double start = std::ceil(s_min / spacing) * spacing;

        for (double s = start; s <= s_max + 1e-9; s += spacing) {
            // Point on the hatch line in 3D
            Vec3 origin = sweep_dir * s;
            // Project origin onto the face plane
            Vec3 centroid = (tri.a + tri.b + tri.c) / 3.0;
            double along_n = n.dot(origin - centroid);
            origin = origin - n * along_n;

            double t0, t1;
            if (!clip_ray_to_triangle_3d(origin, hatch_dir,
                                         tri.a, tri.b, tri.c, n, t0, t1))
                continue;

            if (t1 - t0 < 1e-9) continue;

            Vec3 P0 = origin + hatch_dir * t0 + n * epsilon;
            Vec3 P1 = origin + hatch_dir * t1 + n * epsilon;
            scene.add_line(P0, P1, hatch_col, tri.id);
        }
    }
}
