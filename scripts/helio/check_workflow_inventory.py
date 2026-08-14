#!/usr/bin/env python3
"""Validate .github/helio-workflows.yml against the workflows actually present.

The manifest is this fork's decision record for which upstream-inherited GitHub
Actions workflows run here. This script is what gives it teeth: an upstream sync
that introduces a new workflow, or adds a new external dependency to an existing
one, fails until somebody records a decision.

Checks (errors fail the build, warnings do not):

  E1  a workflow file exists with no manifest entry        -> unclassified
  E2  a manifest entry has no workflow file                -> stale entry
  E3  a `deleted` entry's file is back on disk             -> resurrected by a sync
  E4  a workflow references a secret/var not declared,     -> new external dependency
      or grants all of them to an external workflow
  E5  the manifest is malformed                            -> schema error

  W1  an entry is `undecided`                              -> backlog
  W2  a declared secret/var is no longer referenced        -> manifest drift
  W3  a `run` entry needs a secret this repo lacks         -> will fail at runtime

W3 is deliberately a warning, not an error: some declared secrets are legitimately
absent (the macOS signing set is only consumed when ENABLE_SIGNING is set), and a
hard failure there would block every PR on an unsigned repo. Use --strict-secrets
to escalate it once the manifest is clean.

Usage:
    check_workflow_inventory.py [--workflows-dir DIR] [--manifest FILE]
                                [--strict-secrets] [--summary FILE]

Secret presence (W3) is only evaluated when SECRET_NAMES_FILE points at a file of
newline-separated secret NAMES, which the calling workflow populates from the
Actions secrets REST API — repository-scoped and organization-scoped, unioned,
since an org-level grant is present at runtime and omitting it makes W3 call a
configured secret absent. Environment-scoped secrets are not covered; a workflow
that targets an environment gets a warning saying so. Secret *values* are never
passed to this script: the earlier `toJSON(secrets)` plumbing put every name and
value into the environment of a process running checked-out code, which is unsafe
on pull_request runs. See .github/workflows/helio-workflow-inventory.yml.

Under --strict-secrets, unavailable or unreadable secret metadata is an error
rather than a warning: a strict run that silently checks nothing is worse than a
strict run that fails loudly.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

VALID_STATUSES = {"run", "disabled", "undecided", "deleted"}
VALID_OWNERS = {"upstream", "helio"}
REQUIRED_FIELDS = ("status", "owner", "reason")

# GITHUB_TOKEN is always provided by Actions and would be noise in every entry.
#
# Both access forms have to be recognised. `${{ secrets.X }}` and
# `${{ secrets['X'] }}` are equivalent to Actions, so matching only the dot form
# is a false negative in the dangerous direction: an undeclared credential would
# produce no E4 and merge unnoticed, which is the exact failure this check exists
# to prevent.
#
# Both forms tolerate expression whitespace around the accessor. Actions accepts
# `secrets [ 'X' ]` and `secrets . X`, and WHOLE_CONTEXT_RE below deliberately
# stands down when an accessor follows — so a pattern that required the accessor
# to be adjacent left the spaced spelling matching *nothing at all*: no name, no
# dynamic finding, no E4. The strictest-looking pattern was the leakiest.
SECRET_DOT_RE = re.compile(r"\bsecrets\s*\.\s*([A-Za-z_][A-Za-z0-9_-]*)")
VARS_DOT_RE = re.compile(r"\bvars\s*\.\s*([A-Za-z_][A-Za-z0-9_-]*)")
SECRET_INDEX_RE = re.compile(r"\bsecrets\s*\[([^\]]*)\]")
VARS_INDEX_RE = re.compile(r"\bvars\s*\[([^\]]*)\]")
# The whole context used as a value — `toJSON(secrets)`, `format(..., secrets)`.
# That consumes *every* available secret, so treating it as "no reference found"
# is the worst possible reading: a workflow with the broadest dependency there is
# would pass E4 declaring nothing. It cannot be resolved to names, so it is
# reported as a dynamic reference, the same as an unresolvable subscript.
WHOLE_CONTEXT_RE = re.compile(r"(?<![.\w'\"])(secrets|vars)\b(?!\s*[.\[])")
# GitHub's object-filter syntax. `${{ toJSON(secrets.*) }}` yields every value in
# the context — the broadest dependency there is — and matched *nothing*: the dot
# patterns require an identifier after the dot, so `*` fails them, and
# WHOLE_CONTEXT_RE stands down whenever a dot follows. Between the two, a
# wildcard consuming every secret read as no reference at all. Like a whole
# context use it cannot be resolved to names, so it is reported as dynamic.
# (`secrets[*]` needs no special case: the index pattern matches it and `*` is
# not a quoted literal, so it is already reported.)
WILDCARD_RE = re.compile(r"\b(secrets|vars)\s*\.\s*\*")
# A bracket subscript that is a plain quoted literal resolves to a known name.
# Anything else (`secrets[matrix.token]`, `secrets[format('{0}_KEY', x)]`) cannot
# be resolved statically and is reported rather than ignored.
QUOTED_LITERAL_RE = re.compile(r"""^\s*(?:'([^']*)'|"([^"]*)")\s*$""")
IMPLICIT_SECRETS = {"GITHUB_TOKEN"}
# Text fallback for `secrets: inherit`, used only when the YAML will not parse.
INHERIT_RE = re.compile(r"^\s*secrets\s*:\s*inherit\s*$", re.MULTILINE)

