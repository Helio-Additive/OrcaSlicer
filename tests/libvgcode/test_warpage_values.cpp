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

TEST_CASE("Z displacement rejects negative values", "[libvgcode][warpage]")
{
    REQUIRE(is_valid_warpage_value(-0.1f, EViewType::WarpageDispX));
    REQUIRE_FALSE(is_valid_warpage_value(-0.1f, EViewType::WarpageDispZ));

    PathVertex vertex;
    vertex.type           = EMoveType::Extrude;
    vertex.warpage_disp_z = -0.1f;

    Viewer viewer;
    viewer.set_view_type(EViewType::WarpageDispZ);
    REQUIRE(viewer.get_vertex_color(vertex) == DUMMY_COLOR);
}

TEST_CASE("hull shrinkage coloring does not require thermal index data", "[libvgcode][warpage]")
{
    PathVertex vertex;
    vertex.type                    = EMoveType::Extrude;
    vertex.warpage_hull_shrinkage = 0.2110f;

    // Keep the default unavailable TI sentinels. Warpage views must use only
    // their corresponding warpage field rather than treating missing TI as
    // missing warpage metadata.
    REQUIRE(vertex.thermal_index_mean < -100.0f);
    REQUIRE(vertex.thermal_index_min < -100.0f);
    REQUIRE(vertex.thermal_index_max < -100.0f);

    Viewer viewer;
    viewer.set_view_type(EViewType::WarpageHullShrinkage);
    REQUIRE(viewer.get_vertex_color(vertex) != DUMMY_COLOR);
}

TEST_CASE("warpage hull and layer shrinkage use distinct fields", "[libvgcode][warpage]")
{
    PathVertex vertex;
    vertex.warpage_hull_shrinkage  = 0.0311f;
    vertex.warpage_layer_shrinkage = 0.0003f;

    REQUIRE_THAT(get_warpage_value(vertex, EViewType::WarpageHullShrinkage),
                 Catch::Matchers::WithinAbs(0.0311f, 0.000001f));
    REQUIRE_THAT(get_warpage_value(vertex, EViewType::WarpageLayerShrinkage),
                 Catch::Matchers::WithinAbs(0.0003f, 0.000001f));
}
