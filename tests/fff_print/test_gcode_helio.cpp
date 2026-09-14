#include <catch2/catch_all.hpp>

#include "libslic3r/GCode/GCodeProcessor.hpp"
#include "libslic3r/PrintConfig.hpp"

#include "test_utils.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>

using namespace Slic3r;
using Catch::Matchers::WithinAbs;

namespace {

GCodeProcessorResult process_gcode(const char* gcode)
{
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
    return processor.extract_result();
}

const GCodeProcessorResult::MoveVertex& extrusion_at(const GCodeProcessorResult& result, float x)
{
    const auto it = std::find_if(result.moves.begin(), result.moves.end(), [x](const auto& move) {
        return move.type == EMoveType::Extrude && std::abs(move.position.x() - x) < 0.001f;
    });
    REQUIRE(it != result.moves.end());
    return *it;
}

} // namespace

TEST_CASE("A following Helio comment adds warpage data to the current path", "[GCode][Helio]")
{
    const auto result = process_gcode(
        "M83\n"
        "G1 X10 E1 ;helioadditive=(ti.max=0.80,ti.min=0.20,ti.mean=0.40,element.index=10)\n"
        ";helioadditive=(wdm=0.0231,wdx=-0.0012,wdy=0.0046,wdz=0.0227,wr=0.422,wtg=-12.3457,wts=0.009449,whs=0.0187,wls=0.009449,element.index=42)\n"
        "G1 X20 E1 ;helioadditive=ti.max=0.9,ti.min=0.8,ti.mean=0.85\n"
        "; unrelated comment\n"
        ";helioadditive=wdm=1.0\n"
        "G1 X30 E1\n"
        ";helioadditive=wdm=2.0\n");

    const auto& annotated = extrusion_at(result, 10.0f);
    CHECK_THAT(annotated.thermal_index_max, WithinAbs(80.0f, 0.001f));
    CHECK_THAT(annotated.thermal_index_min, WithinAbs(20.0f, 0.001f));
    CHECK_THAT(annotated.thermal_index_mean, WithinAbs(40.0f, 0.001f));
    CHECK_THAT(annotated.warpage_displacement, WithinAbs(0.0231f, 0.000001f));
    CHECK_THAT(annotated.warpage_disp_x, WithinAbs(-0.0012f, 0.000001f));
    CHECK_THAT(annotated.warpage_layer_shrinkage, WithinAbs(0.009449f, 0.000001f));

    const auto& separated = extrusion_at(result, 20.0f);
    CHECK_THAT(separated.thermal_index_mean, WithinAbs(85.0f, 0.001f));
    CHECK(std::isnan(separated.warpage_displacement));

    const auto& unannotated = extrusion_at(result, 30.0f);
    CHECK(std::isnan(unannotated.warpage_displacement));
}