# Only look inside places Actions actually evaluates expressions. Scanning raw
# file text matches prose and filenames too — a step handling `/tmp/secrets.json`
# was read as a secret named `json`.
#
# `if:` needs its own handling because the `${{ }}` wrapper is optional there:
# `if: secrets.FOO != ''` is a real reference. Omitting it would trade a false
# positive for a false negative, which is the worse direction for this check.
# Line-oriented fallback only, used when PyYAML cannot load the file. It also
# matches `if:` keys that are not conditions (an action input named `if`), which
# is why the parsed-YAML walk below is preferred whenever it is available.
IF_CONDITION_RE = re.compile(r"^[ \t-]*if\s*:\s*(.+)$", re.MULTILINE)

EXPRESSION_OPEN = "${{"


def _scan_string_aware(text: str, start: int, stop_at_expression_end: bool):
    """Walk expression text from `start`, tracking single-quoted strings.

    Actions expressions quote with `'`, escaping a literal quote by doubling it.
    Both of this function's callers need the same walk: one to find where an
    expression really ends, the other to blank out the string literals inside
    it. Doing it by regex is what produced the two bugs this replaces.

    Returns (index, spans) where spans lists the (open, close) offsets of each
    string literal encountered.
    """
    i, n = start, len(text)
    spans: list[tuple[int, int]] = []
    quote_start = -1
    in_string = False
    while i < n:
        char = text[i]
        if in_string:
            if char == "'":
                if i + 1 < n and text[i + 1] == "'":  # '' is an escaped quote
                    i += 2
                    continue
                in_string = False
                spans.append((quote_start, i))
        elif char == "'":
            in_string = True
            quote_start = i
        elif (
            stop_at_expression_end
            and char == "}"
            and i + 1 < n
            and text[i + 1] == "}"
        ):
            return i, spans
        i += 1
    return n, spans


def expression_spans(text: str) -> list[str]:
    """The `${{ ... }}` spans in a file, respecting quoted strings.

    A non-greedy `\\$\\{\\{(.*?)\\}\\}` terminates at the first `}}` it sees,
    including one inside a string:

        ${{ format('{{{0}}}', secrets.NEW_TOKEN) }}

    There the regex stops inside the format string, before the secret, and E4
    reports nothing — a false negative in the direction that matters.
    """
    spans: list[str] = []
    index = 0
    while True:
        start = text.find(EXPRESSION_OPEN, index)
        if start < 0:
            return spans
        body_start = start + len(EXPRESSION_OPEN)
        end, _ = _scan_string_aware(text, body_start, stop_at_expression_end=True)
        spans.append(text[body_start:end])
        # An unterminated expression consumes the rest; nothing follows it.
        if end >= len(text):
            return spans
        index = end + 2


