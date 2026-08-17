#!/usr/bin/env python3
"""Exercise the real `check` and `graft` step scripts from helio-upstream-sync.yml
against synthetic repositories that reproduce each false-skip scenario.

The step bodies are extracted from the workflow, so this tests the shipped code
rather than a transcription of it.
"""
import json, os, re, shutil, subprocess, sys, tempfile
import yaml

WF = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "..", "..", ".github", "workflows", "helio-upstream-sync.yml")
EXPR = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")

# The `check` and `graft` steps take their inputs through `env:` (upstream tag
# names must not be interpolated into shell source), so the harness supplies the
# same variable names directly and no expression substitution is needed. Any
# expression left in a body is a mapping the harness does not know about, and is
# raised rather than silently passed through as literal text.
MAP: dict[str, str] = {}


def step_body(name):
    """Return (script, literal_env) for a step.

    literal_env is the step's own `env:` entries that are plain values rather
    than `${{ }}` expressions — MAX_WALK is one. Reading them from the workflow
    instead of hardcoding them here is what makes the harness catch their
    removal: the graft step's rejection warning interpolates $MAX_WALK under
    `set -u`, so dropping it from the workflow env aborts the step, and the
    scenarios then fail on the step status rather than passing anyway.
    """
    wf = yaml.safe_load(open(WF))
    for s in wf["jobs"]["sync"]["steps"]:
        if s.get("name") == name:
            body = s["run"]
            def sub(m):
                key = m.group(1)
                if key in MAP:
                    return "${%s}" % MAP[key]
                raise SystemExit("unmapped expression in %r: %s" % (name, key))
            literal = {k: str(v) for k, v in (s.get("env") or {}).items()
                       if not EXPR.search(str(v))}
            # no-op once every input arrives via env
            return EXPR.sub(sub, body), literal
    raise SystemExit("step not found: " + name)


CHECK, CHECK_ENV = step_body("Check if already synced")
GRAFT, GRAFT_ENV = step_body("Establish correct merge base (ephemeral graft)")


CONTENT_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "upstream_content.sh")


def install_content_script(repo):
    """Put the real upstream_content.sh where the step bodies expect it.

    The steps resolve it through $GITHUB_WORKSPACE, so the synthetic repo needs
    a copy at the same relative path. Copied rather than reimplemented — the
    point of this harness is to run the shipped code.
    """
    dest = os.path.join(repo, "scripts", "helio")
    os.makedirs(dest, exist_ok=True)
    for name in ("upstream_content.sh", "sync_completion.sh"):
        src = os.path.join(os.path.dirname(CONTENT_SH), name)
        shutil.copy2(src, os.path.join(dest, name))
        os.chmod(os.path.join(dest, name), 0o755)


def sh(cmd, cwd, env=None, check=True):
    e = dict(os.environ)
    e.update(env or {})
    # Match the shell GitHub Actions uses for `run:` bodies:
    # `bash --noprofile --norc -e -o pipefail`. The `check` step body has no
    # `set -e` of its own — only `graft` does — so running it under a plain
    # `bash -c` gives the harness WEAKER error semantics than production. A
    # command that fails mid-body aborts the step on Actions and would have
    # carried on here, so a scenario could pass locally and behave differently
    # in CI. That is the exact class of defect this file exists to catch.
    p = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail",
                        "-c", cmd], cwd=cwd, env=e,
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        print(p.stdout, p.stderr)
        raise SystemExit("command failed: " + cmd)
    return p


def git(repo, *args):
    return sh("git " + " ".join(args), repo).stdout.strip()


