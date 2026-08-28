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

**A second, independent reason not to flip that branch filter.** Rule 13's argument
is about *cost* — editing an upstream-owned file buys a conflict on every future
sync. But `check_profiles.yml` would also simply **fail today** if it were wired up,
on data nobody here wrote. It downloads the **nightly** validator built from upstream
`main`, while this fork is pinned to the v2.4.2 release, so the validator rejects keys
that were valid at v2.4.2 and removed later. Run against the parity branch:

```
error: resources/profiles/Qidi/process/fdm_process_n_common.json contains incorrect keys:
       machine_prepare_compensation_time, which were removed
error: resources/profiles/Qidi/machine/fdm_qidi_x3_common.json contains incorrect keys:
       filament_dev_ams_drying_*, ... which were removed
Validation failed
```

Both key families are absent from this fork's own `PrintConfig.cpp`, and `git log` on
both files shows only upstream-sync commits — this is inherited version skew, not
Helio drift. So enabling it unchanged would red-light every profile PR on day one, on
top of the conflict cost. Pinning the validator to the matching release, or scoping
validation to changed vendors, would have to come first.

`scripts/orca_extra_profile_check.py` **does** pass on the parity branch today
(0 errors, exit 0), so that half could be enabled independently of the validator.

### Rule 14: Inherited CI Trigger Filters (branch & path)

The *reachability* complement to Rule 12: the manifest records whether an inherited
workflow **should** run here, this rule covers whether it **can**.

Upstream workflows are written for **upstream's** branch layout: they gate on
`branches: [main]` (plus `release/*`). This fork's release branch is
`orca-latest-parity-bambu`, so an inherited workflow is **silently inert here**
unless someone adds that branch to its filter. Nothing fails — the workflow simply
never starts, which is far harder to notice than a red check. Rule 13's
`check_profiles.yml` / `check_locale.yml` / `check_profiles_comment.yml` are the
worked example; that inertness was discovered, not chosen.

When a sync adds or edits a workflow with a `pull_request` / `push` trigger, check
both filters:

| filter | failure mode if wrong |
| --- | --- |
| `branches:` | workflow never runs on this fork's PRs at all |
| `paths:` | workflow never runs for the file types you care about |

**`paths:` is evaluated before any job-level `if:`.** This matters for the
`ready-to-build` opt-in on `build_all.yml`: a label cannot start a workflow that the
path filter excluded, so a profile-only PR carrying `ready-to-build` produced no build
at all until `resources/**` and `localization/**` were added to the `pull_request`
`paths:` list (they were already in the `push` list — the asymmetry was the bug).

Note the two rules pull in opposite directions on the same question, and the
difference is **who owns the file**. Rule 12 says don't edit an upstream-owned
workflow to make it reachable, because the edit conflicts on every sync. Rule 14 says
an unreachable workflow is a silent hole. Where both apply, the reachability fix is
worth its conflict cost only when the workflow does something no Helio-owned file
could do instead — `build_all.yml` qualifies (it is the build), `check_profiles.yml`
does not (Rule 13 already guarantees profile parity by construction).

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
branch tip. For tag-release syncs that commit is derived from `version.inc` (it
names the synced release) provided it is a **strict** ancestor of the sync target —
see the rules below for why that qualifier matters; for `main` syncs it comes from
the `upstream-commit:` record on the previous sync commit, falling back to the
`helio-last-synced-main` tracking tag (`version.inc` would name an older release
there and must not be used):

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

**Never** merge an upstream-sync PR with "Create a merge commit" — it both
violates the signature rule and re-flattens on the following sync. Always squash.

