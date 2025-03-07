#ifndef slic3r_HelioDragon_hpp_
#define slic3r_HelioDragon_hpp_

#include <string>
#include <wx/string.h>
#include <boost/optional.hpp>
#include <boost/asio/ip/address.hpp>

#include <condition_variable>
#include <mutex>
#include <boost/thread.hpp>
#include <wx/event.h>

#include "PrintHost.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "nlohmann/json.hpp"
#include "../GUI/BackgroundSlicingProcess.hpp"
#include "../GUI/NotificationManager.hpp"
#include "libslic3r/GCode/GCodeProcessor.hpp"
#include "../GUI/GUI_Preview.hpp"
#include "../GUI/Plater.hpp"

namespace Slic3r {

class DynamicPrintConfig;
class Http;
class AppConfig;

class HelioQuery
{
public:
    struct PresignedURLResult
    {
        std::string key;
        std::string mimeType;
        std::string url;
        unsigned    status;
        std::string error;
    };

    struct UploadFileResult
    {
        bool        success;
        std::string error;
    };

    struct CreateGCodeResult
    {
        unsigned    status;
        bool        success;
        std::string name;
        std::string id;
        std::string error;
    };

    struct CreateSimulationResult
    {
        unsigned    status;
        bool        success;
        std::string name;
        std::string id;
        std::string error;
    };

    struct CheckSimulationProgressResult
    {
        unsigned    status;
        bool        is_finished;
        float       progress;
        std::string id;
        std::string name;
        std::string url;
        std::string error;
    };

    static PresignedURLResult create_presigned_url(const std::string helio_api_url, const std::string helio_api_key);
    static UploadFileResult   upload_file_to_presigned_url(const std::string file_path_string, const std::string upload_url);
    static CreateGCodeResult  create_gcode(const std::string key,
                                           const std::string helio_api_url,
                                           const std::string helio_api_key,
                                           const std::string printer_id,
                                           const std::string filament_id);

    static CreateSimulationResult create_simulation(const std::string helio_api_url,
                                                    const std::string helio_api_key,
                                                    const std::string gcode_id,
                                                    const float       initial_room_airtemp,
                                                    const float       layer_threshold,
                                                    const float       object_proximity_airtemp);

    static CheckSimulationProgressResult check_simulation_progress(const std::string helio_api_url,
                                                                   const std::string helio_api_key,
                                                                   const std::string simulation_id);
};

class HelioBackgroundProcess
{
public:
    enum State {
        // m_thread  is not running yet, or it did not reach the STATE_IDLE yet (it does not wait on the condition yet).
        STATE_INITIAL = 0,
        // m_thread is waiting for the task to execute.
        STATE_IDLE,
        STATE_STARTED,
        // m_thread is executing a task.
        STATE_RUNNING,
        // m_thread finished executing a task, and it is waiting until the UI thread picks up the results.
        STATE_FINISHED,
        // m_thread finished executing a task, the task has been canceled by the UI thread, therefore the UI thread will not be notified.
        STATE_CANCELED,
        // m_thread exited the loop and it is going to finish. The UI thread should join on m_thread.
        STATE_EXIT,
        STATE_EXITED,
    };

    std::mutex              m_mutex;
    std::condition_variable m_condition;
    boost::thread           m_thread;
    State                   m_state = STATE_INITIAL;
    std::string             helio_api_key;
    std::string             helio_api_url;
    std::string             printer_id;
    std::string             filament_id;

    Slic3r::GCodeProcessorResult* m_gcode_result;
    Slic3r::GCodeProcessor        m_gcode_processor;
    Slic3r::GUI::Preview*         m_preview;
    std::function<void()>         m_update_function;

    void helio_threaded_process_start(std::mutex&                                slicing_mutex,
                                      std::condition_variable&                   slicing_condition,
                                      BackgroundSlicingProcess::State&           slicing_state,
                                      std::unique_ptr<GUI::NotificationManager>& notification_manager);

    void helio_thread_start(std::mutex&                                slicing_mutex,
                            std::condition_variable&                   slicing_condition,
                            BackgroundSlicingProcess::State&           slicing_state,
                            std::unique_ptr<GUI::NotificationManager>& notification_manager);

    HelioBackgroundProcess() { helio_api_url = "https://api2.helioadditive.com/graphql/sdk"; }

    ~HelioBackgroundProcess()
    {
        m_gcode_result = nullptr;
        if (m_thread.joinable()) {
            m_thread.join();
        }
    }

    void init(std::string                   api_key,
              std::string                   printer_id,
              std::string                   filament_id,
              Slic3r::GCodeProcessorResult* gcode_result,
              Slic3r::GUI::Preview*         preview,
    std::function<void()>         function)
    {
        m_gcode_processor.reset();
        helio_api_key     = api_key;
        this->printer_id  = printer_id;
        this->filament_id = filament_id;
        m_gcode_result    = gcode_result;
        m_preview         = preview;
        m_update_function          = function;
    }

    void set_helio_api_key(std::string api_key);
    void set_gcode_result(Slic3r::GCodeProcessorResult* gcode_result);
    void create_simulation_step(HelioQuery::CreateGCodeResult              create_gcode_res,
                                std::unique_ptr<GUI::NotificationManager>& notification_manager);
    void save_downloaded_gcode_and_load_preview(std::string                                file_download_url,
                                                std::string                                simulated_gcode_path,
                                                std::unique_ptr<GUI::NotificationManager>& notification_manager);

    std::string create_path_for_simulated_gcode(std::string unsimulated_gcode_path)
    {
        boost::filesystem::path p(unsimulated_gcode_path);

        if (!p.has_filename()) {
            throw std::runtime_error("Invalid path: No filename present.");
        }

        boost::filesystem::path parent       = p.parent_path();
        std::string             new_filename = "simulated_" + p.filename().string();

        return (parent / new_filename).string();
    }

    void load_simulation_to_viwer(std::string file_path);
};
} // namespace Slic3r
#endif

/*

void GCodeViewer::SequentialView::GCodeWindow::load_gcode(const std::string& filename, const std::vector<size_t> &lines_ends)
{
    assert(! m_file.is_open());
    if (m_file.is_open())
        return;

    m_filename   = filename;
    m_lines_ends = lines_ends;

    m_selected_line_id = 0;
    m_last_lines_size = 0;

    try
    {
        m_file.open(boost::filesystem::path(m_filename));
        BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << ": mapping file " << m_filename;
    }
    catch (...)
    {
        BOOST_LOG_TRIVIAL(error) << "Unable to map file " << m_filename << ". Cannot show G-code window.";
        reset();
    }
}

*/
