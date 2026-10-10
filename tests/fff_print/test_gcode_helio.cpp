#include <catch2/catch_all.hpp>

#include "libslic3r/GCode/GCodeProcessor.hpp"
#include "libslic3r/PrintConfig.hpp"

#include "test_utils.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <string>
#include <utility>
#include <vector>

using namespace Slic3r;
using Catch::Matchers::WithinAbs;

namespace {

class ScopedPrinterTagMode
{
public:
    explicit ScopedPrinterTagMode(bool bbl) : m_previous(std::exchange(GCodeProcessor::s_IsBBLPrinter, bbl)) {}
    ~ScopedPrinterTagMode() { GCodeProcessor::s_IsBBLPrinter = m_previous; }
    ScopedPrinterTagMode(const ScopedPrinterTagMode&) = delete;
    ScopedPrinterTagMode& operator=(const ScopedPrinterTagMode&) = delete;
private:
    bool m_previous;
};

std::vector<GCodeProcessorResult::MoveVertex> process_gcode(const char* gcode, bool* is_helio_gcode = nullptr)
{
    // Other tests change this shared tag mode (for example WipeTower2).
    // These fixtures use BBL tags; restore the caller's mode even on exceptions.
    const ScopedPrinterTagMode tag_mode(true);
    FullPrintConfig config;
    config.gcode_flavor.value = gcfMarlinFirmware;

    ScopedTemporaryFile temp(".gcode");
    {
        std::ofstream output(temp.string());
        output << gcode;
    }

    GCodeProcessor processor;
    processor.apply_config(config);
    processor.process_file(temp.string());
    // GCodeProcessorResult holds a std::mutex, so it is neither copyable nor movable;
    // bind the returned rvalue reference instead of constructing a local copy.
    auto&& result = processor.extract_result();
    if (is_helio_gcode != nullptr)
        *is_helio_gcode = result.is_helio_gcode;
    return std::move(result.moves);
}

const GCodeProcessorResult::MoveVertex& extrusion_at(const std::vector<GCodeProcessorResult::MoveVertex>& moves, float x)
{
    const auto it = std::find_if(moves.begin(), moves.end(), [x](const auto& move) {
        return move.type == EMoveType::Extrude && std::abs(move.position.x() - x) < 0.001f;
    });
    REQUIRE(it != moves.end());
    return *it;
}

} // namespace

