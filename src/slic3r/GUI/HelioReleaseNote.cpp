#include "HelioReleaseNote.hpp"
#include "I18N.hpp"

#include "libslic3r/Utils.hpp"
#include "libslic3r/Thread.hpp"
#include "GUI.hpp"
#include "GUI_App.hpp"
#include "GUI_Preview.hpp"
#include "MainFrame.hpp"
#include "format.hpp"
#include "GLToolbar.hpp"
#include "Widgets/ProgressDialog.hpp"
#include "Widgets/RoundedRectangle.hpp"
#include "Widgets/StaticBox.hpp"
#include "Widgets/WebView.hpp"
#include "Widgets/SwitchButton.hpp"
#include <wx/regex.h>
#include <wx/progdlg.h>
#include <wx/clipbrd.h>
#include <wx/dcgraph.h>
#include <miniz.h>
#include <wx/valnum.h>
#include <algorithm>
#include "Plater.hpp"
#include "BitmapCache.hpp"

namespace Slic3r { namespace GUI {
 HelioStatementDialog::HelioStatementDialog(wxWindow *parent /*= nullptr*/)
    : DPIDialog(static_cast<wxWindow *>(wxGetApp().mainframe), wxID_ANY, _L("Third-Party Extension"), wxDefaultPosition, wxDefaultSize, wxCAPTION | wxCLOSE_BOX)
{
     shared_ptr = std::make_shared<int>(0);

     SetBackgroundColour(*wxWHITE);

     wxBoxSizer *main_sizer = new wxBoxSizer(wxVERTICAL);

     wxPanel* line = new wxPanel(this, wxID_ANY, wxDefaultPosition, wxSize(-1, 1), wxTAB_TRAVERSAL);
     line->SetBackgroundColour(wxColour(166, 169, 170));

     wxBoxSizer* helio_top_hsizer = new wxBoxSizer(wxHORIZONTAL);
     wxBoxSizer* helio_top_vsizer = new wxBoxSizer(wxVERTICAL);
     wxBoxSizer* helio_top_content_sizer = new wxBoxSizer(wxHORIZONTAL);

     auto helio_top_background = new wxPanel(this);
     helio_top_background->SetBackgroundColour(wxColour(16, 16, 16));
     helio_top_background->SetMinSize(wxSize(-1, FromDIP(70)));
     helio_top_background->SetMaxSize(wxSize(-1, FromDIP(70)));
     auto helio_top_icon = new wxStaticBitmap(helio_top_background, wxID_ANY, create_scaled_bitmap("helio_icon", helio_top_background, 32), wxDefaultPosition, wxSize(FromDIP(32), FromDIP(32)), 0);
     auto helio_top_label = new Label(helio_top_background, Label::Body_16 , L("HELIO ADDITIVE"));
     wxFont bold_font = helio_top_label->GetFont();
     bold_font.SetWeight(wxFONTWEIGHT_BOLD);
     helio_top_label->SetFont(bold_font);
     helio_top_label->SetForegroundColour(wxColour("#FEFEFF"));
     //helio_top_hsizer->Add(0, 0, wxLEFT, FromDIP(40));
     helio_top_content_sizer->Add(helio_top_icon, 0, wxLEFT|wxALIGN_CENTER, FromDIP(45));
     helio_top_content_sizer->Add(helio_top_label, 0, wxLEFT|wxALIGN_CENTER,FromDIP(8));
     helio_top_vsizer->Add(helio_top_content_sizer, 0, wxALIGN_CENTER, 0);
     helio_top_hsizer->Add( helio_top_vsizer, 0, wxALIGN_CENTER, 0 );
     helio_top_background->SetSizer(helio_top_hsizer);
     helio_top_background->Layout();

     //page 1
     wxBoxSizer* page1_sizer = new wxBoxSizer(wxVERTICAL);
     page1_panel = new wxPanel(this);
     page1_panel->SetBackgroundColour(*wxWHITE);

     wxWebView* m_vebview = WebView::CreateWebView(page1_panel, "");
     m_vebview->Bind(wxEVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, [this](const wxWebViewEvent& evt) {
         open_url(evt.GetString().ToStdString());
     });

     std::string phurl1;
     std::string phurl2;
     if (GUI::wxGetApp().app_config->get("region") == "China") {
         m_vebview->SetMinSize(wxSize(FromDIP(720), FromDIP(460)));
         m_vebview->SetMaxSize(wxSize(FromDIP(720), FromDIP(460)));
         phurl1 = "web/helio/helio_service_cn.html";
         phurl2 = "web/helio/helio_service_snote_cn.html";
     }
     else {
         m_vebview->SetMinSize(wxSize(FromDIP(720), FromDIP(650)));
         m_vebview->SetMaxSize(wxSize(FromDIP(720), FromDIP(650)));
         phurl1 = "web/helio/helio_service_en.html";
         phurl2 = "web/helio/helio_service_snote_en.html";
     }

     phurl1 += GUI::wxGetApp().dark_mode() ? "?darkmode=1" : "?darkmode=0";
     phurl2 += GUI::wxGetApp().dark_mode() ? "?darkmode=1" : "?darkmode=0";

     auto _language = GUI::into_u8(GUI::wxGetApp().current_language_code());
     fs::path ph(resources_dir());
     ph /= phurl1;
     if (!fs::exists(ph)) {
         ph =  fs::path(resources_dir());
         ph /= phurl1;
     }
     auto url = ph.string();
     std::replace(url.begin(), url.end(), '\\', '/');
     url = "file:///" + url;
     m_vebview->LoadURL(from_u8(url));


     page1_sizer->Add(m_vebview, 0, wxLEFT|wxRIGHT, FromDIP(33));
     page1_panel->SetSizer(page1_sizer);
     page1_panel->Layout();
     page1_panel->Fit();

     //page 2
     wxBoxSizer* page2_sizer = new wxBoxSizer(wxVERTICAL);
     page2_panel = new wxPanel(this);

     wxWebView* m_vebview2 = WebView::CreateWebView(page2_panel, "");
     m_vebview2->Bind(wxEVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, [this](const wxWebViewEvent& evt) {
         open_url(evt.GetString().ToStdString());
     });
     m_vebview2->SetMinSize(wxSize(FromDIP(720), FromDIP(200)));
     m_vebview2->SetMaxSize(wxSize(FromDIP(720), FromDIP(200)));

     fs::path ph2(resources_dir());
     ph2 /= phurl2;
     if (!fs::exists(ph2)) {
         ph2 = fs::path(resources_dir());
         ph2 /= phurl2;
     }
     auto url2 = ph2.string();
     std::replace(url2.begin(), url2.end(), '\\', '/');
     url2 = "file:///" + url2;
     m_vebview2->LoadURL(from_u8(url2));

     page2_sizer->Add(m_vebview2, 0, wxLEFT | wxRIGHT, FromDIP(33));
     page2_panel->SetSizer(page2_sizer);
     page2_panel->Layout();
     page2_panel->Fit();

     //page 3
     wxBoxSizer* page3_sizer = new wxBoxSizer(wxVERTICAL);
     wxBoxSizer* page3_content_sizer = new wxBoxSizer(wxVERTICAL);
     page3_panel = new wxPanel(this);
     auto page3_content_panel = new wxPanel(page3_panel);
     page3_content_panel->SetBackgroundColour(*wxWHITE);
     page3_content_panel->SetMinSize(wxSize(FromDIP(720), FromDIP(200)));
     page3_content_panel->SetMaxSize(wxSize(FromDIP(720), FromDIP(200)));

     auto enable_pat_title = new Label(page3_content_panel, Label::Head_14, _L("Helio Additive third - party software service feature has been successfully enabled!"));
     bold_font = enable_pat_title->GetFont();
     bold_font.SetWeight(wxFONTWEIGHT_BOLD);
     enable_pat_title->SetFont(bold_font);

     auto split_line = new wxPanel(page3_content_panel, wxID_ANY, wxDefaultPosition, wxSize(-1, 1), wxTAB_TRAVERSAL);
     split_line->SetMaxSize(wxSize(-1, FromDIP(1)));
     split_line->SetBackgroundColour(wxColour(236, 236, 236));

     wxBoxSizer* pat_token_sizer = new wxBoxSizer(wxHORIZONTAL);
     auto helio_pat_title = new Label(page3_content_panel, Label::Body_15, L("Helio-PAT"));
     helio_input_pat = new ::TextInput(page3_content_panel, wxEmptyString, wxEmptyString, wxEmptyString, wxDefaultPosition, wxDefaultSize, wxTE_PROCESS_ENTER | wxTE_RIGHT);
     helio_input_pat->SetFont(Label::Body_15);
     helio_input_pat->SetMinSize(wxSize(FromDIP(530), FromDIP(22)));
     helio_input_pat->SetMaxSize(wxSize(FromDIP(530), FromDIP(22)));
     helio_input_pat->Disable();
     wxString pat = Slic3r::HelioQuery::get_helio_pat();
     pat = wxString(pat.Length(), '*');
     helio_input_pat->SetLabel(pat);
     helio_pat_refresh = new wxStaticBitmap(page3_content_panel, wxID_ANY, create_scaled_bitmap("helio_refesh", page3_content_panel, 24), wxDefaultPosition, wxSize(FromDIP(24), FromDIP(24)), 0);
     helio_pat_refresh->Bind(wxEVT_ENTER_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_HAND); });
     helio_pat_refresh->Bind(wxEVT_LEAVE_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_ARROW); });
     helio_pat_refresh->Bind(wxEVT_LEFT_DOWN, [this](auto& e) {
        request_pat();
     });

     helio_pat_eview = new wxStaticBitmap(page3_content_panel, wxID_ANY, create_scaled_bitmap("helio_eview", page3_content_panel, 24), wxDefaultPosition, wxSize(FromDIP(24), FromDIP(24)), 0);
     helio_pat_eview->Bind(wxEVT_ENTER_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_HAND); });
     helio_pat_eview->Bind(wxEVT_LEAVE_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_ARROW); });
     helio_pat_eview->Bind(wxEVT_LEFT_DOWN, [this](auto& e) {
         wxString pat = helio_input_pat->GetLabel();
         pat = wxString(pat.Length(), '*');
         helio_input_pat->SetLabel(pat);
         show_pat_option("dview");
     });

     helio_pat_dview = new wxStaticBitmap(page3_content_panel, wxID_ANY, create_scaled_bitmap("helio_dview", page3_content_panel, 24), wxDefaultPosition, wxSize(FromDIP(24), FromDIP(24)), 0);
     helio_pat_dview->Bind(wxEVT_ENTER_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_HAND); });
     helio_pat_dview->Bind(wxEVT_LEAVE_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_ARROW); });
     helio_pat_dview->Bind(wxEVT_LEFT_DOWN, [this](auto& e) {
         helio_input_pat->SetLabel(Slic3r::HelioQuery::get_helio_pat());
         show_pat_option("eview");
     });

     helio_pat_copy = new wxStaticBitmap(page3_content_panel, wxID_ANY, create_scaled_bitmap("helio_copy", page3_content_panel, 24), wxDefaultPosition, wxSize(FromDIP(24), FromDIP(24)), 0);
     helio_pat_copy->Bind(wxEVT_ENTER_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_HAND); });
     helio_pat_copy->Bind(wxEVT_LEAVE_WINDOW, [this](auto& e) { SetCursor(wxCURSOR_ARROW); });


     helio_pat_copy->Bind(wxEVT_LEFT_DOWN, [this](auto& e) {
         bool copySuccess = false;
         if (wxTheClipboard->Open()){
             wxTheClipboard->Clear();
             wxTextDataObject* dataObj = new wxTextDataObject(Slic3r::HelioQuery::get_helio_pat());
             wxTheClipboard->SetData(dataObj);
             wxTheClipboard->Close();
         }
         MessageDialog msg(this, _L("Copy successful!"), _L("Copy"), wxOK | wxYES_DEFAULT);
         msg.ShowModal();
     });

     helio_pat_refresh->Hide();
     helio_pat_eview->Hide();
     helio_pat_dview->Hide();
     helio_pat_copy->Hide();

     pat_token_sizer->Add(helio_pat_title, 0, wxALIGN_CENTER, 0);
     pat_token_sizer->Add(0, 0, 0, wxLEFT, FromDIP(10));
     pat_token_sizer->Add(helio_input_pat, 0, wxALIGN_CENTER, 0);
     pat_token_sizer->Add(0, 0, 0, wxLEFT, FromDIP(10));
     pat_token_sizer->Add(helio_pat_eview, 0, wxALIGN_CENTER, 0);
     pat_token_sizer->Add(helio_pat_dview, 0, wxALIGN_CENTER, 0);
     pat_token_sizer->Add(helio_pat_refresh, 0, wxALIGN_CENTER, 0);
     pat_token_sizer->Add(0, 0, 0, wxLEFT, FromDIP(10));
     pat_token_sizer->Add(helio_pat_copy, 0, wxALIGN_CENTER, 0);

     //pat failed
     pat_err_label = new Label(page3_content_panel, Label::Body_14, wxEmptyString);
     pat_err_label->SetMinSize(wxSize(FromDIP(720), -1));
     pat_err_label->SetMaxSize(wxSize(FromDIP(720), -1));
     pat_err_label->Wrap(FromDIP(720));
     pat_err_label->SetForegroundColour(wxColour("#FC8800"));

     wxBoxSizer* helio_links_sizer = new wxBoxSizer(wxHORIZONTAL);
     LinkLabel* helio_home_link =  new LinkLabel(page3_content_panel, _L("Helio Additive"), "https://www.helioadditive.com/");
     LinkLabel* helio_privacy_link = nullptr;
     LinkLabel* helio_tou_link =  nullptr;

     if (GUI::wxGetApp().app_config->get("region") == "China") {
         helio_privacy_link = new LinkLabel(page3_content_panel, _L("Privacy Policy of Helio Additive"), "https://www.helioadditive.com/zh-cn/policies/privacy");
         helio_tou_link     = new LinkLabel(page3_content_panel, _L("Terms of Use of Helio Additive"), "https://www.helioadditive.com/zh-cn/policies/terms");
     }
     else {
         helio_privacy_link = new LinkLabel(page3_content_panel, _L("Privacy Policy of Helio Additive"), "https://www.helioadditive.com/en-us/policies/privacy");
         helio_tou_link     = new LinkLabel(page3_content_panel, _L("Terms of Use of Helio Additive"), "https://www.helioadditive.com/en-us/policies/terms");
     }

     helio_home_link->SetFont(Label::Body_13);
     helio_tou_link->SetFont(Label::Body_13);
     helio_privacy_link->SetFont(Label::Body_13);
     helio_home_link->SeLinkLabelFColour(wxColour(0, 119, 250));
     helio_tou_link->SeLinkLabelFColour(wxColour(0, 119, 250));
     helio_privacy_link->SeLinkLabelFColour(wxColour(0, 119, 250));

     helio_links_sizer->Add(helio_home_link, 0, wxLEFT, 0);
     helio_links_sizer->Add(helio_privacy_link, 0, wxLEFT, FromDIP(40));
     helio_links_sizer->Add(helio_tou_link, 0, wxLEFT, FromDIP(40));


     StateColor btn_bg_green = StateColor(std::pair<wxColour, int>(wxColour(61, 203, 115), StateColor::Hovered), std::pair<wxColour, int>(wxColour(0, 174, 66), StateColor::Normal));

     page3_content_sizer->Add(enable_pat_title, 0, wxTOP, FromDIP(2));
     page3_content_sizer->Add(0, 0, 0, wxTOP, FromDIP(14));
     page3_content_sizer->Add(split_line, 0, wxEXPAND, 0);
     page3_content_sizer->Add(0, 0, 0, wxTOP, FromDIP(20));
     page3_content_sizer->Add(pat_token_sizer, 0, wxEXPAND, 0);
     page3_content_sizer->Add(pat_err_label, 0, wxTOP, FromDIP(10));
     page3_content_sizer->Add(0, 0, 0, wxTOP, FromDIP(28));
     page3_content_sizer->Add(helio_links_sizer, 0, wxEXPAND, 0);
     page3_content_sizer->Add(0, 0, 0, wxTOP, FromDIP(12));
     //page3_content_sizer->Add(m_button_uninstall, 0, wxLEFT, 0);


     page3_content_panel->SetSizer(page3_content_sizer);
     page3_content_panel->Layout();
     page3_sizer->Add(page3_content_panel, 0, wxLEFT | wxRIGHT, FromDIP(33));
     page3_panel->SetSizer(page3_sizer);
     page3_panel->Layout();
     page3_panel->Fit();

     m_button_confirm = new Button(this, _L("Agree and proceed"));
     m_button_confirm->SetBackgroundColor(btn_bg_green);
     m_button_confirm->SetBorderColor(*wxWHITE);
     m_button_confirm->SetTextColor(wxColour(255, 255, 254));
     m_button_confirm->SetFont(Label::Body_12);
     m_button_confirm->SetSize(wxSize(FromDIP(58), FromDIP(26)));
     m_button_confirm->SetMinSize(wxSize(FromDIP(58), FromDIP(26)));
     m_button_confirm->SetCornerRadius(FromDIP(12));
     m_button_confirm->Bind(wxEVT_LEFT_DOWN, &HelioStatementDialog::on_confirm, this);

     m_button_cancel = new Button(this, _L("Got it"));
     m_button_cancel->SetBackgroundColor(btn_bg_green);
     m_button_cancel->SetBorderColor(*wxWHITE);
     m_button_cancel->SetTextColor(wxColour(255, 255, 254));
     m_button_cancel->SetFont(Label::Body_12);
     m_button_cancel->SetSize(wxSize(FromDIP(58), FromDIP(26)));
     m_button_cancel->SetMinSize(wxSize(FromDIP(58), FromDIP(26)));
     m_button_cancel->SetCornerRadius(FromDIP(12));
     m_button_cancel->Bind(wxEVT_LEFT_DOWN, [this](wxMouseEvent &e) { EndModal(wxID_NO); });


     wxBoxSizer* button_sizer = new wxBoxSizer(wxHORIZONTAL);
     button_sizer->Add(0, 0, 1, wxEXPAND, 0);
     button_sizer->Add(m_button_confirm, 0, 0, 0);
     button_sizer->Add(m_button_cancel, 0, wxLEFT, FromDIP(20));
     button_sizer->Add(0, 0, 0, wxRIGHT, FromDIP(50));

     main_sizer->Add(line, 0, wxEXPAND, 0);
     main_sizer->Add(helio_top_background, 0, wxEXPAND, 0);
     main_sizer->Add(0, 0, 0, wxTOP, FromDIP(16));
     main_sizer->Add(page1_panel, 0, wxEXPAND, 0);
     main_sizer->Add(page2_panel, 0, wxEXPAND, 0);
     main_sizer->Add(page3_panel, 0, wxEXPAND, 0);
     main_sizer->Add(0, 0, 0, wxTOP, FromDIP(15));
     main_sizer->Add(button_sizer, 0, wxEXPAND, 0);
     main_sizer->Add(0, 0, 0, wxTOP, FromDIP(16));

     //page show/hide

     if (GUI::wxGetApp().app_config->get("enable_helio_processing") == "true") {
         show_pat_page();
         request_pat();
         m_button_confirm->Hide();
     }
     else {
         show_agreement_page1();
         m_button_confirm->Show();
     }


     SetSizer(main_sizer);
     Layout();
     Fit();

     CentreOnParent();
     wxGetApp().UpdateDlgDarkUI(this);
 }

 void HelioStatementDialog::OnLoaded(wxWebViewEvent& event)
 {
     event.Skip();
 }

 void HelioStatementDialog::OnTitleChanged(wxWebViewEvent& event)
 {
     event.Skip();
 }
 void HelioStatementDialog::OnError(wxWebViewEvent& event)
 {
     event.Skip();
 }

