#pragma once
#include <vector>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <cstdint>
#include <cstdio>
#include <algorithm>
#include <array>
#include <unordered_set>
#include "vec_math.h"
#include "primitives.h"
#include "camera.h"
#include "rapidjson/document.h"
#include "rapidjson/istreamwrapper.h"


struct HatchParams {
    double max_spacing  = 0.2;
    double min_spacing  = 0.05;
    double shade_cutoff = 0.95;
    double epsilon      = 0.001;
    color  hatch_col    = color{180, 180, 180};
};

struct Scene {
    std::vector<Line3D>     lines;
    std::vector<Triangle3D> triangles;
    Vec3                    light_direction = {0.0, -1.0, -1.0};  // world-space, not normalised
    Camera                  cam;
    bool                    show_intersection_lines = true;  // if false, skip add_triangle_intersection_lines
    HatchParams             hatch;

    void add_line(const Vec3& a, const Vec3& b, color col = color{}, int parent_tri = -1) {
        lines.push_back({a, b, col});
        lines.back().parent_tri = parent_tri;
    }
    void add_triangle(const Vec3& a, const Vec3& b, const Vec3& c) {
        triangles.push_back({a, b, c});
        triangles.back().id = (int)triangles.size() - 1;
    }

    // Adds an axis-aligned box with one corner at `origin` and given width/height/depth.
    // show_edges[0..3]  = bottom edges: v0-v1, v1-v2, v2-v3, v3-v0
    // show_edges[4..7]  = top edges:    v4-v5, v5-v6, v6-v7, v7-v4
    // show_edges[8..11] = vertical:     v0-v4, v1-v5, v2-v6, v3-v7
    // group_id: when >= 0, overrides the automatic per-primitive group with a
    //           caller-supplied value; all primitives sharing the same group_id
    //           will not generate triangle-intersection lines between them.
    void add_block(const Vec3& origin, double dx, double dy, double dz,
                   color col = color{}, bool show_edges[12] = nullptr, int group_id = -1) {
        Vec3 v[8] = {
            origin,
            origin + Vec3{dx,  0,  0},
            origin + Vec3{dx, dy,  0},
            origin + Vec3{ 0, dy,  0},
            origin + Vec3{ 0,  0, dz},
            origin + Vec3{dx,  0, dz},
            origin + Vec3{dx, dy, dz},
            origin + Vec3{ 0, dy, dz},
        };

        // Add triangles first so their IDs are known when we set parent_tri on edges.
        // Faces as quads {f0,f1,f2,f3}:
        //   triA = (f0,f1,f2) owns outer edges f0-f1 and f1-f2
        //   triB = (f0,f2,f3) owns outer edges f2-f3 and f3-f0
        int base = (int)triangles.size();
        int faces[6][4] = {
            {0,3,2,1}, {4,5,6,7},
            {0,1,5,4}, {2,3,7,6},
            {0,4,7,3}, {1,2,6,5},
        };
        for (auto& f : faces) {
            add_triangle(v[f[0]], v[f[1]], v[f[2]]);  // triA
            add_triangle(v[f[0]], v[f[2]], v[f[3]]);  // triB
        }
        // Tag all 12 triangles with a shared group so intra-block
        // intersection lines are suppressed.
        int gid = (group_id >= 0) ? group_id : base;
        for (int i = base; i < (int)triangles.size(); ++i)
            triangles[i].group_id = gid;

        // Edges with parent_tri set to one of the triangles they lie on.
        auto e = [&](int i) { return !show_edges || show_edges[i]; };
        // bottom edges (0-3)
        if (e(0)) add_line(v[0], v[1], col, base+1);
        if (e(1)) add_line(v[1], v[2], col, base+1);
        if (e(2)) add_line(v[2], v[3], col, base+0);
        if (e(3)) add_line(v[3], v[0], col, base+0);
        // top edges (4-7)
        if (e(4)) add_line(v[4], v[5], col, base+2);
        if (e(5)) add_line(v[5], v[6], col, base+2);
        if (e(6)) add_line(v[6], v[7], col, base+3);
        if (e(7)) add_line(v[7], v[4], col, base+3);
        // vertical edges (8-11)
        if (e(8))  add_line(v[0], v[4], col, base+5);
        if (e(9))  add_line(v[1], v[5], col, base+4);
        if (e(10)) add_line(v[2], v[6], col, base+7);
        if (e(11)) add_line(v[3], v[7], col, base+6);
    }

// Adds a quad defined by 4 coplanar points, splitting it into two triangles.
    // triA = (a,b,c) owns outer edges a-b and b-c.
    // triB = (a,c,d) owns outer edges c-d and d-a.
    // show_edges[0..3] = ab, bc, cd, da
    void add_rectangle(const Vec3& a, const Vec3& b, const Vec3& c, const Vec3& d,
                       color col = color{}, bool show_edges[4] = nullptr, int group_id = -1) {
        int base = (int)triangles.size();
        add_triangle(a, b, c);  // triA = base+0
        add_triangle(a, c, d);  // triB = base+1
        int gid = (group_id >= 0) ? group_id : base;
        triangles[base].group_id = triangles[base+1].group_id = gid;
        bool defaults[4] = {true, true, true, true};
        bool* e = show_edges ? show_edges : defaults;
        if (e[0]) add_line(a, b, col, base+0);
        if (e[1]) add_line(b, c, col, base+0);
        if (e[2]) add_line(c, d, col, base+1);
        if (e[3]) add_line(d, a, col, base+1);
    }

