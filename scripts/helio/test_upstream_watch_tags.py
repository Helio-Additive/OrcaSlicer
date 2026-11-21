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


def upstream_tags_fn():
    """The `upstream_tags` helper, lifted out of the same step.

    It sits outside the extracted markers because the selection is not its only
    caller, so the harness has to supply it — and supplying a transcription
    would mean the suite could pass while the shipped helper enumerated
    something else. Extracting it keeps that impossible.
    """
    wf = yaml.safe_load(open(WF))
    steps = wf["jobs"]["watch"]["steps"]
    body = next(s["run"] for s in steps if s.get("id") == "digest")

    m = re.search(r"^[ \t]*upstream_tags\(\)[ \t]*\{.*?^[ \t]*\}[ \t]*$",
                  body, re.S | re.M)
    if not m:
        sys.exit("FATAL: upstream_tags() not found in the digest step of %s. "
                 "If it was renamed or inlined, this harness is feeding the "
                 "selection a helper the workflow no longer has." % WF)

    fn = m.group(0)
    lines = fn.split("\n")
    pad = min(len(ln) - len(ln.lstrip()) for ln in lines if ln.strip())
    fn = "\n".join(ln[pad:] if ln.strip() else "" for ln in lines)

    if "refs/upstream-tags/" not in fn:
        sys.exit("FATAL: upstream_tags() no longer reads refs/upstream-tags/. "
                 "If the enumeration moved back to refs/tags, fork-created v* "
                 "tags are visible to the digest again and the exclusion test "
                 "below would be asserting nothing.")
    return fn


