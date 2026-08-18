#!/usr/bin/env bash
#
# Did the sync for a given upstream target already land on the release branch?
# Answered from the GitHub API, not from git.
#
# WHY THIS EXISTS
# ---------------
# Every other "already synced?" guard in helio-upstream-sync.yml reasons about
# content (`upstream_content.sh`) or ancestry. Both are correct for a CLEAN
# sync. Neither can answer for a sync that CONFLICTED, and the reason is not a
# gap in the implementation — it is definitional:
#
#   Resolving a conflict means a human deliberately chose NOT to take some of
#   upstream's content.
#
# So after a resolved-and-merged conflict sync, the tree legitimately does not
# hold everything upstream has at that target. `upstream_content.sh holds`
# therefore answers "no", correctly, for ever. Ancestry answers "no" too,
# because the resolution branch is squash-merged like everything else here.
# `noop` never runs, because `noop` only runs after a clean merge.
#
# The result is a sync that IS finished being re-proposed every Monday: the
# merge re-conflicts, the conflict issue is refreshed, and a human is asked
# again to resolve something they already resolved. That is #107's shape
# reached from the conflict side, and no amount of looking at files can fix it,
# because "we never got this content" and "we got it and chose ours" produce
# byte-identical trees.
#
# The only system that knows the difference is GitHub: was the resolution PR
# merged? This script asks exactly that, and nothing else.
#
# WHAT COUNTS AS PROOF
# --------------------
# A pull request that is all of:
#   * merged (merged_at set — closed-unmerged must NOT count, that is the
#     "PR closed unmerged skips the release for ever" bug in reverse),
#   * based on the release branch we are syncing into,
#   * identified as this exact sync target.
#
# Identification prefers a machine-readable marker in the PR body:
#
#     <!-- helio-sync-target: <40-hex sync sha> -->
#
# written by the workflow when it opens the PR. The marker names a COMMIT, so
# it survives upstream force-retagging a release: a retag changes the sha, the
# marker stops matching, and the sync is correctly re-proposed. Matching on the
# branch name alone cannot distinguish those, because the branch name carries
# only the tag.
#
# Branch-name matching is kept as a fallback for PRs opened before the marker
# existed, and says so loudly on stderr — those are the only ones where a
# force-retag could be missed.
#
# USAGE
#   sync_completion.sh <sync_sha> <base_branch> [branch_name]
#
#   exit 0  a merged PR proves this target landed; evidence on stdout
#   exit 1  no such PR (or the API could not be consulted)
#
# TESTING
#   Set HELIO_PR_FIXTURE to a file containing the JSON array the API would
#   return. The script then never calls `gh`, so the decision logic is testable
#   without a network or a token.

set -euo pipefail

SYNC_SHA="${1:?usage: sync_completion.sh <sync_sha> <base_branch> [branch_name]}"
BASE_BRANCH="${2:?usage: sync_completion.sh <sync_sha> <base_branch> [branch_name]}"
BRANCH_NAME="${3:-}"

SHORT_SHA="${SYNC_SHA:0:7}"

# ---------------------------------------------------------------------------
# Fetch candidate PRs.
#
# Closed PRs based on the release branch. `merged` is not a queryable state on
# this endpoint (a merged PR is a closed one with merged_at set), so the filter
# happens below rather than in the query.
# ---------------------------------------------------------------------------
fetch_prs() {
  if [ -n "${HELIO_PR_FIXTURE:-}" ]; then
    cat "$HELIO_PR_FIXTURE"
    return 0
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "sync_completion: gh CLI unavailable — cannot consult the API" >&2
    return 1
  fi

  # --paginate: a busy release branch can have more closed PRs than one page,
  # and the resolution PR we are looking for is by definition an old one.
  gh api --paginate \
    "repos/${GITHUB_REPOSITORY:?GITHUB_REPOSITORY unset}/pulls?state=closed&base=${BASE_BRANCH}&per_page=100&sort=updated&direction=desc" \
    2>/dev/null || return 1
}