**The other side effect: "already synced" becomes hard to detect.** Every cheap
test for "have we got this release already?" reasons about **ancestry** — is the
target an ancestor of `HEAD`, does a trial merge apply cleanly — and ancestry is
precisely what the squash destroyed. In August 2026 that produced #107: an empty
PR re-proposing `v2.4.2` three and a half hours after #96 merged it, which would
have recurred every Monday (#110). The workflow now answers the question with
**four** guards, cheapest first. Two of them still reason about ancestry and are
kept only as cheap early exits; the authoritative one does not:

| guard | when | basis | can it skip on its own? |
| --- | --- | --- | --- |
| `version.inc` equals the target | before any merge | a version *string* — sets an expectation only | **no** |
| tracking tag equals the target | before any merge | a commit id, only ever written after content was validated | yes |
| ancestor check / trial merge | before the graft | **ancestry-dependent** — only meaningful when history was not flattened, which after a squash it always is | yes |
| **merged tree == target-branch tree** | after the grafted merge | content: "did this change anything?" | yes — **this is the authority** |

The last one is the backstop and cannot be fooled: if the merge produces a tree
identical to the release branch's, there is nothing to propose, whatever the
history says. It skips the PR, records why in the job summary, and advances the
tracking tag.

**`version.inc` deliberately cannot skip a run by itself.** It is a version string
in a file, and the release it names can stop describing the tree without the file
changing — upstream force-retagging a release we already synced, or a local version
bump landing before the content. Either way the string equals the sync target while
the target's content is absent, and skipping there would **silently drop upstream
work**, with every later run reaching the same wrong conclusion. That failure is
invisible; the empty PR of #107 was merely noisy. So `version.inc` selects the
baseline and sets an expectation, and the merged-tree comparison decides.

### The `upstream-commit:` baseline record

The squash step writes two lines as the **final paragraph** of every sync commit:

```text
upstream-commit: <40-hex upstream sha>
upstream-sync-mode: tag|main
```

**Why it exists, given `version.inc` and the tracking tag.** It is for `main` mode.
There `version.inc` is deliberately excluded — it names a *release*, and a `main`
sync is ahead of it — so the only other candidate is `helio-last-synced-main`, a tag
that is mutable and, **with the workflow's current `GITHUB_TOKEN`, cannot be
written**: pushing it makes upstream's `.github/workflows/**` reachable, and a
GitHub App token may not introduce workflow content without the `workflows`
permission — which a workflow's `permissions:` block cannot grant. That is a
property of the credential, not of the repository: a PAT with `workflows` scope
could write it, at the cost of a long-lived credential able to rewrite workflow
files. See "Why the push is refused" below for the full diagnosis and the three
options, none of which has been chosen. So as things stand a `main` sync has no
durable baseline. A trailer on the commit is immutable, travels with the branch,
and needs no permission beyond committing.

It only **adds a candidate**. It is content-validated alongside every other one, so
a record that disagrees with the tree loses to one that matches it.

Four properties are load-bearing; changing any of them breaks it silently:

- **The two lines must be adjacent**, and the mode must match. That is what stops a
  message quoting an older record from being spliced onto a newer one.
- **The last such pair in a message wins** — a commit's own record is written below
  anything it quotes.
- **Read the full message, not `%(trailers:…)`.** Git parses trailers only from the
  last paragraph, and GitHub appends `Co-authored-by:` in a paragraph of its own
  when it squash-merges a PR with more than one commit author, which drops the
  record.
- **`git log --grep` is a candidate filter, not the answer.** It matches when both
  patterns appear anywhere, including non-adjacently, so parsing only the newest
  match lets one malformed commit **shadow every valid record beneath it**. Walk
  candidates newest-first and take the first that yields an adjacent pair.

When resolving a sync by hand, carry the record into your commit — the same two
lines, adjacent, as the final paragraph, naming **the commit you actually merged**.

Three further rules keep the baseline honest, and all of them are load-bearing:

1. **Every write of the tracking tag must be backed by content** — an ancestry hit,
   a clean no-diff trial merge, the tree-level content test, a merged resolution
   PR for the exact target commit, or an identical merged tree. That is what lets
   the tag (unlike `version.inc`) skip a run on its own.

   "A sync PR was opened" is **not** such evidence, and the workflow used to treat
   it as if it were: the tag advanced as soon as the PR was created. That made the
   tag a record of intent while the rest of the workflow read it as a record of
   content, and two silent drops followed. A PR closed unmerged left the tag at a
   release the branch never received, so the `check` step skipped it for good; and
   while the PR merely sat open, the next release grafted that unreceived commit as
   the merge base. The tag now moves only once the content is on the target branch —
   the first run after the sync PR merges takes one of the paths above and
   advances it there. Until then each run redoes the merge and refreshes the same
   PR, which is the honest description of the state: not synced yet.
2. **The graft base must be a *strict* ancestor of the sync target.**
   `git merge-base --is-ancestor` is true for a commit and itself, so a `version.inc`
   naming the target would otherwise graft the target onto the branch tip, making the
   merge-base the target — the merge is then a no-op *by construction* and the tree
   comparison "confirms" a release that was never merged. The one content-based guard
   becomes a rubber stamp. The `check` step's refusal to skip on `version.inc` alone
   only works together with this.

   When the records *do* name the target itself, the base becomes the target's
   **first parent** — which is what "our content is based on this release" actually
   means, so the merge applies that release's own delta and the tree comparison
   still decides. Rejecting the candidate outright instead left no graft at all,
   and the merge then ran against the ancient pre-squash ancestor and conflicted,
   turning a run that should quietly do nothing into a weekly conflict issue.

3. **Every graft candidate must be content-validated, for its *inherited*
   content — not just its own delta.** Choosing the graft base is **asymmetric**:
   too old is merely expensive (more delta recomputed, conflict set inflated),
   while too new **silently drops upstream work** — git reads the content between
   the real base and the claimed one as deliberate local reversions and never
   re-applies it. The merge succeeds, the PR opens, and it claims a release whose
   content is only partly present.

   Strictness alone does not catch this. If the tree holds v2.4.1, `version.inc`
   says v2.4.2 and the target is v2.4.3, then v2.4.2 *is* a strict ancestor of the
   target — so it passes rule 2 and grafts, and only `v2.4.2..v2.4.3` is applied.

   Validating the candidate's **own delta** does not catch it either, and that is
   the subtle part. Grafting the candidate's first parent and trial-merging it
   proves the candidate's last step is present and *assumes* everything under it.
   When the gap sits below a small step, the assumption is exactly what is false:
   tree at v2.4.0, `version.inc` says v2.4.2, v2.4.1 added a file, and v2.4.2 only
   bumped the version string — which the fork already carries, so the trial passes
   and v2.4.1's file is dropped. The same hole reached through the tracking tag,
   which was not validated at all.

   So validation asks about inherited content, and it compares **trees**. The
   work lives in `scripts/helio/upstream_content.sh`, shared with the `check`
   step so that "does this branch hold release X?" has one implementation; it was
   inline in the graft step before, which is precisely why `check` could not use
   it and went on trusting the tracking tag.

   A path upstream changed between a base four releases below the candidate and
   the candidate itself, which our tree still holds at exactly the base version,
   is a change we never applied. Comparing changed path **names** is not enough:
   if upstream edits one hunk of a file and Helio independently edits another
   hunk, the path appears on both sides and a name-level set difference cancels
   it out while upstream's hunk is genuinely absent. So blob ids are compared —
   two `git diff --raw` calls give every id on both sides — and for the remainder
   where our blob matches neither side, a three-way merge decides:

   | our blob + mode | verdict |
   | --- | --- |
   | equals the candidate's | held |
   | equals the base's | **missing** |
   | neither, merge is clean and changes ours | **missing** |
   | neither, merge is clean and leaves ours alone | held |
   | neither, merge conflicts | **unknown** |

   Mode is part of the comparison, not just the blob, and it is decided **before**
   the three-way merge rather than inside it. A path whose only change is
   `100644` → `100755` has identical blob ids on both sides, so a blob-only test
   reports nothing and the executable bit is dropped from the sync for good.
   Comparing blob-and-mode together closes that case but not the next one: if
   upstream changes only the mode while Helio independently edits the blob, the
   composite values differ for a reason unrelated to the mode, and the text merge
   — which is handed blob ids and cannot see modes at all — finds upstream's blob
   equal to the base's, leaves ours alone and answers *held*. So the rule is
   applied first and separately: upstream moved the mode and we are still at the
   base's mode, therefore we never received it, whatever the blobs then say.

   **`unknown` is a third answer, and the two callers lean opposite ways on it.**
   A conflict cannot distinguish "we have upstream's change with our edit on top"
   from "we never received it", because both produce overlapping hunks. So:

   | question | caller | `unknown` means |
   | --- | --- | --- |
   | is the sync already done? | `holds`, in `check` | **not** done — do not skip |
   | is this safe as a merge base? | `base-ok`, in `graft` | tolerated — but only as a last resort |

   Guessing *yes* on the first skips a release silently. Guessing *no* on the
   second leaves no graft, and the merge then runs against the ancient
   pre-squash ancestor and conflicts every week. Collapsing the two was a real
   bug: the conflict case was reasoned about for the graft base, then the same
   function was reused for the skip decision, where the safe direction inverts.

   **Tolerated is not the same as preferred**, and that distinction was itself a
   bug for two rounds. The argument above is sound about *rejecting* an
   undecidable candidate and unsound about *accepting* one, because an
   undecidable path in the **base** is the single shape that drops upstream work
   with no conflict at all: if the base already carries upstream's value for that
   path and the sync target has not moved it since, the merge sees
   `theirs == base`, keeps ours, and nothing is reported. So `graft` takes a
   candidate outright only when `holds` passes. A candidate that is merely
   `base-ok` sends the run looking for a provably-held base *below* it
   (`first-held … strict`), where the same paths are still in motion and the
   merge must therefore present them — as a change applied or as a conflict,
   either way visible. Only when no such base exists within `MAX_WALK` steps is
   the undecidable candidate used, and then the run says so and names the paths.
   Preferring an older base costs conflict volume, which is the direction this
   whole mechanism chooses everywhere else.

   `MAX_WALK` is set in the `check` and `graft` steps' own `env:` blocks, not
   only inside `upstream_content.sh`. The script runs as a separate process, so
   a value defined only there is invisible to the workflow's shell — and the
   graft step interpolates `$MAX_WALK` into its rejection warnings under
   `set -u`, where an unset variable aborts the step instead of warning and
   carrying on. `CONTENT_DEPTH` deliberately has no such duplication: no step
   body expands it, so it lives only in the script, whose
   `CONTENT_DEPTH="${CONTENT_DEPTH:-4}"` default is the single source — both
   steps call the same script and therefore always validate at the same depth.

   The candidate records themselves are evaluated **newest-first by ancestry,
   with fall-through**: strictly-held on any candidate beats degraded
   acceptance on any, and the walk below a candidate begins only after every
   newer candidate has failed. Record preference — version.inc, then the
   tracking tag, then (when the records self-name the target) the target's
   first parent, appended last — is *not* ancestry order, and evaluating in
   record order let a stale tracking tag's walk-down defeat a strictly newer
   candidate that validates: with the tree fully holding the target and the
   tag stale at v2.3.2, the tag was base-ok-with-unknowns, its strict walk
   grafted v2.3.0, and the expected-no-op verification merge conflicted on
   content already on the branch — the weekly treadmill of #110 for an
   already-merged release.

   Within the walk, releases are ordered by **ancestry** (`git describe` on
   each successive parent), not by tag date — tags sharing a timestamp sort
   arbitrarily, and a base one release too new is the very thing being
   rejected.

   A candidate that fails is not simply dropped: the run walks down to the newest
   commit whose content *is* present and grafts that, warning loudly and naming
   the files that were never applied. The walk prefers a provably-held base and
   falls back to a merely base-ok one only when the strict walk exhausts
   `MAX_WALK` — the fallback then carries undecidable paths by construction, so
   the run emits the same warning naming them that the base-ok candidate case
   emits. Rejecting outright leaves no graft, and the merge then runs against
   the ancient pre-squash ancestor and conflicts — the weekly treadmill rule 2
   already had to undo once.

   The window is four releases. Any finite window has a floor — a change older
   than the base is outside the diff and invisible — so this is a depth/cost
   trade rather than a proof.


`scripts/helio/test_sync_noop_guards.py` pins all of this. It extracts the real
`check` and `graft` step bodies from the workflow rather than transcribing them,
and runs them against synthetic repositories whose content is held by a squashed
commit with no upstream ancestry. Add a row there before changing any of the three
rules above — every one of them was added in response to a failure that the
then-current tests did not catch.

**The tracking tag is a convenience, not a source of truth.** `helio-last-synced`
is only advanced by a successful push at the end of a run, so an out-of-band merge
— or a run whose tag push was refused — leaves it behind while the tree moves on.
It sat at `v2.3.2-rc2` through three releases that way. Two consequences are baked
into the workflow: for tag-release syncs `version.inc` is preferred over the tag
as the baseline whenever it names a **strictly newer** release, and a **refused tag
push warns rather than failing the run**. If you see that warning, a maintainer can
heal it with:

```bash
git push helio +<upstream_commit>:refs/tags/helio-last-synced
```

**Why the push is refused — it is not what it looked like.** This was recorded for
months as "the token cannot *always* force-update tags (`HTTP 403`)", which implied
an intermittent permission gap or a tag-protection rule. Neither is true. The real
message, from run `32014594574`:

```text
! [remote rejected] helio-last-synced -> helio-last-synced
  (refusing to allow a GitHub App to create or update workflow
   `.github/workflows/build_all.yml` without `workflows` permission)
```

The tracking tag points at an **upstream** commit. Creating that ref makes
upstream's `.github/workflows/**` newly reachable from a ref in this repository,
and GitHub refuses to let any GitHub App token — `GITHUB_TOKEN` included — create
a ref that introduces workflow content without the `workflows` permission. That
permission is **not** one of the scopes a workflow's `permissions:` block can
grant, so this cannot be fixed by editing the workflow: it fails on every run, and
always will. That, not bad luck, is why the tag stuck at `v2.3.2-rc2` across three
releases and let the ancestry problem compound into #107.

Three ways out, none yet chosen:

| option | cost |
| --- | --- |
| PAT with `workflows` scope, stored as a **repo secret** | a long-lived credential able to rewrite workflow files, held to solve a bookkeeping problem |
| drop the tag entirely | every decision already has a content-backed fallback, so this is mostly deletion |
| point the tag at the **Helio** commit, upstream sha in the annotated tag message | needs no new permission (the commit is already reachable), but every reader of the tag has to change |

Do **not** attempt to fix this by adding `workflows:` to the workflow's
`permissions:` block. It is not a valid key there, and a run will not tell you so —
it will just keep failing the same way.

Note the remote. The workflow's own pushes use `origin` because `actions/checkout`
configures origin as *this fork*; you are running this in your own clone, where
`origin` is upstream OrcaSlicer and `helio` is the fork (see "Git Workflow" in
`CLAUDE.md`). Every maintainer-facing command the workflow prints says `helio` for
that reason — pushing a Helio tracking tag to `origin` would aim it at upstream.

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
