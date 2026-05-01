#pragma once
#include <vector>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <functional>
#include <cctype>
#include <cstdint>
#include "vec_math.h"
#include "primitives.h"
#include "camera.h"


struct Scene {
    std::vector<Line3D>     lines;
    std::vector<Triangle3D> triangles;
    Vec3                    light_direction = {0.0, -1.0, -1.0};  // world-space, not normalised
    Camera                  cam;

    void add_line(const Vec3& a, const Vec3& b, color col = color{}, int parent_tri = -1) {
        lines.push_back({a, b, col});
        lines.back().parent_tri = parent_tri;
    }
    void add_triangle(const Vec3& a, const Vec3& b, const Vec3& c) {
        triangles.push_back({a, b, c});
        triangles.back().id = (int)triangles.size() - 1;
    }

    // Adds an axis-aligned box with one corner at `origin` and given width/height/depth.
    void add_block(const Vec3& origin, double dx, double dy, double dz,
                   color col = color{}) {
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

        // Edges with parent_tri set to one of the triangles they lie on.
        // face 0 ({0,3,2,1}): triA=base+0 owns {0,3},{2,3}; triB=base+1 owns {1,2},{0,1}
        add_line(v[0], v[1], col, base+1);
        add_line(v[1], v[2], col, base+1);
        add_line(v[2], v[3], col, base+0);
        add_line(v[3], v[0], col, base+0);
        // face 1 ({4,5,6,7}): triA=base+2 owns {4,5},{5,6}; triB=base+3 owns {6,7},{7,4}
        add_line(v[4], v[5], col, base+2);
        add_line(v[5], v[6], col, base+2);
        add_line(v[6], v[7], col, base+3);
        add_line(v[7], v[4], col, base+3);
        // face 2 ({0,1,5,4}): triA=base+4 owns {1,5}; triB=base+5 owns {0,4}
        add_line(v[1], v[5], col, base+4);
        add_line(v[0], v[4], col, base+5);
        // face 3 ({2,3,7,6}): triA=base+6 owns {3,7}; triB=base+7 owns {2,6}
        add_line(v[3], v[7], col, base+6);
        add_line(v[2], v[6], col, base+7);
    }