def build(tmp, *, version, retag=False, bump_ahead=False, tag_at_target=False,
          new_release=False, no_tag=False, fork_at=None, tag_at=None,
          chain=None, target_tag=None):
    """Fork repo whose profile tree holds v2.4.2 via a SQUASHED commit.

    `chain` selects an alternative upstream shape for the round-5 findings. Both
    need four releases so that a release the records name sits ABOVE a release
    whose content the fork lacks — that gap is what neither guard could see.

    chain="thin" — the top release's whole delta is the version string:

        v2.4.0  core.c            <- what the fork's tree really holds
        v2.4.1  + src/mid.c       <- the content that must not be dropped
        v2.4.2  version.inc only  <- the thin release version.inc names
        v2.4.3  + src/newfile.c   <- the sync target

    Delta-only validation passes v2.4.2 because the only thing it checks is a
    version bump the fork already carries for an unrelated reason.

    chain="stale" — same gap, reached through the tracking tag instead. Upstream
    never rewrites version.inc, so the fork's copy matches at every release and
    cannot conflict; that keeps the merge clean and lets the dropped content show
    up as a missing file rather than being masked by a conflict. version.inc's
    own candidate IS rejected here, which is the point: the run then falls
    through to the tracking tag, which nothing validated.
    """
    up = os.path.join(tmp, "upstream")
    os.makedirs(up)
    sh("git init -q -b main && git config user.email a@b && git config user.name A", up)

    def commit(msg, files):
        for path, content in files.items():
            full = os.path.join(up, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write(content)
        sh("git add -A && git commit -q -m %r" % msg, up)
        return git(up, "rev-parse", "HEAD")

    def verinc(v):
        return 'set(SoftFever_VERSION "%s")\n' % v

    if chain == "thin":
        commit("2.4.0", {"version.inc": verinc("2.4.0"), "src/core.c": "int main(){}\n"})
        sh("git tag v2.4.0", up)
        commit("2.4.1", {"version.inc": verinc("2.4.1"),
                         "src/mid.c": "// content that only v2.4.1 introduced\n"})
        v241 = git(up, "rev-parse", "HEAD")
        sh("git tag v2.4.1", up)
        # Whole delta is the version string. This is what defeats delta-only
        # validation: the fork's version.inc already reads 2.4.2.
        commit("2.4.2", {"version.inc": verinc("2.4.2")})
        sh("git tag v2.4.2", up)
    elif chain == "hunks":
        # Codex round 6: upstream edits one hunk of a file, Helio independently
        # edits another hunk of the SAME file. Comparing changed path NAMES sees
        # the path on both sides and cancels it out, while upstream's hunk is
        # genuinely absent. Only looking inside the file can tell.
        wide = "\n".join("line %d" % i for i in range(1, 41)) + "\n"
        commit("2.4.0", {"version.inc": verinc("2.4.2"), "src/wide.c": wide})
        sh("git tag v2.4.0", up)
        # Upstream changes the TOP of the file.
        top = wide.replace("line 3\n", "line 3 CHANGED UPSTREAM\n")
        commit("2.4.1", {"src/wide.c": top})
        v241 = git(up, "rev-parse", "HEAD")
        sh("git tag v2.4.1", up)
        commit("2.4.2", {"src/core.c": "int main(){return 0;}\n"})
        sh("git tag v2.4.2", up)
    elif chain == "deep":
        # Nine releases, and the fork holds only the bottom one. Every candidate
        # is definitively missing content AND so is every one of the MAX_WALK=6
        # steps below it, so `first-held` returns nothing and the graft step
        # reaches its LAST branch — the "no validated older base" warning.
        #
        # Nothing else here reaches that branch, which is how `$MAX_WALK` came to
        # be interpolated into it while only ever being set inside
        # upstream_content.sh's own process: under `set -u` that aborts the step
        # instead of warning and carrying on.
        commit("2.4.0", {"version.inc": verinc("2.4.0"), "src/core.c": "int main(){}\n"})
        sh("git tag v2.4.0", up)
        v241 = git(up, "rev-parse", "HEAD")
        for n in range(1, 9):
            commit("2.4.%d" % n, {"version.inc": verinc("2.4.%d" % n),
                                  "src/only_in_24%d.c" % n: "// only v2.4.%d\n" % n})
            sh("git tag v2.4.%d" % n, up)
            if n == 1:
                v241 = git(up, "rev-parse", "HEAD")
    elif chain == "stale":
        # version.inc is written once and never touched again, so the fork's copy
        # agrees with upstream at every release and the merge cannot conflict on
        # it. Without that, a version.inc conflict masks the dropped file and the
        # scenario passes for the wrong reason.
        commit("2.4.0", {"version.inc": verinc("2.4.2"), "src/core.c": "int main(){}\n"})
        sh("git tag v2.4.0", up)
        # A non-ASCII path, because git octal-escapes those in `--raw` output
        # and this repo has accented filenames under resources/profiles.
        commit("2.4.1", {"src/mid.c": "// content that only v2.4.1 introduced\n",
                         "src/wéird nàme.json": "{}\n"})
        v241 = git(up, "rev-parse", "HEAD")
        sh("git tag v2.4.1", up)
        commit("2.4.2", {"src/core.c": "int main(){return 0;}\n"})
        sh("git tag v2.4.2", up)
    else:
        commit("base", {"version.inc": verinc("2.4.1"), "src/core.c": "int main(){}\n"})
        v241 = git(up, "rev-parse", "HEAD")
        sh("git tag v2.4.1", up)

        commit("2.4.2", {"version.inc": verinc("2.4.2"),
                         "src/core.c": "int main(){return 0;}\n",
                         "src/mid.c": "// content that only v2.4.2 introduced\n"})
        sh("git tag v2.4.2", up)

    # The fork: upstream content + a Helio delta, collapsed into ONE commit with
    # no upstream ancestry (what squash-merging a sync PR leaves behind).
    fork = os.path.join(tmp, "fork")
    sh("git clone -q %s %s" % (up, fork), tmp)
    sh("git config user.email a@b && git config user.name A", fork)
    # Check out the release the fork's content is based on FIRST, then make the
    # branch parentless. `--orphan` keeps the index and worktree, so this yields
    # a root commit holding exactly that release's tree plus the Helio delta.
    # (Clearing the index and read-tree'ing afterwards does not work: files from
    # the previous checkout survive as untracked and get committed anyway, which
    # silently made an earlier version of this fixture test nothing.)
    sh("git checkout -q -f %s" % (fork_at or "HEAD"), fork)
    sh("git checkout -q --orphan release", fork)
    open(os.path.join(fork, "helio.c"), "w").write("// helio thermal_index\n")
    if chain == "hunks":
        # Helio edits the BOTTOM of the same file, from the v2.4.0 content.
        wide_path = os.path.join(fork, "src", "wide.c")
        body = open(wide_path).read()
        open(wide_path, "w").write(body.replace("line 38\n", "line 38 helio thermal_index\n"))
    open(os.path.join(fork, "version.inc"), "w").write(verinc(version))
    sh("git add -A && git commit -q -m 'Upstream sync: v2.4.2 (squashed)'", fork)

    if retag:
        # Upstream force-retags v2.4.2 onto a NEW commit with new content.
        commit("retagged 2.4.2", {"version.inc": verinc("2.4.2"),
                                  "src/newfeature.c": "// added after retag\n"})
        sh("git tag -f v2.4.2", up)
    if bump_ahead or new_release:
        files = {"src/newfile.c": "// genuinely new upstream work\n"}
        if chain != "stale":  # see the chain="stale" note: version.inc stays put
            files["version.inc"] = verinc("2.4.3")
        commit("2.4.3", files)
        sh("git tag v2.4.3", up)

    install_content_script(fork)
    sh("git fetch -q origin '+refs/heads/*:refs/remotes/origin/*' '+refs/tags/*:refs/tags/*' --force", fork)

    target = target_tag or ("v2.4.3" if (bump_ahead or new_release) else "v2.4.2")
    sync_sha = git(fork, "rev-list", "-n1", target)
    if no_tag:
        sh("git tag -d helio-last-synced 2>/dev/null || true", fork)
    else:
        at = sync_sha if tag_at_target else (tag_at or v241)
        sh("git tag -f helio-last-synced %s" % at, fork)
    return fork, target, sync_sha


def run_check(fork, target, sync_sha, extra_env=None):
    outfile = os.path.join(fork, "..", "ghout")
    open(outfile, "w").close()
    env = {
        "SYNC_SHA": sync_sha, "SYNC_LABEL": target,
        "TRACKING_TAG": "helio-last-synced", "SYNC_REF": target,
        "GITHUB_OUTPUT": outfile, "GITHUB_STEP_SUMMARY": outfile + ".sum",
        "GITHUB_WORKSPACE": fork,
        # Inputs to the completion signal. Supplied unconditionally because the
        # step runs under `set -u` — omitting them would abort the step rather
        # than exercise the guard. With no HELIO_PR_FIXTURE and no `gh` on the
        # box, sync_completion.sh reports "cannot tell" and the step falls
        # through to its existing behaviour, which is what every pre-existing
        # scenario here expects.
        "RELEASE_BRANCH": "orca-latest-parity-bambu",
        "BRANCH_NAME": "helio-release-candidate-%s" % target,
    }
    env.update(CHECK_ENV)
    if extra_env:
        env.update(extra_env)
    p = sh(CHECK, fork, env, check=False)
    out = dict(l.split("=", 1) for l in open(outfile).read().splitlines() if "=" in l)
    return p, out


def run_graft_and_merge(fork, target, sync_sha):
    outfile = os.path.join(fork, "..", "ghout2")
    open(outfile, "w").close()
    env = {
        "SYNC_SHA": sync_sha, "SYNC_LABEL": target,
        "TRACKING_TAG": "helio-last-synced", "SYNC_REF": target,
        "GITHUB_OUTPUT": outfile,
        "GITHUB_WORKSPACE": fork,
    }
    env.update(GRAFT_ENV)
    p = sh(GRAFT, fork, env, check=False)
    gout = dict(l.split("=", 1) for l in open(outfile).read().splitlines() if "=" in l)
    pre_merge = git(fork, "rev-parse", "HEAD")
    m = sh("git merge %s --no-edit" % target, fork, check=False)
    status = "clean" if m.returncode == 0 else "conflict"
    if gout.get("grafted") == "true":
        sh("git replace -d %s || true" % gout["graft_commit"], fork, check=False)
    noop = None
    if status == "clean":
        noop = git(fork, "rev-parse", "HEAD^{tree}") == git(fork, "rev-parse", pre_merge + "^{tree}")
    return p, gout, status, noop


def scenario(name, expect_skip, expect_noop, expect_file=None,
             no_silent_drop=False, expect_text=None, expect_file_extra=None,
             expect_graft_warning=None, **kw):
    """no_silent_drop: pass if the merge conflicts (safe — a human resolves it)
    OR completes cleanly with every expected file present. Fail only on the
    dangerous combination: a clean merge that quietly omits upstream content."""
    wanted = [expect_file] if isinstance(expect_file, str) else (expect_file or [])
    wanted = wanted + (expect_file_extra or [])
    tmp = tempfile.mkdtemp()
    try:
        fork, target, sync_sha = build(tmp, **kw)
        cp, out = run_check(fork, target, sync_sha)
        ok_files = True
        ok_steps = cp.returncode == 0
        skip = out.get("skip") == "true"
        results = ["check.skip=%s (exit %d)" % (skip, cp.returncode)]
        if not ok_steps:
            results.append("check STEP FAILED -> Actions would stop here")
            FAILURES.append(name + " / check step exit %d" % cp.returncode)
        gp = None
        noop = None
        if not skip:
            gp, gout, status, noop = run_graft_and_merge(fork, target, sync_sha)
            # A nonzero graft step is a FAILED RUN on Actions: the job stops and
            # never reaches the merge. Ignoring it here let an aborted graft be
            # followed by an ungrafted merge whose conflict was then scored as
            # "conflict -> safe" and printed as a PASS, so a scenario could go
            # green for a step that never ran.
            if gp.returncode != 0:
                ok_steps = False
                results.append("graft STEP FAILED (exit %d) -> Actions would stop here" % gp.returncode)
                FAILURES.append(name + " / graft step exit %d" % gp.returncode)
            if gout.get("prev_upstream"):
                results.append("base=%s" % gout["prev_upstream"][:8])
            results.append("grafted=%s" % gout.get("grafted"))
            results.append("merge=%s" % status)
            results.append("noop=%s" % noop)
            # Asserting the WARNING TEXT, not just that the step survived.
            # Without it this scenario passes for any route through the loop,
            # including one that never reaches the branch it exists to cover.
            if expect_graft_warning:
                blob = gp.stdout + gp.stderr
                got = expect_graft_warning in blob
                results.append("graft warns %r=%s" % (expect_graft_warning, got))
                if not got:
                    results.append("MISSING -> did not reach the intended branch")
                    ok_files = False
                    FAILURES.append(name + " / graft warning")
            # ok_steps guards this: a conflict is only "safe" when it is the
            # conflict Actions would actually have reached.
            if ok_steps and ok_files and no_silent_drop and status == "conflict":
                results.append("conflict -> safe (human resolves, nothing claimed)")
                print("  PASS  " + name)
                print("        " + " | ".join(results))
                return True
            if expect_text:
                path, needle = expect_text
                body = ""
                full = os.path.join(fork, path)
                if os.path.exists(full):
                    body = open(full).read()
                got = needle in body
                results.append("%s contains %r=%s" % (path, needle, got))
                if not got:
                    results.append("MISSING -> upstream hunk silently dropped")
                    ok_files = False
                    FAILURES.append(name + " / " + path)
            for want in wanted:
                present = os.path.exists(os.path.join(fork, want))
                results.append("%s present=%s" % (want, present))
                if not present:
                    results.append("MISSING -> content silently dropped")
                    ok_files = False
                    FAILURES.append(name + " / " + want)
        ok = (skip == expect_skip) and (noop == expect_noop) and ok_files and ok_steps
        print(("  PASS  " if ok else "  FAIL  ") + name)
        print("        " + " | ".join(results))
        if not ok:
            print("        expected skip=%s noop=%s" % (expect_skip, expect_noop))
            print(cp.stdout[-1500:])
            # The graft step's output, not just the check step's: when a
            # scenario fails at the graft stage, printing only `check` shows the
            # step that worked.
            if gp is not None:
                print(gp.stdout[-1500:])
                print(gp.stderr[-1500:])
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


FAILURES: list[str] = []

print("Scenarios (fork tree holds v2.4.2 via a squashed commit; tag stale at v2.4.1)\n")
r = []
# Was expect_skip=False/noop=True: the run merged, then discovered the merge
# changed nothing. The content test in `check` now answers the same question
# before merging, so the same invariant — NO PR for a release we already hold —
# is reached earlier and without depending on ancestry. The assertion is on the
# outcome, not on which guard produced it.
r.append(scenario(
    "#107: cron re-proposes v2.4.2, already merged -> no PR (content test, pre-merge)",
    expect_skip=True, expect_noop=None, version="2.4.2"))
r.append(scenario(
    "FALSE SKIP A: upstream force-retags v2.4.2 onto new content -> must NOT skip",
    expect_skip=False, expect_noop=False, expect_file="src/newfeature.c",
    version="2.4.2", retag=True))
r.append(scenario(
    "FALSE SKIP B: version.inc bumped to 2.4.3 before content landed -> must NOT skip",
    expect_skip=False, expect_noop=False, expect_file="src/newfile.c",
    version="2.4.3", bump_ahead=True))
r.append(scenario(
    "content-backed early exit: tracking tag already at the target -> skip",
    expect_skip=True, expect_noop=None, version="2.4.2", tag_at_target=True))
r.append(scenario(
    "positive control: genuinely new v2.4.3 -> merge brings it, PR proceeds",
    expect_skip=False, expect_noop=False, expect_file="src/newfile.c",
    version="2.4.2", new_release=True))

r.append(scenario(
    "REGRESSION CHECK: #107 shape but NO usable tracking tag -> must still open no PR",
    expect_skip=True, expect_noop=None, version="2.4.2", no_tag=True))

r.append(scenario(
    "hardest: force-retag AND no tracking tag -> parent-of-target base, content must arrive",
    expect_skip=False, expect_noop=False, expect_file="src/newfeature.c",
    version="2.4.2", retag=True, no_tag=True))
r.append(scenario(
    "hardest: version.inc bumped ahead AND no tracking tag -> content must arrive",
    expect_skip=False, expect_noop=False, expect_file="src/newfile.c",
    version="2.4.3", bump_ahead=True, no_tag=True))

r.append(scenario(
    "CODEX P1: tree at v2.4.1, version.inc claims v2.4.2, target v2.4.3 -> v2.4.2 content"
    " must NOT be dropped",
    expect_skip=False, expect_noop=False,
    expect_file=["src/mid.c", "src/newfile.c"],
    version="2.4.2", new_release=True, fork_at="v2.4.1", tag_at="v2.4.1",
    no_silent_drop=True))
r.append(scenario(
    "same, with NO tracking tag to fall back to",
    expect_skip=False, expect_noop=False,
    expect_file=["src/mid.c", "src/newfile.c"],
    version="2.4.2", new_release=True, fork_at="v2.4.1", no_tag=True,
    no_silent_drop=True))

# Round 5. Both findings are the same hole seen from two sides: a candidate was
# accepted on a claim about the tree rather than a check of it. Delta-only
# validation cannot see the gap when the gap is BELOW the delta being checked,
# and the tracking tag was not validated at all.
r.append(scenario(
    "CODEX P1 (a): version.inc names a thin release (version bump only) whose PARENT"
    " release we lack -> v2.4.1 content must NOT be dropped",
    expect_skip=False, expect_noop=False,
    expect_file=["src/mid.c", "src/newfile.c"],
    version="2.4.2", chain="thin", new_release=True,
    fork_at="v2.4.0", tag_at="v2.4.0", no_silent_drop=True))
r.append(scenario(
    "CODEX P1 (b): tracking tag advanced by an unmerged sync PR names v2.4.2 while"
    " the tree is at v2.4.0 -> v2.4.1 content must NOT be dropped",
    expect_skip=False, expect_noop=False,
    expect_file=["src/mid.c", "src/newfile.c"],
    expect_file_extra=["src/wéird nàme.json"],
    version="2.4.2", chain="stale", new_release=True,
    fork_at="v2.4.0", tag_at="v2.4.2", no_silent_drop=True))
r.append(scenario(
    "control for (a): same thin-release shape but the tree really does hold"
    " v2.4.2 -> normal sync, target content arrives",
    expect_skip=False, expect_noop=False, expect_file="src/newfile.c",
    version="2.4.2", chain="thin", new_release=True,
    fork_at="v2.4.2", tag_at="v2.4.2"))
r.append(scenario(
    "control for (b): same stale-tag shape but the tree really does hold v2.4.2"
    " -> normal sync, target content arrives",
    expect_skip=False, expect_noop=False, expect_file="src/newfile.c",
    version="2.4.2", chain="stale", new_release=True,
    fork_at="v2.4.2", tag_at="v2.4.2"))


# Round 6. Both are cases the previous round's fix could not see.
r.append(scenario(
    "CODEX P1: upstream edits one hunk, Helio edits another hunk of the SAME file"
    " -> the upstream hunk must not be treated as already applied",
    expect_skip=False, expect_noop=False, expect_file="src/core.c",
    version="2.4.2", chain="hunks", new_release=True,
    fork_at="v2.4.0", tag_at="v2.4.2", no_silent_drop=True,
    expect_text=("src/wide.c", "line 3 CHANGED UPSTREAM")))
r.append(scenario(
    "CODEX P1: a LEGACY tracking tag at the target, written by the old workflow"
    " for a PR that never merged -> must not skip the release for ever",
    expect_skip=False, expect_noop=False,
    expect_file=["src/mid.c", "src/newfile.c"],
    version="2.4.2", chain="stale", new_release=True,
    fork_at="v2.4.0", tag_at_target=True, no_silent_drop=True))

r.append(scenario(
    "CODEX P2: a resolved+squash-merged CONFLICT sync (branch holds the release"
    " WITH Helio edits on top) -> must be recognised as synced, not re-conflicted"
    " every week",
    expect_skip=True, expect_noop=None,
    version="2.4.2", chain="hunks", fork_at="v2.4.2", tag_at="v2.4.0"))


# ---------------------------------------------------------------------------
# Direct tests of upstream_content.sh. The scenarios above exercise it through
# the workflow, which cannot reach these cases: they are about the boundary
# between "missing", "held" and "cannot tell".
# ---------------------------------------------------------------------------
print("\nupstream_content.sh — the three-way boundary\n")


def content_repo(tmp, *, mode_only=False, overlap=False, prereleases=False,
                 mode_and_blob=False, mode_divergent=False):
    """Upstream + a squashed fork, shaped for one boundary case."""
    up = os.path.join(tmp, "up")
    os.makedirs(up)
    sh("git init -q -b main && git config user.email a@b && git config user.name A", up)

    def wr(path, content, mode=None):
        full = os.path.join(up, path)
        os.makedirs(os.path.dirname(full) or up, exist_ok=True)
        open(full, "w").write(content)
        if mode is not None:
            os.chmod(full, mode)

    wr("tool.sh", "#!/bin/sh\necho hi\n", 0o644)
    wr("cfg.ini", "\n".join("k%d=v%d" % (i, i) for i in range(1, 21)) + "\n")
    sh("git add -A && git commit -q -m 2.4.0 && git tag v2.4.0", up)

    if prereleases:
        # Upstream tags several prereleases per release. base_below must not
        # count these as steps, or the walk stays inside one release family.
        for n, rc in enumerate(("v2.4.1-rc1", "v2.4.1-rc2"), start=1):
            wr("cfg.ini",
               "\n".join("k%d=v%d" % (i, i) for i in range(1, 21)) + "\nrc%d\n" % n)
            sh("git add -A && git commit -q -m %s && git tag %s" % (rc, rc), up)

    if mode_only or mode_and_blob or mode_divergent:
        # ONLY the mode changes upstream: identical blob on both sides. With
        # mode_and_blob the FORK then edits the blob independently (below), so
        # all three composite mode/blob values differ and the composite
        # comparison added for mode_only no longer catches it — the text merge
        # sees theirs == base, leaves our blob alone and answers `held`.
        os.chmod(os.path.join(up, "tool.sh"), 0o755)
        sh("git add -A && git commit -q -m 2.4.1 && git tag v2.4.1", up)
    elif overlap:
        # Upstream rewrites the SAME line Helio will rewrite.
        wr("cfg.ini", "\n".join("k%d=v%d" % (i, i) for i in range(1, 21)).replace(
            "k5=v5", "k5=upstream") + "\n")
        sh("git add -A && git commit -q -m 2.4.1 && git tag v2.4.1", up)
    else:
        wr("new.c", "// new\n")
        sh("git add -A && git commit -q -m 2.4.1 && git tag v2.4.1", up)

    fork = os.path.join(tmp, "fork")
    sh("git clone -q %s %s" % (up, fork), tmp)
    sh("git config user.email a@b && git config user.name A", fork)
    sh("git checkout -q -f v2.4.0 && git checkout -q --orphan release", fork)
    if overlap:
        cfg = os.path.join(fork, "cfg.ini")
        open(cfg, "w").write(open(cfg).read().replace("k5=v5", "k5=helio"))
    if mode_and_blob:
        # Helio edits the file's CONTENT while leaving the mode at 100644.
        tool = os.path.join(fork, "tool.sh")
        open(tool, "w").write("#!/bin/sh\necho helio\n")
        os.chmod(tool, 0o644)
    if mode_divergent:
        # Upstream sets 100755; Helio moves the SAME path to a THIRD mode by
        # replacing it with a symlink (120000). No side agrees with any other.
        tool = os.path.join(fork, "tool.sh")
        os.remove(tool)
        os.symlink("cfg.ini", tool)
    sh("git add -A && git commit -q -m squashed", fork)
    sh("git fetch -q origin '+refs/tags/*:refs/tags/*' --force", fork)
    install_content_script(fork)
    return fork, git(fork, "rev-list", "-n1", "v2.4.0")


def content(fork, *args):
    return sh("scripts/helio/upstream_content.sh " + " ".join(args), fork, check=False)


def boundary(label, *, kw, cmd, want_rc=None, want_out=None, want_empty=False,
             want_v240=False, want_not_v240=False):
    tmp = tempfile.mkdtemp()
    try:
        fork, v240 = content_repo(tmp, **kw)
        p = content(fork, *cmd)
        got = p.stdout.strip()
        ok = True
        detail = "rc=%d out=%r" % (p.returncode, got)
        if want_rc is not None and p.returncode != want_rc:
            ok = False
        if want_out is not None and want_out not in got:
            ok = False
        # `x in y` is vacuously true for the empty string, so "reports nothing"
        # needs its own assertion rather than want_out="".
        if want_empty and got != "":
            ok = False
        if want_v240:
            detail += " v2.4.0=%s" % v240[:8]
            if got != v240:
                ok = False
        # "stopped somewhere newer than v2.4.0" — the permissive counterpart to
        # want_v240, so the pair actually asserts the two forms DISAGREE rather
        # than both merely exiting 0.
        if want_not_v240:
            detail += " v2.4.0=%s" % v240[:8]
            if got == v240 or got == "":
                ok = False
        print(("  PASS  " if ok else "  FAIL  ") + label)
        print("        " + detail)
        if not ok:
            print("        wanted rc=%s out~=%r empty=%s v2.4.0=%s"
                  % (want_rc, want_out, want_empty, want_v240))
            FAILURES.append(label)
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


b = []
# A mode-only change has identical blobs on both sides, so a blob-only
# comparison reports nothing missing and the executable bit is dropped for good.
b.append(boundary("mode-only change (100644 -> 100755) is reported missing",
                  kw=dict(mode_only=True), cmd=["missing", "v2.4.1"],
                  want_out="tool.sh"))
b.append(boundary("mode-only change means NOT already-synced",
                  kw=dict(mode_only=True), cmd=["holds", "v2.4.1"], want_rc=1))

# Overlapping edits: git merge-file conflicts, which cannot distinguish
# "we have it, with our edit on top" from "we never got it".
b.append(boundary("overlapping edit is `unknown`, not `missing`",
                  kw=dict(overlap=True), cmd=["unknown", "v2.4.1"],
                  want_out="cfg.ini"))
b.append(boundary("overlapping edit does NOT report missing",
                  kw=dict(overlap=True), cmd=["missing", "v2.4.1"], want_empty=True))
# The pair that was the bug: strict must refuse, permissive must allow.
b.append(boundary("`holds` REFUSES on unknown -> the sync is not skipped",
                  kw=dict(overlap=True), cmd=["holds", "v2.4.1"], want_rc=1))
b.append(boundary("`base-ok` ALLOWS on unknown -> the graft is not lost",
                  kw=dict(overlap=True), cmd=["base-ok", "v2.4.1"], want_rc=0))

# Prereleases must not count as steps in the ancestry walk.
# Two prereleases sit between v2.4.0 and v2.4.1. One step below v2.4.1 must be
# v2.4.0, not v2.4.1-rc2 -- otherwise a four-release window can stay inside one
# release family and the depth guarantee is worth nothing.
b.append(boundary("base_below skips prerelease tags and lands on v2.4.0",
                  kw=dict(prereleases=True), cmd=["base-below", "v2.4.1", "1"],
                  want_v240=True))

# Round 7, Codex P2. Upstream changes ONLY the mode while Helio independently
# edits the blob. All three composite values then differ, so the composite
# comparison added for the mode-only case does not fire, and the text merge --
# handed blob ids with the modes stripped -- sees theirs == base, leaves our
# blob alone and answers `held`. The executable bit is dropped for good and
# `holds` reports the release as already synced.
b.append(boundary("mode change + INDEPENDENT blob edit is reported missing",
                  kw=dict(mode_and_blob=True), cmd=["missing", "v2.4.1"],
                  want_out="tool.sh"))
b.append(boundary("mode change + independent blob edit means NOT already-synced",
                  kw=dict(mode_and_blob=True), cmd=["holds", "v2.4.1"], want_rc=1))

# Round 8, CodeRabbit. Upstream moves the mode one way and Helio moves the SAME
# path a different way (here, to a symlink). All three modes differ, so "we took
# upstream's change and then changed it again" and "we never got it and changed
# it ourselves" are indistinguishable -- the mode equivalent of an overlapping
# hunk. Falling through to the blobs answers `held`, because upstream's blob
# equals the base's; the mode must produce `unknown` instead.
b.append(boundary("upstream and Helio move the mode differently -> unknown",
                  kw=dict(mode_divergent=True), cmd=["unknown", "v2.4.1"],
                  want_out="tool.sh"))
b.append(boundary("divergent modes are NOT reported missing",
                  kw=dict(mode_divergent=True), cmd=["missing", "v2.4.1"],
                  want_empty=True))
b.append(boundary("divergent modes mean NOT already-synced (`holds` refuses)",
                  kw=dict(mode_divergent=True), cmd=["holds", "v2.4.1"], want_rc=1))
b.append(boundary("divergent modes still allow a graft base (`base-ok` tolerates)",
                  kw=dict(mode_divergent=True), cmd=["base-ok", "v2.4.1"], want_rc=0))

# Round 7, Codex P1. `first-held ... strict` must walk PAST a candidate carrying
# undecidable paths, so the graft lands on a base where those paths are still in
# motion and the merge has to present them. The permissive form must still stop
# at the same candidate, because that is what keeps a graft from being lost
# entirely -- the two forms disagreeing here is the whole point.
b.append(boundary("`first-held strict` walks past an undecidable candidate to v2.4.0",
                  kw=dict(overlap=True), cmd=["first-held", "v2.4.1", "strict"],
                  want_v240=True))
b.append(boundary("`first-held` (permissive) still stops at the undecidable candidate",
                  kw=dict(overlap=True), cmd=["first-held", "v2.4.1"],
                  want_rc=0, want_not_v240=True))

r += b

# Round 7, CodeRabbit. Reaches the LAST branch of the graft step's candidate
# loop — every candidate rejected AND no validated base within MAX_WALK steps
# below it. Nothing else in this file got there, which is how a `$MAX_WALK` that
# only ever existed inside upstream_content.sh's own process survived review: in
# the workflow's shell, under `set -u`, it aborts the step instead of warning.
# The value now comes from the step's `env:` block, read out of the workflow by
# step_body, so deleting it there fails this scenario rather than going unseen.
r.append(scenario(
    "CODERABBIT: every graft candidate rejected and no validated base within the"
    " walk -> warn and continue, do not abort the step",
    expect_skip=False, expect_noop=None,
    version="2.4.7", chain="deep", fork_at="v2.4.0", tag_at="v2.4.7",
    target_tag="v2.4.8", no_silent_drop=True,
    expect_graft_warning="no validated older base was found within 6 steps"))


# ---------------------------------------------------------------------------
# The completion signal for CONFLICT syncs (scripts/helio/sync_completion.sh).
#
# This is the one guard in the workflow that leaves git, because the question it
# answers cannot be answered from content: after a resolved conflict the tree
# legitimately lacks some of upstream's changes, so a tree that never received
# the sync and a tree whose resolver chose Helio's version are identical.
#
# The danger is entirely in the FALSE POSITIVE direction — a wrong "yes" skips a
# release permanently — so most of what follows asserts refusal, not acceptance.
# ---------------------------------------------------------------------------
COMPLETION_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "sync_completion.sh")

