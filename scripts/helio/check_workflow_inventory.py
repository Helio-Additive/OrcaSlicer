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
  E4  a workflow references a secret/var not declared      -> new external dependency
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
Actions secrets REST API. Secret *values* are never passed to this script: the
earlier `toJSON(secrets)` plumbing put every name and value into the environment
of a process running checked-out code, which is unsafe on pull_request runs. See
the header of .github/workflows/helio-workflow-inventory.yml.

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

# `secrets: inherit` has no dot or bracket, so it is not matched. GITHUB_TOKEN is
# always provided by Actions and would be noise in every entry.
#
# Both access forms have to be recognised. `${{ secrets.X }}` and
# `${{ secrets['X'] }}` are equivalent to Actions, so matching only the dot form
# is a false negative in the dangerous direction: an undeclared credential would
# produce no E4 and merge unnoticed, which is the exact failure this check exists
# to prevent.
SECRET_DOT_RE = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_-]*)")
VARS_DOT_RE = re.compile(r"\bvars\.([A-Za-z_][A-Za-z0-9_-]*)")
SECRET_INDEX_RE = re.compile(r"\bsecrets\[([^\]]*)\]")
VARS_INDEX_RE = re.compile(r"\bvars\[([^\]]*)\]")
# A bracket subscript that is a plain quoted literal resolves to a known name.
# Anything else (`secrets[matrix.token]`, `secrets[format('{0}_KEY', x)]`) cannot
# be resolved statically and is reported rather than ignored.
QUOTED_LITERAL_RE = re.compile(r"""^\s*(?:'([^']*)'|"([^"]*)")\s*$""")
IMPLICIT_SECRETS = {"GITHUB_TOKEN"}

# Only look inside places Actions actually evaluates expressions. Scanning raw
# file text matches prose and filenames too — a step handling `/tmp/secrets.json`
# was read as a secret named `json`.
#
# `if:` needs its own pattern because the `${{ }}` wrapper is optional there:
# `if: secrets.FOO != ''` is a real reference. Omitting it would trade a false
# positive for a false negative, which is the worse direction for this check.
EXPRESSION_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
IF_CONDITION_RE = re.compile(r"^[ \t-]*if\s*:\s*(.+)$", re.MULTILINE)


def expression_regions(text: str) -> str:
    """The parts of a workflow file where Actions evaluates contexts."""
    return "\n".join(EXPRESSION_RE.findall(text) + IF_CONDITION_RE.findall(text))


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


def referenced(raw_text: str) -> tuple[set[str], set[str], set[str]]:
    """Secrets, vars, and unresolvable dynamic references found in a workflow."""
    text = expression_regions(raw_text)
    secrets = set(SECRET_DOT_RE.findall(text))
    static, dyn_secrets = _resolve_index(SECRET_INDEX_RE.findall(text))
    secrets |= static
    secrets -= IMPLICIT_SECRETS

    variables = set(VARS_DOT_RE.findall(text))
    static, dyn_vars = _resolve_index(VARS_INDEX_RE.findall(text))
    variables |= static

    dynamic = {f"secrets[{d}]" for d in dyn_secrets} | {f"vars[{d}]" for d in dyn_vars}
    return secrets, variables, dynamic


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
    names = {line.strip() for line in raw.splitlines() if line.strip()}
    return names or None


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
            for absent in sorted(declared_secrets - secrets_present):
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
