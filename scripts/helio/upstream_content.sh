#!/usr/bin/env bash
#
# Content-based answers about what the current branch holds, independent of
# ancestry.
#
# helio-upstream-sync.yml squash-merges its PRs, which discards upstream
# ancestry. Every ancestry-based question ("is this release merged?", "what is
# our merge base?") therefore returns the wrong answer on this fork, and the
# workflow's history is a series of guards that looked like they answered a
# content question but actually asked an ancestry one, or asked about a record
# rather than about the tree.
#
# This script only ever compares trees. It is used from two steps of the
# workflow — `Check if already synced` and `Establish correct merge base` — so
# that "does this branch hold release X?" has ONE implementation. It lived
# inline in the graft step before, which is why the check step could not use it
# and went on trusting the tracking tag.
#
#   base-below <ref> [n]   the nth stable release tag strictly older than <ref>
#   missing <candidate>    upstream paths at <candidate> this tree never received
#   unknown <candidate>    paths where presence cannot be decided from content
#   holds <candidate>      exit 0 only if nothing is missing AND nothing unknown
#   base-ok <candidate>    exit 0 if nothing is missing (unknown tolerated)
#   first-held <start> [strict]
#                          newest commit at or below <start> usable as a base;
#                          `strict` demands `holds`, the default `base-ok`
#
# `holds` and `base-ok` differ on purpose, because the two callers need opposite
# treatment of "cannot tell":
#
#   * `holds` answers "is the sync already done?", and a true there SKIPS the
#     sync and advances the tracking tag. Guessing yes drops a release silently,
#     so undecidable must read as NOT held.
#   * `base-ok` answers "is this safe as a merge base?". Guessing no leaves no
#     graft, and the merge then runs against the ancient pre-squash ancestor and
#     conflicts every week. Undecidable is tolerated there.
#
# Collapsing the two is a real bug and was one: the conflict case was reasoned
# about for the graft base, then the same function was reused for the skip
# decision, where the safe direction is inverted.
#
# Run against the repository in the current working directory; `HEAD` is the
# branch being asked about.

set -euo pipefail

# How many releases of INHERITED content a candidate must account for.
#
# One is not enough: validating only a candidate's own delta assumes everything
# below it, and the assumption fails exactly when the gap sits under a small
# step (a release whose whole delta is a version bump the fork already carries).
# Any finite window still has a floor — a change older than the base is outside
# the diff and invisible — so this is a depth/cost trade, not a proof. Four
# releases is well past the one-release lie that has actually occurred here,
# while keeping the compared diff small enough that the ambiguous set stays
# roughly Helio's own touchpoints.
CONTENT_DEPTH="${CONTENT_DEPTH:-4}"
# How far to walk down looking for a base whose content we do hold.
MAX_WALK="${MAX_WALK:-6}"

EMPTY_BLOB="0000000000000000000000000000000000000000"

# Same exclusion the sync-target selection uses. Upstream tags several
# prereleases per release, so counting them as steps keeps the walk INSIDE one
# release family: `base_below v2.4.2 2` would return v2.4.2-rc1 rather than
# v2.4.0, the diff would not span the release that was actually skipped, and the
# depth guarantee this file rests on would be silently worth nothing.
# Must stay byte-identical to the grep in helio-upstream-sync.yml's "Resolve
# sync target" step (drift is pinned by test_sync_noop_guards.py).
PRERELEASE_RE='-(alpha|beta|rc|pre|dev)([.-]?[0-9A-Za-z]+)?$'