def string_literal_spans(expression: str) -> list[tuple[int, int]]:
    """The (open, close) offsets of each quoted string literal in `expression`."""
    _, spans = _scan_string_aware(expression, 0, stop_at_expression_end=False)
    return spans


def without_string_literals(expression: str) -> str:
    """`expression` with the contents of quoted strings blanked out.

    Prose inside a string is not a context access: `contains('no secrets here',
    x)` must not read as a use of the `secrets` context. Blanking rather than
    deleting keeps offsets, so nothing accidentally joins across a removed span.
    """
    spans = string_literal_spans(expression)
    if not spans:
        return expression
    chars = list(expression)
    for open_index, close_index in spans:
        for i in range(open_index, close_index + 1):
            chars[i] = " "
    return "".join(chars)


def _condition_values(document: object) -> list[str]:
    """Values of the `if:` keys Actions actually evaluates as conditions.

    Only two exist in a workflow file: `jobs.<id>.if` and
    `jobs.<id>.steps[].if`. A recursive walk for any key named `if` also picks
    up inputs that merely happen to be called `if` (`with: {if: ...}`), whose
    values are plain strings Actions never evaluates — reporting a credential
    dependency there is a fatal E4 on a workflow that has none.
    """
    values: list[str] = []
    if not isinstance(document, dict):
        return values
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return values

    def take(container: object) -> None:
        if isinstance(container, dict):
            value = container.get("if")
            if isinstance(value, (str, bool, int, float)):
                values.append(str(value))

    for job in jobs.values():
        take(job)
        if isinstance(job, dict) and isinstance(job.get("steps"), list):
            for step in job["steps"]:
                take(step)
    return values


def _all_scalars(node: object) -> list[str]:
    """Every string scalar in the parsed document, keys included.

    An expression is evaluated wherever it appears — `run:`, `env:`, `with:`, a
    key — so there is no location to filter on here. That is the difference from
    `_condition_values`, which must be selective precisely because an unwrapped
    condition is only a condition in two places.
    """
    out: list[str] = []
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                stack.append(key)
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str):
            out.append(current)
    return out


def expression_regions(text: str) -> str:
    """The parts of a workflow file where Actions evaluates contexts.

    `${{ }}` spans are read from the parsed document's scalar values, not from
    the raw file. Reading raw text also scans YAML comments, so a disabled step
    left behind by an upstream sync —

        # token: ${{ secrets.OLD_TOKEN }}

    — read as a live credential dependency and produced a fatal E4 for a
    workflow that has none. Every place Actions evaluates an expression is a
    scalar in the parsed document, so walking scalars loses nothing and drops
    comments for free. Block and folded scalars arrive already joined, so a
    multi-line expression still reads as one span.

    Condition values are collected separately, because the `${{ }}` wrapper is
    optional for them: a folded scalar

        if: >-
          secrets.NEW_TOKEN != ''

    is a valid unwrapped condition whose expression lives on the *following*
    lines, so a line-oriented regex sees only the `>-` marker and reports no
    dependency at all.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        document = None

    if document is None:
        # Unparseable: fall back to scanning raw text, comments and all. It
        # over-matches, but a file this check cannot read must not become a
        # silent hole — a false E4 is arguable, a missed credential is not.
        return "\n".join(expression_spans(text) + IF_CONDITION_RE.findall(text))

    regions: list[str] = []
    for scalar in _all_scalars(document):
        regions += expression_spans(scalar)
    regions += _condition_values(document)
    return "\n".join(regions)


class Report:
    """Collects findings and emits them as GitHub annotations + a job summary."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def error(self, code: str, message: str) -> None:
        self.errors.append((code, message))
        print(f"::error title=Workflow inventory {code}::{message}")

    def warn(self, code: str, message: str) -> None:
        self.warnings.append((code, message))
        print(f"::warning title=Workflow inventory {code}::{message}")

    def write_summary(self, path: str | None, counts: dict[str, int]) -> None:
        lines = ["### Workflow inventory", ""]
        if self.errors:
            lines.append(f"❌ **{len(self.errors)} error(s)** — the manifest and the "
                         "workflows on disk disagree.")
        else:
            lines.append("✅ Every workflow on disk is classified in "
                         "`.github/helio-workflows.yml`.")
        lines.append("")
        lines.append("| status | count |")
        lines.append("| --- | --- |")
        for status in ("run", "disabled", "undecided", "deleted"):
            lines.append(f"| `{status}` | {counts.get(status, 0)} |")
        lines.append("")

        for label, items in (("Errors", self.errors), ("Warnings", self.warnings)):
            if not items:
                continue
            lines.append(f"#### {label}")
            lines.append("")
            for code, message in items:
                lines.append(f"- **{code}** — {message}")
            lines.append("")

        if counts.get("undecided"):
            lines.append(
                f"> {counts['undecided']} workflow(s) are still `undecided`. That is the "
                "backlog of inherited infrastructure nobody has ruled on — each one is "
                "something running (or failing) on this repo by inheritance rather than "
                "by choice."
            )
            lines.append("")

        text = "\n".join(lines)
        print("\n" + text)
        if path:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(text + "\n")


