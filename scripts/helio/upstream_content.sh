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
#   base-below <ref> [n]   the nth release tag strictly older than <ref>
#   missing <candidate>    upstream paths at <candidate> this tree never received
#   holds <candidate>      exit 0 if this tree holds <candidate>'s content
#   first-held <start>     newest commit at or below <start> whose content we hold
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
    [ -n "$p" ] || break
    t=$(git describe --tags --abbrev=0 --match 'v*' "$p" 2>/dev/null || true)
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

# _change_absent <orig> <ours> <theirs>: for a path all three sides changed,
# does our blob already contain upstream's orig->theirs change?
#
# This is the case comparing path NAMES could not see. If upstream edits one
# hunk and Helio independently edits another hunk of the same file, the path
# appears on both sides and a name-level set difference cancels it out — while
# upstream's hunk is genuinely absent. Only looking inside the file answers it.
#
# A clean three-way merge that CHANGES our blob means upstream's edit applies and
# we did not have it: definitively missing. A clean merge that leaves our blob
# alone means we already have it. A CONFLICT means the two edits overlap, which
# is inconclusive by nature — an up-to-date fork whose local edit sits on top of
# upstream's in the same region conflicts here too, so rejecting on conflict
# would reject precisely Helio's own touchpoint files every week. Inconclusive
# is reported by the caller rather than treated as missing.
_change_absent() {
  local orig="$1" ours="$2" theirs="$3" dir rc
  dir=$(mktemp -d)
  _blob_to "$orig" "$dir/base"
  _blob_to "$ours" "$dir/ours"
  _blob_to "$theirs" "$dir/theirs"
  if git merge-file -q -p "$dir/ours" "$dir/base" "$dir/theirs" > "$dir/merged" 2>/dev/null; then
    if cmp -s "$dir/ours" "$dir/merged"; then rc=1; else rc=0; fi
  else
    rc=1  # conflict or binary: inconclusive, do not claim missing
  fi
  rm -rf "$dir"
  return $rc
}

# missing_paths <base> <candidate>: upstream paths changed between base and
# candidate that this tree demonstrably never received.
#
# Two `git diff --raw` calls give every blob id on both sides, so classification
# is text processing rather than a merge per path. Only the ambiguous remainder
# — paths where our blob matches neither side, i.e. roughly Helio's own
# touchpoints — costs a three-way merge.
missing_paths() {
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
    U_ORIG["$path"]="$3"; U_NEW["$path"]="$4"
  done < <(git -c core.quotePath=false diff --raw --no-renames "$base" "$cand" 2>/dev/null || true)

  while IFS=$'\t' read -r meta path; do
    [ -n "${path:-}" ] || continue
    # shellcheck disable=SC2086  # as above
    set -- $meta
    OURS["$path"]="$4"
  done < <(git -c core.quotePath=false diff --raw --no-renames "$base" HEAD 2>/dev/null || true)

  [ "${#U_NEW[@]}" -gt 0 ] || return 0
  for path in "${!U_NEW[@]}"; do
    orig="${U_ORIG[$path]}"
    theirs="${U_NEW[$path]}"
    # A path absent from our own diff against base is unchanged from base.
    ours="${OURS[$path]:-$orig}"
    if [ "$theirs" = "$ours" ]; then continue; fi                # we hold it
    if [ "$ours" = "$orig" ]; then echo "$path"; continue; fi    # never applied
    # All three differ: only looking inside the file can decide.
    if _change_absent "$orig" "$ours" "$theirs"; then echo "$path"; fi
  done
}

holds_content() {
  local candidate="$1" base missing
  base=$(base_below "$candidate")
  # No older release and no parent: the start of history, so there is nothing
  # underneath that could be missing.
  [ -n "$base" ] || return 0
  missing=$(missing_paths "$base" "$candidate")
  [ -z "$missing" ]
}

# first_held <start>: the newest commit at or below <start> whose content this
# tree holds. Walking down on failure matters — rejecting outright leaves no
# graft, and the merge then runs against the ancient pre-squash ancestor and
# conflicts, which is a treadmill this workflow has produced before. A base that
# is too old only costs conflict volume; one that is too new drops work silently.
first_held() {
  local c="$1" i
  for (( i=0; i<MAX_WALK; i++ )); do
    [ -n "$c" ] || return 1
    if holds_content "$c"; then echo "$c"; return 0; fi
    c=$(base_below "$c" 1)
  done
  return 1
}

case "${1:-}" in
  base-below) base_below "$2" "${3:-$CONTENT_DEPTH}" ;;
  missing)    missing_paths "$(base_below "$2")" "$2" ;;
  holds)      holds_content "$2" ;;
  first-held) first_held "$2" ;;
  *) echo "usage: $0 {base-below|missing|holds|first-held} <ref>" >&2; exit 2 ;;
esac
