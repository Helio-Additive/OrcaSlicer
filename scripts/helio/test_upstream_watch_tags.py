#!/usr/bin/env python3
"""Regression suite for helio-upstream-watch.yml's new-tag selection.

The block under test is extracted verbatim from the workflow, between the
`>>> new-tags-selection` / `<<< new-tags-selection` markers, so this tests the
shipped code rather than a transcription of it — the same arrangement
test_sync_noop_guards.py uses for the sync workflow's `check` and `graft` steps.

What it pins, and why that needs pinning:

The digest's "New Tags Since Last Sync" list used `git merge-base
--is-ancestor <baseline> <tag>`. Upstream cuts every release/* branch from
`main` and tags there, so consecutive releases are siblings rather than
descendants and the ancestor test is false across every release boundary. The
list read "None" with four v2.5.0 tags present, in the same comment that
printed "Latest upstream tag: v2.5.0". The fixtures below reproduce that
topology, and `ancestry_selftest` asserts the old test really does fail on it,
so a future reader can see the bug rather than take the fix on trust.

The second trap is ordering: both `sort -V` and git's `version:refname` rank a
stable release BELOW its own prereleases, so a baseline that is itself a
prerelease (the workflow's hardcoded v2.3.2-rc2 fallback is one) drops the
stable release that followed it. `prerelease_baseline` covers that directly.
"""

import os
import re
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "..", "..", ".github", "workflows",
                  "helio-upstream-watch.yml")

BEGIN = "# >>> new-tags-selection"
END = "# <<< new-tags-selection"

failures = []


def selection_block():
    """The new-tag selection, lifted out of the workflow's `digest` step.

    Indentation is stripped so the fragment is runnable on its own. A missing
    marker is a hard error, not an empty block: silently testing nothing is
    how a guard suite rots into decoration.
    """
    wf = yaml.safe_load(open(WF))
    steps = wf["jobs"]["watch"]["steps"]
    body = next(s["run"] for s in steps if s.get("id") == "digest")

    if BEGIN not in body or END not in body:
        sys.exit("FATAL: new-tags-selection markers missing from %s — the "
                 "block was renamed or removed and this suite is testing "
                 "nothing." % WF)

    # The marker line carries a trailing note after the marker itself, so cut
    # at the newline that ends it — not at the marker — or the remainder of
    # that comment's text becomes the fragment's first command.
    block = body.split(BEGIN, 1)[1].split("\n", 1)[1].split(END, 1)[0]
    # The workflow indents the step body; dedent to the shallowest real line.
    lines = [ln for ln in block.split("\n")]
    real = [ln for ln in lines if ln.strip()]
    pad = min(len(ln) - len(ln.lstrip()) for ln in real)
    out = "\n".join(ln[pad:] if ln.strip() else "" for ln in lines)

    if "${{" in out:
        sys.exit("FATAL: the selection block now contains a GitHub expression; "
                 "it would reach this harness as literal text and the test "
                 "would pass on code that cannot run.")
    return out


BLOCK = selection_block()


def git(repo, *args, **kw):
    return subprocess.run(("git",) + args, cwd=repo, check=kw.get("check", True),
                          capture_output=True, text=True).stdout.strip()


def build_repo(tmp):
    """A fixture shaped like upstream: release branches cut from `main`.

    This is the whole point of the fixture. Tagging the releases on a single
    linear branch would make every release an ancestor of the next and the
    original bug would not reproduce.
    """
    repo = os.path.join(tmp, "upstream")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@test")
    git(repo, "config", "user.name", "t")

    def commit(msg):
        with open(os.path.join(repo, "f.txt"), "a") as fh:
            fh.write(msg + "\n")
        git(repo, "add", "f.txt")
        git(repo, "commit", "-q", "-m", msg)
        return git(repo, "rev-parse", "HEAD")

    def release(branch, base, tags):
        """Cut `branch` off main at `base` and tag on it, as upstream does."""
        git(repo, "checkout", "-q", "-b", branch, base)
        for t in tags:
            commit("work for " + t)
            git(repo, "tag", t)
        git(repo, "checkout", "-q", "main")

    commit("initial")
    base_23 = commit("main towards 2.3")
    release("release/v2.3", base_23, ["v2.3.2-beta", "v2.3.2-rc",
                                      "v2.3.2-rc2", "v2.3.2"])
    base_24 = commit("main towards 2.4")
    release("release/v2.4", base_24, ["v2.4.0-alpha", "v2.4.0", "v2.4.1",
                                      "v2.4.2"])
    base_25 = commit("main towards 2.5")
    release("release/v2.5", base_25, ["v2.5.0-alpha", "v2.5.0-beta",
                                      "v2.5.0-rc", "v2.5.0"])
    commit("main after 2.5")
    return repo


def run_selection(repo, baseline, latest):
    """Run the extracted block and return (NEW_TAGS, warnings)."""
    script = (
        "set -e -o pipefail\n"
        'BASELINE_TAG="$1"\n'
        'LATEST_TAG="$2"\n'
        + BLOCK +
        '\nprintf "%s" "$NEW_TAGS"\n'
    )
    p = subprocess.run(["bash", "-c", script, "bash", baseline, latest],
                       cwd=repo, capture_output=True, text=True)
    if p.returncode != 0:
        return None, ["EXIT %d: %s" % (p.returncode, p.stderr.strip())]
    # The guard emits its ::warning on stdout, ahead of the printed value.
    warns = [ln for ln in p.stdout.split("\n") if ln.startswith("::warning")]
    value = p.stdout
    for w in warns:
        value = value.replace(w + "\n", "")
    return value, warns