TEST_CASE("A following Helio comment adds warpage data to the current path", "[GCode][Helio]")
{
    const auto moves = process_gcode(
        "M83\n"
        "G1 X10 E1 ;helioadditive=(ti.max=0.80,ti.min=0.20,ti.mean=0.40,element.index=10)\n"
        ";helioadditive=(wdm=0.0231,wdx=-0.0012,wdy=0.0046,wdz=0.0227,wr=0.422,wtg=-12.3457,wts=0.009449,whs=0.0187,wls=0.009449,element.index=42)\n"
        "G1 X20 E1 ;helioadditive=ti.max=0.9,ti.min=0.8,ti.mean=0.85\n"
        "; unrelated comment\n"
        ";helioadditive=wdm=1.0\n"
        "G1 X30 E1\n"
        ";helioadditive=whs=0.2110\n"
        "G1 X40 E1 ;helioadditive=(ti.max=0.7,ti.min=0.3,ti.mean=0.5,element.index=40)\n"
        "  ;helioadditive=(wdm=0.04,wls=0.004)\n"
        "G1 X50 E1 ;helioadditive=(wdx=0.05,wdy=0.06)\n"
        ";helioadditive=(wr=0.7)\n"
        "G1 X60 E1 ;helioadditive=(wdm=inf,wdx=0.08,wdy=-inf)\n"
        ";helioadditive=(wdx=nan,wr=inf)\n");

    const auto& annotated = extrusion_at(moves, 10.0f);
    CHECK_THAT(annotated.thermal_index_max, WithinAbs(80.0f, 0.001f));
    CHECK_THAT(annotated.thermal_index_min, WithinAbs(20.0f, 0.001f));
    CHECK_THAT(annotated.thermal_index_mean, WithinAbs(40.0f, 0.001f));
    CHECK_THAT(annotated.warpage_displacement, WithinAbs(0.0231f, 0.000001f));
    CHECK_THAT(annotated.warpage_disp_x, WithinAbs(-0.0012f, 0.000001f));
    CHECK_THAT(annotated.warpage_disp_y, WithinAbs(0.0046f, 0.000001f));
    CHECK_THAT(annotated.warpage_disp_z, WithinAbs(0.0227f, 0.000001f));
    CHECK_THAT(annotated.warpage_risk, WithinAbs(0.422f, 0.000001f));
    CHECK_THAT(annotated.warpage_ti_gradient, WithinAbs(-12.3457f, 0.000001f));
    CHECK_THAT(annotated.warpage_thermal_strain, WithinAbs(0.009449f, 0.000001f));
    CHECK_THAT(annotated.warpage_hull_shrinkage, WithinAbs(0.0187f, 0.000001f));
    CHECK_THAT(annotated.warpage_layer_shrinkage, WithinAbs(0.009449f, 0.000001f));

    const auto& separated = extrusion_at(moves, 20.0f);
    CHECK_THAT(separated.thermal_index_mean, WithinAbs(85.0f, 0.001f));
    CHECK(std::isnan(separated.warpage_displacement));

    const auto& partially_backfilled = extrusion_at(moves, 50.0f);
    CHECK_THAT(partially_backfilled.warpage_disp_x, WithinAbs(0.05f, 0.000001f));
    CHECK_THAT(partially_backfilled.warpage_disp_y, WithinAbs(0.06f, 0.000001f));
    CHECK_THAT(partially_backfilled.warpage_risk, WithinAbs(0.7f, 0.000001f));

    const auto& non_finite = extrusion_at(moves, 60.0f);
    CHECK(std::isnan(non_finite.warpage_displacement));
    CHECK_THAT(non_finite.warpage_disp_x, WithinAbs(0.08f, 0.000001f));
    CHECK(std::isnan(non_finite.warpage_disp_y));
    CHECK(std::isnan(non_finite.warpage_risk));

    const auto& warpage_only = extrusion_at(moves, 30.0f);
    CHECK_THAT(warpage_only.warpage_hull_shrinkage, WithinAbs(0.2110f, 0.000001f));
    CHECK(warpage_only.thermal_index_mean < -100.0f);

    const auto& indented = extrusion_at(moves, 40.0f);
    CHECK_THAT(indented.thermal_index_mean, WithinAbs(50.0f, 0.001f));
    CHECK_THAT(indented.warpage_displacement, WithinAbs(0.04f, 0.000001f));
    CHECK_THAT(indented.warpage_layer_shrinkage, WithinAbs(0.004f, 0.000001f));
}

TEST_CASE("Warpage-only metadata identifies Helio G-code", "[GCode][Helio]")
{
    bool       is_helio_gcode = false;
    const auto moves = process_gcode(
        "M83\n"
        "G1 X10 E1\n"
        ";helioadditive=whs=0.2110\n",
        &is_helio_gcode);

    CHECK(is_helio_gcode);
    CHECK_THAT(extrusion_at(moves, 10.0f).warpage_hull_shrinkage, WithinAbs(0.2110f, 0.000001f));
}

TEST_CASE("Standalone warpage metadata covers every arc segment without crossing layers", "[GCode][Helio]")
{
    const auto moves = process_gcode(
        "M83\n"
        "; CHANGE_LAYER\n"
        "G1 Z0.4\n"
        "G1 X1 Y0\n"
        "G3 X0 Y1 I-1 J0 E1 ;helioadditive=(ti.max=-0.2,ti.min=-0.2,ti.mean=-0.2)\n"
        ";helioadditive=(whs=0.0644)\n"
        "; CHANGE_LAYER\n"
        "G1 Z0.6\n"
        "G1 X11 Y0\n"
        "G2 X10 Y-1 I-1 J0 E1 ;helioadditive=(ti.max=-0.18,ti.min=-0.18,ti.mean=-0.18)\n"
        ";helioadditive=(whs=0.0311)\n"
        "; CHANGE_LAYER\n"
        "G1 Z0.8\n"
        "G1 X21 Y0\n"
        "G3 X20 Y1 I-1 J0 E1 ;helioadditive=(whs=0.0003)\n");

    const std::array<float, 3> expected_whs = { 0.0644f, 0.0311f, 0.0003f };
    for (size_t layer_id = 0; layer_id < expected_whs.size(); ++layer_id) {
        size_t segment_count = 0;
        for (const auto& move : moves) {
            if (move.type != EMoveType::Extrude || move.layer_id != layer_id)
                continue;
            ++segment_count;
            CHECK_THAT(move.warpage_hull_shrinkage, WithinAbs(expected_whs[layer_id], 0.000001f));
        }
        // Each G2/G3 is discretized, so this also verifies that standalone metadata
        // is backfilled to every generated subsegment rather than only the endpoint.
        CHECK(segment_count > 1);
    }
}

