# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Helio Integration

This is the Helio-Additive fork of OrcaSlicer. For Helio integration details, conflict resolution rules during upstream syncs, and the complete file-by-file modification map, see **`HELIO_INTEGRATION.md`**.

## CI/CD Workflows

### Upstream Sync (`helio-upstream-sync.yml`)
- Scheduled workflow that syncs upstream OrcaSlicer changes into `orca-latest-parity-bambu`
- Auto-creates merge conflict issues (labeled `upstream-sync`, `claude-work`) when conflicts occur. Deduped by title: a repeat run with the same unresolved conflict refreshes the existing open `upstream-sync` issue's body rather than opening another one
- Auto-creates sync PRs with changelog and Helio-relevant change reports
- Uses `claude-work` label to flag items for automated triage
- Detects out-of-band merges (e.g. manual PRs) via ancestor check and auto-updates the tracking tag
- **Never opens an empty PR.** "Already synced?" is answered cheapest first, but only **content-backed** answers may skip a run: the tracking tag equalling the target (a commit id, and only ever written after content was validated), the ancestor/trial-merge checks, the `upstream_content.sh holds` test, and — as the backstop — comparing the **merged tree** with the target branch's tree after the grafted merge. `version.inc` equalling the target is *not* on that list: it is a version string, it sets an expectation only, and it cannot skip on its own (see the next bullet). Two of those checks are immune to squash-flattened history — `upstream_content.sh holds` and the merged-tree comparison, both of which ask the tree — while the ancestor check and the pre-graft trial merge are not, which is what produced the empty #107. The merged-tree comparison is the backstop because it is the only one that runs *after* the corrected merge. A no-op merge skips the PR, explains itself in the job summary, and advances the tracking tag
- **`version.inc` sets an expectation; it never skips a run on its own.** It is a version string, and the release it names can stop describing the tree without the file changing (upstream force-retagging a release we already synced, or a local version bump landing before the content). Skipping there would silently drop upstream work — far worse than #107's empty PR. Three invariants protect this: every write of the tracking tag must be content-backed (that is why the *tag* may skip a run but `version.inc` may not, and why opening a sync PR no longer advances it — see below); the merge-base graft requires a **strict** ancestor, falling back to the target's first parent when the records name the target itself; and **every** graft candidate — `version.inc` and the tracking tag alike — must be validated for its **inherited** content, not just its own delta. Validation compares **trees**, in `scripts/helio/upstream_content.sh` — shared with the `check` step so "does this branch hold release X?" has one implementation. A path upstream changed between a base four releases down and the candidate, which our tree still holds at the base version, is a change we never applied. Comparing changed path *names* is not enough: if upstream edits one hunk of a file and Helio independently edits another, the path appears on both sides and cancels out while upstream's hunk is absent — so blob **and mode** are compared (a mode-only `100644`→`100755` change has identical blobs and would otherwise be dropped for good), and where ours matches neither side a three-way merge decides. A conflict is a third answer, `unknown`, not a synonym for held: `holds` (the already-synced question, where a wrong yes skips a release) refuses on unknown, while `base-ok` (the merge-base question, where a wrong no means a weekly conflict) tolerates it. Tolerating it is not the same as *preferring* it, and the graft no longer accepts an undecidable candidate outright: an undecidable path in the **base** is the one shape that drops upstream work without a conflict, because if the base already carries upstream's value and the sync target has not moved it since, the three-way merge sees theirs == base and keeps ours silently. So a candidate carrying undecidable paths is used only after `first-held … strict` fails to find a provably-held base below it — and when it is used, the run says so and names the paths. Candidate records are evaluated **newest-first by ancestry, with fall-through** — strictly-held on any candidate beats degraded acceptance on any, and the walk-down below a candidate starts only after every newer candidate has failed. Record preference (version.inc, tag, then the target's first parent when the records self-name the target) is not ancestry order, and evaluating in record order let a stale tracking tag's walk-down graft v2.3.0 under a tree that fully held the target — turning the designed no-op verification merge into a weekly conflict for an already-merged release. A mode change is decided **before** the text merge for the same reason: upstream flipping `100644`→`100755` while Helio independently edits the blob leaves the text merge comparing blobs whose modes it cannot see, and it answers `held` for a change we never received. The ancestry walk skips prerelease tags, using the same exclusion as the sync-target selection — counting `v2.4.2-rc1` as a step keeps the window inside one release family and makes the depth guarantee worthless. Within the walk, releases are ordered by ancestry via `git describe`, not by tag date. A candidate that fails is not dropped — the run walks down to the newest commit whose content is present (provably-held preferred; the permissive fallback carries undecidable paths by construction and the run names them), names the files that were never applied, and grafts that. Choosing a graft base is asymmetric: too old only inflates the conflict set, too new makes git treat the missing content as deliberate reversions and drop it from the sync silently. Regression tests: `scripts/helio/test_sync_noop_guards.py` (runs the real step bodies extracted from the workflow)
- **Opening a sync PR does not advance the tracking tag.** It used to, which made `helio-last-synced` a record of "a PR exists" while every reader treated it as "this content is on the branch". A PR closed unmerged then skipped that release permanently, and a PR left open got grafted as a merge base it had not earned. The tag now advances only on evidence the content is on the branch — the ancestor hit, the no-diff trial merge, the merged-tree comparison, or the content test below. Runs in between redo the merge and refresh the same PR
- **"Already synced?" is ultimately a content question, so `check` asks the tree.** `upstream_content.sh holds <target>` is ancestry-independent and therefore immune to the squash, unlike the ancestor check and the pre-graft trial merge above it. It covers three cases those miss: an out-of-band merge, a **conflict** sync whose resolution branch was squash-merged (the ancestor check misses it, the trial merge conflicts against the wrong base, and `noop` never runs because `noop` only runs after a *clean* merge — so nothing would ever record that a resolved sync landed, and the conflict issue would be refreshed weekly for ever), and a **legacy** tracking tag written by the old PR-creation path. A tag that fails this check is marked untrusted for the whole run: rejecting it at the early exit alone was not enough, because it also feeds the baseline, and a baseline equal to the target hits a second "nothing to sync" exit further down
- **A resolved conflict sync is completed by evidence from GitHub, not from content.** This is the one guard in the workflow that leaves git, and it is there because the question is not answerable any other way: resolving a conflict *means* deliberately not taking some of upstream's content, so afterwards a tree that never received the sync and a tree whose resolver kept Helio's version are byte-identical. `upstream_content.sh holds` therefore answers "not synced" for ever on a finished conflict sync, the ancestor check misses it (the resolution branch is squash-merged too), and `noop` never runs because `noop` only runs after a *clean* merge — so the sync is re-proposed every Monday and the conflict issue refreshed, asking a human to redo work already done. `scripts/helio/sync_completion.sh` asks the API instead: is there a **merged** PR, based on the release branch, carrying `<!-- helio-sync-target: <sha> -->` for this exact commit? The marker names a **commit, not a tag**, so an upstream force-retag stops matching and the release is correctly re-proposed. A marker naming a *different* sha rejects that PR outright and is never reconsidered by the branch-name fallback — getting that wrong reinstated the retag hole while appearing to close it, and is caught by a regression test. Branch-name matching survives only for PRs opened before the marker existed, and warns on stderr when used. Closed-but-unmerged never counts (that is the "closed PR skips the release for ever" bug from the other side), and an API failure reads as "cannot tell", falling through to the ordinary merge path rather than to a false skip; `gh --paginate`'s concatenated page arrays are decoded value-by-value, so a branch with more than one page of closed PRs does not degrade the signal. The conflict issue tells resolvers to paste the marker into their PR, and says what breaks if they don't
- **The tracking tag is a convenience, not a source of truth.** `helio-last-synced` only moves on a successful push at the end of a run, so an out-of-band merge or a refused push leaves it stale (it sat at `v2.3.2-rc2` through three releases). For tag-release syncs `version.inc` is preferred as the baseline whenever it names a strictly newer release, and a **refused tag push warns instead of failing the run**. The refusal is not intermittent and not a tag-protection rule, which is what it was assumed to be until [run 32014594574](https://github.com/Helio-Additive/OrcaSlicer/actions/runs/32014594574) printed the real message: `refusing to allow a GitHub App to create or update workflow '.github/workflows/build_all.yml' without 'workflows' permission`. Pointing the tag at an **upstream** commit makes upstream's `.github/workflows/**` newly reachable from a ref in this repo, and GitHub blocks any GitHub App token from creating such a ref without the `workflows` permission — which is **not** among the scopes a workflow's `permissions:` block can grant. So `GITHUB_TOKEN` can never do this, on any run; that is why the tag sat at `v2.3.2-rc2` through three releases rather than failing occasionally. Options, none yet chosen: a PAT with `workflows` scope as a repo secret; dropping the tag (it is already non-load-bearing); or pointing it at the **Helio** commit with the upstream sha in an annotated tag message, which needs no new permission because that commit is already reachable. Until then, heal it by hand with `git push helio +<commit>:refs/tags/helio-last-synced` (`helio`, not `origin` — you are in your own clone, where origin is upstream; the workflow's own pushes use `origin` because inside Actions origin is this fork)
- Handles pre-existing conflict branches safely: skips the push entirely when the branch has an **open PR** (resolution in flight), otherwise checks for divergence before replacing (skips if someone has pushed resolution commits, force-pushes to replace stale branches from previous runs). The open-PR check has to come first: resolvers squash their branch to satisfy `require-squashed-sync`, which rewrites history and defeats the ancestor test. A force-push rejected by a repository ruleset is warned about, not treated as a sync failure. Whenever the push is skipped for any of these reasons, the step reports `pushed=false` and the auto-created conflict issue leads with a warning saying the branch does **not** hold that run's conflict state, so resolvers redo the merge from the release branch instead of trusting a stale branch.
- Detects squash merges: when the ancestor check fails, tries a trial merge to detect if content is already incorporated. Note this runs **before** the merge-base graft, so on a squash-flattened history it is computed against the same wrong base the graft exists to correct and usually conflicts instead — it is a cheap early exit, not a guarantee. The tree comparison above is what actually holds
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
- Triggers on push/PR to `main`, `release/*` and `orca-latest-parity-bambu`
- Runs full build matrix + unit tests + Flatpak builds
- **On `orca-latest-parity-bambu`, PR builds are opt-in**: the PR must carry the
  `ready-to-build` label. PRs to `main` / `release/*` are not label-gated. This is how a
  reviewer asks for build artifacts on a parity PR. Four jobs enforce it directly —
  `build_linux`, `build_windows`, `build_macos_arch`, `flatpak` each carry the `if:`.
  The other two do not: `build_macos_universal` (`needs: build_macos_arch`) and
  `unit_tests` (`needs: build_linux`) skip only because their dependency skipped. Same
  outcome today, but the gate on those two is inherited, not stated — dropping or
  re-pointing a `needs:` would let them run unlabelled.
- **The `paths:` filter runs before the label gate.** GitHub evaluates trigger paths at
  the workflow level, so a PR that touches no path in the `pull_request` `paths:` list
  never starts the workflow at all and the `ready-to-build` label does nothing — the
  label cannot re-trigger a workflow that was filtered out. Keep the `pull_request`
  `paths:` list a superset of anything a reviewer might want built; it previously omitted
  `resources/**` and `localization/**` (which the `push` filter already had), which left
  the label inert on profile-only and translation-only PRs.
- Adding those paths does **not** make profile syncs build automatically — the label gate
  still skips every job on an unlabelled parity-branch PR. Widening `paths:` only changes
  whether the workflow *starts*; the label decides whether it *builds*. The exception is
  PRs based on `main` / `release/*`, which are not label-gated: a profile-only *or*
  translation-only PR to those branches now builds the full matrix. This fork opens none.

### Profile & locale validation — inactive on this fork
`check_profiles.yml` and `check_locale.yml` are inherited from upstream and both declare
`pull_request: branches: [main]`. This fork's PRs target `orca-latest-parity-bambu`, so
**neither has ever run on a PR here**, and `check_profiles_comment.yml` (which reports
results via `workflow_run` on "Check profiles") is dead along with them.

Do not simply add the parity branch to those filters: as of v2.4.2 the inherited profile
data does not pass the validator the workflow downloads. `check_profiles.yml` fetches the
**nightly** validator built from upstream `main`, while this fork is pinned to the v2.4.2
release, so the validator rejects keys that were valid at v2.4.2 and removed later
(`machine_prepare_compensation_time`, the `filament_dev_ams_drying_*` family). Turning the
workflow on unchanged would fail every profile PR immediately. Pinning the validator to the
matching release, or scoping validation to changed vendors, has to be decided first.

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
