#!/usr/bin/env python3
"""Regression suite for the release-channel rules.

Two halves:

  * `version_channel.py` directly, for the decision rules;
  * the real `Determine release tag` step body, extracted from
    helio-release.yml rather than transcribed, so the tag actually shipped is
    the thing under test.

The case that matters most is `experimental_not_above_stable`. A build that
fails it looks completely healthy — it compiles, publishes, and appears on the
Releases page — and is simply never offered to anyone, because the update check
skips any release that is not newer than what the user is running. Nothing else
in the pipeline would notice.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "version_channel.py")
WF = os.path.join(HERE, "..", "..", ".github", "workflows", "helio-release.yml")

EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}", re.DOTALL)

# The tag step takes every input through `env:`, so the harness supplies the
# same variable names and no expression substitution is needed. An expression
# left in a body is a mapping this harness does not know about, and raises
# rather than being passed through as literal shell text.
MAP: dict[str, str] = {}

failures = []


def step_body(job, name):
    wf = yaml.safe_load(open(WF))
    for step in wf["jobs"][job]["steps"]:
        if step.get("name") == name:
            def sub(m):
                key = m.group(1)
                if key in MAP:
                    return "${%s}" % MAP[key]
                raise SystemExit("unmapped expression in %r: %s" % (name, key))
            return EXPR.sub(sub, step["run"])
    raise SystemExit("step not found: %s" % name)


def write_header(tmp, flag, name):
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, "HelioChannel.hpp")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#define HELIO_RELEASE_CHANNEL \"%s\"\n" % name)
        fh.write("#define HELIO_EXPERIMENTAL_BUILD %s\n" % flag)
    return path


# Cases about the other rules assume a bridge release exists; the bridge rule
# itself is exercised explicitly with bridge_release="".
BRIDGE = "helio-v2.4.2"


def run_channel(header, version, branch, latest_stable="", latest_experimental="",
                bridge_release=BRIDGE):
    return subprocess.run(
        [sys.executable, SCRIPT, "check", "--header", header, "--version", version,
         "--branch", branch, "--latest-stable", latest_stable,
         "--latest-experimental", latest_experimental,
         "--bridge-release", bridge_release],
        capture_output=True, text=True)


GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")


FAKE_GH = r"""#!/usr/bin/env bash
# Stand-in for `gh api --paginate repos/$GITHUB_REPOSITORY/releases --jq EXPR`.
# Serves FAKE_RELEASES (a JSON array, as the API returns) and applies the step's
# own --jq expression with real jq, so the draft/prerelease filter under test is
# the one in helio-release.yml, not a copy of it.
[ -n "${FAKE_GH_FAIL:-}" ] && { echo "gh: HTTP 503" >&2; exit 1; }
expr=""
while [ $# -gt 0 ]; do
  case "$1" in --jq) expr="$2"; shift 2;; *) shift;; esac
done
printf '%s' "${FAKE_RELEASES:-[]}" | jq -r "$expr"
"""


def install_fake_gh(tmp):
    d = os.path.join(tmp, "fakebin")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "gh")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(FAKE_GH)
    os.chmod(path, 0o755)
    os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
    os.environ["GITHUB_REPOSITORY"] = "test/test"


def releases(*published, drafts=(), prereleases=(), empty=()):
    """JSON for FAKE_RELEASES: published finals, plus drafts, prereleases and
    published finals with no assets."""
    import json
    a = [{"name": "Helio_OrcaSlicer.AppImage"}]
    rows = [{"tag_name": t, "draft": False, "prerelease": False, "assets": a} for t in published]
    rows += [{"tag_name": t, "draft": True, "prerelease": False, "assets": a} for t in drafts]
    rows += [{"tag_name": t, "draft": False, "prerelease": True, "assets": a} for t in prereleases]
    rows += [{"tag_name": t, "draft": False, "prerelease": False, "assets": []} for t in empty]
    return json.dumps(rows)


def commit_gui_app(repo, reads_experimental_tags, msg="x"):
    """Commit a GUI_App.cpp that does, or does not, carry the new tag parser.

    The release step decides whether a stable tag is a bridge by reading that
    tag's own source, so the fixture has to be a real committed tree."""
    d = os.path.join(repo, "src", "slic3r", "GUI")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "GUI_App.cpp"), "w", encoding="utf-8") as fh:
        fh.write('const std::string helio_prefix = HELIO_STABLE_TAG_PREFIX;\n')
        if reads_experimental_tags:
            fh.write('const std::string helio_exp_prefix = HELIO_EXPERIMENTAL_TAG_PREFIX;\n')
    subprocess.run(["git", "-C", repo, "add", "src/slic3r/GUI/GUI_App.cpp"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "--allow-empty", "-m", msg],
                   check=True, env=GIT_ENV)


