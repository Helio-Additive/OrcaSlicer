# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Helio Integration

This is the Helio-Additive fork of OrcaSlicer. For Helio integration details, conflict resolution rules during upstream syncs, and the complete file-by-file modification map, see **`HELIO_INTEGRATION.md`**.

### Scope: this fork maintains Helio code

**A bug in upstream code is not ours to fix, even when it costs us.** Before changing any file, check whether it carries Helio changes — `git diff <synced-upstream-tag> HEAD -- <file>` (the tag `version.inc` names). Empty means the file is byte-identical to upstream's, so it is upstream's, and a local patch buys a divergence to reconcile at every future sync forever, usually to front-run a fix upstream has already written. The touchpoint map in `HELIO_INTEGRATION.md` is a faster first look but it is hand-maintained and drifts; git settles it.

This applies to a failing test, a broken build, or a red check that is blocking a Helio PR. "It is breaking our CI" is the reasoning that produced PR #116 — a patch to `src/libslic3r/Print.hpp`, a file with zero Helio changes, for a defect upstream had already fixed. It was closed, not merged. Confirm our diff did not cause it, record it as an issue (#115 is the worked example), then rebuild or wait for the sync. Do not patch it, do not quarantine the test, and do not file it upstream on Helio's behalf.

Helio-owned CI (`.github/workflows/helio-*.yml`, `scripts/helio/**`), Helio code, and files the diff above confirms still carry Helio changes are ours outright — the touchpoint map is the quick first look, not the qualifier, since a file can stay listed after its Helio content is reverted or absorbed upstream. See `HELIO_INTEGRATION.md` → Rule 15.

## CI/CD Workflows

