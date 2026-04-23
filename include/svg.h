#pragma once
#include <fstream>
#include <string>
#include <vector>
#include "project.h"

struct SvgWriter {
    SvgWriter(const std::string& path, float width, float height)
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
                   const std::string& color = "black",
                   float stroke_width = 1.0f) {
        for (const auto& l : lines) {
            _file << "  <line"
                  << " x1=\"" << l.x0 << "\" y1=\"" << l.y0 << "\""
                  << " x2=\"" << l.x1 << "\" y2=\"" << l.y1 << "\""
                  << " stroke=\"" << color << "\""
                  << " stroke-width=\"" << stroke_width << "\""
                  << "/>\n";
        }
    }

    ~SvgWriter() { _file << "</svg>\n"; }

private:
    std::ofstream _file;
    float _width, _height;
};
