# Helio Integration Map

> Auto-generated from diff: `orca-latest-parity-bambu` vs `v2.3.2-rc2`
> This is the authoritative reference for AI agents resolving merge conflicts or build fixes.
> Updated for the v2.4.0-beta upstream sync: upstream added `acceleration` and `jerk`
> visualization fields that sit **between** `pressure_advance` and the Helio
> `thermal_index_*` fields in `PathVertex` (libvgcode) and `MoveVertex` (GCodeProcessor).
> All positional aggregate initializers (Rule 5) must keep that order:
> `..., pressure_advance, acceleration, jerk, thermal_index_mean, thermal_index_min, thermal_index_max`.
> The `EViewType` enum likewise orders `Acceleration, Jerk` before `ThermalIndexMean/Min/Max`.
> Also note: v2.4.0 refactored `GCodeViewer.cpp` tooltips into a `properties_rows`
> vector and moved the status-bar text into a `detail_buf` switch in
> `render_position_window()` — the Helio TI rows/cases live there now.

## Stats
- **70 files changed**: 36 new, 34 modified, 0 deleted
- **+13,363 lines added, -195 lines removed** — measured at the v2.4.0-beta sync.
  The support-data catalog work (#95) adds ~1,000 further lines in the four new
  `HelioSupportData` / `HelioRetryPolicy` files, plus the region-change hook in
  `WebGuideDialog.cpp`.

## Architecture

Event-driven cloud slicing pipeline:

```
"Slice with Helio" button (MainFrame)
  → EVT_HELIO_INPUT_DLG
  → HelioInputDialog (mode selection, material/printer matching)
  → on_helio_process() (V2 single-material or V3 multi-material dispatch)
  → HelioBackgroundProcess (GraphQL API polling via HelioDragon)
  → EVT_HELIO_PROCESSING_COMPLETED
  → GCode swap (rename original, copy Helio result)
  → Preview reload with ThermalIndex view
```

Key data flow:
- `HelioQuery` (HelioDragon.hpp) — API client, PAT auth, supported printer/material cache
- `HelioBackgroundProcess` — thread wrapper, polls job status, parses result gcode
- `HelioPlateResult` — per-plate result storage on `PartPlate`
- `HelioCompletionEvent` — carries result path + quality metrics to UI thread
- Thermal Index — parsed from `;helioadditive=` gcode comments in `GCodeProcessor`

## Helio-Only Files (36 files — NEVER exist upstream, always preserve)

### Core API Client

| File | Purpose |
|-|-|
| `src/slic3r/Utils/HelioDragon.hpp` | API client declarations: `HelioQuery`, `HelioBackgroundProcess`, `HelioPlateResult`, GraphQL types |
| `src/slic3r/Utils/HelioDragon.cpp` | Full API implementation: auth, job dispatch, polling, gcode download, supported data cache |

### Support Data Catalog
Added by #95 (port of BambuStudio #63) — replaces the old thread-unsafe static
vector/bool cache that produced false "Unsupported Materials" errors.

| File | Purpose |
|-|-|
| `src/slic3r/Utils/HelioSupportData.hpp` | `SupportDataCatalogStore` declaration: snapshot-based catalog, `SupportDataLoadState` / `SupportDataAvailability` state machine, generation tagging, pending-refresh handoff |
| `src/slic3r/Utils/HelioSupportData.cpp` | Store implementation: paginated loading with per-page retries, bounded pagination restarts, `invalidate()` revoking in-flight runs, publish/fail guarded by run generation |
| `src/slic3r/Utils/HelioRetryPolicy.hpp` | Retry classification declarations for Helio HTTP/GraphQL responses |
| `src/slic3r/Utils/HelioRetryPolicy.cpp` | `helio_classify_retry` / `helio_classify_graphql_response`: transient vs terminal failure classification |

Readers must go through `HelioQuery::supported_printers_snapshot()` /
`HelioQuery::supported_materials_snapshot()` and gate on
`HelioQuery::supported_data_availability()` — never on a bare "fetched" bool.
Credential and endpoint changes must call
`HelioQuery::invalidate_support_data_for_endpoint_change()` (region) or go
through `HelioQuery::set_helio_pat()` (PAT), both of which bump the credential
generation so work started under the old credential can never land.

### UI Dialogs

| File | Purpose |
|-|-|
| `src/slic3r/GUI/HelioReleaseNote.hpp` | All Helio dialog declarations: `HelioInputDialog`, `HelioResultDialog`, `HelioStatusNotification` |
| `src/slic3r/GUI/HelioReleaseNote.cpp` | Dialog implementations (4334 lines): mode selection, progress, results with TI visualization. `on_confirm()` calls `ShowExpandButton()` to show Helio button immediately after install (mirrors `on_uninstall()` hide logic) |
| `src/slic3r/GUI/HelioHistoryDialog.hpp` | History dialog declaration |
| `src/slic3r/GUI/HelioHistoryDialog.cpp` | History dialog: lists past Helio jobs, re-download results |

### Widgets

| File | Purpose |
|-|-|
| `src/slic3r/GUI/Widgets/LinkLabel.hpp` | Clickable hyperlink label widget declaration |
| `src/slic3r/GUI/Widgets/LinkLabel.cpp` | LinkLabel implementation |

### Resources

| File | Purpose |
|-|-|
| `resources/images/expand_helio.png` | Helio button icon (toolbar) |
| `resources/images/expand_program.svg` | Program expand button icon |
| `resources/images/helio_icon.svg` | Helio brand icon |
| `resources/images/helio_icon_dark.svg` | Dark theme variant |
| `resources/images/helio_icon_disable.svg` | Disabled state icon |
| `resources/images/helio_loading.svg` | Loading spinner |
| `resources/images/helio_advanced_option0.svg` | Advanced option icon (off) |
| `resources/images/helio_advanced_option1.svg` | Advanced option icon (on) |
| `resources/images/helio_copy.svg` | Copy icon |
| `resources/images/helio_dview.svg` | Detail view icon |
| `resources/images/helio_eview.svg` | Expanded view icon |
| `resources/images/helio_feature_check.svg` | Feature check icon |
| `resources/images/helio_feature_shield_check.svg` | Shield check icon |
| `resources/images/helio_feature_speed.svg` | Speed feature icon |
| `resources/images/helio_refesh.svg` | Refresh icon |
| `resources/images/helio_switch_send_mode_tag_on.svg` | Toggle tag icon |
| `resources/web/helio/helio_service_cn.html` | Service terms (Chinese) |
| `resources/web/helio/helio_service_en.html` | Service terms (English) |
| `resources/web/helio/helio_service_snote_cn.html` | Service notes (Chinese) |
| `resources/web/helio/helio_service_snote_en.html` | Service notes (English) |
| `resources/data/helio_hints.ini` | First-time tutorial hint text |

### CI/CD Workflows (Helio-only)

| File | Purpose |
|-|-|
| `.github/workflows/helio-release.yml` | Release workflow: builds all platforms, creates GitHub Release with Helio-prefixed assets. Triggers on merged PR with `release` label or manual `workflow_dispatch` (restricted to `orca-latest-parity-bambu`) |
| `.github/workflows/helio-upstream-sync.yml` | Upstream sync: merges upstream changes, creates conflict issues (labeled `claude-work`), creates sync PRs |
| `.github/workflows/helio-upstream-watch.yml` | Monitors upstream for new tags/releases, creates tracking issues |
| `.github/workflows/helio-workflow-inventory.yml` | Enforces the workflow inventory manifest (see Rule 12) |
| `.github/helio-workflows.yml` | The inventory manifest itself — fork policy for every workflow in the repo |
| `scripts/helio/check_workflow_inventory.py` | Validator behind the inventory workflow |

## Modified Files (34 files — conflict risk, detailed per-file guide)

### CRITICAL RISK

#### `src/slic3r/GUI/Plater.cpp` (+2319/-182)
The heaviest modification. Contains the entire Helio processing pipeline.

**Includes added** (after existing includes):
- `#include <thread>`, `#include <boost/nowide/cstdio.hpp>`, `#include <wx/choicdlg.h>`
- `#include "../Utils/HelioDragon.hpp"`, `#include "HelioReleaseNote.hpp"`

**Global/static additions** (after `namespace GUI {`):
- `g_helio_pre_select_optimization` flag + `get_helio_pre_select_optimization_flag()`

**Event definitions** (after `EVT_PRINT_FROM_SDCARD_VIEW`):
- `EVT_HELIO_INPUT_DLG`, `EVT_HELIO_PROCESSING_STARTED`, `EVT_HELIO_PROCESSING_COMPLETED`

**Members added to `Plater::priv`** (after `background_process`):
- `helio_background_process`, `helio_elements_fetched`, `helio_processing_disabled`, `helio_using_reference_material`

**Method declarations added to `Plater::priv`** (after `on_slicing_began()`):
- `on_helio_processing_complete()`, `on_helio_processing_start()`, `on_helio_input_dlg()`
- `on_helio_process()`, `on_action_helio_processing()`
- `update_helio_background_process_v2()`, `update_helio_background_process()`

**Event bindings** (in `priv::priv()` constructor, after `EVT_ADD_CUSTOM_FILAMENT`):
- `EVT_HELIO_PROCESSING_COMPLETED`, `EVT_HELIO_PROCESSING_STARTED`, `EVT_HELIO_INPUT_DLG`, `EVT_GLTOOLBAR_ACTION_HELIO`

**Interleaved modifications to `restart_background_process()`**:
- Two insertion points: auto-stop running helio + clear helio result before reslice
- Located at the two `if (this->background_process.start())` blocks

**Modified call in `on_slicing_update()`**:
- `set_slicing_progress_percentage()` gains `evt.status.is_helio` third argument

**Large block insertion after `on_slicing_completed()`** (~1970 lines):
- Replaces/relocates `on_export_began()` and `on_export_finished()`
- All Helio handler implementations: `on_helio_processing_complete()`, `on_helio_processing_start()`, `on_helio_input_dlg()`, `on_helio_process()`
- Helper structs: `FilamentSupportInfo`, matching functions, dialog classes
- V2/V3 dispatch: `update_helio_background_process_v2()`, `update_helio_background_process()`

**Destructor and cleanup** (at end of file):
- `Plater::~Plater()` — stops helio background thread
- Clear helio result on gcode load and reslice

#### `src/slic3r/GUI/Plater.hpp` (+30/-1)
- Added `#include <optional>`, forward declaration `class HelioCompletionEvent`
- Event declarations: `EVT_HELIO_INPUT_DLG`, `EVT_HELIO_PROCESSING_STARTED`, `EVT_HELIO_PROCESSING_COMPLETED`
- Changed `~Plater() = default` → `~Plater()`
- Added public methods: `stop_helio_process()`, `feedback_helio_process()`, `get_helio_process_status()`, material/printer getters/setters, `has_helio_simulation_result()`, `show_helio_simulation_summary()`

### HIGH RISK

#### `src/slic3r/GUI/MainFrame.cpp` (+67/-1)
- Added includes: `SwitchButton.hpp`, `HelioReleaseNote.hpp`, `HelioHistoryDialog.hpp`
- **In `create_side_tools()`**: Added `ExpandButtonHolder` with helio button, event binding for `EVT_HELIO_INPUT_DLG`, visibility toggle based on `enable_helio_processing` config, rich tooltip
- **In slice dropdown**: Added "Slice with Helio" `SideButton` (guarded by `enable_helio_processing`)
- **In Help menu**: Added "Helio History" menu item

#### `src/slic3r/GUI/MainFrame.hpp` (+6)
- Added `#include "Widgets/SwitchButton.hpp"`
- Members: `expand_program_id`, `expand_helio_id`, `split_line_icon`, `expand_program_holder`

#### `src/slic3r/GUI/GCodeViewer.cpp` (+45)
- **In view type name function**: 3 new `else if` branches for `ThermalIndexMean/Min/Max`
- **In tooltip render**: TI value display block (3 `append_table_row` calls)
- **In status bar format**: 3 new `case` branches in switch statement

#### `src/slic3r/GUI/GCodeViewer.hpp` (+7)
- Syncs dropdown selection index when view type changes programmatically (prevents dropdown/view desync)

#### `src/slic3r/GUI/LibVGCode/LibVGCodeWrapper.cpp` (+8/-8)
- **4 positional initializer lists modified**: appended `curr.thermal_index_mean, curr.thermal_index_min, curr.thermal_index_max` to `PathVertex` aggregate initializations
- Very fragile — if upstream changes `PathVertex` fields or reorders initializer, these break

### MEDIUM RISK

#### `src/slic3r/GUI/NotificationManager.cpp` (+56/-2)
- Added `#include <sstream>`
- New method: `push_helio_error_notification()` — rich error formatting with numbered list and URL extraction
- Modified: `set_slicing_progress_began()` and `set_slicing_progress_percentage()` — added `bool is_helio` parameter

#### `src/slic3r/GUI/NotificationManager.hpp` (+8/-2)
- Added `HelioSlicingError` enum value in `NotificationType`
- Added `push_helio_error_notification()` declaration
- Modified signatures: `set_slicing_progress_began(bool is_helio = false)`, `set_slicing_progress_percentage(..., bool is_helio = false)`

#### `src/slic3r/GUI/Preferences.cpp` (+79)
- Added `#include "../Utils/HelioDragon.hpp"`
- **New "Helio" tab** appended to preferences: enable toggle, PAT input (password field), multi-material toggle, API URL display
- **Toggle listener**: `enable_helio_processing` toggle immediately shows/hides the Helio button in MainFrame via `ShowExpandButton()` + `Layout()` (no restart required)
- **Region combobox**: both region-write paths call `HelioQuery::invalidate_support_data_for_endpoint_change()` — region selects both the Helio endpoint and which regional PAT key is read, so the previous endpoint's catalogs must be dropped

#### `src/slic3r/GUI/GUI_App.cpp` (+28)
- Added `#include "../Utils/HelioDragon.hpp"`
- The startup block always requests the Helio supported-data catalogs (no "already loaded" guard)
- New methods: `is_helio_enable()`, `request_helio_pat()`, `request_helio_supported_data(bool force_refresh = false)`
- `OnExit()` calls `HelioQuery::shutdown_background_requests()` so support-data
  workers are torn down cleanly — keep this line when upstream reworks `OnExit()`

#### `src/slic3r/GUI/GUI_App.hpp` (+4)
- 4 method declarations: `is_helio_enable()`, `request_helio_pat()`, `request_helio_supported_data(bool force_refresh = false)`

#### `src/slic3r/GUI/PartPlate.cpp` (+27)
- Added `#include "../Utils/HelioDragon.hpp"`
- New methods appended: `get_helio_result()`, `set_helio_result()`, `clear_helio_result()`, `has_helio_result()`

#### `src/slic3r/GUI/PartPlate.hpp` (+19)
- Added `#include <memory>`, forward declaration `struct HelioPlateResult`
- New members: `m_helio_apply_invalid`, `m_helio_result` (unique_ptr)
- New inline methods: `can_helio_slice()`, `is_helio_apply_result_invalid()`, `update_helio_apply_result_invalid()`
- New declared methods: `get_helio_result()`, `set_helio_result()`, `clear_helio_result()`, `has_helio_result()`

#### `src/slic3r/GUI/BackgroundSlicingProcess.hpp` (+25)
- New class appended: `HelioCompletionEvent` (wxEvent subclass with path, success, quality metrics)

#### `src/libslic3r/GCode/GCodeProcessor.cpp` (+18)
- **In `process_G1()`**: Thermal index parsing block — extracts `ti.max/min/mean` from `;helioadditive=` comments using regex
- Sets `m_is_helio_gcode` flag when helio comments found

#### `src/libslic3r/GCode/GCodeProcessor.hpp` (+4)
- Added to `GCodeProcessorResult`: `bool is_helio_gcode`
- Added to `MoveVertex`: `thermal_index_mean/min/max` floats
- Added member variables: `m_thermal_index_mean/min/max`, `m_is_helio_gcode`

#### `src/libvgcode/src/ViewerImpl.cpp` (+33)
- **3 switch statements**: Added `ThermalIndexMean/Min/Max` cases in `get_vertex_color()`, `get_range()`, `set_palette()`
- Added size calculation for 3 new `ColorRange` members

#### `src/libvgcode/src/ViewerImpl.hpp` (+2)
- 3 new members: `m_thermal_index_mean_range`, `m_thermal_index_min_range`, `m_thermal_index_max_range`

#### `src/slic3r/GUI/Widgets/TextInput.hpp` (+63)
- Added `#include <memory>`, `#include <vector>`, forward declaration
- New member: `m_checkers` vector, `SetValCheckers()`, `CheckValid()`
- New class hierarchy appended: `TextInputValChecker` (base), `TextInputValIntMinChecker`, `TextInputValIntRangeChecker`, `TextInputValDoubleMinChecker`, `TextInputValDoubleRangeChecker`

#### `src/slic3r/GUI/Widgets/TextInput.cpp` (+68)
- Added includes: `I18N.hpp`, `MsgDialog.hpp`
- Implementations appended: `TextInputValChecker::Create*()` factory methods, `TextInput::CheckValid()`

### LOW RISK

#### `src/libslic3r/AppConfig.cpp` (+25)
- **Appended** defaults block in `set_defaults()`: `helio_api_url`, `enable_helio_processing` (defaults to `false`), `helio_api_china`, `helio_api_other`, `helio_multimaterial_enabled`, `helio_first_time_tutorial`

#### `src/libslic3r/PrintBase.hpp` (+1)
- Added `bool is_helio { false }` to `SlicingStatus` struct

#### `src/libslic3r/PrintConfig.cpp` (+21)
- Appended 3 config definitions: `helio_printer_id` (string), `helio_initial_room_air_temp` (float), `helio_layer_threshold` (float)

#### `src/libvgcode/include/PathVertex.hpp` (+4)
- Appended 3 floats to `PathVertex` struct: `thermal_index_mean/min/max`

#### `src/libvgcode/include/Types.hpp` (+2)
- Appended 3 enum values to `EViewType`: `ThermalIndexMean`, `ThermalIndexMin`, `ThermalIndexMax`

#### `src/slic3r/CMakeLists.txt` (+12)
- Appended 12 source file entries (6 hpp + 6 cpp for Helio files), including
  `Utils/HelioSupportData.{cpp,hpp}` and `Utils/HelioRetryPolicy.{cpp,hpp}`

#### `src/slic3r/GUI/WebGuideDialog.cpp` (+7)
- Added `#include "slic3r/Utils/HelioDragon.hpp"`
- `GuideFrame::SaveProfile()` writes `region` directly (a second setter alongside
  Preferences), so it calls `HelioQuery::invalidate_support_data_for_endpoint_change()`
  when the region actually changed — otherwise catalogs from the previous endpoint
  survive a wizard-driven region switch

#### `src/slic3r/GUI/GLCanvas3D.cpp` (+4/-1)
- Null-guard fix: added `get_notification_manager()` null check in existing condition
- `_update_imgui_select_plate_toolbar()` takes a `force` flag. `IMToolbar::is_render_finish`
  is set at the end of every plate-toolbar render and is only cleared by
  `set_enabled(false)` (i.e. when the preview panel is left), so any refresh
  requested while the preview is already showing was silently dropped. The Helio
  completion path never leaves the preview panel — `select_tab_silent()` uses
  `ChangeSelection` and `set_current_panel(preview, true)` re-enables the toolbar
  without resetting the flag — so the plate items stayed stuck with whatever
  textures they had when `on_idle` first built them (none, if that happened before
  the thumbnails were rendered) and the plate preview rendered black forever.
  The explicit refresh entry points (`update_plate_thumbnails()`, `on_set_focus()`
  on the preview canvas) now pass `force = true`; the idle path still uses the
  cache, so textures are not regenerated every frame.

#### `src/slic3r/GUI/GLToolbar.cpp` (+1)
- Added `wxDEFINE_EVENT(EVT_GLTOOLBAR_ACTION_HELIO, SimpleEvent)`

#### `src/slic3r/GUI/GLToolbar.hpp` (+1)
- Added `wxDECLARE_EVENT(EVT_GLTOOLBAR_ACTION_HELIO, SimpleEvent)`

#### `src/slic3r/GUI/Selection.cpp` (+4/-1)
- Shutdown guard: wrapped `handle_sidebar_focus_event` call in `is_closing()` + null checks

#### `src/slic3r/GUI/Widgets/SwitchButton.cpp` (+469)
- **Appended** entire `CustomToggleButton` class + `ExpandButtonHolder` class (no upstream entanglement)

#### `src/slic3r/GUI/Widgets/SwitchButton.hpp` (+96)
- **Appended** declarations for `CustomToggleButton`, `ExpandButtonHolder`, `wxEXPAND_LEFT_DOWN` event

## Conflict Resolution Rules

### Rule 1: Helio-Only Files
Never touched by upstream. If they appear in conflicts, something went very wrong — flag for human review.

### Rule 2: Appended Code (Low Risk)
Files where Helio code is appended at end: `SwitchButton.cpp/hpp`, `AppConfig.cpp`, `CMakeLists.txt`, `PrintConfig.cpp`, `PartPlate.cpp`, `TextInput.cpp/hpp`, `BackgroundSlicingProcess.hpp`.
- Usually conflict-free
- If upstream reformatted the file, just re-append the Helio block
- If upstream added entries to the same list (e.g., CMakeLists), merge both additions

### Rule 3: Interleaved Code (Critical/High Risk)
Files where Helio code is inserted within upstream functions: `Plater.cpp`, `MainFrame.cpp`.

**Plater.cpp rules:**
- Preserve ALL `EVT_HELIO_*` event definitions and bindings
- Preserve ALL `helio_*` member variables in `Plater::priv`
- The `restart_background_process()` helio insertions are at two specific locations — find the `background_process.start()` calls and re-insert before them
- The large handler block goes after `on_slicing_completed()` — find that function and insert after it
- If upstream renamed `get_slice_result()`, update Helio calls to match
- If upstream added parameters to functions Helio calls, add defaults

**MainFrame.cpp rules:**
- `ExpandButtonHolder` creation goes in `create_side_tools()`
- "Slice with Helio" button goes in the slice dropdown creation
- "Helio History" menu item goes in Help menu
- All guarded by `enable_helio_processing` config check

### Rule 4: Switch Statement Cases
Files: `GCodeViewer.cpp`, `ViewerImpl.cpp`.
- Add `ThermalIndexMean/Min/Max` cases alongside upstream's existing cases
- If upstream reordered `EViewType` enum, match new order
- If upstream added new view types, ensure TI cases don't conflict

### Rule 5: Positional Initializer Lists
File: `LibVGCodeWrapper.cpp`.
- 4 `PathVertex` aggregate initializations have `thermal_index_mean/min/max` appended
- If upstream changes `PathVertex` struct layout, these MUST be reordered to match
- If upstream switches from aggregate to designated initializers, convert accordingly

### Rule 6: Modified Function Signatures
Files: `NotificationManager.hpp/cpp`.
- `set_slicing_progress_began(bool is_helio = false)` — preserve default parameter
- `set_slicing_progress_percentage(..., bool is_helio = false)` — preserve default parameter
- If upstream adds its own parameters, add `is_helio` after them with default

### Rule 7: Struct Member Additions
Files: `GCodeProcessor.hpp`, `PathVertex.hpp`, `Types.hpp`, `PrintBase.hpp`.
- Members are appended to existing structs — low conflict risk
- If upstream reorders the struct, append Helio members at the end of the new layout

### Rule 8: Include Ordering
Helio includes go after the last upstream include in the same category:
- `#include "../Utils/HelioDragon.hpp"` — after other Utils includes
- `#include "HelioReleaseNote.hpp"` — after other GUI includes
- Standard library includes (`<thread>`, `<sstream>`) — with other standard includes

### Rule 9: Never Remove
Any line containing these identifiers must be preserved:
`helio`, `Helio`, `HELIO`, `thermal_index`, `ThermalIndex`, `HelioPlateResult`, `HelioQuery`, `HelioBackgroundProcess`, `HelioCompletionEvent`, `helioadditive`, `EVT_HELIO`, `EVT_GLTOOLBAR_ACTION_HELIO`, `SupportDataCatalogStore`, `SupportDataAvailability`, `SupportDataLoadState`

### Rule 10: API Renames
If upstream renames functions that Helio calls, update Helio code to use the new name:
- `get_slice_result()` → used in `on_helio_processing_complete()`
- `get_partplate_list()` → used throughout Helio handlers
- `get_notification_manager()` → used for error/progress notifications
- `restart_background_process()` → contains interleaved Helio code
- `set_slicing_progress_percentage()` → signature modified by Helio

### Rule 11: Branding & Distribution Docs (keep `--ours`)
`README.md` is deliberately rebranded for the Helio fork ("Helio Orca Slicer",
downloads point at the **Helio** releases page, assets are `Helio`-prefixed).
Upstream frequently "improves" install docs, but those improvements point at
**upstream's** distribution channels — which do **not** serve Helio:
- Flathub `com.orcaslicer.OrcaSlicer` — Helio is **not** published on Flathub.
- AppImage / release links to `github.com/OrcaSlicer/OrcaSlicer/releases` — Helio
  ships from `github.com/Helio-Additive/OrcaSlicer/releases` with `Helio`-prefixed
  asset names.

So for `README.md` conflicts (and any other branding/distribution/marketing copy),
**keep the Helio side (`--ours`)** unless a change is genuinely branding-neutral.
Do **not** blanket "take upstream" on docs the way you would for upstream-owned
data files (e.g. `resources/profiles/*.json`). If upstream adds a genuinely useful
branding-neutral note, port just that note into the Helio wording by hand.

### Rule 12: Inherited Workflows (classify, don't edit or delete)

Upstream ships **repo infrastructure**, not just slicer code — workflows, bot
integrations, and dependencies on external services (Claude, Statsig, Cloudflare
R2, WinGet). Every sync pulls all of it in. Some of it cannot work here (it needs
credentials only upstream has); some of it should not run here (it targets
**upstream's** distribution channels). Rule 11 is the README-shaped instance of
this; Rule 12 is the general case.

`.github/helio-workflows.yml` records a decision for **every** workflow in the
repo, and `helio-workflow-inventory.yml` fails a PR that introduces one nobody
has classified, or that adds an undeclared dependency on a secret or repo
variable. So a sync that brings in new infrastructure cannot merge silently.

**When a sync adds or changes a workflow:**
1. The inventory check fails with `E1` (unclassified) or `E4` (undeclared
   dependency). That is working as intended — it is asking for a decision.
2. Add or update the entry. Fill in `reason` properly; it is the decision record
   the next person reviewing a sync will read.
3. If the workflow should **not** run here, set `status: disabled` and disable it
   at the repo level via the Actions API. **Do not edit or delete the file.**

**Why not just delete it.** Deleting an upstream-owned file means a
`modify/delete` conflict on every future sync that touches it; editing it means a
content conflict. Disabling via the API leaves the file byte-identical to upstream
forever and carries zero conflict surface. Encode fork policy in Helio-owned
files, never inside files upstream owns.

**Known live hazard — `winget_updater.yml`.** It triggers on
`release: [released]` with **no repository guard** and publishes to
`identifier: SoftFever.OrcaSlicer`, upstream's public WinGet package.
`helio-release.yml` creates stable releases with `draft: false` and
`prerelease: false`, so cutting one fires this workflow and it attempts to push a
Helio build to upstream's WinGet entry under a `helio-v*` tag. The only thing
preventing that today is `WINGET_TOKEN` being unset — which is a reason **not** to
treat "missing secret" as a harmless condition to paper over.

Its manifest entry is `disabled`: Helio does not publish to WinGet, and there is
no configuration of this workflow that is correct on this fork. **That entry
records the intent but does not enforce it** — the Actions-API reconciler does not
exist yet, so the workflow is still enabled at the repo level. Until someone turns
it off under **Settings → Actions**, an unset secret is the only control, and
setting `WINGET_TOKEN` for any unrelated reason would arm the publish path without
a code change. Do this by hand before cutting the next stable release.

**Secret-presence (`W3`) reads names, never values.** The check needs to know
which secrets exist on the repo, and the obvious way to answer that —
`${{ toJSON(secrets) }}` — serialises every secret name *and value* into the
runner environment. On a `pull_request` run that environment belongs to a job
executing the PR's own copy of the validator, so anyone who can open a branch
could rewrite the script to exfiltrate the lot. Instead the workflow splits in
two: the `inventory` job holds no credentials and runs on every event, and a
separate `secret-presence` job — excluded from `pull_request` — reads secret
**names** from the Actions secrets REST API, which never returns values. Apply the
same rule to anything added here later: never hand a credential to a job that
executes pull-request-controlled code.

### Rule 13: Profiles are taken verbatim from upstream (never merged)

`resources/profiles/**` is **upstream data**. Helio has never customised it —
every commit that has ever touched that tree is an upstream sync. So the sync
workflow does not merge profiles at all; after each merge it overwrites the whole
tree with upstream's:

```bash
rm -rf resources/profiles
git checkout "$SYNC_REF" -- resources/profiles
git add -A resources/profiles
```

**Do not hand-resolve a conflict under `resources/profiles/`.** If you are
resolving a sync by hand, run the three lines above instead. A conflict there can
only produce damage, because there is no Helio content to preserve.

**Why, concretely.** Both known profile divergences were created by resolution,
not by intent:

- `Anycubic.json` was hand-resolved and came out with its JSON keys **reordered**.
  The content was semantically identical to upstream — verified by parsing both
  and comparing — but the 2468-line textual diff then conflicted again on *every*
  subsequent sync. It appears in the conflict list of issues #88, #92 and #94:
  three resolutions, each one creating the next.
- A resolution failed to propagate an upstream **deletion**, leaving three
  `Anet A8 Plus` files that Helio shipped and upstream did not — a genuine
  product-level parity break.

Overwriting makes profile conflicts structurally impossible and guarantees
profile parity by construction. It also means upstream's own CI has already
validated the exact tree Helio ships, which is why `check_profiles.yml` is left
inert here rather than being wired to the parity branch (see below).

**The `rm -rf` is load-bearing.** `git checkout <ref> -- <path>` adds and updates
files but never deletes them, which is exactly how the stale Anet files survived
several syncs.

**If Helio ever needs a fork-specific profile**, this step must grow an exception
path first — as written it will silently discard such a change. That is the one
assumption Rule 13 depends on, and it is worth re-checking before adding any
Helio printer or filament definition.

#### Why `check_profiles.yml` / `check_locale.yml` stay inert

Both are upstream workflows whose `pull_request` triggers are filtered to
`branches: [main]`. This fork's base is `orca-latest-parity-bambu`, so **neither
has ever run here** — a branch rename silently disabled them.

They are deliberately left that way. The value of profile validation on a fork is
catching damage introduced *by the merge*; Rule 13 removes the merge, so upstream's
own CI already covers the exact tree. Wiring them up means adding a branch name to
an upstream-owned file, and `build_all.yml` shows what that costs: Helio added its
branch there, and it now appears in the conflict list of **8 of 13** sync issues.

Both still have `workflow_dispatch`, so either can be run by hand against a sync
branch if a specific sync warrants it.

## Upstream Sync: squash merges & the merge-base graft

**Why upstream-sync PRs are squash-merged.** The release branch enforces a
"commits must have verified signatures" rule. Upstream (SoftFever) commits are
unsigned, so a real merge — which drags hundreds of unsigned commits into the
branch — is rejected. Squash-merging collapses the whole sync into **one
GitHub-signed commit**, which satisfies the rule. So: **upstream-sync PRs must be
squash-merged** (normal Helio feature PRs are unaffected).

**The side effect.** A squash keeps the *file contents* of the upstream release
but discards its *ancestry*. Git no longer knows those files came from upstream.
On the **next** sync, git's merge-base falls all the way back to the last commit
we still share with upstream, and every upstream change since then re-surfaces as
a conflict. Real example: a `v2.4.0-beta → v2.4.1` delta of **~5 files** exploded
to **7,876** because the base fell back to `v2.3.2`.

**The fix (automated in `helio-upstream-sync.yml`).** Before merging, the
workflow ephemerally grafts the upstream commit our content is based on onto the
branch tip:

```bash
git replace --graft <release_tip> $(git rev-parse <release_tip>^@) <prev_upstream_commit>
git merge <new_upstream_tag>      # now only the true delta conflicts
git replace -d <release_tip>      # remove overlay BEFORE any push
```

`git replace --graft` is a **local-only** overlay (`refs/replace/*`) that is never
pushed — it only corrects git's merge-base computation. It is removed before any
push, so nothing unsigned reaches a protected branch. When resolving a conflict
issue by hand, run the exact `git replace --graft` command from the issue body
first, or you will face the full (inflated) conflict set instead of the real delta.

### Where `<prev_upstream_commit>` comes from — the `upstream-commit:` trailer

Every sync commit records the upstream SHA it brought in, plus which mode brought
it, as git trailers in the last paragraph of its message:

```text
upstream-commit: 8500fcdccaa10b5099ac20d252af3a7c560046f1
upstream-sync-mode: tag
```

Both sync paths write them — the workflow's clean-merge squash step, and step 4
of the resolution instructions in the auto-created conflict issue. Both trailers
must sit in the **same** `-m`: git reads trailers only from the last paragraph,
and each `-m` starts a new one.

The next sync reads the newest matching record on the release branch's
**first-parent** line, scoped to its own mode (`tag` for release syncs, `main`
for `main` syncs):

```bash
git log --first-parent \
  --format='%H %(trailers:key=upstream-commit,valueonly,separator=%x20) %(trailers:key=upstream-sync-mode,valueonly,separator=%x20)' \
  orca-latest-parity-bambu \
  | awk -v mode=tag 'NF == 3 && $3 == mode && !seen { print; seen = 1 }'
```

**Why the mode scoping.** Tag syncs and main syncs advance the branch along
different upstream lines, so the newest record overall is not necessarily the
right baseline for a given run. If a `main` sync records **M** and a later tag
sync records an older **B**, a mode-blind read would hand **B** to the next
`main` sync — dragging the whole `B..M` range back into the conflict set, which
is the inflated-conflict failure the graft exists to prevent. The
`version.inc` / tracking-tag split was already mode-specific; the record keeps
that property. A commit carrying `upstream-commit:` with no `upstream-sync-mode:`
is ignored rather than guessed at.

Two details that look like oversights but are not. The `awk` sets a flag rather
than calling `exit`: closing the pipe early can `SIGPIPE` `git log`, and the
workflow step runs under `set -o pipefail`, which would turn that into a step
failure. And the search is **unbounded** — a commit cap would silently expire
the record once that many commits landed since the last sync, dropping back to
the mutable-tag path and re-opening the retag hole below.

**Why a trailer and not a tag.** The graft used to re-derive the baseline from
`version.inc` (tag syncs) or the `helio-last-synced-main` tracking tag (main
syncs). Both resolve through a **mutable** ref, and the validation
(`git merge-base --is-ancestor $candidate $sync_target`) proves only that the
candidate is an ancestor of the *incoming* target — not that it is what this
branch actually holds. Those are different questions, and a retag separates them:

1. `v2.4.2` is synced from commit **A**; the branch tree holds A.
2. Upstream retags `v2.4.2` from A to **B**.
3. The next sync targets **C**, a descendant of B — the ordinary forward retag.
4. `--is-ancestor B C` passes, so **B** is accepted as the baseline.
5. The graft asserts our content is based on B, and the merge computes only B..C.

Everything in **A..B** is then never merged. The branch silently keeps A's content
for those files, with no conflict, no warning, and a sync PR that looks clean —
the merge-base bug inverted, producing too *few* conflicts instead of too many.
The trailer does not move when the tag moves, which closes this.

**Precedence, and what happens when the record is bad:**

| Situation | Behaviour |
|---|---|
| Record found for this mode, SHA resolves | Used. Mutable-ref fallbacks are **not** consulted |
| Record found, SHA resolves but is not an ancestor of the target | Used anyway (upstream rewrote history; the record is still what we built from), with a `::warning::` |
| Record found, SHA does not resolve to a commit | **Graft skipped entirely** — deliberately no fall back to a tag guess |
| No record for this mode on the first-parent line (legacy commits, or a record written by the other mode) | `version.inc` / tracking-tag derivation, as before |

That third row is the load-bearing choice: a *wrong* graft under-merges in
silence, while *no* graft only inflates the conflict count — loud, and a resolver
can fix it by hand. Loud failure beats silent data loss.

**When resolving by hand, keep both trailers.** The commands in the conflict issue
include them in the `git commit-tree` invocation; leaving them out re-opens the
retag hole for the following sync. It must land on the **release-branch** commit, since
the sync branch does not survive the mandated squash — and when you squash-merge
the PR, leave the trailer in GitHub's pre-filled commit message. No other record
of the baseline is durable: the conflict issue's body is overwritten by the next
run for the same tag (it dedupes on a title built from the tag), and the
`helio-last-synced*` tracking tags are mutable refs the workflow force-updates
(`git tag -f` + `git push --force`) on each successful sync — so they record
wherever the last *succeeding* run pointed them, not what this branch holds.
They are also stale in practice, still sitting at `v2.3.2-rc2`, because every
sync so far has ended in conflicts and never reached that step.

**Never** merge an upstream-sync PR with "Create a merge commit" — it both
violates the signature rule and re-flattens on the following sync. Always squash.

**Squash the sync branch *before* the PR is opened, too.** GitHub auto-subscribes
the author of every commit in a PR to that PR's notification thread. A sync branch
that still carries upstream's hundreds of individual commits therefore subscribes
~100+ external upstream contributors, who then get emailed on every bot/reviewer
comment on the fork's sync PR ("why am I on this email chain"). The workflow now
collapses a clean merge into a single internally-authored commit before pushing
(`git commit-tree <merge-tree> -p <target-tip>`), and the conflict-resolution issue
instructs resolvers to do the same. The squashed commit's tree is byte-identical to
the merge result, so nothing is lost. See CLAUDE.md → "Upstream Sync" for the
one-liner.

## Build Verification

### Linux (CI — cheapest, catches 95%+ of issues)
```bash
# Deps (cached)
cmake -S deps -B deps/build -G Ninja -DDEP_WX_GTK3=ON
cmake --build deps/build

# Slicer
cmake -S . -B build -G Ninja -DCMAKE_PREFIX_PATH=$(pwd)/deps/build/destdir/usr/local
cmake --build build
```

### macOS (local dev)
```bash
cmake --build build/arm64 --config RelWithDebInfo --target all
```

### Quick Compile Check (header-only changes)
```bash
# Just rebuild the slic3r target to catch include errors
cmake --build build --target OrcaSlicer
```

## High-Conflict-Risk Files (checked during upstream sync)

These are upstream-owned files with Helio modifications — the sync workflow specifically monitors these for upstream changes:

1. `src/slic3r/GUI/Plater.cpp` — Critical
2. `src/slic3r/GUI/Plater.hpp` — Critical
3. `src/slic3r/GUI/MainFrame.cpp` — High
4. `src/slic3r/GUI/MainFrame.hpp` — High
5. `src/slic3r/GUI/GCodeViewer.cpp` — High
6. `src/slic3r/GUI/LibVGCode/LibVGCodeWrapper.cpp` — High
7. `src/slic3r/GUI/NotificationManager.cpp` — Medium
8. `src/slic3r/GUI/NotificationManager.hpp` — Medium
9. `src/slic3r/GUI/PartPlate.hpp` — Medium
10. `src/slic3r/GUI/PartPlate.cpp` — Medium
11. `src/slic3r/GUI/GUI_App.cpp` — Medium
12. `src/slic3r/GUI/GUI_App.hpp` — Medium
13. `src/slic3r/GUI/Preferences.cpp` — Medium
14. `src/slic3r/GUI/BackgroundSlicingProcess.hpp` — Medium
15. `src/slic3r/GUI/Widgets/SwitchButton.cpp` — Low
16. `src/slic3r/GUI/Widgets/SwitchButton.hpp` — Low
17. `src/slic3r/GUI/Widgets/TextInput.cpp` — Low
18. `src/slic3r/GUI/Widgets/TextInput.hpp` — Low
19. `src/slic3r/CMakeLists.txt` — Low
20. `src/libslic3r/AppConfig.cpp` — Low
21. `src/libslic3r/PrintBase.hpp` — Low
22. `src/libslic3r/PrintConfig.cpp` — Low
23. `src/libslic3r/GCode/GCodeProcessor.cpp` — Medium
24. `src/libslic3r/GCode/GCodeProcessor.hpp` — Medium
25. `src/libvgcode/include/PathVertex.hpp` — Medium
26. `src/libvgcode/include/Types.hpp` — Low
27. `src/libvgcode/src/ViewerImpl.cpp` — Medium
28. `src/libvgcode/src/ViewerImpl.hpp` — Low
29. `src/slic3r/GUI/GLCanvas3D.cpp` — Low
30. `src/slic3r/GUI/GLToolbar.cpp` — Low
31. `src/slic3r/GUI/GLToolbar.hpp` — Low
32. `src/slic3r/GUI/Selection.cpp` — Low