# base_below <ref> <n>: the nth release tag strictly older than <ref> on its
# ancestry; the oldest reachable if there are fewer than n; <ref>^1 if there are
# no release tags at all. Empty only at the start of history.
#
# Ordered by ANCESTRY, walking `git describe` down successive first parents.
# Sorting `git tag --merged` by creatordate looks equivalent and is not: tags
# sharing a timestamp come back in an arbitrary order, so the walk could return a
# base one release too NEW — the exact thing this whole file exists to reject.
base_below() {
  local ref="$1" want="${2:-$CONTENT_DEPTH}" c i p t last=""
  c=$(git rev-parse "${ref}^{commit}")
  for (( i=0; i<want; i++ )); do
    p=$(git rev-parse -q --verify "${c}^1" 2>/dev/null || true)
    t=""
    # Walk back past prereleases until a stable release tag is found.
    while [ -n "$p" ]; do
      t=$(git describe --tags --abbrev=0 --match 'v*' "$p" 2>/dev/null || true)
      [ -n "$t" ] || break
      printf '%s' "$t" | grep -Eqi -- "$PRERELEASE_RE" || break
      p=$(git rev-parse -q --verify "refs/tags/$t^{commit}^1" 2>/dev/null || true)
      t=""
    done
    [ -n "$t" ] || break
    c=$(git rev-parse "refs/tags/$t^{commit}")
    last="$c"
  done
  if [ -n "$last" ]; then echo "$last"; return 0; fi
  git rev-parse -q --verify "${ref}^1" 2>/dev/null || true
}

# Write a blob to a file, or an empty file for the all-zero (absent) id.
_blob_to() {
  if [ "$1" = "$EMPTY_BLOB" ]; then : > "$2"; else git cat-file blob "$1" > "$2" 2>/dev/null || : > "$2"; fi
}

# _change_state <orig> <ours> <theirs>: for a path all three sides changed, is
# upstream's orig->theirs change already in our blob? Prints held|absent|unknown.
#
# This is the case comparing path NAMES could not see. If upstream edits one
# hunk and Helio independently edits another hunk of the same file, the path
# appears on both sides and a name-level set difference cancels it out — while
# upstream's hunk is genuinely absent. Only looking inside the file answers it.
#
# A clean three-way merge that leaves our blob alone means we already have it. A
# clean merge that CHANGES our blob means upstream's edit applies and we did not
# have it. A CONFLICT means the two edits overlap and this cannot tell: an
# up-to-date fork whose local edit sits on top of upstream's in the same region
# conflicts exactly like a fork that never received it.
#
# `unknown` is a THIRD answer, not a synonym for held. Folding it into held is
# what let a conflicting merge satisfy the already-synced check and skip a real
# sync; folding it into absent would reject Helio's own touchpoint files weekly.
# The callers decide which way to lean, because they lean opposite ways.
_change_state() {
  local orig="$1" ours="$2" theirs="$3" dir out
  dir=$(mktemp -d)
  _blob_to "$orig" "$dir/base"
  _blob_to "$ours" "$dir/ours"
  _blob_to "$theirs" "$dir/theirs"
  if git merge-file -q -p "$dir/ours" "$dir/base" "$dir/theirs" > "$dir/merged" 2>/dev/null; then
    if cmp -s "$dir/ours" "$dir/merged"; then out=held; else out=absent; fi
  else
    # Conflict, binary, or a merge-file error — all indistinguishable here.
    #
    # BINARIES ARE THE UNMEASURED CASE. `git merge-file` exits 255 on binary
    # content, so any binary upstream changed that Helio also changed is
    # permanently `unknown`, and `holds` refuses on unknown. Mostly that is
    # cheap: a false `holds`=0 sends the run to the merge, where the `noop`
    # tree comparison decides correctly. The exception is a conflict-resolution
    # sync, where `noop` never runs — there it would mean a conflict issue
    # refreshed weekly for a merged sync.
    #
    # Helio's image touchpoints are ADDITIONS (`helio_*.svg`, `expand_helio.png`),
    # which upstream never touches and which therefore never enter this
    # comparison at all. So the exposure looks empty in practice — but that is
    # read off HELIO_INTEGRATION.md, not measured against a real four-release
    # window, and it should be measured before being relied on.
    out=unknown
  fi
  rm -rf "$dir"
  printf '%s' "$out"
}