void HelioStatementDialog::on_confirm(wxMouseEvent& e)
 {
    if (current_page == 0) {
        page1_agree = true;
        show_agreement_page2();
        m_button_confirm->Refresh();
    }
    else if (current_page == 1) {
        page2_agree = true;
        //m_button_uninstall->Show();
        m_button_confirm->Hide();
    }

    if (page1_agree && page2_agree) {
        wxGetApp().app_config->set_bool("enable_helio_processing", true);
        if (wxGetApp().getAgent()) {
            json j;
            j["operate"] = "switch";
            j["content"] = "enable";
            wxGetApp().getAgent()->track_event("helio_state", j.dump());
        }

        show_pat_page();
        request_pat();

        /*hide helio on main windows*/
        if (wxGetApp().mainframe->expand_program_holder) {
            wxGetApp().mainframe->expand_program_holder->ShowExpandButton(wxGetApp().mainframe->expand_helio_id, true);
            wxGetApp().mainframe->Layout();
        }
    }

    current_page++;
    Layout();
    Fit();
    CentreOnParent();
 }

void HelioStatementDialog::open_url(std::string type)
{
    std::string helio_home_link =  "https://www.helioadditive.com/";
    std::string helio_privacy_link;
    std::string helio_tou_link;

    if (GUI::wxGetApp().app_config->get("region") == "China") {
        helio_privacy_link = "https://www.helioadditive.com/zh-cn/policies/privacy";
        helio_tou_link =  "https://www.helioadditive.com/zh-cn/policies/terms";
    }
    else {
        helio_privacy_link = "https://www.helioadditive.com/en-us/policies/privacy";
        helio_tou_link = "https://www.helioadditive.com/en-us/policies/terms";
    }

    if (type == "helio_link_pp") {
        wxLaunchDefaultBrowser(helio_privacy_link);
    }
    else if (type == "helio_link_tou") {
        wxLaunchDefaultBrowser(helio_tou_link);
    }
    else if (type == "helio_link_home") {
        wxLaunchDefaultBrowser(helio_home_link);
    }
    else {
        wxLaunchDefaultBrowser(helio_home_link);
    }
}

