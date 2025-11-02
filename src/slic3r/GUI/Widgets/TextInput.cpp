#include "TextInput.hpp"
#include "Label.hpp"
#include "TextCtrl.h"
#include "slic3r/GUI/Widgets/Label.hpp"

#include <wx/dcclient.h>
#include <wx/dcgraph.h>
#include "../MsgDialog.hpp"

BEGIN_EVENT_TABLE(TextInput, StaticBox)

EVT_PAINT(TextInput::paintEvent)

END_EVENT_TABLE()

/*
 * Called by the system of by wxWidgets when the panel needs
 * to be redrawn. You can also trigger this call by
 * calling Refresh()/Update().
 */

TextInput::TextInput()
    : label_color(std::make_pair(0x6B6B6B, (int) StateColor::Disabled),
                 std::make_pair(0x6B6B6B, (int) StateColor::Normal))
    , text_color(std::make_pair(0x6B6B6B, (int) StateColor::Disabled),
                 std::make_pair(0x262E30, (int) StateColor::Normal))
{
    radius = 0;
    border_width = 1;
    border_color = StateColor(std::make_pair(0xDBDBDB, (int) StateColor::Disabled), std::make_pair(0x009688, (int) StateColor::Hovered),
                              std::make_pair(0xDBDBDB, (int) StateColor::Normal));
    background_color = StateColor(std::make_pair(0xF0F0F1, (int) StateColor::Disabled), std::make_pair(*wxWHITE, (int) StateColor::Normal));
    SetFont(Label::Body_12);
}

TextInput::TextInput(wxWindow *     parent,
                     wxString       text,
                     wxString       label,
                     wxString       icon,
                     const wxPoint &pos,
                     const wxSize & size,
                     long           style,
					 wxString suffix_icon)
    : TextInput()
{
    Create(parent, text, label, icon, pos, size, style, suffix_icon);
}

void TextInput::Create(wxWindow *     parent,
                       wxString       text,
                       wxString       label,
                       wxString       icon,
                       const wxPoint &pos,
                       const wxSize & size,
                       long           style,
					   wxString suffix_icon)
{
        text_ctrl = nullptr;
    StaticBox::Create(parent, wxID_ANY, pos, size, style);
    wxWindow::SetLabel(label);
    style &= ~wxRIGHT;
    state_handler.attach({&label_color, & text_color});
    state_handler.update_binds();
    text_ctrl = new TextCtrl(this, wxID_ANY, text, {4, 4}, wxDefaultSize, style | wxBORDER_NONE | wxTE_PROCESS_ENTER);
    text_ctrl->SetFont(Label::Body_14);
    text_ctrl->SetInitialSize(text_ctrl->GetBestSize());
    text_ctrl->SetBackgroundColour(background_color.colorForStates(state_handler.states()));
    text_ctrl->SetForegroundColour(text_color.colorForStates(state_handler.states()));
    state_handler.attach_child(text_ctrl);
    text_ctrl->Bind(wxEVT_KILL_FOCUS, [this](auto &e) {
        OnEdit();
        e.SetId(GetId());
        ProcessEventLocally(e);
        e.Skip();
    });
    text_ctrl->Bind(wxEVT_TEXT_ENTER, [this](auto &e) {
        OnEdit();
        e.SetId(GetId());
        ProcessEventLocally(e);
    });
    text_ctrl->Bind(wxEVT_RIGHT_DOWN, [this](auto &e) {}); // disable context menu
    if (!icon.IsEmpty()) {
        this->icon = ScalableBitmap(this, icon.ToStdString(), 16);
    }
    if (!suffix_icon.IsEmpty()) {
        this->suffix_icon = ScalableBitmap(this, suffix_icon.ToStdString(), 16);
    }
    messureSize();
}

void TextInput::SetCornerRadius(double radius)
{
    this->radius = radius;
    Refresh();
}

void TextInput::SetLabel(const wxString& label)
{
    wxWindow::SetLabel(label);
    messureSize();
    Refresh();
}

void TextInput::SetIcon(const wxBitmap &icon)
{
    this->icon = ScalableBitmap();
    this->icon.bmp() = icon;
    Rescale();
}

void TextInput::SetSuffixIcon(const wxBitmap &icon)
{
    this->suffix_icon = ScalableBitmap();
    this->suffix_icon.bmp() = icon;
    Rescale();
}