# missing_paths <base> <candidate>: upstream paths changed between base and
# candidate that this tree demonstrably never received.
#
# Two `git diff --raw` calls give every blob id on both sides, so classification
# is text processing rather than a merge per path. Only the ambiguous remainder
# — paths where our blob matches neither side, i.e. roughly Helio's own
# touchpoints — costs a three-way merge.
_classify_paths() {
  local base="$1" cand="$2" meta path orig theirs ours
  declare -A U_ORIG U_NEW OURS

  # `git diff --raw` gives ":srcmode dstmode srcsha dstsha status\tpath", so the
  # word splitting on $meta below is deliberate, not an oversight.
  #
  # core.quotePath=false stops git octal-escaping non-ASCII paths. Correctness
  # does not depend on it — the path is only a key for cross-referencing the two
  # diffs, and both quote identically, while the comparison itself is on blob
  # ids — but this repository has accented filenames under resources/profiles,
  # and "never applied: \"resources/profiles/w\\303\\251ird.json\"" is not a
  # message anyone can act on.
  while IFS=$'\t' read -r meta path; do
    [ -n "${path:-}" ] || continue
    # shellcheck disable=SC2086  # splitting the raw header into fields is the point
    set -- $meta
    # MODE and blob together. A path whose only change is 100644 -> 100755 has
    # identical blob ids on both sides, so comparing blobs alone reports nothing
    # missing and the executable bit is dropped from the sync for good. Same for
    # a regular file becoming a symlink.
    U_ORIG["$path"]="${1#:} $3"; U_NEW["$path"]="$2 $4"
  done < <(git -c core.quotePath=false diff --raw --no-renames "$base" "$cand" 2>/dev/null || true)

  while IFS=$'\t' read -r meta path; do
    [ -n "${path:-}" ] || continue
    # shellcheck disable=SC2086  # as above
    set -- $meta
    OURS["$path"]="$2 $4"
  done < <(git -c core.quotePath=false diff --raw --no-renames "$base" HEAD 2>/dev/null || true)

  [ "${#U_NEW[@]}" -gt 0 ] || return 0
  for path in "${!U_NEW[@]}"; do
    orig="${U_ORIG[$path]}"
    theirs="${U_NEW[$path]}"
    # A path absent from our own diff against base is unchanged from base.
    ours="${OURS[$path]:-$orig}"
    if [ "$theirs" = "$ours" ]; then continue; fi                        # held
    if [ "$ours" = "$orig" ]; then printf 'missing\t%s\n' "$path"; continue; fi
    # MODE FIRST, before the text merge, because the text merge cannot see modes
    # and answers `held` for a mode change that is genuinely absent.
    #
    # Upstream flips 100644 -> 100755 and changes nothing else, while Helio
    # independently edits the blob. All three composite values then differ, so we
    # reach here — but `_change_state` is handed blob ids only, and upstream's
    # blob equals the base's, so the three-way merge leaves our blob alone and
    # returns `held`. `holds` succeeds and the executable bit is dropped from the
    # sync for good. Comparing the composite values (added for the mode-ONLY
    # case) does not catch this one: our blob diverges too, so the composites
    # differ for a reason that has nothing to do with the mode.
    #
    # So decide the mode separately, and in three ways rather than two — the
    # same held/absent/unknown split the blobs get, for the same reason.
    if [ "${theirs%% *}" != "${orig%% *}" ]; then
      if [ "${ours%% *}" = "${orig%% *}" ]; then
        # We are still sitting at the base's mode, so we never received the
        # change. Whatever the blobs say cannot make it present.
        printf 'missing\t%s\n' "$path"; continue
      elif [ "${ours%% *}" != "${theirs%% *}" ]; then
        # Upstream moved the mode and we moved it somewhere ELSE — Helio chmod'd
        # the file independently. That is the mode equivalent of an overlapping
        # hunk: "we took upstream's change and then changed it again" and "we
        # never got upstream's change and changed it ourselves" produce the same
        # three values. A text merge cannot rule on it, and letting it fall
        # through to the blobs invites exactly the `held` this block exists to
        # prevent. Undecidable, so say so.
        printf 'unknown\t%s\n' "$path"; continue
      fi
      # ours == theirs: we already carry upstream's mode. Fall through and let
      # the blobs decide the rest of the change.
    fi
    # Blobs. Only looking inside the file can decide, and it may not be able to.
    case "$(_change_state "${orig#* }" "${ours#* }" "${theirs#* }")" in
      absent)  printf 'missing\t%s\n' "$path" ;;
      unknown) printf 'unknown\t%s\n' "$path" ;;
    esac
  done
}