def load_manifest(path: Path, report: Report) -> dict:
    if not path.exists():
        report.error("E5", f"manifest not found at {path}")
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        report.error("E5", f"manifest is not valid YAML: {exc}")
        return {}

    # A YAML document root that is not a mapping (a bare list, a scalar) would
    # otherwise reach .get() and raise AttributeError. Every type below is
    # checked before use so a malformed manifest produces E5 rather than a
    # traceback — a validator that crashes on bad input teaches people to
    # distrust it.
    if not isinstance(data, dict):
        report.error("E5", "manifest root must be a mapping")
        return {}

    entries = data.get("workflows")
    if not isinstance(entries, dict):
        report.error("E5", "manifest has no `workflows:` mapping")
        return {}

    cleaned: dict[str, dict] = {}
    for name, entry in entries.items():
        # YAML keys are not necessarily strings — `2024: {...}` parses to an int,
        # `on: {...}` to a bool. One of those alongside a normal entry makes
        # sorted(manifest.items()) raise TypeError comparing str to int, which
        # crashes the validator on input it exists to reject.
        if not isinstance(name, str):
            report.error(
                "E5",
                f"workflow entry name must be a string, got {type(name).__name__} "
                f"({name!r}). Quote it if the file name looks like a number or a "
                "YAML keyword.",
            )
            continue

        if not isinstance(entry, dict):
            report.error("E5", f"`{name}`: entry must be a mapping")
            continue

        valid = True
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                report.error("E5", f"`{name}`: missing required field `{field}`")
                valid = False

        for field, allowed in (("status", VALID_STATUSES), ("owner", VALID_OWNERS)):
            value = entry.get(field)
            if value is None:
                continue
            if not isinstance(value, str):
                report.error(
                    "E5",
                    f"`{name}`: {field} must be a string, got "
                    f"{type(value).__name__}",
                )
                valid = False
            elif value not in allowed:
                report.error(
                    "E5",
                    f"`{name}`: {field} `{value}` is not one of "
                    f"{', '.join(sorted(allowed))}",
                )
                valid = False

        # A scalar string here is valid YAML but would be turned into a set of
        # single characters by set(), silently corrupting E4/W2/W3.
        for field in ("requires_secrets", "requires_vars"):
            value = entry.get(field)
            if value is None:
                continue
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                report.error(
                    "E5",
                    f"`{name}`: {field} must be a list of strings, got "
                    f"{type(value).__name__}",
                )
                valid = False

        if valid:
            cleaned[name] = entry
    return cleaned


def _resolve_index(subscripts: list[str]) -> tuple[set[str], set[str]]:
    """Split bracket subscripts into statically-known names and dynamic ones."""
    static: set[str] = set()
    dynamic: set[str] = set()
    for raw in subscripts:
        match = QUOTED_LITERAL_RE.match(raw)
        if match:
            name = match.group(1) if match.group(1) is not None else match.group(2)
            if name:
                static.add(name)
            else:
                dynamic.add(raw.strip())
        else:
            dynamic.add(raw.strip())
    return static, dynamic


