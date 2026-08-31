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


def run_channel(header, version, branch, latest_stable=""):
    return subprocess.run(
        [sys.executable, SCRIPT, "--header", header, "--version", version,
         "--branch", branch, "--latest-stable", latest_stable],
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


def main():
    comparator_cases()
    with tempfile.TemporaryDirectory() as tmp:
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

        # --- the real tag step -------------------------------------------------
        tag_step = step_body("check", "Determine release tag")
        for label, prefix, version, want in (
            ("tag: stable", "helio-v", "2.4.2", "helio-v2.4.2"),
            ("tag: experimental", "helio-exp-v", "2.4.3-exp01", "helio-exp-v2.4.3-exp01"),
        ):
            env = dict(os.environ, TAG_OVERRIDE="", VERSION=version, TAG_PREFIX=prefix,
                       MERGE_SHA="0123456789abcdef", GITHUB_OUTPUT=os.path.join(tmp, "out"))
            open(env["GITHUB_OUTPUT"], "w").close()
            # Run in a git repo with no remote: `git ls-remote` then fails, which
            # is the no-collision path.
            repo = os.path.join(tmp, "repo")
            os.makedirs(repo, exist_ok=True)
            subprocess.run(["git", "init", "-q", repo], check=True)
            r = subprocess.run(["bash", "-c", tag_step], cwd=repo, env=env,
                               capture_output=True, text=True)
            got = open(env["GITHUB_OUTPUT"]).read().strip()
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
