#!/usr/bin/env python3
"""Tests for check_workflow_inventory.py.

Every case here is a review finding from #106. The expression scanner went
through nine review rounds verified by hand against a temp copy of the repo,
which is how the same class of bug — a pattern that looks strict but matches
*nothing*, so E4 stays silent — kept reappearing in a new spelling. These pin
the behaviour so the next round starts from a known floor.

The bias throughout: for a check whose job is to stop an undeclared credential
dependency merging, a false negative (no finding) is far worse than a false
positive (a fatal E4 on a workflow that is fine). Cases are labelled with which
direction they guard.

Run: python3 scripts/helio/test_check_workflow_inventory.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_workflow_inventory as cwi  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n        got  {got!r}\n        want {want!r}")
        FAILURES.append(label)


def wf(body: str) -> str:
    """A minimal workflow whose single step carries `body`."""
    return (
        "name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo hi\n" + body
    )


def refs(text: str):
    secrets, variables, dynamic = cwi.referenced(text)
    return sorted(secrets), sorted(variables), sorted(dynamic)


print("Reference detection — must-not-miss (false negative = undeclared secret merges)\n")

check("dot access",
      refs(wf("        env:\n          A: ${{ secrets.DEPLOY_TOKEN }}\n"))[0],
      ["DEPLOY_TOKEN"])

check("bracket access with a quoted literal",
      refs(wf("        env:\n          A: ${{ secrets['DEPLOY_TOKEN'] }}\n"))[0],
      ["DEPLOY_TOKEN"])

# The pattern required the accessor to be adjacent, while WHOLE_CONTEXT_RE stood
# down whenever one followed after whitespace — so this matched nothing at all.
check("SPACED bracket access, `secrets [ 'X' ]`",
      refs(wf("        env:\n          A: ${{ secrets [ 'DEPLOY_TOKEN' ] }}\n"))[0],
      ["DEPLOY_TOKEN"])

check("SPACED dot access, `secrets . X`",
      refs(wf("        env:\n          A: ${{ secrets . DEPLOY_TOKEN }}\n"))[0],
      ["DEPLOY_TOKEN"])

check("vars, spaced bracket",
      refs(wf("        env:\n          A: ${{ vars [ 'RELEASE_CHANNEL' ] }}\n"))[1],
      ["RELEASE_CHANNEL"])

check("whole-context use consumes every secret -> reported as dynamic",
      refs(wf("        env:\n          A: ${{ toJSON(secrets) }}\n"))[2],
      ["the whole `secrets` context"])

check("unresolvable subscript -> reported as dynamic",
      refs(wf("        env:\n          A: ${{ secrets[matrix.token] }}\n"))[2],
      ["secrets[matrix.token]"])

# A non-greedy `.*?` terminator stops at the `}}` inside the format string,
# before the secret.
check("expression whose string literal contains `}}`",
      refs(wf("        env:\n          A: ${{ format('{{{0}}}', secrets.NEW_TOKEN) }}\n"))[0],
      ["NEW_TOKEN"])

# A line-oriented regex captures only the `>-` marker.
check("folded `if:` condition, expression on following lines",
      refs("name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
           "    if: >-\n      secrets.NEW_TOKEN != ''\n"
           "    steps:\n      - run: echo hi\n")[0],
      ["NEW_TOKEN"])

check("unwrapped `if:` condition",
      refs("name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
           "    steps:\n      - run: echo hi\n"
           "        if: vars.FLAG != ''\n")[1],
      ["FLAG"])

print("\nReference detection — must-not-fire (false positive = blocks a clean sync)\n")

check("GITHUB_TOKEN is implicit, never a declared dependency",
      refs(wf("        env:\n          A: ${{ secrets.GITHUB_TOKEN }}\n"))[0],
      [])

check("the word `secrets` inside a string literal",
      refs(wf("        env:\n          A: ${{ contains('no secrets are used', 'used') }}\n"))[2],
      [])

# Bracket bodies are read with strings intact (the name in `secrets['X']` IS a
# literal), which alone matches bracket-shaped text wholly inside a literal.
check("bracket-SHAPED text inside a string literal",
      refs(wf("        env:\n          A: ${{ contains('secrets[foo]', 'foo') }}\n"))[2],
      [])

check("a real subscript still resolves alongside a decoy literal",
      refs(wf("        env:\n          A: ${{ contains('secrets[foo]', 'x') }}\n"
              "          B: ${{ secrets['REAL_TOKEN'] }}\n"))[0],
      ["REAL_TOKEN"])

check("an `if` that is an action INPUT, not a condition",
      refs("name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
           "    steps:\n      - uses: some/action@v1\n"
           "        with:\n          if: secrets.NOT_A_REFERENCE\n")[0],
      [])

check("a path that merely looks like a context access",
      refs(wf("        run: cat /tmp/secrets.json\n"))[0],
      [])

print("\nMalformed input must fail toward detection, never toward silence\n")

# The string walk tracks quotes to find where an expression ends. An unterminated
# quote makes it consume the rest of the file — the question is whether that
# swallows later genuine references into a "literal" and suppresses them. It does
# not: an unclosed quote records no span, so nothing is blanked and nothing is
# filtered. Both secrets below are still reported.
check("unterminated quote does not suppress later references",
      refs(wf("        env:\n"
              "          A: ${{ contains('unterminated , secrets.REAL_TOKEN) }}\n"
              "          B: ${{ secrets.SECOND_TOKEN }}\n"))[0],
      ["REAL_TOKEN", "SECOND_TOKEN"])

# The accessor patterns allow whitespace, and `\s` includes newlines, while the
# scanned text is expression regions joined by "\n". A match could in principle
# be fabricated across a region boundary. It cannot here: a boundary crossing
# would need one region ending in a bare `secrets` and the next starting with
# `.NAME`, and a bare `secrets` is already a fatal whole-context finding on its
# own — so there is no case where the boundary is the only thing E4 reports.
check("adjacent regions do not fabricate a dot access across the join",
      refs(wf("        env:\n          A: ${{ secrets }}\n"
              "          B: ${{ vars.OK }}\n")),
      ([], ["OK"], ["the whole `secrets` context"]))

print("\n`secrets: inherit` — an all-secrets grant to code this check cannot read\n")

check("external reusable workflow",
      sorted(cwi.inherited_secret_grants(
          "name: t\non: push\njobs:\n  j:\n    uses: other/repo/.github/workflows/w.yml@main\n"
          "    secrets: inherit\n")) != [],
      True)

check("LOCAL reusable workflow is fine — its own entry is checked",
      sorted(cwi.inherited_secret_grants(
          "name: t\non: push\njobs:\n  j:\n    uses: ./.github/workflows/local.yml\n"
          "    secrets: inherit\n")),
      [])

print("\nSecret inventory — empty must stay distinct from unavailable\n")


def inventory(write: str | None):
    with tempfile.TemporaryDirectory() as tmp:
        if write is None:
            os.environ["SECRET_NAMES_FILE"] = os.path.join(tmp, "missing")
        else:
            path = Path(tmp) / "names.txt"
            path.write_text(write, encoding="utf-8")
            os.environ["SECRET_NAMES_FILE"] = str(path)
        try:
            return cwi.configured_secret_names()
        finally:
            del os.environ["SECRET_NAMES_FILE"]


# A repo with zero secrets is the state where W3 has the most to report; folding
# it to None skipped every per-secret warning and made --strict-secrets claim the
# file had not been supplied.
check("empty file -> empty set (a repo with no secrets), NOT None",
      inventory(""), set())
check("populated file -> names", inventory("A\nB\n"), {"A", "B"})
check("unreadable file -> None (no metadata)", inventory(None), None)

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} of the above")
    sys.exit(1)
print("OK: all passed")