    // Loads lines, triangles, blocks and light_direction from a JSON file.
    // Format:
    //   { "light_direction": [x,y,z],
    //     "lines":     [{ "a":[x,y,z], "b":[x,y,z], "col":[r,g,b] }, ...],
    //     "triangles": [{ "a":[x,y,z], "b":[x,y,z], "c":[x,y,z]  }, ...],
    //     "blocks":    [{ "origin":[x,y,z], "dx":n, "dy":n, "dz":n, "col":[r,g,b] }, ...] }
    void load_json(const std::string& path) {
        std::ifstream f(path);
        if (!f) throw std::runtime_error("Cannot open scene file: " + path);
        std::string src((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());
        size_t pos = 0;

        auto skip = [&] {
            while (pos < src.size() && (src[pos]==' '||src[pos]=='\t'||
                                        src[pos]=='\n'||src[pos]=='\r')) ++pos;
        };
        auto peek = [&]() -> char { skip(); return pos < src.size() ? src[pos] : '\0'; };
        auto eat  = [&](char c) {
            skip();
            if (pos >= src.size() || src[pos] != c)
                throw std::runtime_error(std::string("JSON: expected '") + c +
                                         "' at pos " + std::to_string(pos));
            ++pos;
        };
        auto read_string = [&]() -> std::string {
            eat('"');
            std::string s;
            while (pos < src.size() && src[pos] != '"') {
                if (src[pos] == '\\') { ++pos; if (pos < src.size()) s += src[pos]; }
                else s += src[pos];
                ++pos;
            }
            eat('"');
            return s;
        };
        auto read_number = [&]() -> double {
            skip();
            size_t start = pos;
            if (pos < src.size() && src[pos] == '-') ++pos;
            while (pos < src.size() && std::isdigit((unsigned char)src[pos])) ++pos;
            if (pos < src.size() && src[pos] == '.') {
                ++pos;
                while (pos < src.size() && std::isdigit((unsigned char)src[pos])) ++pos;
            }
            if (pos < src.size() && (src[pos]=='e'||src[pos]=='E')) {
                ++pos;
                if (pos < src.size() && (src[pos]=='+'||src[pos]=='-')) ++pos;
                while (pos < src.size() && std::isdigit((unsigned char)src[pos])) ++pos;
            }
            return std::stod(src.substr(start, pos - start));
        };
        auto read_v3 = [&]() -> Vec3 {
            eat('['); double x=read_number(); eat(','); double y=read_number();
            eat(','); double z=read_number(); eat(']'); return {x,y,z};
        };
        auto read_col = [&]() -> color {
            eat('['); double r=read_number(); eat(','); double g=read_number();
            eat(','); double b=read_number(); eat(']');
            return {(uint8_t)r,(uint8_t)g,(uint8_t)b};
        };
        // Skip an unknown JSON value (handles nesting).
        std::function<void()> skip_val = [&]() {
            char c = peek();
            if (c == '"')      { read_string(); }
            else if (c == '[') {
                eat('[');
                if (peek() != ']') { skip_val(); while (peek()==','){eat(','); skip_val();} }
                eat(']');
            } else if (c == '{') {
                eat('{');
                if (peek() != '}') {
                    read_string(); eat(':'); skip_val();
                    while (peek()==',') { eat(','); read_string(); eat(':'); skip_val(); }
                }
                eat('}');
            } else if (c=='t') { pos+=4; } // true
            else if (c=='f')   { pos+=5; } // false
            else if (c=='n')   { pos+=4; } // null
            else               { read_number(); }
        };

        eat('{');
        while (peek() != '}') {
            std::string key = read_string();
            eat(':');
            if (key == "light_direction") {
                light_direction = read_v3();
            } else if (key == "camera") {
                eat('{');
                while (peek() != '}') {
                    std::string k = read_string(); eat(':');
                    if      (k=="position")     cam.position     = read_v3();
                    else if (k=="target")       cam.target       = read_v3();
                    else if (k=="up")           cam.up           = read_v3();
                    else if (k=="fov")          cam.fov          = read_number();
                    else if (k=="near")         cam.near         = read_number();
                    else if (k=="far")          cam.far          = read_number();
                    else if (k=="ortho_height") cam.ortho_height = read_number();
                    else if (k=="projection") {
                        std::string v = read_string();
                        cam.proj_mode = (v == "orthographic") ? ProjectionMode::Orthographic
                                                              : ProjectionMode::Perspective;
                    } else skip_val();
                    if (peek()==',') eat(',');
                }
                eat('}');
            } else if (key == "lines") {
                eat('[');
                while (peek() != ']') {
                    Vec3 a{}, b{}; color col{};
                    eat('{');
                    while (peek() != '}') {
                        std::string k = read_string(); eat(':');
                        if      (k=="a")   a   = read_v3();
                        else if (k=="b")   b   = read_v3();
                        else if (k=="col") col = read_col();
                        else skip_val();
                        if (peek()==',') eat(',');
                    }
                    eat('}');
                    add_line(a, b, col);
                    if (peek()==',') eat(',');
                }
                eat(']');
            } else if (key == "triangles") {
                eat('[');
                while (peek() != ']') {
                    Vec3 a{}, b{}, c{};
                    eat('{');
                    while (peek() != '}') {
                        std::string k = read_string(); eat(':');
                        if      (k=="a") a = read_v3();
                        else if (k=="b") b = read_v3();
                        else if (k=="c") c = read_v3();
                        else skip_val();
                        if (peek()==',') eat(',');
                    }
                    eat('}');
                    add_triangle(a, b, c);
                    if (peek()==',') eat(',');
                }
                eat(']');
            } else if (key == "blocks") {
                eat('[');
                while (peek() != ']') {
                    Vec3 origin{}; double dx{},dy{},dz{}; color col{};
                    eat('{');
                    while (peek() != '}') {
                        std::string k = read_string(); eat(':');
                        if      (k=="origin") origin = read_v3();
                        else if (k=="dx")     dx     = read_number();
                        else if (k=="dy")     dy     = read_number();
                        else if (k=="dz")     dz     = read_number();
                        else if (k=="col")    col    = read_col();
                        else skip_val();
                        if (peek()==',') eat(',');
                    }
                    eat('}');
                    add_block(origin, dx, dy, dz, col);
                    if (peek()==',') eat(',');
                }
                eat(']');
            } else {
                skip_val();
            }
            if (peek()==',') eat(',');
        }
        eat('}');
    }
};