SHA = "8500fcdccaa10b5099ac20d252af3a7c560046f1"
OTHER_SHA = "1111111111111111111111111111111111111111"
BASE_BR = "orca-latest-parity-bambu"
BRANCH = "helio-release-candidate-v2.4.2"


def completion(prs, *, sync_sha=SHA, base=BASE_BR, branch=BRANCH):
    """Run the real script against a fixture standing in for the API."""
    tmp = tempfile.mkdtemp()
    try:
        fx = os.path.join(tmp, "prs.json")
        with open(fx, "w") as fh:
            json.dump(prs, fh)
        p = subprocess.run(
            ["bash", COMPLETION_SH, sync_sha, base, branch],
            capture_output=True, text=True,
            env={**os.environ, "HELIO_PR_FIXTURE": fx},
        )
        return p
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pr(number, *, merged=True, base=BASE_BR, head=BRANCH, body=""):
    return {
        "number": number,
        "merged_at": "2026-08-01T00:00:00Z" if merged else None,
        "base": {"ref": base},
        "head": {"ref": head},
        "body": body,
    }


MARKER = "<!-- helio-sync-target: %s -->" % SHA

c = []


def comp_case(label, prs, *, want_rc, want_pr=None, want_stderr=None, **kw):
    p = completion(prs, **kw)
    ok = (p.returncode == want_rc)
    if ok and want_pr is not None:
        ok = p.stdout.strip() == str(want_pr)
    if ok and want_stderr is not None:
        ok = want_stderr in p.stderr
    print("  %s  %s" % ("PASS" if ok else "FAIL", label))
    if not ok:
        print("        rc=%s (want %s) out=%r err=%r"
              % (p.returncode, want_rc, p.stdout.strip(), p.stderr.strip()))
        FAILURES.append(label)
    return ok