# The classification is a pure function of three trees — the base's, the
# candidate's, and HEAD's — and the callers keep re-asking it: every verb runs
# it, and the graft step's candidate phases plus the check step's warnings ask
# about the same (base, candidate) pair several times per run, each costing two
# full-tree raw diffs and a merge per ambiguous path. Cache each answer in a
# file keyed on the three content ids. Keying on content is what makes a stale
# entry impossible — any input changing changes the key, so a new HEAD, a
# retagged candidate, or another repository all miss rather than mislead. The
# write is atomic (mktemp + mv) so a killed run cannot leave a half answer for
# the next one; an empty file is a valid answer (nothing missing or unknown).
classify_paths() {
  local base cand cache tmp
  # No base: start of history, nothing underneath — same empty answer the
  # uncached diff produced for it.
  [ -n "${1:-}" ] || return 0
  base=$(git rev-parse "$1^{commit}")
  cand=$(git rev-parse "$2^{commit}")
  cache="${TMPDIR:-/tmp}/helio-upstream-content-${base}-${cand}-$(git rev-parse 'HEAD^{tree}')"
  if [ -f "$cache" ]; then cat "$cache"; return 0; fi
  tmp=$(mktemp "${cache}.XXXXXX")
  _classify_paths "$base" "$cand" > "$tmp"
  mv -f "$tmp" "$cache"
  cat "$cache"
}

missing_paths()  { classify_paths "$1" "$2" | sed -n 's/^missing\t//p'; }
unknown_paths()  { classify_paths "$1" "$2" | sed -n 's/^unknown\t//p'; }

# Strict: nothing missing AND nothing undecidable. Used for the "is the sync
# already done?" question, where a wrong yes skips a release silently.
holds_content() {
  local candidate="$1" base
  base=$(base_below "$candidate")
  # No older release and no parent: the start of history, so there is nothing
  # underneath that could be missing.
  [ -n "$base" ] || return 0
  [ -z "$(classify_paths "$base" "$candidate")" ]
}

# Permissive: nothing definitively missing; undecidable is tolerated. Used for
# "is this safe as a merge base?", where a wrong no costs a weekly conflict.
base_ok() {
  local candidate="$1" base
  base=$(base_below "$candidate")
  [ -n "$base" ] || return 0
  [ -z "$(missing_paths "$base" "$candidate")" ]
}

# first_held <start> [strict]: the newest commit at or below <start> usable as a
# merge base.
#
# Walking down on failure matters — rejecting outright leaves no graft, and the
# merge then runs against the ancient pre-squash ancestor and conflicts, which is
# a treadmill this workflow has produced before. A base that is too old only
# costs conflict volume; one that is too new drops work silently.
#
# Default is permissive (`base_ok`), so an undecidable path does not cost the
# graft entirely. `strict` uses `holds_content`, and exists for the caller that
# wants a base carrying nothing undecidable at all: an undecidable path in the
# BASE is the one shape that drops upstream work without a conflict, because if
# the base already carries upstream's value and the target has not moved it
# since, the three-way merge sees theirs == base and silently keeps ours.
first_held() {
  local c mode="${2:-permissive}" i
  # Normalise to a commit id so the answer does not depend on whether the caller
  # passed a tag or a sha — this value is echoed into warnings and grafted.
  c=$(git rev-parse -q --verify "${1:-}^{commit}" 2>/dev/null || true)
  for (( i=0; i<MAX_WALK; i++ )); do
    [ -n "$c" ] || return 1
    if [ "$mode" = "strict" ]; then
      if holds_content "$c"; then echo "$c"; return 0; fi
    elif base_ok "$c"; then
      echo "$c"; return 0
    fi
    c=$(base_below "$c" 1)
  done
  return 1
}

case "${1:-}" in
  base-below) base_below "$2" "${3:-$CONTENT_DEPTH}" ;;
  missing)    missing_paths "$(base_below "$2")" "$2" ;;
  unknown)    unknown_paths "$(base_below "$2")" "$2" ;;
  holds)      holds_content "$2" ;;
  base-ok)    base_ok "$2" ;;
  first-held) first_held "$2" "${3:-}" ;;
  *) echo "usage: $0 {base-below|missing|unknown|holds|base-ok|first-held} <ref>" >&2; exit 2 ;;
esac
