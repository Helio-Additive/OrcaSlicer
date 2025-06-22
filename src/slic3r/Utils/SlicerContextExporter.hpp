#ifndef slic3r_SlicerContextExporter_hpp_
#define slic3r_SlicerContextExporter_hpp_

#include <string>

namespace Slic3r {

// Export a JSON file containing an integrated view of the slicer context.
void export_integrated_slicer_context_json(const std::string& output_folder);

} // namespace Slic3r

#endif // slic3r_SlicerContextExporter_hpp_
