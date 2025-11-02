#ifndef slic3r_GUI_HelioReleaseNote_hpp_
#define slic3r_GUI_HelioReleaseNote_hpp_

#include <limits>
#include <wx/wx.h>
#include <wx/intl.h>
#include <wx/collpane.h>
#include <wx/dataview.h>
#include <wx/artprov.h>
#include <wx/xrc/xmlres.h>
#include <wx/dataview.h>
#include <wx/gdicmn.h>
#include <wx/font.h>
#include <wx/colour.h>
#include <wx/settings.h>
#include <wx/string.h>
#include <wx/sizer.h>
#include <wx/stattext.h>
#include <wx/hyperlink.h>
#include <wx/button.h>
#include <wx/dialog.h>
#include <wx/popupwin.h>
#include <wx/spinctrl.h>
#include <wx/artprov.h>
#include <wx/wrapsizer.h>
#include <wx/event.h>
#include <wx/hyperlink.h>
#include <wx/richtext/richtextctrl.h>

#include "GUI_Utils.hpp"
#include "wxExtensions.hpp"
#include "HelioDragon.hpp"
#include "Widgets/Label.hpp"
#include "Widgets/Button.hpp"
#include "Widgets/CheckBox.hpp"
#include "Widgets/ComboBox.hpp"
#include "Widgets/LinkLabel.hpp"
#include "Widgets/ScrolledWindow.hpp"
#include <wx/hashmap.h>
#include <wx/webview.h>


namespace Slic3r { namespace GUI {

wxDECLARE_EVENT(EVT_SECONDARY_CHECK_CONFIRM, wxCommandEvent);
wxDECLARE_EVENT(EVT_SECONDARY_CHECK_CANCEL, wxCommandEvent);
wxDECLARE_EVENT(EVT_SECONDARY_CHECK_RETRY, wxCommandEvent);
wxDECLARE_EVENT(EVT_SECONDARY_CHECK_DONE, wxCommandEvent);
wxDECLARE_EVENT(EVT_SECONDARY_CHECK_RESUME, wxCommandEvent);
wxDECLARE_EVENT(EVT_UPDATE_NOZZLE, wxCommandEvent);
wxDECLARE_EVENT(EVT_UPDATE_TEXT_MSG, wxCommandEvent);
wxDECLARE_EVENT(EVT_ERROR_DIALOG_BTN_CLICKED, wxCommandEvent);

class HelioStatementDialog : public DPIDialog
{
private:
    Label *m_title{nullptr};
    Button *m_button_confirm{nullptr};
    Button *m_button_cancel{nullptr};

    int current_page{ 0 };
    std::shared_ptr<int> shared_ptr{nullptr};

    wxPanel* page1_panel{ nullptr };
    wxPanel* page2_panel{ nullptr };
    wxPanel* page3_panel{ nullptr };

    bool page1_agree{ false };
    bool page2_agree{ false };

    Label* pat_err_label{ nullptr };
    TextInput* helio_input_pat{ nullptr };
    wxStaticBitmap* helio_pat_refresh{ nullptr };
    wxStaticBitmap* helio_pat_eview{ nullptr };
    wxStaticBitmap* helio_pat_dview{ nullptr };
    wxStaticBitmap* helio_pat_copy{ nullptr };

public:
    HelioStatementDialog(wxWindow *parent = nullptr);
    ~HelioStatementDialog() {};

    // void on_ok(wxMouseEvent &evt);
    void on_dpi_changed(const wxRect &suggested_rect) override;
    void show_err_info(std::string type);
    void show_pat_option(std::string opt);
    void show_agreement_page1();
    void show_agreement_page2();
    void show_pat_page();
    void request_pat();
    void on_confirm(wxMouseEvent& e);
    void open_url(std::string type);

    void OnLoaded(wxWebViewEvent& event);
    void OnTitleChanged(wxWebViewEvent& event);
    void OnError(wxWebViewEvent& event);
};

}} // namespace Slic3r::GUI

#endif
