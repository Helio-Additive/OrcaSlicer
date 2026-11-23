#pragma once

// Helio release channel.
//
// This header is the *only* thing in the tree that says which channel a build
// belongs to, and it is the one file that deliberately differs between the two
// branches:
//
//   orca-latest-parity-bambu  ->  "stable"        HELIO_EXPERIMENTAL_BUILD 0
//   helio-experimental        ->  "experimental"  HELIO_EXPERIMENTAL_BUILD 1
//
// `helio-experimental` is a two-line branch off the release branch — this file
// and the version in `version.inc` — re-created whenever an experimental build
// is cut. Experimental *code* does not live there: it merges to the release
// branch like anything else and stays dark behind
// helio_experimental_features_enabled(). A feature therefore graduates by
// deleting its gate, not by porting it, and what stable eventually ships is the
// same code the experimental testers ran.
//
// The channel comes from the checked-out content rather than a build flag
// because the compile is done by the upstream-owned build_orca.yml, which
// checks a ref out and builds it as-is. Teaching it a "build with feature X"
// input would be an upstream file edit, and so a merge conflict on every future
// sync. A branch costs nothing and cannot disagree with what was compiled.
//
// Consumers use the constexpr accessors below rather than #if, so both sides of
// every channel-dependent path are compiled on both channels: a typo in
// experimental-only code fails the stable build instead of waiting for the next
// experimental release to be cut.

#define HELIO_RELEASE_CHANNEL "stable"
#define HELIO_EXPERIMENTAL_BUILD 0

// Release-tag prefixes written by helio-release.yml. Deliberately not prefixes
// of one another ("helio-exp-v..." does not start with "helio-v..."), so a tag
// belongs to exactly one channel and the update check can read the version out
// of either.
#define HELIO_STABLE_TAG_PREFIX "helio-v"
#define HELIO_EXPERIMENTAL_TAG_PREFIX "helio-exp-v"

namespace Slic3r {

// True in builds cut from the experimental branch.
inline constexpr bool helio_is_experimental_build() { return HELIO_EXPERIMENTAL_BUILD != 0; }

// "stable" or "experimental".
inline constexpr const char *helio_release_channel() { return HELIO_RELEASE_CHANNEL; }

// Gate for features that are shipped but not finished.
//
// Every in-progress feature is merged to the release branch behind this, so it
// is present in the source but absent from a stable build. Today it is the
// build channel alone. The intended next rung, once a feature has survived real
// testing, is `|| app_config->get_bool("enable_experimental_features")` — a
// Preferences opt-in that makes the work discoverable to stable users without
// turning it on for them. Graduation is then deleting the call.
//
// Note this gates *features*, not the update check: an experimental release is
// published as a GitHub prerelease and is deliberately offered to stable users,
// who accept or decline it in the update dialog. See HELIO_INTEGRATION.md.
inline constexpr bool helio_experimental_features_enabled() { return helio_is_experimental_build(); }

} // namespace Slic3r
