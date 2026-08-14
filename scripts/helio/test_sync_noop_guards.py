#!/usr/bin/env python3
"""Exercise the real `check` and `graft` step scripts from helio-upstream-sync.yml
against synthetic repositories that reproduce each false-skip scenario.

The step bodies are extracted from the workflow, so this tests the shipped code
rather than a transcription of it.
"""
import os, re, shutil, subprocess, sys, tempfile
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
    wf = yaml.safe_load(open(WF))
    for s in wf["jobs"]["sync"]["steps"]:
        if s.get("name") == name:
            body = s["run"]
            def sub(m):
                key = m.group(1)
                if key in MAP:
                    return "${%s}" % MAP[key]
                raise SystemExit("unmapped expression in %r: %s" % (name, key))
            return EXPR.sub(sub, body)  # no-op once every input arrives via env
    raise SystemExit("step not found: " + name)


CHECK = step_body("Check if already synced")
GRAFT = step_body("Establish correct merge base (ephemeral graft)")


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
    shutil.copy2(CONTENT_SH, os.path.join(dest, "upstream_content.sh"))
    os.chmod(os.path.join(dest, "upstream_content.sh"), 0o755)


def sh(cmd, cwd, env=None, check=True):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=e,
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        print(p.stdout, p.stderr)
        raise SystemExit("command failed: " + cmd)
    return p


def git(repo, *args):
    return sh("git " + " ".join(args), repo).stdout.strip()


def build(tmp, *, version, retag=False, bump_ahead=False, tag_at_target=False,
          new_release=False, no_tag=False, fork_at=None, tag_at=None,
          chain=None):
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
    elif chain == "stale":
        # version.inc is written once and never touched again, so the fork's copy
        # agrees with upstream at every release and the merge cannot conflict on
        # it. Without that, a version.inc conflict masks the dropped file and the
        # scenario passes for the wrong reason.
        commit("2.4.0", {"version.inc": verinc("2.4.2"), "src/core.c": "int main(){}\n"})
        sh("git tag v2.4.0", up)
        commit("2.4.1", {"src/mid.c": "// content that only v2.4.1 introduced\n"})
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

    target = "v2.4.3" if (bump_ahead or new_release) else "v2.4.2"
    sync_sha = git(fork, "rev-list", "-n1", target)
    if no_tag:
        sh("git tag -d helio-last-synced 2>/dev/null || true", fork)
    else:
        at = sync_sha if tag_at_target else (tag_at or v241)
        sh("git tag -f helio-last-synced %s" % at, fork)
    return fork, target, sync_sha


def run_check(fork, target, sync_sha):
    outfile = os.path.join(fork, "..", "ghout")
    open(outfile, "w").close()
    env = {
        "SYNC_SHA": sync_sha, "SYNC_LABEL": target,
        "TRACKING_TAG": "helio-last-synced", "SYNC_REF": target,
        "GITHUB_OUTPUT": outfile, "GITHUB_STEP_SUMMARY": outfile + ".sum",
        "GITHUB_WORKSPACE": fork,
    }
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
             no_silent_drop=False, expect_text=None, **kw):
    """no_silent_drop: pass if the merge conflicts (safe — a human resolves it)
    OR completes cleanly with every expected file present. Fail only on the
    dangerous combination: a clean merge that quietly omits upstream content."""
    wanted = [expect_file] if isinstance(expect_file, str) else (expect_file or [])
    tmp = tempfile.mkdtemp()
    try:
        fork, target, sync_sha = build(tmp, **kw)
        cp, out = run_check(fork, target, sync_sha)
        ok_files = True
        skip = out.get("skip") == "true"
        results = ["check.skip=%s (exit %d)" % (skip, cp.returncode)]
        noop = None
        if not skip:
            gp, gout, status, noop = run_graft_and_merge(fork, target, sync_sha)
            if gout.get("prev_upstream"):
                results.append("base=%s" % gout["prev_upstream"][:8])
            results.append("grafted=%s" % gout.get("grafted"))
            results.append("merge=%s" % status)
            results.append("noop=%s" % noop)
            if no_silent_drop and status == "conflict":
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
        ok = (skip == expect_skip) and (noop == expect_noop) and ok_files
        print(("  PASS  " if ok else "  FAIL  ") + name)
        print("        " + " | ".join(results))
        if not ok:
            print("        expected skip=%s noop=%s" % (expect_skip, expect_noop))
            print(cp.stdout[-1500:])
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

print("\n%d/%d passed" % (sum(r), len(r)))
sys.exit(0 if all(r) else 1)
