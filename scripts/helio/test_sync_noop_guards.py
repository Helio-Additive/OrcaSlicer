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
          new_release=False, no_tag=False, fork_at=None, tag_at=None):
    """Fork repo whose profile tree holds v2.4.2 via a SQUASHED commit."""
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

    commit("base", {"version.inc": verinc("2.4.1"), "src/core.c": "int main(){}\n"})
    v241 = git(up, "rev-parse", "HEAD")
    sh("git tag v2.4.1", up)

    commit("2.4.2", {"version.inc": verinc("2.4.2"),
                     "src/core.c": "int main(){return 0;}\n",
                     "src/mid.c": "// content that only v2.4.2 introduced\n"})
    v242_a = git(up, "rev-parse", "HEAD")
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
    open(os.path.join(fork, "version.inc"), "w").write(verinc(version))
    sh("git add -A && git commit -q -m 'Upstream sync: v2.4.2 (squashed)'", fork)

    if retag:
        # Upstream force-retags v2.4.2 onto a NEW commit with new content.
        commit("retagged 2.4.2", {"version.inc": verinc("2.4.2"),
                                  "src/newfeature.c": "// added after retag\n"})
        sh("git tag -f v2.4.2", up)
    if bump_ahead or new_release:
        commit("2.4.3", {"version.inc": verinc("2.4.3"),
                         "src/newfile.c": "// genuinely new upstream work\n"})
        sh("git tag v2.4.3", up)

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
             no_silent_drop=False, **kw):
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
r.append(scenario(
    "#107: cron re-proposes v2.4.2, already merged -> no PR (decided by tree, not version.inc)",
    expect_skip=False, expect_noop=True, version="2.4.2"))
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
    "REGRESSION CHECK: #107 shape but NO usable tracking tag -> must still be a clean no-op",
    expect_skip=False, expect_noop=True, version="2.4.2", no_tag=True))

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

print("\n%d/%d passed" % (sum(r), len(r)))
sys.exit(0 if all(r) else 1)