print("\nCompletion signal — a merged PR is the only thing that may skip a conflict sync")

# Accepts: the shape this exists for.
c.append(comp_case("merged PR carrying the sync-target marker is accepted",
                   [pr(96, body="Resolved v2.4.2.\n" + MARKER)],
                   want_rc=0, want_pr=96))

# Refuses: each of these, wrongly accepted, skips a release for ever.
c.append(comp_case("closed-but-UNMERGED PR is refused (the #107 bug in reverse)",
                   [pr(96, merged=False, body=MARKER)],
                   want_rc=1))
c.append(comp_case("merged into a DIFFERENT base is refused",
                   [pr(96, base="main", body=MARKER)],
                   want_rc=1))
c.append(comp_case("marker naming a DIFFERENT sha is refused (upstream force-retag)",
                   [pr(96, body="<!-- helio-sync-target: %s -->" % OTHER_SHA,
                       head="some-other-branch")],
                   want_rc=1))
c.append(comp_case("no PRs at all -> refused",
                   [], want_rc=1))
c.append(comp_case("merged PR for an unrelated branch is refused",
                   [pr(96, head="feature/unrelated", body="no marker here")],
                   want_rc=1))

# The retag case is the subtle one: same branch name, different content. The
# marker is what separates them, so assert the two answers differ on the SAME
# fixture rather than only that each is individually plausible.
retag_fixture = [pr(96, body="Resolved v2.4.2.\n" + MARKER)]
c.append(comp_case("same fixture, retagged target -> refused where the original was accepted",
                   retag_fixture, sync_sha=OTHER_SHA, want_rc=1))

