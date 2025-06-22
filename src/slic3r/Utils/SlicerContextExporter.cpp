#include "SlicerContextExporter.hpp"

#include <boost/nowide/fstream.hpp>
#include <boost/filesystem.hpp>
#include "nlohmann/json.hpp"
#include <iomanip>

namespace Slic3r {

void export_integrated_slicer_context_json(const std::string& output_folder)
{
    using json = nlohmann::json;
    json root;

    json ui_settings;
    ui_settings["layer_height_mm"]      = 0.2;
    ui_settings["print_speed_mm_per_s"] = 60;
    ui_settings["fan_percent"]          = 50;
    ui_settings["temperature_nozzle_c"] = 210;
    ui_settings["temperature_bed_c"]    = 60;
    ui_settings["sandwich_mode"] = {
        {"enabled", true},
        {"wiki_explanation", "Sandwich Mode varies infill patterns between walls for clarity and strength..."}
    };
    ui_settings["supports"] = {
        {"enabled", true},
        {"type", "tree"},
        {"wiki_explanation", "Supports are generated for overhangs exceeding the critical angle threshold..."}
    };
    ui_settings["adaptive_layer_height"] = {
        {"enabled", true},
        {"min_mm", 0.1},
        {"max_mm", 0.28},
        {"wiki_explanation", "Layer height varies based on geometry curvature for speed/quality balance..."}
    };
    root["ui_settings"] = ui_settings;

    json material_profile;
    material_profile["name"]                 = "PLA";
    material_profile["glass_transition_c"]   = 60;
    material_profile["bridging_threshold_mm"] = 12;
    material_profile["cooling_strategy"]     = "Max fan on bridges, slower outer walls";
    material_profile["wiki_explanation"]     = "PLA is a thermoplastic that requires strong cooling and moderate speeds...";
    root["material_profile"] = material_profile;

    json modifiers = json::array();
    modifiers.push_back({
        {"type", "speed_override"},
        {"region", "top_half"},
        {"effect", "speed = 30mm/s"},
        {"trigger", "modifier mesh"}
    });
    root["modifiers"] = modifiers;

    json internal_logic;
    internal_logic["bridging"] = {
        {"condition", "unsupported_span > 10mm"},
        {"decision", "reduce speed to 40mm/s, set fan to 100%"},
        {"wiki_explanation", "Bridging logic reduces extrusion speed and maximizes cooling to span unsupported gaps."}
    };
    internal_logic["supports"] = {
        {"condition", "overhang_angle > 60\xC2\xB0"},
        {"decision", "generate support under feature"},
        {"wiki_explanation", "Supports are generated under features with angles too steep to self-support."}
    };
    root["internal_logic"] = internal_logic;

    json geometry;
    geometry["layer_14"] = {
        {"features", {"thin_wall", "steep_overhang"}},
        {"analysis", "Wall too thin to extrude reliably. Overhang > 65\xC2\xB0, will require support."}
    };
    root["geometry"] = geometry;

    json dynamic_adjustments = json::array();
    dynamic_adjustments.push_back({
        {"layer", 14},
        {"segment", "bridge"},
        {"adjustments", {
            {"speed_mm_per_s", 40},
            {"fan_percent", 100},
            {"temperature_c", 200}
        }},
        {"reason", "bridge >10mm requires slower speed and increased cooling"}
    });
    root["dynamic_adjustments"] = dynamic_adjustments;

    json toolpath_layers = json::array();
    json layer;
    layer["layer_number"] = 14;
    layer["height_mm"] = 0.2;
    layer["segments"] = json::array({{
        {"type", "outer_wall"},
        {"coordinates", json::array({json::array({10,10,2.8}), json::array({20,10,2.8})})},
        {"speed_mm_per_s", 60},
        {"fan_percent", 50},
        {"extrusion_width_mm", 0.42},
        {"extrusion_temp_c", 210},
        {"reasoning", "Outer walls printed slowly to maintain dimensional accuracy"},
        {"wiki_explanation", "Outer walls are usually printed slower to ensure a clean surface finish."}
    }});
    toolpath_layers.push_back(layer);
    root["toolpath_layers"] = toolpath_layers;

    root["gcode_generation"] = {
        {"segment_to_gcode_mapping", "Segment generates G1 X... Y... E... F... lines; M106 sets fan speed, M104/M109 sets temperature."}
    };

    json risk_flags = json::array();
    risk_flags.push_back({
        {"layer", 14},
        {"issue", "bridge at 12mm span with insufficient cooling"},
        {"suggestion", "reduce speed or increase fan"}
    });
    root["risk_flags"] = risk_flags;

    boost::filesystem::path out_dir(output_folder);
    boost::filesystem::path out_file = out_dir / "integrated_slicer_context.json";

    boost::nowide::ofstream ofs(out_file.string());
    if (ofs.is_open()) {
        ofs << std::setw(4) << root << std::endl;
    }
}

} // namespace Slic3r