BLOCK = selection_block()
UPSTREAM_TAGS_FN = upstream_tags_fn()


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

    def up_tag(name, rev="HEAD"):
        """Tag as the workflow sees upstream tags: in refs/upstream-tags/.

        The fetch step mirrors upstream's refs/tags/* into a namespace of its
        own precisely so a fork-created tag cannot be read as an upstream
        release, so the fixture has to put them where the selection looks. A
        plain `git tag` here would test nothing about that split.
        """
        git(repo, "update-ref", "refs/upstream-tags/" + name,
            git(repo, "rev-parse", rev))

    def release(branch, base, tags):
        """Cut `branch` off main at `base` and tag on it, as upstream does."""
        git(repo, "checkout", "-q", "-b", branch, base)
        for t in tags:
            commit("work for " + t)
            up_tag(t)
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
        # Defined in the digest step outside the extracted markers, so the
        # harness supplies it. Kept byte-identical to the workflow's body by
        # upstream_tags_drift() below rather than by hope.
        + UPSTREAM_TAGS_FN + "\n"
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
        ["git", "merge-base", "--is-ancestor", "refs/upstream-tags/v2.4.2",
         "refs/upstream-tags/v2.5.0"], cwd=repo, capture_output=True)
    check(label, anc.returncode != 0, True)

    label2 = "selftest: and it holds WITHIN one release family"
    anc2 = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "refs/upstream-tags/v2.3.2-rc2",
         "refs/upstream-tags/v2.3.2"], cwd=repo, capture_output=True)
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
        git(repo, "update-ref", "-d", "refs/upstream-tags/v2.5.0")
        case("prerelease baseline above the newest stable -> None, quietly",
             repo, "v2.5.0-rc", "v2.4.2", want_none=True, want_warning=False)
        git(repo, "update-ref", "refs/upstream-tags/v2.5.0",
            git(repo, "rev-parse", "refs/upstream-tags/v2.5.0-rc"))

        print("\n== the consistency guard fires on an impossible answer ==")
        # LATEST_TAG names a release newer than the baseline that is absent
        # from the tag list, so the selection is empty while the digest header
        # claims a newer release exists — the shape that hid the bug.
        case("empty list + strictly newer latest -> warns and says so",
             repo, "v2.5.0", "v2.9.9", want_none=True, want_warning=True)

        print("\n== legacy underscore prereleases (upstream really ships these) ==")
        # Codex P2 on PR #157. Upstream tagged v1.4.0_beta1/2/3 with an
        # UNDERSCORE. A hyphen-only stable/prerelease test reads those as
        # stable, appends the sentinel to them, and then ranks
        # v1.4.0_beta1-zzzzz above v1.4.0-zzzzz — silently omitting the stable
        # release that followed. The consistency guard cannot catch it because
        # it shares the same comparison, which is what makes it worth a test
        # rather than a comment.
        git(repo, "checkout", "-q", "-b", "release/v1.4", "main")
        for t in ["v1.4.0_beta1", "v1.4.0_beta2", "v1.4.0"]:
            git(repo, "update-ref", "refs/upstream-tags/" + t,
                git(repo, "rev-parse", "HEAD"))
        git(repo, "checkout", "-q", "main")
        case("stable v1.4.0 is newer than v1.4.0_beta1/2, not older",
             repo, "v1.4.0_beta1", "v1.4.0",
             want_tags=["v2.5.0", "v2.5.0-rc", "v2.5.0-beta",
                        "v2.5.0-alpha", "v2.4.2", "v2.4.1", "v2.4.0",
                        "v2.4.0-alpha", "v2.3.2", "v2.3.2-rc2", "v2.3.2-rc",
                        "v2.3.2-beta", "v1.4.0", "v1.4.0_beta2"],
             want_target=["v1.4.0"])

        case("and the underscore family orders among itself",
             repo, "v1.4.0_beta2", "v1.4.0",
             want_tags=["v2.5.0", "v2.5.0-rc", "v2.5.0-beta",
                        "v2.5.0-alpha", "v2.4.2", "v2.4.1", "v2.4.0",
                        "v2.4.0-alpha", "v2.3.2", "v2.3.2-rc2", "v2.3.2-rc",
                        "v2.3.2-beta", "v1.4.0"],
             want_target=["v1.4.0"])

        print("\n== fork-created v* tags are not upstream releases ==")
        # CodeRabbit on PR #157. `git tag -l 'v*'` lists the union of
        # upstream's tags and the fork's own, and this fork really carries four
        # v*-shaped tags (v2.3.0.1-rc1..rc3, v2.3.1-rc1). All four happen to
        # sit below today's baseline, so nothing is misreported right now — the
        # digest simply must not depend on that. These go in refs/tags only,
        # exactly as actions/checkout leaves them.
        git(repo, "tag", "v2.9.9")          # stable-looking, above the baseline
        git(repo, "tag", "v2.6.0-rc1")      # prerelease-looking
        # A real upstream release above the baseline, so this discriminates
        # rather than just asserting an empty list: v2.9.9 sorts ABOVE v2.6.0,
        # so if fork tags were visible it would head the list and take the
        # sync-target mark.
        git(repo, "checkout", "-q", "-b", "release/v2.6", "main")
        git(repo, "update-ref", "refs/upstream-tags/v2.6.0",
            git(repo, "rev-parse", "HEAD"))
        git(repo, "checkout", "-q", "main")
        case("fork tags are invisible; the real upstream release still lists",
             repo, "v2.5.0", "v2.6.0",
             want_tags=["v2.6.0"], want_target=["v2.6.0"])

        print("\n== ordering is numeric, not lexical ==")
        git(repo, "checkout", "-q", "main")
        git(repo, "checkout", "-q", "-b", "release/v2.10", "main")
        git(repo, "update-ref", "refs/upstream-tags/v2.10.0",
            git(repo, "rev-parse", "HEAD"))
        git(repo, "checkout", "-q", "main")
        # v2.6.0 exists from the case above, and v2.10.0 must sort ABOVE it
        # rather than lexically below ("1" < "6").
        case("v2.10.0 sorts above v2.6.0, not lexically below it",
             repo, "v2.5.0", "v2.10.0",
             want_tags=["v2.10.0", "v2.6.0"], want_target=["v2.10.0"])

    print("")
    if failures:
        print("FAILED (%d): %s" % (len(failures), ", ".join(failures)))
        return 1
    print("All upstream-watch tag-selection checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
