#include <catch2/catch_all.hpp>

#include "libvgcode/include/ColorRange.hpp"
#include "libvgcode/include/GCodeInputData.hpp"
#include "libvgcode/include/PathVertex.hpp"
#include "libvgcode/include/Viewer.hpp"

#include <array>
#include <cmath>
#include <limits>

using namespace libvgcode;

TEST_CASE("non-finite warpage values do not pollute color ranges", "[libvgcode][warpage]")
{
    const std::array<float, 4> values = {
        0.02f, std::numeric_limits<float>::infinity(), 0.09f, 0.2f
    };

    GCodeInputData gcode_data;
    for (float value : values) {
        PathVertex vertex;
        vertex.type = EMoveType::Extrude;
        vertex.warpage_displacement = value;
        gcode_data.vertices.emplace_back(vertex);
    }

    Viewer viewer;
    viewer.load(std::move(gcode_data));
    const ColorRange& range = viewer.get_color_range(EViewType::WarpageDisplacement);
    REQUIRE(range.get_range() == std::array<float, 2>{ 0.02f, 0.2f });
    for (float legend_value : range.get_values())
        REQUIRE(std::isfinite(legend_value));
}

TEST_CASE("all nine warpage fields reject non-finite values", "[libvgcode][warpage]")
{
    const float infinity = std::numeric_limits<float>::infinity();
    PathVertex vertex;
    vertex.warpage_displacement = infinity;
    vertex.warpage_disp_x = infinity;
    vertex.warpage_disp_y = infinity;
    vertex.warpage_disp_z = infinity;
    vertex.warpage_risk = infinity;
    vertex.warpage_ti_gradient = infinity;
    vertex.warpage_thermal_strain = infinity;
    vertex.warpage_hull_shrinkage = infinity;
    vertex.warpage_layer_shrinkage = infinity;

    const std::array<float, 9> values = {
        vertex.warpage_displacement, vertex.warpage_disp_x, vertex.warpage_disp_y,
        vertex.warpage_disp_z, vertex.warpage_risk, vertex.warpage_ti_gradient,
        vertex.warpage_thermal_strain, vertex.warpage_hull_shrinkage, vertex.warpage_layer_shrinkage
    };
    for (float value : values)
        REQUIRE_FALSE(is_valid_warpage_value(value));

    Viewer viewer;
    const std::array<EViewType, 9> view_types = {
        EViewType::WarpageDisplacement, EViewType::WarpageDispX, EViewType::WarpageDispY,
        EViewType::WarpageDispZ, EViewType::WarpageRisk, EViewType::WarpageTIGradient,
        EViewType::WarpageThermalStrain, EViewType::WarpageHullShrinkage, EViewType::WarpageLayerShrinkage
    };
    for (EViewType view_type : view_types) {
        viewer.set_view_type(view_type);
        REQUIRE(viewer.get_vertex_color(vertex) == DUMMY_COLOR);
    }
}