def run_check_tag(tag, channel, version):
    return subprocess.run(
        [sys.executable, SCRIPT, "check-tag", "--tag", tag,
         "--channel", channel, "--version", version],
        capture_output=True, text=True)


def check(label, cond, detail=""):
    print("%-42s %s" % (label, "ok" if cond else "FAIL"))
    if not cond:
        failures.append("%s %s" % (label, detail))


def outputs(proc):
    return dict(line.split("=", 1) for line in proc.stdout.strip().splitlines() if "=" in line)


def comparator_cases():
    """Pin semver_cmp directly.

    The channel rules only ever compare a prerelease against a release, so a
    wrong answer in the other direction survives every scenario below — an
    inverted prerelease rule was confirmed to pass the whole suite before these
    cases existed. The comparator is general, so it is pinned generally.
    """
    sys.path.insert(0, HERE)
    import version_channel as vc

    v = vc.parse_semver
    for label, a, b, want in (
        ("cmp: patch order", "2.4.2", "2.4.3", -1),
        ("cmp: minor beats patch", "2.5.0", "2.4.9", 1),
        ("cmp: equal", "2.4.2", "2.4.2", 0),
        ("cmp: prerelease below its release", "2.4.3-exp.1", "2.4.3", -1),
        ("cmp: release above its prerelease", "2.4.3", "2.4.3-exp.1", 1),
        ("cmp: prerelease above older release", "2.4.3-exp.1", "2.4.2", 1),
        ("cmp: exp.2 after exp.1", "2.4.3-exp.1", "2.4.3-exp.2", -1),
        ("cmp: exp.10 after exp.9", "2.4.3-exp.9", "2.4.3-exp.10", -1),
        ("cmp: published format below its release", "2.4.3-exp01", "2.4.3", -1),
        ("cmp: published format above older release", "2.4.3-exp01", "2.4.2", 1),
        ("cmp: exp02 after exp01", "2.4.3-exp01", "2.4.3-exp02", -1),
        ("cmp: exp10 after exp09 (padding)", "2.4.3-exp09", "2.4.3-exp10", -1),
        ("cmp: unpadded would invert", "2.4.3-exp9", "2.4.3-exp10", 1),
        ("cmp: numeric below alphanumeric", "2.4.3-1", "2.4.3-exp", -1),
        ("cmp: longer prerelease wins ties", "2.4.3-exp", "2.4.3-exp.1", -1),
    ):
        got = vc.semver_cmp(v(a), v(b))
        check(label, got == want, "%s vs %s: got %d, want %d" % (a, b, got, want))

    check("cmp: rejects non-semver", v("2.4") is None and v("helio-v2.4.2") is None)
    # Neither has a defined ordering, so accepting them would let the comparator
    # answer a question semver does not define.
    check("cmp: rejects empty prerelease identifier", v("2.4.3-exp..1") is None)
    check("cmp: rejects leading-zero numeric identifier", v("2.4.3-exp.01") is None)
    check("cmp: still accepts the published format", v("2.4.3-exp01") is not None)