# Branch-name fallback: accepted for pre-marker PRs, but it must SAY so, because
# it is the one path that cannot detect a force-retag.
c.append(comp_case("pre-marker PR matches on branch name and warns that it did",
                   [pr(107, body="opened before the marker existed")],
                   want_rc=0, want_pr=107, want_stderr="matched by BRANCH NAME"))
c.append(comp_case("main-mode branch matches on the short sha it embeds",
                   [pr(88, head="helio-upstream-main-2026-08-10-%s" % SHA[:7],
                       body="")],
                   want_rc=0, want_pr=88, branch=""))
c.append(comp_case("main-mode branch with a DIFFERENT short sha is refused",
                   [pr(88, head="helio-upstream-main-2026-08-10-deadbee", body="")],
                   want_rc=1, branch=""))

# A merged PR must not be found by luck: put the real one behind decoys.
c.append(comp_case("finds the marker PR among unmerged and unrelated ones",
                   [pr(1, merged=False, body=MARKER),
                    pr(2, base="main", body=MARKER),
                    pr(3, head="x", body="nothing"),
                    pr(96, body=MARKER)],
                   want_rc=0, want_pr=96))

# Malformed / unreachable API must read as "cannot tell", never as "synced".
c.append(comp_case("malformed API payload is refused, not treated as proof",
                   "not json at all", want_rc=1))