PRS="$(fetch_prs)" || {
  # An API failure must read as "cannot tell", never as "not synced" and never
  # as "synced". Returning 1 leaves the caller on its existing content-based
  # path, which is the pre-existing behaviour — degraded, not wrong.
  echo "sync_completion: could not reach the API; falling back to content checks" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Decide.
#
# python3 rather than jq: the marker test is a substring match against a body
# that may be null, and the branch-name fallback needs a suffix test. Both are
# awkward to keep readable in jq, and python3 is present on every runner.
# ---------------------------------------------------------------------------
RESULT="$(
  # The single quotes around the Python source are deliberate and load-bearing:
  # this is Python, not shell, and `$` in it must reach the interpreter intact.
  # Every shell value it needs is passed as an explicit argv entry below, which
  # is also what keeps a branch name or sha from being interpolated into source.
  # shellcheck disable=SC2016
  printf '%s' "$PRS" | python3 -c '
import json, sys

sync_sha   = sys.argv[1]
short_sha  = sys.argv[2]
base       = sys.argv[3]
branch     = sys.argv[4]

raw = sys.stdin.read().strip()
if not raw:
    sys.exit(1)

# `gh --paginate` concatenates pages: a list endpoint emits its pages as
# back-to-back top-level arrays ("[...][...]"), which a single json.loads
# rejects as trailing data. That is not a corner case — it is every run once
# the release branch has more than one page of closed PRs, and the resolution
# PR being looked for is by definition an old one. Decode value by value and
# flatten: an array is a page, a lone object is a single PR. Anything
# raw_decode cannot consume (truncated output, non-JSON) is still refused as
# malformed — that reads as "cannot tell", never as "synced".
decoder = json.JSONDecoder()
prs = []
pos = 0
try:
    while pos < len(raw):
        value, pos = decoder.raw_decode(raw, pos)
        if isinstance(value, list):
            prs.extend(value)
        elif isinstance(value, dict):
            prs.append(value)
        else:
            raise ValueError("top-level %s" % type(value).__name__)
        while pos < len(raw) and raw[pos] in " \t\r\n":
            pos += 1
except (json.JSONDecodeError, ValueError):
    print("MALFORMED", file=sys.stderr)
    sys.exit(1)

marker = "helio-sync-target: %s" % sync_sha

exact = None
fallback = None

for pr in prs:
    if not isinstance(pr, dict):
        continue
    if not pr.get("merged_at"):
        continue                                  # closed-unmerged proves nothing
    if (pr.get("base") or {}).get("ref") != base:
        continue                                  # merged somewhere else entirely

    body = pr.get("body") or ""
    if marker in body:
        exact = pr
        break                                     # sha-identified: authoritative

    # A marker that names a DIFFERENT sha is positive evidence about a different
    # target, not an absence of evidence — so this PR is out, and in particular
    # it must not be reconsidered by the branch-name fallback below.
    #
    # Getting this wrong defeats the entire reason the marker names a commit.
    # Upstream force-retags v2.4.2; the old resolution PR keeps both its stale
    # marker AND the branch name `helio-release-candidate-v2.4.2`; the marker
    # correctly declines, the branch name then accepts, and the retagged release
    # is skipped for ever. The first version of this script did exactly that and
    # the regression test below caught it.
    if "helio-sync-target:" in body:
        continue

    head = ((pr.get("head") or {}).get("ref")) or ""
    if not head:
        continue
    # Tag mode: helio-release-candidate-<tag>. Main mode:
    # helio-upstream-main-<date>-<short sha>. The tag-mode branch name does not
    # carry a sha, so an exact branch match is the best available signal there.
    if branch and head == branch:
        fallback = fallback or pr
    elif head.startswith("helio-upstream-main-") and head.endswith("-" + short_sha):
        fallback = fallback or pr

if exact:
    print("marker %d" % exact["number"])
    sys.exit(0)
if fallback:
    print("branch %d" % fallback["number"])
    sys.exit(0)
sys.exit(1)
' "$SYNC_SHA" "$SHORT_SHA" "$BASE_BRANCH" "$BRANCH_NAME"
)" || exit 1

HOW="${RESULT%% *}"
PR_NUMBER="${RESULT##* }"

if [ "$HOW" = "branch" ]; then
  echo "sync_completion: PR #${PR_NUMBER} matched by BRANCH NAME, not by sync-target marker — it predates the marker. If upstream force-retagged this release, this match cannot detect it." >&2
fi

echo "$PR_NUMBER"
exit 0