def main():
    comparator_cases()
    with tempfile.TemporaryDirectory() as tmp:
        install_fake_gh(tmp)
        stable = write_header(tmp, "0", "stable")
        experimental = write_header(os.path.join(tmp, "exp"), "1", "experimental")
        contradictory = write_header(os.path.join(tmp, "bad"), "1", "stable")

        # --- the happy paths -------------------------------------------------
        p = run_channel(stable, "2.4.2", "orca-latest-parity-bambu", "2.4.1")
        o = outputs(p)
        check("stable release", p.returncode == 0 and o.get("channel") == "stable"
              and o.get("tag_prefix") == "helio-v" and o.get("prerelease") == "false"
              and o.get("asset_tag") == "Helio", p.stderr)

        p = run_channel(experimental, "2.4.3-exp01", "helio-experimental", "2.4.2")
        o = outputs(p)
        check("experimental release", p.returncode == 0 and o.get("channel") == "experimental"
              and o.get("tag_prefix") == "helio-exp-v" and o.get("prerelease") == "true"
              and o.get("asset_tag") == "Helio_EXPERIMENTAL", p.stderr)

        # --- the format the deployed update check can actually read -----------
        # Found by Codex on #130. `get_version()` applies the shipped regex with
        # std::regex_match — whole-string — and its prerelease group is
        # `(-[A-Za-z0-9]+)?`, which forbids a dot. The originally-specified
        # `-exp.1` therefore parses as invalid in every released build and the
        # release is skipped in silence: published, visible on the Releases page,
        # offered to nobody. This is not fixable in the C++, because the clients
        # that must read the tag are the builds already installed.
        p = run_channel(experimental, "2.4.3-exp.1", "helio-experimental", "2.4.2")
        check("dotted prerelease rejected", p.returncode != 0, p.stdout)
        check("  ... and names the cause", "DEPLOYED_MATCHER" in p.stderr or "expNN" in p.stderr,
              p.stderr)

        # Unpadded sorts wrongly at the tenth build: prerelease identifiers that
        # are not purely numeric compare as strings, so `exp9` > `exp10`.
        p = run_channel(experimental, "2.4.3-exp1", "helio-experimental", "2.4.2")
        check("unpadded exp number rejected", p.returncode != 0, p.stdout)

        p = run_channel(experimental, "2.4.3-exp10", "helio-experimental", "2.4.2")
        check("two-digit exp number accepted", p.returncode == 0, p.stderr)

        # --- channel/branch disagreement -------------------------------------
        p = run_channel(experimental, "2.4.3-exp01", "orca-latest-parity-bambu", "2.4.2")
        check("experimental tree, stable branch", p.returncode != 0, p.stdout)

        p = run_channel(stable, "2.4.2", "helio-experimental", "2.4.1")
        check("stable tree, experimental branch", p.returncode != 0, p.stdout)

        p = run_channel(stable, "2.4.2", "some/feature-branch", "2.4.1")
        check("release from an unrelated branch", p.returncode != 0, p.stdout)

        # A header that contradicts itself means one of the two lines was missed
        # when the experimental branch was cut; the binary and its label would
        # then describe different things.
        p = run_channel(contradictory, "2.4.3-exp01", "helio-experimental", "2.4.2")
        check("self-contradictory header", p.returncode != 0, p.stdout)

        # --- version markers --------------------------------------------------
        p = run_channel(experimental, "2.4.3", "helio-experimental", "2.4.2")
        check("experimental without -exp marker", p.returncode != 0, p.stdout)

        p = run_channel(stable, "2.4.3-exp01", "orca-latest-parity-bambu", "2.4.2")
        check("stable carrying -exp marker", p.returncode != 0, p.stdout)

        # --- ordering: the silent one -----------------------------------------
        # 2.4.2-exp01 sorts *below* the 2.4.2 stable release, so the update check
        # skips it and no stable user is ever shown it. The version is otherwise
        # well-formed, so this fails on ordering alone.
        p = run_channel(experimental, "2.4.2-exp01", "helio-experimental", "2.4.2")
        check("experimental_not_above_stable", p.returncode != 0, p.stdout)
        check("  ... and says why", "offered to nobody" in p.stderr, p.stderr)

        p = run_channel(experimental, "2.4.1-exp01", "helio-experimental", "2.4.2")
        check("experimental below an older stable", p.returncode != 0, p.stdout)

        # Ordering is unenforceable with no published stable release; that must
        # not be fatal, or the very first release could never be cut.
        p = run_channel(experimental, "2.4.3-exp01", "helio-experimental", "")
        check("no stable release published yet", p.returncode == 0, p.stderr)

        # The prerelease must stay below the release it anticipates, or testers
        # are never moved onto stable when it ships.
        p = run_channel(stable, "2.4.3", "orca-latest-parity-bambu", "2.4.2")
        check("stable supersedes its own prerelease", p.returncode == 0, p.stderr)

        # --- metadata-bearing versions and tags --------------------------------
        # Found by Codex on #130. Build metadata is a tag-side decoration, but
        # `version.inc` may carry its own, and stripping it from only one side
        # would reject every release of such a version.
        ok = run_check_tag("helio-v2.4.2+rebuild1", "stable", "2.4.2+rebuild1")
        check("tag check: metadata on both sides", ok.returncode == 0, ok.stderr)
        ok = run_check_tag("helio-v2.4.2+sha1234", "stable", "2.4.2+rebuild1")
        check("tag check: collision replaces metadata", ok.returncode == 0, ok.stderr)
        bad = run_check_tag("helio-v9.9.9+rebuild1", "stable", "2.4.2+rebuild1")
        check("tag check: metadata does not mask a rename", bad.returncode != 0, bad.stdout)

        # --- the published tag itself ------------------------------------------
        # Found by Codex on #130. Validating the version is not enough: the
        # update check derives the offered version from the TAG, never from the
        # binary, so every path that builds one can misrepresent the build.
        ok = run_check_tag("helio-exp-v2.4.3-exp01", "experimental", "2.4.3-exp01")
        check("tag check: plain experimental", ok.returncode == 0, ok.stderr)
        ok = run_check_tag("helio-v2.4.2", "stable", "2.4.2")
        check("tag check: plain stable", ok.returncode == 0, ok.stderr)

        # `-<sha>` collisions: rejected outright on experimental (a second `-`
        # component), and on stable they parse but sort BELOW the release being
        # re-cut, so neither reaches a user.
        bad = run_check_tag("helio-exp-v2.4.3-exp01-0123456", "experimental", "2.4.3-exp01")
        check("tag check: -sha collision rejected (exp)", bad.returncode != 0, bad.stdout)
        bad = run_check_tag("helio-v2.4.2-0123456", "stable", "2.4.2")
        check("tag check: -sha collision rejected (stable)", bad.returncode != 0, bad.stdout)

        # `+<sha>` build metadata is the accepted form: parseable, equal precedence.
        ok = run_check_tag("helio-exp-v2.4.3-exp01+0123456", "experimental", "2.4.3-exp01")
        check("tag check: +sha collision accepted", ok.returncode == 0, ok.stderr)
        ok = run_check_tag("helio-v2.4.2+0123456", "stable", "2.4.2")
        check("tag check: +sha accepted (stable)", ok.returncode == 0, ok.stderr)

        # An override naming another version: right prefix, wrong build. Users
        # would be offered a 2.4.3-exp01 binary as 9.9.9, for ever.
        bad = run_check_tag("helio-exp-v9.9.9", "experimental", "2.4.3-exp01")
        check("tag check: override renaming version rejected", bad.returncode != 0, bad.stdout)
        check("  ... and says the tag decides", "from the tag" in bad.stderr, bad.stderr)

        bad = run_check_tag("helio-v2.4.2", "experimental", "2.4.3-exp01")
        check("tag check: wrong channel prefix rejected", bad.returncode != 0, bad.stdout)

        # --- ordering against the newest preview --------------------------------
        # Found by Codex on #130. Sorting above the newest stable release does
        # not imply sorting above the newest preview, so a reused or mistyped NN
        # passed every guard and reached nobody already testing this channel.
        p = run_channel(experimental, "2.4.3-exp01", "helio-experimental", "2.4.2", "2.4.3-exp02")
        check("preview below an existing preview", p.returncode != 0, p.stdout)
        check("  ... and says who misses it", "already on that preview" in p.stderr, p.stderr)

        p = run_channel(experimental, "2.4.3-exp02", "helio-experimental", "2.4.2", "2.4.3-exp02")
        check("preview reusing the newest NN", p.returncode != 0, p.stdout)

        p = run_channel(experimental, "2.4.3-exp03", "helio-experimental", "2.4.2", "2.4.3-exp02")
        check("preview above the newest preview", p.returncode == 0, p.stderr)

        # A preview of the next version supersedes previews of the previous one.
        p = run_channel(experimental, "2.4.4-exp01", "helio-experimental", "2.4.3", "2.4.3-exp02")
        check("preview of a newer version", p.returncode == 0, p.stderr)

        # First preview ever: nothing to compare against, must not be fatal.
        p = run_channel(experimental, "2.4.3-exp01", "helio-experimental", "2.4.2", "")
        check("first preview, no previous", p.returncode == 0, p.stderr)

        # --- the bridge release ------------------------------------------------
        # Builds released before the experimental channel read only `helio-v`
        # and `v` tags, so they drop `helio-exp-v…` silently. A preview with no
        # bridge release published would be cut, listed, and offered to nobody.
        p = run_channel(experimental, "2.4.3-exp01", "helio-experimental", "2.4.2", "",
                        bridge_release="")
        check("preview refused with no bridge release", p.returncode != 0, p.stdout)
        check("  ... and says who misses it", "reach nobody" in p.stderr, p.stderr[:300])
        p = run_channel(stable, "2.4.3", "orca-latest-parity-bambu", "2.4.2",
                        bridge_release="")
        check("stable release needs no bridge", p.returncode == 0, p.stderr)
        # CI checks a branch's own consistency, not what has been published
        # (Codex, #130: the guard-tests step would otherwise fail on every
        # experimental PR). Opt-in only; the release path stays fail-closed.
        p = subprocess.run(
            [sys.executable, SCRIPT, "check", "--header", experimental,
             "--version", "2.4.3-exp01", "--branch", "helio-experimental", "--tree-only"],
            capture_output=True, text=True)
        check("--tree-only skips the bridge rule", p.returncode == 0, p.stderr[:300])
        p = subprocess.run(
            [sys.executable, SCRIPT, "check", "--header", experimental,
             "--version", "2.4.3-exp.1", "--branch", "helio-experimental", "--tree-only"],
            capture_output=True, text=True)
        check("  ... but still checks the tree", p.returncode != 0, p.stdout)
        p = subprocess.run(
            [sys.executable, SCRIPT, "check", "--header", experimental,
             "--version", "2.4.3-exp01", "--branch", "helio-experimental"],
            capture_output=True, text=True)
        check("no flags at all fails closed", p.returncode != 0, p.stdout)

        # --- the real baseline step --------------------------------------------
        # The ordering guard is only as good as the baseline it is given. A
        # stable release whose only tag carries build metadata must still count
        # as that release; discarding it reports the previous one as newest and
        # lets an experimental build that sorts BELOW the real release through.
        # Runs the shipped step body against real tags.
        chan_step = step_body("check", "Determine release channel")
        base = os.path.join(tmp, "baseline")
        os.makedirs(os.path.join(base, "scripts", "helio"), exist_ok=True)
        os.makedirs(os.path.join(base, "src", "libslic3r"), exist_ok=True)
        shutil.copy2(SCRIPT, os.path.join(base, "scripts", "helio", "version_channel.py"))
        shutil.copy2(experimental, os.path.join(base, "src", "libslic3r", "HelioChannel.hpp"))
        subprocess.run(["git", "init", "-q", base], check=True)
        commit_gui_app(base, reads_experimental_tags=True)
        for t in ("helio-v2.4.1", "helio-v2.4.2+rebuild1"):
            subprocess.run(["git", "-C", base, "tag", t], check=True)

        env = dict(os.environ, VERSION="2.4.2-exp01", BRANCH="helio-experimental",
                   GITHUB_OUTPUT=os.path.join(tmp, "bout"),
                   FAKE_RELEASES=releases("helio-v2.4.1", "helio-v2.4.2+rebuild1"))
        open(env["GITHUB_OUTPUT"], "w").close()
        r = subprocess.run(["bash", "-c", chan_step], cwd=base, env=env,
                           capture_output=True, text=True)
        # 2.4.2-exp01 sorts below the real 2.4.2, so this must be refused.
        check("baseline: metadata tag counts as its release", r.returncode != 0,
              "expected refusal, rc=%d out=%s" % (r.returncode, r.stdout[:200]))

        env["VERSION"] = "2.4.3-exp01"
        open(env["GITHUB_OUTPUT"], "w").close()
        r = subprocess.run(["bash", "-c", chan_step], cwd=base, env=env,
                           capture_output=True, text=True)
        check("baseline: above it is accepted", r.returncode == 0, r.stderr[:200])

        # --- the first experimental release ------------------------------------
        # The case that will actually run first, and the one no other case
        # covers: a stable release exists, no experimental one does yet. Worth
        # pinning because the ordering guard reads only `helio-v*` tags, so
        # "no experimental releases yet" must not be a distinct input — and
        # `helio-exp-v…` must not be picked up by that glob, or the baseline
        # would start comparing experimental releases against each other.
        first = os.path.join(tmp, "first")
        os.makedirs(os.path.join(first, "scripts", "helio"), exist_ok=True)
        os.makedirs(os.path.join(first, "src", "libslic3r"), exist_ok=True)
        shutil.copy2(SCRIPT, os.path.join(first, "scripts", "helio", "version_channel.py"))
        shutil.copy2(experimental, os.path.join(first, "src", "libslic3r", "HelioChannel.hpp"))
        subprocess.run(["git", "init", "-q", first], check=True)
        commit_gui_app(first, reads_experimental_tags=True)
        subprocess.run(["git", "-C", first, "tag", "helio-v2.4.2"], check=True)

        env = dict(os.environ, VERSION="2.4.3-exp01", BRANCH="helio-experimental",
                   GITHUB_OUTPUT=os.path.join(tmp, "fout"),
                   FAKE_RELEASES=releases("helio-v2.4.2"))
        open(env["GITHUB_OUTPUT"], "w").close()
        r = subprocess.run(["bash", "-c", chan_step], cwd=first, env=env,
                           capture_output=True, text=True)
        out = open(env["GITHUB_OUTPUT"]).read()
        check("first experimental release accepted",
              r.returncode == 0 and "channel=experimental" in out and "prerelease=true" in out,
              "rc=%d out=%r err=%s" % (r.returncode, out, r.stderr[:200]))
        check("  ... baseline saw the stable release",
              "Newest published stable release: 2.4.2" in r.stdout, r.stdout[:200])

        # Once one exists, it must not become the stable baseline.
        subprocess.run(["git", "-C", first, "tag", "helio-exp-v2.4.3-exp01"], check=True)
        env["FAKE_RELEASES"] = releases("helio-v2.4.2", prereleases=("helio-exp-v2.4.3-exp01",))
        env["VERSION"] = "2.4.3-exp02"
        open(env["GITHUB_OUTPUT"], "w").close()
        r = subprocess.run(["bash", "-c", chan_step], cwd=first, env=env,
                           capture_output=True, text=True)
        check("second experimental release accepted", r.returncode == 0, r.stderr[:200])
        check("  ... exp tag not read as stable",
              "Newest published stable release: 2.4.2" in r.stdout, r.stdout[:200])

        # --- the bridge, through the real step ---------------------------------
        # The step finds the bridge among *published* releases and reads each
        # one's own tagged source, so this runs it against real tags on real
        # trees, with the release list served through the step's own --jq filter.
        nb = os.path.join(tmp, "nobridge")
        os.makedirs(os.path.join(nb, "scripts", "helio"), exist_ok=True)
        os.makedirs(os.path.join(nb, "src", "libslic3r"), exist_ok=True)
        shutil.copy2(SCRIPT, os.path.join(nb, "scripts", "helio", "version_channel.py"))
        shutil.copy2(experimental, os.path.join(nb, "src", "libslic3r", "HelioChannel.hpp"))
        subprocess.run(["git", "init", "-q", nb], check=True)
        commit_gui_app(nb, reads_experimental_tags=False, msg="pre-channel stable")
        subprocess.run(["git", "-C", nb, "tag", "helio-v2.4.2"], check=True)

        def run_nb(version, published):
            env = dict(os.environ, VERSION=version, BRANCH="helio-experimental",
                       GITHUB_OUTPUT=os.path.join(tmp, "nbout"), FAKE_RELEASES=published)
            open(env["GITHUB_OUTPUT"], "w").close()
            return subprocess.run(["bash", "-c", chan_step], cwd=nb, env=env,
                                  capture_output=True, text=True)

        NONE = "Stable release that can see previews: <none>"
        r = run_nb("2.4.3-exp01", releases("helio-v2.4.2"))
        check("step: preview refused before any bridge", r.returncode != 0,
              "rc=%d out=%s" % (r.returncode, r.stdout[:200]))
        check("  ... and reports no bridge", NONE in r.stdout, r.stdout[:300])

        # The parser lands, and a final-shaped tag is pushed on that tree.
        commit_gui_app(nb, reads_experimental_tags=True, msg="parser lands")
        subprocess.run(["git", "-C", nb, "tag", "helio-v2.4.3"], check=True)

        # Codex, #130: a tag is not a release. Pushed but never published, it
        # must not count — installed users have nothing to download.
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2"))
        check("step: unpublished tag is not a bridge", r.returncode != 0 and NONE in r.stdout,
              "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        # ... nor while its release is a draft,
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", drafts=("helio-v2.4.3",)))
        check("step: draft release is not a bridge", r.returncode != 0 and NONE in r.stdout,
              "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        # ... nor when published as a prerelease, which stable users never see.
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", prereleases=("helio-v2.4.3",)))
        check("step: prerelease is not a bridge", r.returncode != 0 and NONE in r.stdout,
              "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        # ... nor when published with no assets: the update prompt has nothing
        # to offer, so installed builds are never moved onto it (Codex, #130).
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", empty=("helio-v2.4.3",)))
        check("step: release without assets is not a bridge", r.returncode != 0 and NONE in r.stdout,
              "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        # Codex, #130: the bridge must itself be readable by installed builds.
        # `+bridge.1` is valid semver and a valid tag, but released builds'
        # whole-string matcher rejects the dot, so nobody is offered the bridge.
        subprocess.run(["git", "-C", nb, "tag", "helio-v2.4.3+bridge.1"], check=True)
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", "helio-v2.4.3+bridge.1"))
        check("step: bridge tag unreadable by installed builds", r.returncode != 0 and NONE in r.stdout,
              "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        # ... while alphanumeric metadata, which they do read, still counts.
        subprocess.run(["git", "-C", nb, "tag", "helio-v2.4.3+rebuild1"], check=True)
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", "helio-v2.4.3+rebuild1"))
        check("step: readable metadata tag is a bridge",
              r.returncode == 0 and "can see previews: helio-v2.4.3+rebuild1" in r.stdout,
              "rc=%d out=%s err=%s" % (r.returncode, r.stdout[:300], r.stderr[:200]))
        # A published release whose tag is absent locally cannot be inspected,
        # so it does not count either (fail closed).
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", "helio-v9.9.9"))
        check("step: uninspectable release is not a bridge", r.returncode != 0 and NONE in r.stdout,
              "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        # An API failure means no bridge: experimental refused ...
        os.environ["FAKE_GH_FAIL"] = "1"
        try:
            r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", "helio-v2.4.3"))
            check("step: API failure refuses a preview", r.returncode != 0 and NONE in r.stdout,
                  "rc=%d out=%s" % (r.returncode, r.stdout[:300]))
        finally:
            del os.environ["FAKE_GH_FAIL"]

        # Published as a final release on a tree with the parser: the bridge.
        r = run_nb("2.4.4-exp01", releases("helio-v2.4.2", "helio-v2.4.3"))
        check("step: preview accepted after the bridge", r.returncode == 0, r.stderr[:300])
        check("  ... and names it",
              "Stable release that can see previews: helio-v2.4.3" in r.stdout, r.stdout[:300])

        # --- the real tag step -------------------------------------------------
        # An override that changes the channel prefix would bypass the
        # channel/branch cross-check entirely: the assets and prerelease flag
        # would follow the real channel while the tag — which is what the update
        # check reads — claimed the other one.
        tag_step = step_body("check", "Determine release tag")
        for label, prefix, version, override, want in (
            ("tag: stable", "helio-v", "2.4.2", "", "helio-v2.4.2"),
            ("tag: experimental", "helio-exp-v", "2.4.3-exp01", "", "helio-exp-v2.4.3-exp01"),
            ("tag: override with build metadata kept", "helio-exp-v", "2.4.3-exp01",
             "helio-exp-v2.4.3-exp01+rebuild1", "helio-exp-v2.4.3-exp01+rebuild1"),
            ("tag: override with -suffix rejected", "helio-exp-v", "2.4.3-exp01",
             "helio-exp-v2.4.3-exp01-hotfix", None),
            ("tag: override renaming the version rejected", "helio-exp-v", "2.4.3-exp01",
             "helio-exp-v9.9.9", None),
            ("tag: cross-channel override rejected", "helio-exp-v", "2.4.3-exp01",
             "helio-v2.4.3", None),
            ("tag: experimental override on stable rejected", "helio-v", "2.4.2",
             "helio-exp-v2.4.2", None),
        ):
            env = dict(os.environ, TAG_OVERRIDE=override, VERSION=version, TAG_PREFIX=prefix,
                       CHANNEL="experimental" if "exp" in prefix else "stable",
                       MERGE_SHA="0123456789abcdef", GITHUB_OUTPUT=os.path.join(tmp, "out"))
            open(env["GITHUB_OUTPUT"], "w").close()
            # Run in a git repo with no remote: `git ls-remote` then fails, which
            # is the no-collision path.
            repo = os.path.join(tmp, "repo")
            os.makedirs(os.path.join(repo, "scripts", "helio"), exist_ok=True)
            subprocess.run(["git", "init", "-q", repo], check=True)
            # The step calls `check-tag` on the tag it just built; copy the real
            # script in rather than stubbing it, so the backstop is exercised.
            shutil.copy2(SCRIPT, os.path.join(repo, "scripts", "helio", "version_channel.py"))
            r = subprocess.run(["bash", "-c", tag_step], cwd=repo, env=env,
                               capture_output=True, text=True)
            got = open(env["GITHUB_OUTPUT"]).read().strip()
            if want is None:
                check(label, r.returncode != 0 and got == "",
                      "expected refusal, got rc=%d out=%r" % (r.returncode, got))
            else:
                check(label, r.returncode == 0 and got == "tag=%s" % want,
                      "got %r, stderr %s" % (got, r.stderr))

    print()
    if failures:
        print("%d failure(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("all release-channel cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
