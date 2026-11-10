#!/usr/bin/env python3
"""Find git branches older than a limit.

One job only: in a git repo, list local branches whose last commit is
older than N days (default 90). Report-only, never deletes anything.
Exits 1 when any stale branch is found, 0 when all are fresh, 2 on
usage errors (not a git repo, bad flag, git missing).

Standard library only. Git itself is the tool being checked, so it is
called through subprocess — no third-party Python module is used.
"""

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"


def run_git(repo, args):
    """Run a git command inside repo. Returns the CompletedProcess."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo)] + args,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def is_git_repo(path):
    result = run_git(path, ["rev-parse", "--git-dir"])
    return result is not None and result.returncode == 0


def current_branch(path):
    """Name of the branch checked out, or None (detached HEAD)."""
    result = run_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if result is not None and result.returncode == 0:
        return result.stdout.strip()
    return None


def list_branches(path, include_remote):
    """All local branches (plus remote-tracking ones with --remote).

    Returns (branches, error): branches is a list of (name, commit_time)
    with commit_time as a unix timestamp, or None when git failed.
    """
    refs = ["refs/heads/"]
    if include_remote:
        refs.append("refs/remotes/")
    result = run_git(
        path,
        ["for-each-ref", "--format=%(refname:short)%00%(committerdate:unix)"]
        + refs,
    )
    if result is None:
        return None, "git is not installed or not on PATH"
    if result.returncode != 0:
        return None, result.stderr.strip() or "git for-each-ref failed"
    branches = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        name, sep, stamp = line.partition("\x00")
        if not sep or not stamp:
            continue
        if name.endswith("/HEAD"):
            continue
        try:
            commit_time = int(stamp)
        except ValueError:
            continue
        branches.append((name, commit_time))
    return branches, None


def check_repo(path, max_age_days, include_remote, exclude):
    """Check one repo. Returns (report dict, error string or None)."""
    if not is_git_repo(path):
        return None, "Not a git repository: %s" % path
    branches, error = list_branches(path, include_remote)
    if error is not None:
        return None, error
    now = int(time.time())
    limit_seconds = max_age_days * 86400
    current = current_branch(path)
    stale = []
    fresh = 0
    for name, commit_time in branches:
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in exclude):
            continue
        age_seconds = now - commit_time
        age_days = age_seconds // 86400
        if age_days < 0:
            age_days = 0
        if name == current:
            fresh += 1
            continue
        if age_seconds > limit_seconds:
            stale.append(
                {
                    "branch": name,
                    "last_commit": datetime.fromtimestamp(
                        commit_time, tz=timezone.utc
                    ).date().isoformat(),
                    "age_days": age_days,
                }
            )
        else:
            fresh += 1
    stale.sort(key=lambda item: item["age_days"], reverse=True)
    report = {
        "repo": str(path),
        "checked": len(stale) + fresh,
        "stale": stale,
        "max_age_days": max_age_days,
    }
    return report, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find git branches older than a limit, fail CI on a stale branch."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="path to the git repo to check (default: current folder)",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=90,
        help="a branch is stale when its last commit is older than this many days (default: 90)",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="also check remote-tracking branches (origin/...), not just local ones",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip branches whose name matches this pattern (may be given more than once)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON on standard output (the plain lines go to standard error)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="git-branch-age-checker-cli " + VERSION,
    )
    args = parser.parse_args(argv)
    if args.max_age_days < 0:
        parser.error("--max-age-days must be 0 or more")
    path = Path(args.path)
    if not path.exists():
        print("No such path: %s" % path, file=sys.stderr)
        return 2
    probe = run_git(path, ["--version"])
    if probe is None:
        print("git is not installed or not on PATH", file=sys.stderr)
        return 2
    report, error = check_repo(path, args.max_age_days, args.remote, args.exclude)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    out = sys.stdout if not args.json else sys.stderr
    if report["stale"]:
        for item in report["stale"]:
            print(
                "%s: last commit %s, %d days ago"
                % (item["branch"], item["last_commit"], item["age_days"]),
                file=out,
            )
        print(
            "Checked %d branch(es), %d stale branch(es)."
            % (report["checked"], len(report["stale"])),
            file=out,
        )
    else:
        print(
            "OK — %d branch(es) checked, all branches are fresh."
            % report["checked"],
            file=out,
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