void HelioStatementDialog::on_dpi_changed(const wxRect &suggested_rect)
{
}

void HelioStatementDialog::show_err_info(std::string type)
{
    if (type.empty()) {
        pat_err_label->Hide();
    }
    else {
        pat_err_label->Show();

        if (type == "error") {
            pat_err_label->SetLabel(_L("Failed to get Helio PAT, Click Refresh to obtain it again."));
        }
        else if (type == "not_enough") {
            pat_err_label->SetLabel(_L("Failed to obtain PAT. The quantity limit has been reached, so it cannot be obtained. Click the refresh button to re-obtain PAT."));
        }
    }
    Layout();
    Fit();
}

void HelioStatementDialog::show_pat_option(std::string opt)
{
    if (opt == "refresh") {
        helio_pat_refresh->Show();
        helio_pat_eview->Hide();
        helio_pat_dview->Hide();
        helio_pat_copy->Hide();
    }
    else if (opt == "eview") {
        helio_pat_refresh->Hide();
        helio_pat_eview->Show();
        helio_pat_dview->Hide();
        helio_pat_copy->Show();
    }
    else if (opt == "dview") {
        helio_pat_refresh->Hide();
        helio_pat_eview->Hide();
        helio_pat_dview->Show();
        helio_pat_copy->Show();
    }
    Layout();
    Fit();
}