def _index_matches(pattern: re.Pattern, text: str,
                   literals: list[tuple[int, int]]) -> list[str]:
    """Subscript bodies for accesses that begin outside any string literal."""
    return [
        match.group(1)
        for match in pattern.finditer(text)
        if not any(start <= match.start() <= end for start, end in literals)
    ]


def referenced(raw_text: str) -> tuple[set[str], set[str], set[str]]:
    """Secrets, vars, and unresolvable dynamic references found in a workflow."""
    text = expression_regions(raw_text)

    # Bracket subscripts are read from the text WITH strings intact — the name
    # in `secrets['X']` is itself a string literal, so blanking first would
    # destroy the very thing being read. But that alone matches bracket-SHAPED
    # text that is entirely inside a literal, e.g. `contains('secrets[foo]', x)`,
    # reporting an unresolvable dynamic reference and failing E4 on a workflow
    # that touches no credential. The discriminator is where the access STARTS:
    # in `secrets['X']` the word `secrets` sits outside any literal; in the
    # `contains` case it sits inside one.
    literals = string_literal_spans(text)
    static_secrets, dyn_secrets = _resolve_index(_index_matches(SECRET_INDEX_RE, text, literals))
    static_vars, dyn_vars = _resolve_index(_index_matches(VARS_INDEX_RE, text, literals))

    bare = without_string_literals(text)

    secrets = set(SECRET_DOT_RE.findall(bare)) | static_secrets
    secrets -= IMPLICIT_SECRETS
    variables = set(VARS_DOT_RE.findall(bare)) | static_vars

    dynamic = {f"secrets[{d}]" for d in dyn_secrets} | {f"vars[{d}]" for d in dyn_vars}
    dynamic |= {f"the whole `{context}` context" for context in WHOLE_CONTEXT_RE.findall(bare)}
    dynamic |= {f"every `{context}` value via `{context}.*`"
                for context in WILDCARD_RE.findall(bare)}
    return secrets, variables, dynamic


def inherited_secret_grants(raw_text: str) -> set[str]:
    """Reusable-workflow calls that hand every secret to code we do not scan.

    `secrets: inherit` is not an expression, so none of the reference patterns
    see it — yet it grants the callee every secret available to this repository.
    A *local* callee (`./.github/workflows/x.yml`) is fine: it is a file in this
    directory, so its own references are checked against its own manifest entry.
    An external callee is an undeclared all-secrets dependency on a repository
    this check cannot read, which is exactly the class of thing a sync can
    introduce silently.
    """
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        document = None

    if not isinstance(document, dict):
        # Better a vague finding than none: an unparseable file must not be a
        # way to smuggle the grant past the check.
        return {"`secrets: inherit` (file could not be parsed to find the callee)"} \
            if INHERIT_RE.search(raw_text) else set()

    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return set()

    grants: set[str] = set()
    for job_name, job in jobs.items():
        if not isinstance(job, dict) or job.get("secrets") != "inherit":
            continue
        target = job.get("uses")
        if isinstance(target, str) and target.startswith("./"):
            continue
        grants.add(f"job `{job_name}` calls `{target}`")
    return grants