### Upstream Sync (`helio-upstream-sync.yml`)
- Scheduled workflow that syncs upstream OrcaSlicer changes into `orca-latest-parity-bambu`
- Auto-creates merge conflict issues (labeled `upstream-sync`, `claude-work`) when conflicts occur. Deduped by title: a repeat run with the same unresolved conflict refreshes the existing open `upstream-sync` issue's body rather than opening another one
- Auto-creates sync PRs with changelog and Helio-relevant change reports
- Uses `claude-work` label to flag items for automated triage
- Detects out-of-band merges (e.g. manual PRs) via ancestor check and auto-updates the tracking tag
- Handles pre-existing conflict branches safely: skips the push entirely when the branch has an **open PR** (resolution in flight), otherwise checks for divergence before replacing (skips if someone has pushed resolution commits, force-pushes to replace stale branches from previous runs). The open-PR check has to come first: resolvers squash their branch to satisfy `require-squashed-sync`, which rewrites history and defeats the ancestor test. A force-push rejected by a repository ruleset is warned about, not treated as a sync failure. Whenever the push is skipped for any of these reasons, the step reports `pushed=false` and the auto-created conflict issue leads with a warning saying the branch does **not** hold that run's conflict state, so resolvers redo the merge from the release branch instead of trusting a stale branch.
- Detects squash merges: when the ancestor check fails, tries a trial merge to detect if content is already incorporated
- **Merge-base graft**: upstream-sync PRs are squash-merged (required by the release branch's "verified signatures" rule — a squash yields one signed commit instead of hundreds of unsigned upstream ones). Squashing discards upstream ancestry, so before each merge the workflow ephemerally grafts the last-synced upstream commit (derived from `version.inc` for tag-release syncs, or the `helio-last-synced-main` tracking tag for `main` syncs) via `git replace --graft` to keep the merge-base correct. Without it, conflicts balloon (a ~5-file delta once exploded to 7,876). The graft is local-only and removed before any push. **Always squash-merge upstream-sync PRs, never a merge commit.** See `HELIO_INTEGRATION.md` → "Upstream Sync: squash merges & the merge-base graft".
- **Profiles are taken verbatim, never merged**: after each merge the workflow overwrites `resources/profiles/**` with upstream's tree (`rm -rf` + `git checkout "$SYNC_REF" -- resources/profiles`). Helio has never customised profiles, so a conflict there can only produce damage — hand-resolving `Anycubic.json` reordered its JSON keys, producing a semantically identical but 2468-line diff that then re-conflicted on every later sync (#88, #92, #94), and another resolution dropped an upstream deletion, leaving three `Anet A8 Plus` files Helio shipped and upstream did not. If every conflict in a sync was under `resources/profiles/`, the workflow now resolves them all and proceeds without human involvement. **When resolving a sync by hand, never hand-merge a profile — re-run those three commands instead.** See `HELIO_INTEGRATION.md` → Rule 13
- **Squash the sync branch *before* opening the PR** (not just at merge time): after a clean merge the workflow collapses the merge commit into a single internally-authored commit (`git commit-tree` on the merge tree with the target-branch tip as sole parent) before pushing. Reason: GitHub auto-subscribes the author of every commit in a PR to that PR's notifications; a merge commit drags in upstream's hundreds of individual commits, which spams ~100+ external upstream contributors with every comment on the fork's sync PR. A single squashed commit has no external authors. Conflict-resolution instructions in the auto-created issue tell human/Claude resolvers to squash the same way before pushing.

### Issue Dedupe (`dedupe-issues.yml`) — **DISABLED**
- **Disabled on this fork as of 2026-08-11**, along with `auto-close-duplicates.yml` and `backfill-duplicate-comments.yml`. Marked `disabled` in `.github/helio-workflows.yml` and disabled at the repo level. The files are left byte-identical to upstream — do not edit or delete them (Rule 12)
- Upstream runs Claude-based issue dedup and has `CLAUDE_CODE_OAUTH_TOKEN`; this fork never did, so the job failed on every `issues: opened` event from the v2.3 merge (2026-03-06) until it was disabled. Diagnosed in PR #49 (2026-04-02) and left running for four more months
- **Do not re-enable `auto-close-duplicates.yml` on its own.** It *closes issues automatically* once a dedupe comment is 3 days old; it has only ever been harmless because dedupe never produced those comments
- If Helio ever does want dedup: add the secret, flip all three entries to `run`, and re-enable them in Settings → Actions

### Workflow Inventory (`helio-workflow-inventory.yml`)
- Enforces `.github/helio-workflows.yml`, the fork's decision record for which upstream-inherited workflows run here. Validator: `scripts/helio/check_workflow_inventory.py`
- **Fails** a PR when a workflow file has no manifest entry (`E1`), when an entry has no file (`E2`), when a `deleted` file is resurrected by a sync (`E3`), when a workflow references a secret/var it does not declare (`E4`), or on a malformed manifest (`E5`)
- **Warns** on `undecided` entries (`W1`), manifest drift (`W2`), and a `run` workflow needing a secret this repo lacks (`W3`). `--strict-secrets` escalates `W3` to an error once the manifest is clean
- Runs on **every** PR and release-branch push — deliberately no `paths:` filter. GitHub evaluates path filters against only the first 300 changed files, and an upstream sync routinely exceeds that (v2.4.2 changed 894), so a filter would skip the check on exactly the PRs it exists to guard
- Split into three jobs, so the token and the repository's code are never in the same job. `inventory` holds no credentials and runs on all events, including `pull_request`. `secret-names` holds the optional `WORKFLOW_INVENTORY_TOKEN` and runs **no third-party actions and no checkout** — just `curl` and `jq` — gated on `github.ref == 'refs/heads/orca-latest-parity-bambu'` (the ref, not the event: `workflow_dispatch` accepts any branch). `secret-presence` checks out the repo with no credentials and consumes the names as ordinary job-output data. **The `if:` ref gate is not the control** — a `workflow_dispatch` runs the workflow definition from the ref it targets, so a feature branch supplies this file and can delete its own guard; equally, any same-repo branch can add a push-triggered workflow that reads a repository secret directly. No in-file condition can protect a repository-scoped secret from someone with write access. The control is `environment: workflow-inventory` on `secret-names`: environment protection rules live in repository settings, so branch code cannot alter them. **Admin setup required before W3 does anything** — create the `workflow-inventory` environment, restrict its deployment branches to `orca-latest-parity-bambu`, and add `WORKFLOW_INVENTORY_TOKEN` there as an *environment* secret (a repository secret of the same name would work and would still be branch-reachable, which is the thing being avoided). Until that exists the token resolves empty and the step skips, so the setting is inert by default. When `WORKFLOW_INVENTORY_TOKEN` is unset, `secret-names` reports `available=false` and `secret-presence` does not run, so W3 is silently unevaluated rather than failing. Never use `toJSON(secrets)` here — it puts every secret name and value in the environment of a job running checked-out code
- W3's name list unions **repository-scoped and organization-scoped** secrets (`/actions/secrets` + `/actions/organization-secrets`, both paginated). An org-level grant is present at runtime, so omitting it makes W3 report a configured secret as absent. A `404` on the org endpoint means the owner is not an org and is fine; any other failure skips W3 entirely rather than reporting from a partial list. Environment-scoped secrets are **not** covered, and the caveat is scoped **per job**: only secrets referenced by a job that targets an `environment:` are downgraded to "may be an environment secret". A secret referenced solely by a job with no environment is answered normally and still escalates under `--strict-secrets`, even when a sibling job in the same file uses one
- The expression scanner reads `${{ }}` spans from the **parsed document's scalars**, not raw file text. Every place Actions evaluates an expression is a scalar, so this loses nothing and drops YAML comments for free — scanning raw text made a commented-out `# token: ${{ secrets.OLD_TOKEN }}` a fatal E4. Unwrapped `if:` conditions are collected separately (the `${{ }}` wrapper is optional there), and a file PyYAML cannot load falls back to a raw scan, because a false E4 is arguable but a missed credential is not. `secrets.*` / `vars.*` object filters are reported as dynamic: they consume every value in the context, and matched neither the dot patterns (no identifier after the dot) nor the whole-context pattern (which stands down when a dot follows)
- Dependency extraction only scans Actions expression contexts (`${{ }}` spans and `if:` values), and matches both `secrets.NAME` and `secrets['NAME']`. Bracket form was previously missed, which is a false negative in the dangerous direction; scanning raw file text instead of expressions produced the opposite problem (a `/tmp/secrets.json` path read as a secret named `json`). Expression spans and string literals are found by a **string-aware scan, not a regex**: a non-greedy `${{ … }}` match ends at a `}}` inside a quoted format string (missing the secret after it), and a word inside a string literal (`contains('no secrets here', x)`) is not a context access. Conditions are read from the **parsed YAML**, and only from `jobs.<id>.if` and `jobs.<id>.steps[].if` — a folded condition (`if: >-` with the expression on following lines) defeats a line regex, while a walk for any key named `if` picks up action inputs Actions never evaluates. Dynamic subscripts (`secrets[matrix.x]`), whole-context uses (`toJSON(secrets)`), and `secrets: inherit` into a **non-local** reusable workflow are all reported as unresolvable dependencies rather than silently ignored — each grants credentials this check cannot account for
- Statuses: `run` / `disabled` / `undecided` / `deleted`. To stop an inherited workflow, set `disabled` and disable it via the Actions API — **do not edit or delete the upstream file**, which would create a merge conflict on every future sync. See `HELIO_INTEGRATION.md` → Rule 12
- Why it exists: upstream ships repo infrastructure along with slicer code, and syncs pull it in wholesale. `dedupe-issues.yml` failed on every opened issue from March to August 2026 because it needs a credential this fork never had, and nothing forced anyone to notice

### Upstream Watch (`helio-upstream-watch.yml`)
- Monitors upstream for new tags/releases and creates tracking issues

### Release (`helio-release.yml`)
- Triggers on: merged PR with `release` label on `orca-latest-parity-bambu`, or manual `workflow_dispatch`
- Builds all platforms (Linux, Windows, macOS universal) via reusable workflows
- Creates GitHub Release with `Helio`-prefixed assets (DMG, AppImage, installer, portable zip)
- Tag format: `helio-v{version}` (from `version.inc`)
- Manual dispatch restricted to `orca-latest-parity-bambu` branch only

### Build Pipeline (reusable workflows)
- `build_check_cache.yml` → `build_deps.yml` → `build_orca.yml`
- macOS signing/notarization gated by `ENABLE_SIGNING` repo variable
- Dependency caching per OS/arch with hash of `deps/**`

### Build All (`build_all.yml`)
- Triggers on push/PR to `main` and `release/*` branches
- Runs full build matrix + unit tests + Flatpak builds

## Git Workflow
- **Base branch**: `orca-latest-parity-bambu` (not `main`)
- **Push remote**: `helio` (never `origin` — that's upstream OrcaSlicer)
- **PRs target**: `orca-latest-parity-bambu`

## Overview

OrcaSlicer is an open-source 3D slicer application forked from Bambu Studio, built using C++ with wxWidgets for the GUI and CMake as the build system. The project uses a modular architecture with separate libraries for core slicing functionality, GUI components, and platform-specific code.

## Build Commands

### Building on Windows
**Always use this command to build the project when testing build issues on Windows.**
```bash
cmake --build . --config %build_type% --target ALL_BUILD -- -m
```

### Building on macOS
**Always use this command to build the project when testing build issues on macOS.**
```bash
cmake --build build/arm64 --config RelWithDebInfo --target all --
```

### Building on Linux
 **Always use this command to build the project when testing build issues on Linux.**
```bash
cmake --build build/ --config RelWithDebInfo --target all --
```
### Build System
- Uses CMake with minimum version 3.13 (maximum 3.31.x on Windows)
- Primary build directory: `build/`
- Dependencies are built in `deps/build/`
- The build process is split into dependency building and main application building
- Windows builds use Visual Studio generators
- macOS builds use Xcode by default, Ninja with -x flag
- Linux builds use Ninja generator

### Testing
Tests are located in the `tests/` directory and use the Catch2 testing framework. Test structure:
- `tests/libslic3r/` - Core library tests (21 test files)
  - Geometry processing, algorithms, file formats (STL, 3MF, AMF)
  - Polygon operations, clipper utilities, Voronoi diagrams
- `tests/fff_print/` - Fused Filament Fabrication tests (12 test files)
  - Slicing algorithms, G-code generation, print mechanics
  - Fill patterns, extrusion, support material
- `tests/sla_print/` - Stereolithography tests (4 test files)
  - SLA-specific printing algorithms, support generation
- `tests/libnest2d/` - 2D nesting algorithm tests
- `tests/slic3rutils/` - Utility function tests
- `tests/sandboxes/` - Experimental/sandbox test code

Run all tests after building:
```bash
cd build && ctest
```

Run tests with verbose output:
```bash
cd build && ctest --output-on-failure
```

Run individual test suites:
```bash
# From build directory
ctest --test-dir ./tests/libslic3r/libslic3r_tests
ctest --test-dir ./tests/fff_print/fff_print_tests
ctest --test-dir ./tests/sla_print/sla_print_tests
# and so on
```

## Architecture

### Core Libraries
- **libslic3r/**: Core slicing engine and algorithms (platform-independent)
  - Main slicing logic, geometry processing, G-code generation
  - Key classes: Print, PrintObject, Layer, GCode, Config
  - Modular design with specialized subdirectories:
    - `GCode/` - G-code generation, cooling, pressure equalization, thumbnails
    - `Fill/` - Infill pattern implementations (gyroid, honeycomb, lightning, etc.)
    - `Support/` - Tree supports and traditional support generation
    - `Geometry/` - Advanced geometry operations, Voronoi diagrams, medial axis
    - `Format/` - File I/O for 3MF, AMF, STL, OBJ, STEP formats
    - `SLA/` - SLA-specific print processing and support generation
    - `Arachne/` - Advanced wall generation using skeletal trapezoidation

- **src/slic3r/**: Main application framework and GUI
  - GUI application built with wxWidgets
  - Integration between libslic3r core and user interface
  - Located in `src/slic3r/GUI/` (not shown in this directory but exists)

### Key Algorithmic Components
- **Arachne Wall Generation**: Variable-width perimeter generation using skeletal trapezoidation
- **Tree Supports**: Organic support generation algorithm  
- **Lightning Infill**: Sparse infill optimization for internal structures
- **Adaptive Slicing**: Variable layer height based on geometry
- **Multi-material**: Multi-extruder and soluble support processing
- **G-code Post-processing**: Cooling, fan control, pressure advance, conflict checking

### File Format Support
- **3MF/BBS_3MF**: Native format with extensions for multi-material and metadata
- **STL**: Standard tessellation language for 3D models
- **AMF**: Additive Manufacturing Format with color/material support  
- **OBJ**: Wavefront OBJ with material definitions
- **STEP**: CAD format support for precise geometry
- **G-code**: Output format with extensive post-processing capabilities

### External Dependencies
- **Clipper2**: Advanced 2D polygon clipping and offsetting
- **libigl**: Computational geometry library for mesh operations
- **TBB**: Intel Threading Building Blocks for parallelization
- **wxWidgets**: Cross-platform GUI framework
- **OpenGL**: 3D graphics rendering and visualization
- **CGAL**: Computational Geometry Algorithms Library (selective use)
- **OpenVDB**: Volumetric data structures for advanced operations
- **Eigen**: Linear algebra library for mathematical operations

## File Organization

### Resources and Configuration
- `resources/profiles/` - Printer and material profiles organized by manufacturer
- `resources/printers/` - Printer-specific configurations and G-code templates  
- `resources/images/` - UI icons, logos, calibration images
- `resources/calib/` - Calibration test patterns and data
- `resources/handy_models/` - Built-in test models (benchy, calibration cubes)

### Internationalization and Localization  
- `localization/i18n/` - Source translation files (.pot, .po)
- `resources/i18n/` - Runtime language resources
- Translation managed via `scripts/run_gettext.sh` / `scripts/run_gettext.bat`

### Platform-Specific Code
- `src/libslic3r/Platform.cpp` - Platform abstractions and utilities
- `src/libslic3r/MacUtils.mm` - macOS-specific utilities (Objective-C++)
- Windows-specific build scripts and configurations
- Linux distribution support scripts in `scripts/linux.d/`

### Build and Development Tools
- `cmake/modules/` - Custom CMake find modules and utilities
- `scripts/` - Python utilities for profile generation and validation  
- `tools/` - Windows build tools (gettext utilities)
- `deps/` - External dependency build configurations

## Development Workflow

### Code Style and Standards
- **C++17 standard** with selective C++20 features
- **Naming conventions**: PascalCase for classes, snake_case for functions/variables
- **Header guards**: Use `#pragma once` 
- **Memory management**: Prefer smart pointers, RAII patterns
- **Thread safety**: Use TBB for parallelization, be mindful of shared state

### Common Development Tasks

#### Adding New Print Settings
1. Define setting in `PrintConfig.cpp` with proper bounds and defaults
2. Add UI controls in appropriate GUI components  
3. Update serialization in config save/load
4. Add tooltips and help text for user guidance
5. Test with different printer profiles

#### Modifying Slicing Algorithms  
1. Core algorithms live in `libslic3r/` subdirectories
2. Performance-critical code should be profiled and optimized
3. Consider multi-threading implications (TBB integration)
4. Validate changes don't break existing profiles
5. Add regression tests where appropriate

#### GUI Development
1. GUI code resides in `src/slic3r/GUI/` (not visible in current tree)
2. Use existing wxWidgets patterns and custom controls
3. Support both light and dark themes
4. Consider DPI scaling on high-resolution displays
5. Maintain cross-platform compatibility

#### Adding Printer Support
1. Create JSON profile in `resources/profiles/[manufacturer].json`
2. Add printer-specific start/end G-code templates
3. Configure build volume, capabilities, and material compatibility
4. Test thoroughly with actual hardware when possible
5. Follow existing profile structure and naming conventions

### Dependencies and Build System
- **CMake-based** with separate dependency building phase
- **Dependencies** built once in `deps/build/`, then linked to main application  
- **Cross-platform** considerations important for all changes
- **Resource files** embedded at build time, platform-specific handling

### Performance Considerations
- **Slicing algorithms** are CPU-intensive, profile before optimizing
- **Memory usage** can be substantial with complex models
- **Multi-threading** extensively used via TBB
- **File I/O** optimized for large 3MF files with embedded textures
- **Real-time preview** requires efficient mesh processing

## Important Development Notes

### Codebase Navigation
- Use search tools extensively - codebase has 500k+ lines
- Key entry points: `src/OrcaSlicer.cpp` for application startup
- Core slicing: `libslic3r/Print.cpp` orchestrates the slicing pipeline
- Configuration: `PrintConfig.cpp` defines all print/printer/material settings

### Compatibility and Stability
- **Backward compatibility** maintained for project files and profiles
- **Cross-platform** support essential (Windows/macOS/Linux)  
- **File format** changes require careful version handling
- **Profile migrations** needed when settings change significantly

### Quality and Testing
- **Regression testing** important due to algorithm complexity
- **Performance benchmarks** help catch performance regressions
- **Memory leak** detection important for long-running GUI application
- **Cross-platform** testing required before releases