TEST_CASE("Standalone warpage metadata survives planner vertex insertions", "[GCode][Helio]")
{
    std::string gcode = "M83\nG1 Z0.2\n";
    // Index expectations by the source motion line, including non-motion lines.
    std::vector<float> expected_by_line(3, NAN);
    auto append = [&](const std::string& line, float value = NAN) {
        gcode += line + "\n";
        expected_by_line.push_back(value);
    };
    for (int layer = 0; layer < 3; ++layer) {
        append("; CHANGE_LAYER");
        append("G1 Z" + std::to_string(0.2 * (layer + 1)));
        // Exceed the planner refresh threshold repeatedly. Distinct per-move
        // values detect overwrites both within a layer and across its boundary.
        for (int i = 0; i < 400; ++i) {
            const float value = float(layer * 400 + i + 1) / 2000.0f;
            append("G1 X" + std::to_string(i % 2 ? 20 : 0) +
                   " Y" + std::to_string(layer * 10 + i % 3) + " E0.5 F6000", value);
            append(";helioadditive=(wdm=" + std::to_string(value) +
                   ",wdx=" + std::to_string(value) + ",wdy=" + std::to_string(value) +
                   ",wdz=" + std::to_string(value) + ",wr=" + std::to_string(value) +
                   ",wtg=" + std::to_string(value) + ",wts=" + std::to_string(value) +
                   ",whs=" + std::to_string(value) + ",wls=" + std::to_string(value) + ")");
        }
    }
    const auto moves = process_gcode(gcode.c_str());
    size_t internal_extrusions = 0;
    size_t extrusions = 0;
    std::array<size_t, 3> layer_extrusions{};
    for (const auto& move : moves) {
        if (move.type != EMoveType::Extrude)
            continue;
        ++extrusions;
        REQUIRE(move.layer_id < layer_extrusions.size());
        ++layer_extrusions[move.layer_id];
        internal_extrusions += move.internal_only;
        REQUIRE(move.gcode_id < expected_by_line.size());
        const float expected = expected_by_line[move.gcode_id];
        REQUIRE(std::isfinite(expected));
        for (float value : { move.warpage_displacement, move.warpage_disp_x, move.warpage_disp_y,
                            move.warpage_disp_z, move.warpage_risk, move.warpage_ti_gradient,
                            move.warpage_thermal_strain, move.warpage_hull_shrinkage,
                            move.warpage_layer_shrinkage }) {
            CHECK_THAT(value, WithinAbs(expected, 0.000001f));
        }
    }
    CHECK(extrusions >= 1200);
    for (size_t count : layer_extrusions)
        CHECK(count >= 400);
    REQUIRE(internal_extrusions > 0);
}

TEST_CASE("Helio fixtures isolate and restore the printer tag mode", "[GCode][Helio]")
{
    const bool initial_mode = GENERATE(false, true);
    const ScopedPrinterTagMode caller_mode(initial_mode);
    const auto moves = process_gcode(
        "M83\n"
        "; CHANGE_LAYER\nG1 Z0.2\nG1 X10 E1\n;helioadditive=(whs=0.2)\n"
        "; CHANGE_LAYER\nG1 Z0.4\nG1 X20 E1\n;helioadditive=(whs=0.4)\n");
    CHECK(GCodeProcessor::s_IsBBLPrinter == initial_mode);
    CHECK(extrusion_at(moves, 10.0f).layer_id == 0);
    CHECK(extrusion_at(moves, 20.0f).layer_id == 1);
}

TEST_CASE("Standalone warpage metadata after a no-op does not annotate an event", "[GCode][Helio]")
{
    const auto tag = GENERATE("; COLOR_CHANGE,T0,#FF0000", "; PAUSE_PRINTING", "; CUSTOM_GCODE");
    const std::string gcode = std::string("M83\nG1 Z0.2\n") + tag +
        "\nG1 F1200\n;helioadditive=(whs=0.9)\n"
        "G1 X10 E1\n;helioadditive=(whs=0.2)\n";
    const auto moves = process_gcode(gcode.c_str());
    size_t events = 0;
    for (const auto& move : moves) {
        if (move.type == EMoveType::Color_change || move.type == EMoveType::Pause_Print ||
            move.type == EMoveType::Custom_GCode) {
            ++events;
            CHECK(std::isnan(move.warpage_hull_shrinkage));
        }
    }
    REQUIRE(events == 1);
    CHECK_THAT(extrusion_at(moves, 10.0f).warpage_hull_shrinkage, WithinAbs(0.2f, 0.000001f));
}
