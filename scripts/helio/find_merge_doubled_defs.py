#!/usr/bin/env python3
"""Find definitions that an upstream merge silently duplicated.

HELIO_INTEGRATION.md Rule 16. A merge git reports as clean can still break the
build: if neither side defined a symbol at the merge base, and upstream and Helio
each *added* a definition in a different part of the same file, the two additions
do not overlap textually, so there is no conflict and no marker -- and the merged
file defines the symbol twice.

The test is comparative. A symbol defined twice in the merged tree is usually an
ordinary overload set, so a count alone is almost all false positives. What marks
the bug is that the symbol is defined twice in the merge but exactly *once* in
both parents.

Usage:
    find_merge_doubled_defs.py --upstream v2.5.0 --ours df651901 [--merged HEAD]

Exit status is 1 when candidates are found, so it can gate a sync.

IMPORTANT: validate before trusting a zero. Run it with --merged set to a commit
you know carries the bug and check it reports it. A scan that finds nothing is
worthless until you have watched it find something.
"""

import argparse
import collections
import re
import subprocess
import sys

# An out-of-class member definition at column 0: `Ret Class::name(`, `Class::Class(`,
# `Class::~Class(`, `Ret Class::operator X(`.
MEMBER = re.compile(
    r'^(?:[A-Za-z_][\w:<>,\s\*&]*?\s+)?([A-Za-z_]\w*)::(~?[A-Za-z_]\w*|operator[^\(]*)\s*\(',
    re.M)

# A free-function definition at column 0, i.e. a signature followed by a body.
FREE = re.compile(
    r'^((?:static|inline|constexpr|extern)\s+)*'
    r'(?!(?:if|for|while|switch|return|else|catch|do)\b)'
    r'[A-Za-z_][\w:<>,\s\*&\[\]]*?\s+\**'
    r'([A-Za-z_]\w*)\s*\([^;{]*\)\s*(?:const\s*)?\{',
    re.M)


def show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def changed_files(a, b, *globs):
    r = subprocess.run(["git", "diff", "--name-only", a, b, "--", *globs],
                       capture_output=True, text=True)
    return r.stdout.split()


def defs(src, pattern, kind):
    found = collections.defaultdict(list)
    for m in pattern.finditer(src):
        if kind == "free" and '::' in m.group(0).split('(')[0]:
            continue  # a member definition; the member scan owns it
        name = (f"{m.group(1)}::{m.group(2)}" if kind == "member"
                else f"{m.group(2)}()")
        found[name].append(src.count('\n', 0, m.start()) + 1)
    return found


def scan(merged_ref, upstream_ref, ours_ref, pattern, kind, globs):
    hits = []
    for path in changed_files(upstream_ref, merged_ref, *globs):
        merged = show(merged_ref, path)
        up = show(upstream_ref, path)
        ours = show(ours_ref, path)
        # A file added or deleted on one side cannot exhibit this shape.
        if merged is None or up is None or ours is None:
            continue
        dm = defs(merged, pattern, kind)
        du = defs(up, pattern, kind)
        do = defs(ours, pattern, kind)
        for name, lines in dm.items():
            if len(lines) < 2:
                continue
            # Already multiply-defined on either side -> an overload set.
            if len(du.get(name, [])) > 1 or len(do.get(name, [])) > 1:
                continue
            # Must exist on BOTH sides for the merge to have doubled it.
            if not du.get(name) or not do.get(name):
                continue
            hits.append((path, name, lines, du[name], do[name]))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", required=True,
                    help="the upstream sync target, e.g. v2.5.0")
    ap.add_argument("--ours", required=True,
                    help="the Helio tip as it was BEFORE the merge")
    ap.add_argument("--merged", default="HEAD", help="the merged tree (default HEAD)")
    args = ap.parse_args()

    scans = [
        ("out-of-class member definitions", MEMBER, "member", ("*.cpp", "*.hpp", "*.h")),
        ("free functions", FREE, "free", ("*.cpp",)),
    ]

    total = 0
    for label, pattern, kind, globs in scans:
        hits = scan(args.merged, args.upstream, args.ours, pattern, kind, globs)
        print(f"\n== {label}: {len(hits)} candidate(s)")
        for path, name, lines, up, ours in hits:
            print(f"   {path}: {name}")
            print(f"       merged at {lines}  (upstream {up}, helio {ours})")
        total += len(hits)

    if total:
        print(f"\n{total} definition(s) look duplicated by the merge.\n"
              "Decide which side's definition survives. Where Helio's has a body and\n"
              "upstream's is `= default` or a stub, Helio's is usually load-bearing --\n"
              "read it before deleting either. Leave a comment where you remove one,\n"
              "or the next sync restores it.")
        return 1

    print("\nNo merge-doubled definitions found.\n"
          "This is only meaningful if you have validated the scan: re-run with\n"
          "--merged <a commit known to carry the bug> and confirm it reports it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