    // Loads lines, triangles, blocks, rectangles and light_direction from a JSON file.
    // Format:
    //   { "light_direction": [x,y,z],
    //     "lines":      [{ "a":[x,y,z], "b":[x,y,z], "col":[r,g,b] }, ...],
    //     "triangles":  [{ "a":[x,y,z], "b":[x,y,z], "c":[x,y,z]  }, ...],
    //     "rectangles": [{ "a":[x,y,z], "b":[x,y,z], "c":[x,y,z], "d":[x,y,z], "col":[r,g,b], "show_edges":[1,1,1,1] }, ...],
    //     "blocks":     [{ "origin":[x,y,z], "dx":n, "dy":n, "dz":n, "col":[r,g,b] }, ...],
    //     "show_intersection_lines": true|false }
    void load_json(const std::string& path) {
        std::ifstream f(path);
        if (!f) throw std::runtime_error("Cannot open scene file: " + path);

        rapidjson::IStreamWrapper isw(f);
        rapidjson::Document doc;
        doc.ParseStream(isw);
        if (doc.HasParseError())
            throw std::runtime_error("JSON parse error in: " + path);

        auto read_v3 = [](const rapidjson::Value& v) -> Vec3 {
            return { v[0].GetDouble(), v[1].GetDouble(), v[2].GetDouble() };
        };
        auto read_col = [](const rapidjson::Value& v) -> color {
            return { (uint8_t)v[0].GetInt(), (uint8_t)v[1].GetInt(), (uint8_t)v[2].GetInt() };
        };

        if (doc.HasMember("show_intersection_lines"))
            show_intersection_lines = doc["show_intersection_lines"].GetBool();

        if (doc.HasMember("hatching")) {
            const auto& h = doc["hatching"];
            if (h.HasMember("max_spacing"))  hatch.max_spacing  = h["max_spacing"].GetDouble();
            if (h.HasMember("min_spacing"))  hatch.min_spacing  = h["min_spacing"].GetDouble();
            if (h.HasMember("shade_cutoff")) hatch.shade_cutoff = h["shade_cutoff"].GetDouble();
            if (h.HasMember("epsilon"))      hatch.epsilon      = h["epsilon"].GetDouble();
            if (h.HasMember("color"))        hatch.hatch_col    = read_col(h["color"]);
        }

        if (doc.HasMember("light_direction"))
            light_direction = read_v3(doc["light_direction"]);

        if (doc.HasMember("camera")) {
            const auto& c = doc["camera"];
            if (c.HasMember("position"))     cam.position     = read_v3(c["position"]);
            if (c.HasMember("target"))       cam.target       = read_v3(c["target"]);
            if (c.HasMember("up"))           cam.up           = read_v3(c["up"]);
            if (c.HasMember("fov"))          cam.fov          = c["fov"].GetDouble();
            if (c.HasMember("near"))         cam.near         = c["near"].GetDouble();
            if (c.HasMember("far"))          cam.far          = c["far"].GetDouble();
            if (c.HasMember("ortho_height")) cam.ortho_height = c["ortho_height"].GetDouble();
            if (c.HasMember("projection")) {
                std::string proj = c["projection"].GetString();
                cam.proj_mode = (proj == "orthographic") ? ProjectionMode::Orthographic
                                                         : ProjectionMode::Perspective;
            }
        }

        if (doc.HasMember("lines")) {
            for (const auto& obj : doc["lines"].GetArray()) {
                Vec3 a{}, b{}; color col{};
                if (obj.HasMember("a"))   a   = read_v3(obj["a"]);
                if (obj.HasMember("b"))   b   = read_v3(obj["b"]);
                if (obj.HasMember("col")) col = read_col(obj["col"]);
                add_line(a, b, col);
            }
        }

        if (doc.HasMember("triangles")) {
            for (const auto& obj : doc["triangles"].GetArray()) {
                Vec3 a{}, b{}, c{};
                if (obj.HasMember("a")) a = read_v3(obj["a"]);
                if (obj.HasMember("b")) b = read_v3(obj["b"]);
                if (obj.HasMember("c")) c = read_v3(obj["c"]);
                add_triangle(a, b, c);
            }
        }

        if (doc.HasMember("rectangles")) {
            for (const auto& obj : doc["rectangles"].GetArray()) {
                Vec3 a{}, b{}, c{}, d{}; color col{};
                bool se[4] = {true, true, true, true};
                bool has_show_edges = false;
                if (obj.HasMember("a"))   a   = read_v3(obj["a"]);
                if (obj.HasMember("b"))   b   = read_v3(obj["b"]);
                if (obj.HasMember("c"))   c   = read_v3(obj["c"]);
                if (obj.HasMember("d"))   d   = read_v3(obj["d"]);
                if (obj.HasMember("col")) col = read_col(obj["col"]);
                if (obj.HasMember("show_edges")) {
                    const auto& arr = obj["show_edges"].GetArray();
                    for (int i = 0; i < 4; ++i) se[i] = (arr[i].GetDouble() != 0.0);
                    has_show_edges = true;
                }
                // if no show_edges key, fall back to show_intersection_lines
                if (!has_show_edges)
                    for (int i = 0; i < 4; ++i) se[i] = show_intersection_lines;
                int gid = obj.HasMember("group_id") ? obj["group_id"].GetInt() : -1;
                add_rectangle(a, b, c, d, col, se, gid);
            }
        }

        if (doc.HasMember("blocks")) {
            for (const auto& obj : doc["blocks"].GetArray()) {
                Vec3 origin{}; double dx{}, dy{}, dz{}; color col{};
                bool se[12] = {true,true,true,true,true,true,true,true,true,true,true,true};
                bool has_show_edges = false;
                if (obj.HasMember("origin")) origin = read_v3(obj["origin"]);
                if (obj.HasMember("dx"))     dx     = obj["dx"].GetDouble();
                if (obj.HasMember("dy"))     dy     = obj["dy"].GetDouble();
                if (obj.HasMember("dz"))     dz     = obj["dz"].GetDouble();
                if (obj.HasMember("col"))    col    = read_col(obj["col"]);
                if (obj.HasMember("show_edges")) {
                    const auto& arr = obj["show_edges"].GetArray();
                    for (int i = 0; i < 12; ++i) se[i] = (arr[i].GetDouble() != 0.0);
                    has_show_edges = true;
                }
                int gid = obj.HasMember("group_id") ? obj["group_id"].GetInt() : -1;
                add_block(origin, dx, dy, dz, col, has_show_edges ? se : nullptr, gid);
            }
        }
        remove_duplicates();
    }