void HelioStatementDialog::show_agreement_page1()
{
    page1_panel->Show();
    page2_panel->Hide();
    page3_panel->Hide();
}

void HelioStatementDialog::show_agreement_page2()
{
    page1_panel->Hide();
    page2_panel->Show();
    page3_panel->Hide();
}

void HelioStatementDialog::show_pat_page()
{
    page1_panel->Hide();
    page2_panel->Hide();
    page3_panel->Show();
}

void HelioStatementDialog::request_pat()
{
    show_err_info("");
    /*request helio pat*/
    std::string helio_api_key = Slic3r::HelioQuery::get_helio_pat();
    if (helio_api_key.empty()) {
        std::weak_ptr<int> weak_ptr = shared_ptr;
        wxGetApp().request_helio_pat([this, weak_ptr](std::string pat) {
            if (auto temp_ptr = weak_ptr.lock()) {
                if (pat == "not_enough") {
                    show_err_info("not_enough");
                    show_pat_option("refresh");
                } else if (pat == "error") {
                    show_err_info("error");
                    show_pat_option("refresh");
                } else {
                    Slic3r::HelioQuery::set_helio_pat(pat);
                    wxString wpat = wxString(pat.length(), '*');
                    helio_input_pat->SetLabel(wpat);
                    show_pat_option("dview");

                    /*request helio data*/
                    wxGetApp().request_helio_supported_data();
                }
            }
        });
    } else {
        show_err_info("");
        show_pat_option("dview");
    }
}

static int s_get_min_chamber_temp()// TODO, use the chamber of used filaments
{
    auto preset_full_config = wxGetApp().preset_bundle->full_config();
    auto chamber_temperatures = preset_full_config.option<ConfigOptionInts>("chamber_temperatures");

    if (chamber_temperatures)
    {
        int min_temp = std::numeric_limits<int>::max();
        for (auto val : chamber_temperatures->values)
        {
            if (val < min_temp)
            {
                min_temp = val;
            }
        }

        if (min_temp != std::numeric_limits<int>::max())
        {
            return min_temp;
        }
    }

    return 0;
}

static double s_round(double value, int n)
{
    double factor = std::pow(10.0, n);
    return std::round(value * factor) / factor;
}

 }} // namespace Slic3r::GUI
