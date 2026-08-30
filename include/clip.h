#pragma once
#include <vector>
#include "primitives.h"

// Clips projected 2D segments to the output canvas [0,w] x [0,h] (Liang-Barsky).
//
// Scenes may deliberately extend past the frame - a city that fills the page,
// for instance - and everything outside is invisible anyway. Without this the
// off-canvas lines still land in the SVG, where downstream tools that scale to
// the drawing's bounding box (svg_to_gcode.py) would zoom the plot back out.
//
// Segment endpoints carry view-space depth in .z; it is interpolated along with
// the position so clipped lines keep a sensible depth value.
inline std::vector<Line3D> clip_to_canvas(const std::vector<Line3D>& lines,
                                          double w, double h) {
    std::vector<Line3D> out;
    out.reserve(lines.size());

    for (const auto& l : lines) {
        double dx = l.b.x - l.a.x, dy = l.b.y - l.a.y;
        double t0 = 0.0, t1 = 1.0;
        const double p[4] = {-dx, dx, -dy, dy};
        const double q[4] = {l.a.x - 0.0, w - l.a.x, l.a.y - 0.0, h - l.a.y};

        bool visible = true;
        for (int i = 0; i < 4 && visible; ++i) {
            if (p[i] == 0.0) {
                if (q[i] < 0.0) visible = false;   // parallel and outside
                continue;
            }
            double t = q[i] / p[i];
            if (p[i] < 0.0) { if (t > t1) visible = false; else if (t > t0) t0 = t; }
            else            { if (t < t0) visible = false; else if (t < t1) t1 = t; }
        }
        if (!visible) continue;

        Line3D c = l;
        if (t0 > 0.0) c.a = l.lerp(t0);
        if (t1 < 1.0) c.b = l.lerp(t1);
        out.push_back(c);
    }
    return out;
}
