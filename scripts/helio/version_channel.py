#!/usr/bin/env python3
"""Decide, and validate, which release channel a build belongs to.

`helio-release.yml` calls this once per release and uses its output for the tag,
the asset names and the prerelease flag. It lives here rather than inline in the
workflow so the rules it enforces can be tested against real inputs
(`test_release_channel.py`) instead of only against a release nobody wants to
re-cut.

The rules exist because the experimental channel is *deliberately* offered to
stable users, through the ordinary in-app update prompt:

  * The channel comes from `HelioChannel.hpp` in the checked-out tree, which is
    what the binary actually compiled with. The branch is cross-checked against
    it, so a build cannot be published under the other channel's tag.

  * An experimental version must carry an `-exp` prerelease marker, and must sort
    strictly above the newest stable release. Both halves matter, and they pull
    in opposite directions:

      - above the newest stable release, or the update check skips it
        (`chosen_version <= current_version` returns early) and no stable user is
        ever offered it;
      - below the stable release it anticipates, so that when 2.4.3 ships, the
        testers running 2.4.3-exp.1 are moved onto it rather than stranded on a
        prerelease for ever. `-exp` gives that for free under semver.

    2.4.3-exp.1 against a 2.4.2 stable satisfies both. 2.4.2-exp.1 would be
    published, look correct, and be silently invisible to every stable user.
"""
import argparse
import re
import sys

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")

STABLE_BRANCH = "orca-latest-parity-bambu"
EXPERIMENTAL_BRANCH = "helio-experimental"

CHANNELS = {
    # channel: (tag prefix, prerelease, asset infix, release-name suffix)
    "stable": ("helio-v", False, "Helio", ""),
    "experimental": ("helio-exp-v", True, "Helio_EXPERIMENTAL", " — EXPERIMENTAL"),
}

BRANCH_FOR_CHANNEL = {"stable": STABLE_BRANCH, "experimental": EXPERIMENTAL_BRANCH}


def die(msg):
    print("Error: " + msg, file=sys.stderr)
    raise SystemExit(1)


def parse_semver(text):
    """Return (major, minor, patch, prerelease-identifiers or None), or None."""
    m = SEMVER.match(text.strip())
    if not m:
        return None
    pre = m.group(4).split(".") if m.group(4) else None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), pre)


def _cmp_pre(a, b):
    """Compare prerelease identifier lists per semver §11."""
    for x, y in zip(a, b):
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            if int(x) != int(y):
                return -1 if int(x) < int(y) else 1
        elif xn != yn:
            # Numeric identifiers always have lower precedence than alphanumeric.
            return -1 if xn else 1
        elif x != y:
            return -1 if x < y else 1
    if len(a) != len(b):
        return -1 if len(a) < len(b) else 1
    return 0


def semver_cmp(a, b):
    """-1 / 0 / 1 for parsed versions. A prerelease sorts below its release."""
    for i in range(3):
        if a[i] != b[i]:
            return -1 if a[i] < b[i] else 1
    if a[3] is None and b[3] is None:
        return 0
    if a[3] is None:
        return 1
    if b[3] is None:
        return -1
    return _cmp_pre(a[3], b[3])


def read_channel(header_path):
    """Read the channel out of HelioChannel.hpp, rejecting a self-contradiction."""
    try:
        with open(header_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        die("cannot read %s: %s\nWithout it the release channel is unknown." % (header_path, exc))

    flag = re.search(r"^#define\s+HELIO_EXPERIMENTAL_BUILD\s+(\d+)\s*$", text, re.M)
    name = re.search(r'^#define\s+HELIO_RELEASE_CHANNEL\s+"([^"]*)"\s*$', text, re.M)
    if not flag:
        die("%s does not define HELIO_EXPERIMENTAL_BUILD" % header_path)
    if not name:
        die("%s does not define HELIO_RELEASE_CHANNEL" % header_path)

    by_flag = {"0": "stable", "1": "experimental"}.get(flag.group(1))
    if by_flag is None:
        die("HELIO_EXPERIMENTAL_BUILD is %r; expected 0 or 1" % flag.group(1))
    if name.group(1) != by_flag:
        # The two are edited together by hand when the experimental branch is
        # cut. Disagreement means one was missed, and the binary and its label
        # would describe different things.
        die("%s contradicts itself: HELIO_EXPERIMENTAL_BUILD says %r but "
            "HELIO_RELEASE_CHANNEL says %r" % (header_path, by_flag, name.group(1)))
    return by_flag


def validate(channel, version, branch, latest_stable):
    expected_branch = BRANCH_FOR_CHANNEL[channel]
    if branch != expected_branch:
        die("this tree is a %s build (per HelioChannel.hpp) but the release was "
            "requested from %r, and %s releases are cut from %r.\n"
            "Publishing anyway would ship a %s binary under the other channel's tag."
            % (channel, branch, channel, expected_branch, channel))

    parsed = parse_semver(version)
    if parsed is None:
        die("version %r is not a semantic version" % version)

    is_marked = parsed[3] is not None and any(p.startswith("exp") for p in parsed[3])
    if channel == "experimental" and not is_marked:
        die("experimental version %r carries no -exp prerelease marker.\n"
            "Without it the build sorts as a final release: it would replace the "
            "stable release in the update prompt instead of being offered as a "
            "preview, and testers would never be moved back onto stable."
            % version)
    if channel == "stable" and is_marked:
        die("stable version %r carries an -exp prerelease marker" % version)

    if channel == "experimental" and latest_stable:
        newest = parse_semver(latest_stable)
        if newest is None:
            die("--latest-stable %r is not a semantic version" % latest_stable)
        if semver_cmp(parsed, newest) <= 0:
            die("experimental version %r does not sort above the newest stable "
                "release %r.\n"
                "The in-app update check skips any release that is not newer than "
                "what the user is running, so this build would be published and "
                "then offered to nobody. Use the next patch version with an -exp "
                "marker (e.g. %d.%d.%d-exp.1)."
                % (version, latest_stable, newest[0], newest[1], newest[2] + 1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--header", required=True, help="path to HelioChannel.hpp")
    ap.add_argument("--version", required=True, help="version from version.inc")
    ap.add_argument("--branch", required=True, help="branch the release is cut from")
    ap.add_argument("--latest-stable", default="",
                    help="newest published stable version; ordering is unchecked when empty")
    args = ap.parse_args(argv)

    channel = read_channel(args.header)
    validate(channel, args.version, args.branch, args.latest_stable)

    tag_prefix, prerelease, asset_tag, suffix = CHANNELS[channel]
    for line in (
        "channel=%s" % channel,
        "tag_prefix=%s" % tag_prefix,
        "prerelease=%s" % ("true" if prerelease else "false"),
        "asset_tag=%s" % asset_tag,
        "release_suffix=%s" % suffix,
    ):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