def environment_scoped_secrets(raw_text: str) -> set[str]:
    """Secrets referenced ONLY by jobs that target a deployment environment.

    "Only" is load-bearing. A secret referenced by an environment job *and* by
    an ordinary job is definitively required from the repository or
    organization, because the ordinary job has no environment to supply it —
    so its absence is a real finding and must still escalate under
    `--strict-secrets`. Returning every secret an environment job touches
    downgraded those too, which is the same under-reporting this function was
    introduced to fix, one level in.

    W3 is answered from repository- and organization-scoped secret names.
    Environment-scoped secrets live behind a third endpoint keyed by environment
    name, so a workflow that uses one would have a perfectly configured secret
    reported as absent. This exists so that the gap says so instead of producing
    a confident wrong answer.

    Scoped per JOB, not per workflow. Treating "some job here uses an
    environment" as a property of the file downgraded every absent secret in a
    mixed workflow — including ones referenced only by jobs with no environment,
    which the repo/org inventory answers for perfectly well. Under
    `--strict-secrets` a definitely-unavailable secret then exited 0, which is
    the enforcement the option promises quietly not happening.
    """
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        return set()
    if not isinstance(document, dict):
        return set()
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return set()

    in_environment: set[str] = set()
    elsewhere: set[str] = set()
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        # Re-serialise the single job and run the same extraction over it. Kept
        # under a `jobs:` mapping so `_condition_values` still recognises the
        # job- and step-level `if:` keys inside it.
        try:
            fragment = yaml.safe_dump({"jobs": {str(job_name): job}})
        except yaml.YAMLError:
            # A job that will not round-trip leaves this function unable to say
            # which references belong where. Scoping nothing means every absent
            # secret keeps escalating, which is the direction that reports too
            # much rather than too little.
            return set()
        job_secrets, _, _ = referenced(fragment)
        if job.get("environment") is None:
            elsewhere |= job_secrets
        else:
            in_environment |= job_secrets
    return in_environment - elsewhere


