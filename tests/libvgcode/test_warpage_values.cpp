#include <catch2/catch_all.hpp>

#include "libvgcode/include/ColorRange.hpp"
#include "libvgcode/include/PathVertex.hpp"
#include "libvgcode/include/Viewer.hpp"

#include <array>
#include <cmath>
#include <limits>

using namespace libvgcode;

namespace libvgcode {

struct ColorRangeTestAccess
{
    static void update(ColorRange& range, float value) { range.update(value); }
};

} // namespace libvgcode

TEST_CASE("warpage validity filtering keeps color ranges finite", "[libvgcode][warpage]")
{
    ColorRange range;
    const float infinity     = std::numeric_limits<float>::infinity();
    const float neg_infinity = -infinity;
    const float nan          = std::numeric_limits<float>::quiet_NaN();
    const std::array<float, 6> values = {
        0.02f, infinity, neg_infinity, nan, 0.09f, 0.2f
    };

    REQUIRE_FALSE(is_valid_warpage_value(infinity));
    REQUIRE_FALSE(is_valid_warpage_value(neg_infinity));
    REQUIRE_FALSE(is_valid_warpage_value(nan));
    for (float value : values) {
        if (is_valid_warpage_value(value))
            ColorRangeTestAccess::update(range, value);
    }

    REQUIRE(range.get_range() == std::array<float, 2>{ 0.02f, 0.2f });
    for (float legend_value : range.get_values())
        REQUIRE(std::isfinite(legend_value));
}

TEST_CASE("all nine warpage fields reject non-finite values", "[libvgcode][warpage]")
{
    const std::array<float, 3> invalid_values = {
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity(),
        std::numeric_limits<float>::quiet_NaN()
    };
    const std::array<EViewType, 9> view_types = {
        EViewType::WarpageDisplacement, EViewType::WarpageDispX, EViewType::WarpageDispY,
        EViewType::WarpageDispZ, EViewType::WarpageRisk, EViewType::WarpageTIGradient,
        EViewType::WarpageThermalStrain, EViewType::WarpageHullShrinkage, EViewType::WarpageLayerShrinkage
    };
    for (float invalid_value : invalid_values) {
        PathVertex vertex;
        vertex.warpage_displacement = invalid_value;
        vertex.warpage_disp_x = invalid_value;
        vertex.warpage_disp_y = invalid_value;
        vertex.warpage_disp_z = invalid_value;
        vertex.warpage_risk = invalid_value;
        vertex.warpage_ti_gradient = invalid_value;
        vertex.warpage_thermal_strain = invalid_value;
        vertex.warpage_hull_shrinkage = invalid_value;
        vertex.warpage_layer_shrinkage = invalid_value;

        Viewer viewer;
        for (EViewType view_type : view_types) {
            viewer.set_view_type(view_type);
            REQUIRE(viewer.get_vertex_color(vertex) == DUMMY_COLOR);
        }
    }
}