    // Removes duplicate lines (same endpoints in either order, same colour) and
    // duplicate triangles (same three vertices in any order).
    void remove_duplicates() {
        const size_t orig_lines = lines.size();
        const size_t orig_tris  = triangles.size();
        // -- lines --------------------------------------------------------
        // Key: sort the two endpoint coords so A-B == B-A, then pack with colour.
        auto line_key = [](const Line3D& l) -> std::tuple<
                double,double,double,double,double,double,uint8_t,uint8_t,uint8_t> {
            double ax = l.a.x, ay = l.a.y, az = l.a.z;
            double bx = l.b.x, by = l.b.y, bz = l.b.z;
            if (std::tie(ax,ay,az) > std::tie(bx,by,bz)) {
                std::swap(ax,bx); std::swap(ay,by); std::swap(az,bz);
            }
            return {ax,ay,az,bx,by,bz,(double)l.col.x,(double)l.col.y,(double)l.col.z};
        };
        std::unordered_set<size_t> seen_lines;
        std::vector<Line3D> unique_lines;
        unique_lines.reserve(lines.size());
        std::hash<double> dh;
        for (const auto& l : lines) {
            auto k = line_key(l);
            // simple hash combine
            size_t h = 0;
            auto mix = [&](size_t v){ h ^= v + 0x9e3779b9 + (h<<6) + (h>>2); };
            mix(dh(std::get<0>(k))); mix(dh(std::get<1>(k))); mix(dh(std::get<2>(k)));
            mix(dh(std::get<3>(k))); mix(dh(std::get<4>(k))); mix(dh(std::get<5>(k)));
            mix(dh(std::get<6>(k))); mix(dh(std::get<7>(k))); mix(dh(std::get<8>(k)));
            if (seen_lines.insert(h).second)
                unique_lines.push_back(l);
        }
        lines = std::move(unique_lines);

        // -- triangles ----------------------------------------------------
        // Key: sort the three vertices lexicographically then hash.
        auto tri_key = [](const Triangle3D& t) -> std::array<double,9> {
            std::array<std::array<double,3>,3> verts = {{
                {t.a.x, t.a.y, t.a.z},
                {t.b.x, t.b.y, t.b.z},
                {t.c.x, t.c.y, t.c.z},
            }};
            std::sort(verts.begin(), verts.end());
            return {verts[0][0],verts[0][1],verts[0][2],
                    verts[1][0],verts[1][1],verts[1][2],
                    verts[2][0],verts[2][1],verts[2][2]};
        };
        std::unordered_set<size_t> seen_tris;
        std::vector<Triangle3D> unique_tris;
        unique_tris.reserve(triangles.size());
        for (const auto& t : triangles) {
            auto k = tri_key(t);
            size_t h = 0;
            auto mix = [&](size_t v){ h ^= v + 0x9e3779b9 + (h<<6) + (h>>2); };
            for (double v : k) mix(dh(v));
            if (seen_tris.insert(h).second)
                unique_tris.push_back(t);
        }
        triangles = std::move(unique_tris);
        // Re-assign IDs after dedup since some entries may have been removed.
        for (int i = 0; i < (int)triangles.size(); ++i)
            triangles[i].id = i;

        const size_t dup_lines = orig_lines - lines.size();
        const size_t dup_tris  = orig_tris  - triangles.size();
        if (dup_lines || dup_tris)
            std::printf("remove_duplicates: removed %zu duplicate line(s), %zu duplicate triangle(s)\n",
                        dup_lines, dup_tris);
    }
};