r += c

# End-to-end: the real `check` step body must actually skip on that signal.
print("\nCompletion signal — end to end through the real `check` step")


def completion_e2e(label, prs, *, want_skip):
    tmp = tempfile.mkdtemp()
    try:
        # A GENUINELY NEW release: the fork does not hold its content, so every
        # content-based guard above correctly declines and the completion signal
        # is the only thing left that can decide. If this repo already held the
        # target, `holds` would skip first and the scenario would pass without
        # ever reaching the code under test.
        fork, target, sync_sha = build(tmp, version="2.4.2", new_release=True)
        # Rewrite the fixture's marker to the sha this synthetic repo actually
        # produced. Hardcoding SHA here would make the scenario pass for the
        # wrong reason, which has already happened twice on this PR.
        fixed = []
        for p in prs:
            q = dict(p)
            q["body"] = (q.get("body") or "").replace(SHA, sync_sha)
            fixed.append(q)
        fx = os.path.join(tmp, "prs.json")
        with open(fx, "w") as fh:
            json.dump(fixed, fh)
        p, out = run_check(fork, target, sync_sha,
                           extra_env={"HELIO_PR_FIXTURE": fx})
        got = out.get("skip") == "true"
        ok = (got == want_skip) and p.returncode == 0
        print("  %s  %s" % ("PASS" if ok else "FAIL", label))
        if not ok:
            print("        skip=%s (want %s) rc=%s" % (out.get("skip"), want_skip, p.returncode))
            print(p.stdout[-1200:], p.stderr[-800:])
            FAILURES.append(label)
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


r.append(completion_e2e(
    "a merged, marker-carrying PR makes the check step skip",
    [pr(96, body=MARKER)], want_skip=True))
r.append(completion_e2e(
    "an unmerged PR does NOT make the check step skip",
    [pr(96, merged=False, body=MARKER)], want_skip=False))

print("\n%d/%d passed" % (sum(r), len(r)))
if FAILURES:
    # FAILURES was collected and never printed, so a run that failed showed the
    # count but not what to look at.
    print("\nfailed:")
    for f in FAILURES:
        print("  - " + f)
# FAILURES gates the exit as well as `r`: a collected failure that somehow left
# every scenario's own verdict True would otherwise be printed and then ignored.
sys.exit(0 if (all(r) and not FAILURES) else 1)