void TextInput::SetIcon(const wxString &icon)
{
    if (this->icon.name() == icon.ToStdString())
        return;
    this->icon = ScalableBitmap(this, icon.ToStdString(), 16);
    Rescale();
}

void TextInput::SetSuffixIcon(const wxString &icon)
{
    if (this->suffix_icon.name() == icon.ToStdString())
        return;
    this->suffix_icon = ScalableBitmap(this, icon.ToStdString(), 16);
    Rescale();
}

void TextInput::SetLabelColor(StateColor const &color)
{
    label_color = color;
    state_handler.update_binds();
}

void TextInput::SetTextColor(StateColor const& color)
{
    text_color= color;
    state_handler.update_binds();
}

void TextInput::Rescale()
{
    if (!this->icon.name().empty())
        this->icon.msw_rescale();
    messureSize();
    Refresh();
}

bool TextInput::Enable(bool enable)
{
    bool result = text_ctrl->Enable(enable) && wxWindow::Enable(enable);
    if (result) {
        wxCommandEvent e(EVT_ENABLE_CHANGED);
        e.SetEventObject(this);
        GetEventHandler()->ProcessEvent(e);
        text_ctrl->SetBackgroundColour(background_color.colorForStates(state_handler.states()));
        text_ctrl->SetForegroundColour(text_color.colorForStates(state_handler.states()));
    }
    return result;
}

void TextInput::SetMinSize(const wxSize& size)
{
    wxSize size2 = size;
    if (size2.y < 0) {
#ifdef __WXMAC__
        if (GetPeer()) // peer is not ready in Create on mac
#endif
        size2.y = GetSize().y;
    }
    wxWindow::SetMinSize(size2);
}

void TextInput::DoSetSize(int x, int y, int width, int height, int sizeFlags)
{
    wxWindow::DoSetSize(x, y, width, height, sizeFlags);
    if (sizeFlags & wxSIZE_USE_EXISTING) return;
    wxSize size = GetSize();
    wxPoint textPos = {5, 0};
    if (this->icon.bmp().IsOk()) {
        wxSize szIcon = this->icon.GetBmpSize();
        textPos.x += szIcon.x;
    }
    bool align_right = GetWindowStyle() & wxRIGHT;
    if (align_right)
        textPos.x += labelSize.x;
    if (text_ctrl) {
        wxSize textSize = text_ctrl->GetSize();
        textSize.x = size.x - textPos.x - labelSize.x - 10;
        text_ctrl->SetSize(textSize);
        text_ctrl->SetPosition({textPos.x, (size.y - textSize.y) / 2});
    }
}

void TextInput::DoSetToolTipText(wxString const &tip)
{
    wxWindow::DoSetToolTipText(tip);
    text_ctrl->SetToolTip(tip);
}

void TextInput::paintEvent(wxPaintEvent &evt)
{
    // depending on your system you may need to look at double-buffered dcs
    wxPaintDC dc(this);
    render(dc);
}

/*
 * Here we do the actual rendering. I put it in a separate
 * method so that it can work no matter what type of DC
 * (e.g. wxPaintDC or wxClientDC) is used.
 */
void TextInput::render(wxDC& dc)
{
    StaticBox::render(dc);
    int states = state_handler.states();
    wxSize size = GetSize();
    bool   align_right = GetWindowStyle() & wxRIGHT;
    // start draw
    wxPoint pt = {5, 0};
    if (icon.bmp().IsOk()) {
        wxSize szIcon = icon.GetBmpSize();
        pt.y = (size.y - szIcon.y) / 2;
        dc.DrawBitmap(icon.bmp(), pt);
        pt.x += szIcon.x + 0;
    }
    auto text = wxWindow::GetLabel();
    if (!text.IsEmpty()) {

		wxSize margin_size = dc.GetMultiLineTextExtent(" ");
        wxSize textSize = text_ctrl->GetSize();
        if (align_right) {
            if (pt.x + labelSize.x > size.x)
                text = wxControl::Ellipsize(text, dc, wxELLIPSIZE_END, size.x - pt.x);
            pt.y = (size.y - labelSize.y) / 2;
        } else {
            pt.x += textSize.x;
            pt.y = (size.y + textSize.y) / 2 - labelSize.y;
        }
        dc.SetTextForeground(label_color.colorForStates(states));
        if(align_right)
            dc.SetFont(GetFont());
        else
            dc.SetFont(Label::Body_12);
        dc.DrawText(text, pt);

		if (suffix_icon.bmp().IsOk()) {
            wxSize tSize = dc.GetMultiLineTextExtent(text);
			pt.x += tSize.x + margin_size.x;
			wxSize szIcon = suffix_icon.GetBmpSize();
			pt.y = (size.y - szIcon.y) / 2;
			dc.DrawBitmap(suffix_icon.bmp(), pt);
		}

    }
}