def check(label, got, want):
    if got == want:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s\n         got:  %r\n         want: %r" % (label, got, want))
        failures.append(label)


def tags_in(value):
    """Tag names from the rendered markdown list, in printed order."""
    return re.findall(r"- `([^`]+)`", value or "")


def case(label, repo, baseline, latest, *, want_tags=None, want_none=False,
         want_warning=False, want_target=None):
    value, warns = run_selection(repo, baseline, latest)
    if value is None:
        print("  FAIL %s (step aborted)\n         %s" % (label, warns))
        failures.append(label)
        return

    if want_none:
        # "None", possibly with the guard's distrust banner appended.
        check(label + " :: empty", value.startswith("None"), True)
    else:
        check(label + " :: tags", tags_in(value), want_tags)

    check(label + " :: warning", bool(warns), want_warning)

    if want_target is not None:
        marked = re.findall(r"- `([^`]+)`[^\n]*\*\*sync target\*\*", value or "")
        check(label + " :: sync-target mark", marked, want_target)


def ancestry_selftest(repo):
    """The bug this suite exists for, asserted rather than described.

    If upstream ever changed to cutting releases from the previous release,
    the ancestor test would start working and this assertion would fail —
    telling the next reader the fixture no longer models upstream, instead of
    leaving a stale rationale in a comment.
    """
    label = "selftest: the old ancestor test fails across a release boundary"
    anc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "refs/tags/v2.4.2",
         "refs/tags/v2.5.0"], cwd=repo, capture_output=True)
    check(label, anc.returncode != 0, True)

    label2 = "selftest: and it holds WITHIN one release family"
    anc2 = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "refs/tags/v2.3.2-rc2",
         "refs/tags/v2.3.2"], cwd=repo, capture_output=True)
    check(label2, anc2.returncode == 0, True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = build_repo(tmp)

        print("\n== fixture self-tests ==")
        ancestry_selftest(repo)

        print("\n== the reported bug: a new release across a branch boundary ==")
        # Baseline v2.4.2, newest stable v2.5.0. The old code answered "None".
        case("v2.4.2 -> sees the whole v2.5.0 family, newest first",
             repo, "v2.4.2", "v2.5.0",
             want_tags=["v2.5.0", "v2.5.0-rc", "v2.5.0-beta", "v2.5.0-alpha"],
             want_target=["v2.5.0"])

        print("\n== prerelease baseline: the stable release must not vanish ==")
        # The workflow's hardcoded fallback baseline is a prerelease. Raw
        # sort -V ranks v2.3.2 BELOW v2.3.2-rc2, so an unnormalised comparison
        # drops the stable release that followed it.
        case("v2.3.2-rc2 -> includes stable v2.3.2 and everything above",
             repo, "v2.3.2-rc2", "v2.5.0",
             want_tags=["v2.5.0", "v2.5.0-rc", "v2.5.0-beta", "v2.5.0-alpha",
                        "v2.4.2", "v2.4.1", "v2.4.0", "v2.4.0-alpha",
                        "v2.3.2"],
             want_target=["v2.5.0"])

        case("v2.3.2-beta -> includes its own later prereleases and v2.3.2",
             repo, "v2.3.2-beta", "v2.4.2",
             want_tags=["v2.5.0", "v2.5.0-rc", "v2.5.0-beta", "v2.5.0-alpha",
                        "v2.4.2", "v2.4.1", "v2.4.0", "v2.4.0-alpha",
                        "v2.3.2", "v2.3.2-rc2", "v2.3.2-rc"],
             want_target=["v2.4.2"])

        print("\n== legitimately empty: no warning ==")
        case("baseline is the newest release -> None, quietly",
             repo, "v2.5.0", "v2.5.0", want_none=True, want_warning=False)

        # A prerelease baseline ahead of the newest STABLE tag: upstream has
        # cut v2.5.0-rc and we hold it, but v2.5.0 itself does not exist yet,
        # so LATEST_TAG is still v2.4.2 and an empty list is correct. A `!=`
        # comparison in the guard would cry wolf here; ver_newer must not.
        git(repo, "tag", "-d", "v2.5.0")
        case("prerelease baseline above the newest stable -> None, quietly",
             repo, "v2.5.0-rc", "v2.4.2", want_none=True, want_warning=False)
        git(repo, "tag", "v2.5.0", "refs/tags/v2.5.0-rc")

        print("\n== the consistency guard fires on an impossible answer ==")
        # LATEST_TAG names a release newer than the baseline that is absent
        # from the tag list, so the selection is empty while the digest header
        # claims a newer release exists — the shape that hid the bug.
        case("empty list + strictly newer latest -> warns and says so",
             repo, "v2.5.0", "v2.9.9", want_none=True, want_warning=True)

        print("\n== ordering is numeric, not lexical ==")
        git(repo, "checkout", "-q", "main")
        git(repo, "checkout", "-q", "-b", "release/v2.10", "main")
        git(repo, "tag", "v2.10.0")
        git(repo, "checkout", "-q", "main")
        case("v2.10.0 sorts above v2.9.x-era tags, not below",
             repo, "v2.5.0", "v2.10.0",
             want_tags=["v2.10.0"], want_target=["v2.10.0"])

    print("")
    if failures:
        print("FAILED (%d): %s" % (len(failures), ", ".join(failures)))
        return 1
    print("All upstream-watch tag-selection checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