def configured_secret_names() -> set[str] | None:
    """Names of the repo's configured secrets, or None when not supplied.

    Read from a file of newline-separated names written by the calling workflow
    from the Actions secrets REST API, which returns names and metadata only.
    Secret values are never available to this process.
    """
    path = os.environ.get("SECRET_NAMES_FILE")
    if not path:
        return None
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    # An empty file is a VALID answer — a repository with no secrets configured —
    # and must stay distinct from "no metadata". Collapsing it to None inverted
    # the result in the one state where W3 has the most to say: every declared
    # secret absent, and no warning about any of them. It also made
    # --strict-secrets report the file as unsupplied when it had been read fine.
    return {line.strip() for line in raw.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=".github/workflows")
    parser.add_argument("--manifest", default=".github/helio-workflows.yml")
    parser.add_argument("--strict-secrets", action="store_true",
                        help="treat a missing secret for a `run` workflow as an error")
    parser.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args()

    report = Report()
    manifest = load_manifest(Path(args.manifest), report)

    workflows_dir = Path(args.workflows_dir)
    on_disk = {
        path.name: path
        for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    }

    # E1 — a workflow nobody has classified. This is the forcing function: a sync
    # that adds a workflow cannot merge until someone records a decision.
    for name in sorted(set(on_disk) - set(manifest)):
        report.error(
            "E1",
            f"`{name}` exists in {workflows_dir} but has no entry in {args.manifest}. "
            "An upstream sync probably introduced it. Add an entry recording whether "
            "it should run on this fork and why.",
        )

    counts: dict[str, int] = {}
    secrets_present = configured_secret_names()

    for name, entry in sorted(manifest.items()):
        status = entry.get("status")
        if isinstance(status, str):
            counts[status] = counts.get(status, 0) + 1
        path = on_disk.get(name)

        if status == "deleted":
            # E3 — a file we deliberately removed has come back in a sync.
            if path is not None:
                report.error(
                    "E3",
                    f"`{name}` is recorded as `deleted` but the file is present again. "
                    "A sync has resurrected it; re-remove it or change the status.",
                )
            continue

        # E2 — the manifest describes something that no longer exists.
        if path is None:
            report.error(
                "E2",
                f"`{name}` is in the manifest but no such workflow file exists. "
                "Upstream may have removed or renamed it; update the entry.",
            )
            continue

        text = path.read_text(encoding="utf-8")
        used_secrets, used_vars, dynamic_refs = referenced(text)
        declared_secrets = set(entry.get("requires_secrets") or [])
        declared_vars = set(entry.get("requires_vars") or [])

        # A subscript this script cannot resolve is not the same as no
        # dependency. Reporting it keeps the check honest about its own blind
        # spot instead of passing silently.
        for ref in sorted(dynamic_refs):
            report.error(
                "E4",
                f"`{name}` references `{ref}`, a dynamic lookup whose name cannot be "
                "resolved statically. Declare the possible names explicitly or "
                "rewrite the reference to a literal so the inventory can verify it.",
            )

        # E4 — `secrets: inherit` into a repository this check cannot read.
        for grant in sorted(inherited_secret_grants(text)):
            report.error(
                "E4",
                f"`{name}`: {grant} with `secrets: inherit`, granting every secret on "
                "this repository to a workflow outside it. The inventory cannot see "
                "what the callee uses. Pass named secrets explicitly, or call a local "
                "`./.github/workflows/…` workflow that is itself in this manifest.",
            )

        # E4 — a new external dependency arrived without being declared. This is
        # what catches "the sync added a dependency on a credential we don't have"
        # at review time instead of at runtime months later.
        for missing in sorted(used_secrets - declared_secrets):
            report.error(
                "E4",
                f"`{name}` references `secrets.{missing}` but does not declare it in "
                "`requires_secrets`. If a sync introduced this, confirm the credential "
                "exists on this repo before letting the workflow run.",
            )
        for missing in sorted(used_vars - declared_vars):
            report.error(
                "E4",
                f"`{name}` references `vars.{missing}` but does not declare it in "
                "`requires_vars`.",
            )

        # W2 — declared but no longer used; keeps the manifest honest over time.
        for stale in sorted(declared_secrets - used_secrets):
            report.warn("W2", f"`{name}` declares `{stale}` but no longer references it.")
        for stale in sorted(declared_vars - used_vars):
            report.warn("W2", f"`{name}` declares var `{stale}` but no longer references it.")

        # W1 — the backlog.
        if status == "undecided":
            report.warn(
                "W1",
                f"`{name}` is `undecided` — it is running (or failing) on this repo by "
                "inheritance rather than by choice.",
            )

        # W3 — a workflow we want, needing a credential we do not have.
        if status == "run" and secrets_present is not None:
            # An environment-scoped secret is real at runtime but invisible
            # here, so "it will fail at runtime" would be exactly the confident
            # wrong answer this check is supposed to avoid. Say what is actually
            # known instead, and never escalate it under --strict-secrets.
            # Per-job, not per-workflow: only the secrets an environment-targeting
            # job actually references are unanswerable here. A secret referenced
            # solely by a job with no environment is answered normally, even in a
            # workflow where some other job does use one.
            env_scoped = environment_scoped_secrets(text)
            unanswerable = declared_secrets & env_scoped
            if unanswerable:
                report.warn(
                    "W3",
                    f"`{name}` references {', '.join('`%s`' % s for s in sorted(unanswerable))} "
                    "from a job targeting a deployment environment. Secret presence is "
                    "checked against repository- and organization-scoped names only, "
                    "so an absence reported for those may be an environment secret "
                    "this check cannot see.",
                )
            for absent in sorted(declared_secrets - secrets_present):
                if absent in env_scoped:
                    report.warn(
                        "W3",
                        f"`{name}` declares `{absent}`, which is not a repository or "
                        "organization secret. If the environment of the job that "
                        "references it provides it, this is expected; otherwise the "
                        "workflow will fail at runtime.",
                    )
                    continue
                message = (
                    f"`{name}` is `run` but `{absent}` is not configured on this "
                    "repository, so it will fail at runtime."
                )
                if args.strict_secrets:
                    report.error("W3", message)
                else:
                    report.warn("W3", message)

    if secrets_present is None:
        message = (
            "SECRET_NAMES_FILE not supplied or unreadable, so secret-presence was "
            "not checked."
        )
        if args.strict_secrets:
            # --strict-secrets promises enforcement. Degrading to a warning here
            # means a misconfigured strict run exits 0 having verified nothing,
            # which reads as a pass.
            report.error(
                "W3",
                message + " --strict-secrets was requested, so this is an error "
                "rather than a silent skip.",
            )
        else:
            report.warn("W3", message)

    report.write_summary(args.summary, counts)

    if report.errors:
        print(f"\nFAILED: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
        return 1
    print(f"\nOK: 0 errors, {len(report.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