void TextInput::messureSize()
{
    wxSize size = GetSize();
    wxClientDC dc(this);
    bool   align_right = GetWindowStyle() & wxRIGHT;
    if (align_right)
        dc.SetFont(GetFont());
    else
        dc.SetFont(Label::Body_12);
    labelSize = dc.GetTextExtent(wxWindow::GetLabel());
    wxSize textSize = text_ctrl->GetSize();
    int h = textSize.y + 8;
    if (size.y < h) {
        size.y = h;
    }
    wxSize minSize = size;
    minSize.x = GetMinWidth();
    SetMinSize(minSize);
    SetSize(size);
}

bool TextInput::CheckValid(bool pop_dlg) const
{
    for (auto checker : m_checkers) {
        wxString error_msg = checker->CheckValid(text_ctrl->GetValue());
        if (!error_msg.IsEmpty()) {
            text_ctrl->SetBackgroundColour(wxColour(255, 220, 220));
            text_ctrl->SetToolTip(error_msg);
            text_ctrl->Refresh();

            if (pop_dlg) {
                Slic3r::GUI::MessageDialog dlg(nullptr, error_msg, _L("Error"), wxOK | wxICON_WARNING);
                dlg.ShowModal();
            }

            return false;
        }
    }

    text_ctrl->SetBackgroundColour(*wxWHITE);
    text_ctrl->SetToolTip(wxEmptyString);
    text_ctrl->Refresh();
    return true;
}

std::shared_ptr<TextInputValChecker> TextInputValChecker::CreateIntMinChecker(int val)
{
    return std::make_shared<TextInputValIntMinChecker>(val);
}

wxString TextInputValIntMinChecker::CheckValid(const wxString& value) const
{
    long num;
    if (value.ToLong(&num) && num >= m_min_value) {
        return wxEmptyString;
    }
    return wxString::Format(_L("Please input a number greater than or equal to %d"), m_min_value);
}

std::shared_ptr<TextInputValChecker> TextInputValChecker::CreateIntRangeChecker(int min, int max)
{
    return std::make_shared<TextInputValIntRangeChecker>(min, max);
}

std::shared_ptr<TextInputValChecker> TextInputValChecker::CreateDoubleMinChecker(double min)
{
    return std::make_shared<TextInputValDoubleMinChecker>(min);
}

std::shared_ptr<TextInputValChecker> TextInputValChecker::CreateDoubleRangeChecker(double min, double max, bool enable)
{
    return std::make_shared<TextInputValDoubleRangeChecker>(min, max, enable);
}

wxString TextInputValIntRangeChecker::CheckValid(const wxString& value) const
{
    long num;
    if (value.ToLong(&num) && num >= m_min_value && num <= m_max_value) {
        return wxEmptyString;
    }
    return wxString::Format(_L("Please enter a number between %d and %d."), m_min_value, m_max_value);
}

wxString TextInputValDoubleMinChecker::CheckValid(const wxString& value) const
{
    double num;
    if (value.ToDouble(&num) && num >= m_min_value) {
        return wxEmptyString;
    }
    return wxString::Format(_L("Please enter a float greater than or equal to %f."), m_min_value);
}

wxString TextInputValDoubleRangeChecker::CheckValid(const wxString& value) const
{
    if (m_enable_empty && value.empty()) {
        return wxEmptyString;
    }

    double num;
    if (value.ToDouble(&num) && num >= m_min_value && num <= m_max_value) {
        return wxEmptyString;
    }
    return wxString::Format(_L("Please enter a float between %f and %f."), m_min_value, m_max_value);
}
