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

Secret presence (W3) is only evaluated when the SECRETS_JSON environment variable
is set, which the calling workflow populates from `toJSON(secrets)`. Only the KEYS
are ever read; values are never logged.
"""

from __future__ import annotations

import argparse
import json
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

# `secrets: inherit` has no dot, so it is not matched. GITHUB_TOKEN is always
# provided by Actions and would be noise in every entry.
SECRET_RE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")
VARS_RE = re.compile(r"vars\.([A-Za-z_][A-Za-z0-9_]*)")
IMPLICIT_SECRETS = {"GITHUB_TOKEN"}


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

    entries = data.get("workflows")
    if not isinstance(entries, dict):
        report.error("E5", "manifest has no `workflows:` mapping")
        return {}

    cleaned: dict[str, dict] = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            report.error("E5", f"`{name}`: entry must be a mapping")
            continue
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                report.error("E5", f"`{name}`: missing required field `{field}`")
        status = entry.get("status")
        if status is not None and status not in VALID_STATUSES:
            report.error(
                "E5",
                f"`{name}`: status `{status}` is not one of "
                f"{', '.join(sorted(VALID_STATUSES))}",
            )
        owner = entry.get("owner")
        if owner is not None and owner not in VALID_OWNERS:
            report.error(
                "E5",
                f"`{name}`: owner `{owner}` is not one of {', '.join(sorted(VALID_OWNERS))}",
            )
        cleaned[name] = entry
    return cleaned


def referenced(text: str) -> tuple[set[str], set[str]]:
    secrets = set(SECRET_RE.findall(text)) - IMPLICIT_SECRETS
    return secrets, set(VARS_RE.findall(text))


def configured_secret_names() -> set[str] | None:
    """Keys of the repo's secrets context, or None when not supplied.

    The caller passes `toJSON(secrets)` through the environment. Only keys are
    read; values are never logged or returned.
    """
    raw = os.environ.get("SECRETS_JSON")
    if not raw:
        return None
    try:
        return set(json.loads(raw).keys())
    except (json.JSONDecodeError, AttributeError):
        return None


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
        used_secrets, used_vars = referenced(text)
        declared_secrets = set(entry.get("requires_secrets") or [])
        declared_vars = set(entry.get("requires_vars") or [])

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
        report.warn(
            "W3",
            "SECRETS_JSON not supplied, so secret-presence was not checked.",
        )

    report.write_summary(args.summary, counts)

    if report.errors:
        print(f"\nFAILED: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
        return 1
    print(f"\nOK: 0 errors, {len(report.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
