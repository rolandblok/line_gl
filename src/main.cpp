#include <cmath>
#include <iostream>
#include <filesystem>
#include "scene.h"
#include "camera.h"
#include "project.h"
#include "hidden_line.h"
#include "intersect.h"
#include "svg.h"
#include "vec_math.h"

[[maybe_unused]] static Scene make_xyz_axis_scene() {
    Scene s;
    s.add_line({0,0,0}, {0.5,0,0}, color{255,0,0});
    s.add_line({0,0,0}, {0,0.5,0}, color{0,255,0});
    s.add_line({0,0,0}, {0,0,0.5}, color{0,0,255});
    return s;
}

int main(int argc, char* argv[]) {
    const double W = 800.0f, H = 600.0f;

    Scene xyz = make_xyz_axis_scene();

    std::filesystem::create_directories("svg");

    auto render = [&](Scene& scene, const std::string& scene_path, bool debug = false) {
        Camera& cam = scene.cam;
        Mat4 view = cam.view();
        const Mat4* view_mat = (cam.proj_mode == ProjectionMode::Orthographic) ? &view : nullptr;
        Mat4 mvp = cam.mvp(W / H);

        auto xyz_p = project_scene_full(xyz, mvp, W, H, view_mat);

        std::string stem = std::filesystem::path(scene_path).stem().string();
        std::string out     = "svg/" + stem + ".svg";
        std::string out_raw = "svg/" + stem + "_raw.svg";
        std::vector<Vec3> crossings;
        auto pscene  = project_scene_full(scene, mvp, W, H, view_mat);
        add_triangle_intersection_lines(pscene);
        auto lines2d = hidden_line_removal(pscene, debug, &crossings);
        std::cout << out << ": " << lines2d.size() << " segments\n";

        SvgWriter svg(out.c_str(), W, H);
        svg.add_lines(lines2d, 1.0f, false);

        if (debug) {
            svg.add_lines(xyz_p.lines, 2.0f, false);
            std::cerr << "Crossings (" << crossings.size() << "):\n";
            for (const auto& p : crossings){
                std::cerr << "  (" << p.x << ", " << p.y << ", " << p.z << ")\n";
                svg.add_dot(p, 4.0, "orange");
            }
        }


        SvgWriter svg_raw(out_raw.c_str(), W, H);
        svg_raw.add_lines(project_scene(scene, mvp, W, H, view_mat), 1.5);
    };

    // Collect scene files: from arguments or all *.json in scenes/
    std::vector<std::string> scene_files;
    if (argc > 1) {
        for (int i = 1; i < argc; ++i)
            scene_files.push_back(argv[i]);
    } else {
        for (const auto& entry : std::filesystem::directory_iterator("scenes"))
            if (entry.path().extension() == ".json")
                scene_files.push_back(entry.path().string());
        std::sort(scene_files.begin(), scene_files.end());
    }

    for (const auto& path : scene_files) {
        Scene s; s.load_json(path);
        render(s, path);
    }

    return 0;
}
