#pragma once
#include <fstream>
#include <string>
#include <vector>
#include "project.h"

struct SvgWriter {
    SvgWriter(const std::string& path, double width, double height)
        : _width(width), _height(height) {
        _file.open(path);
        _file << "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
              << "<svg xmlns=\"http://www.w3.org/2000/svg\""
              << " width=\""   << width  << "\""
              << " height=\""  << height << "\""
              << " viewBox=\"0 0 " << width << " " << height << "\">\n"
              << "  <rect width=\"100%\" height=\"100%\" fill=\"white\"/>\n";
    }

    void add_lines(const std::vector<Line2D>& lines,
                   double stroke_width = 1.0f,
                   bool debug_endpoints = false) {
        for (const auto& l : lines) {
            _file << "  <line"
                  << " x1=\"" << l.a.x << "\" y1=\"" << l.a.y << "\""
                  << " x2=\"" << l.b.x << "\" y2=\"" << l.b.y << "\""
                  << " stroke=\"rgb(" << l.col.x << "," << l.col.y << "," << l.col.z << ")\""
                  << " stroke-width=\"" << stroke_width << "\""
                  << "/>\n";
            if (debug_endpoints) {
                // small hollow red circle at start
                _file << "  <circle cx=\"" << l.a.x << "\" cy=\"" << l.a.y << "\""
                      << " r=\"3\" fill=\"none\" stroke=\"red\" stroke-width=\"1\"/>\n";
                // larger hollow green circle at end
                _file << "  <circle cx=\"" << l.b.x << "\" cy=\"" << l.b.y << "\""
                      << " r=\"5\" fill=\"none\" stroke=\"green\" stroke-width=\"1\"/>\n";
            }
        }
    }

    // Draw a single segment between two projected points.
    void add_segment(Vec3 a, Vec3 b,
                     const std::string& color = "orange",
                     double stroke_width = 0.75) {
        _file << "  <line"
              << " x1=\"" << a.x << "\" y1=\"" << a.y << "\""
              << " x2=\"" << b.x << "\" y2=\"" << b.y << "\""
              << " stroke=\"" << color << "\""
              << " stroke-width=\"" << stroke_width << "\""
              << "/>\n";
    }

    // Draw a projected triangle outline (dashed).
    void add_triangle_outline(Vec3 a, Vec3 b, Vec3 c,
                              const std::string& color = "blue",
                              double stroke_width = 0.5) {
        _file << "  <polygon"
              << " points=\"" << a.x << "," << a.y << " "
                              << b.x << "," << b.y << " "
                              << c.x << "," << c.y << "\""
              << " fill=\"none\""
              << " stroke=\"" << color << "\""
              << " stroke-width=\"" << stroke_width << "\""
              << " stroke-dasharray=\"4 2\""
              << "/>\n";
    }

    // Draw a small hollow circle marker at a projected point.
    void add_dot(Vec3 p, double r = 3.0, const std::string& color = "red") {
        _file << "  <circle cx=\"" << p.x << "\" cy=\"" << p.y << "\""
              << " r=\"" << r << "\""
              << " fill=\"none\""
              << " stroke=\"" << color << "\""
              << " stroke-width=\"1\"/>\n";
    }

    ~SvgWriter() { _file << "</svg>\n"; }

private:
    std::ofstream _file;
    double _width, _height;
};
