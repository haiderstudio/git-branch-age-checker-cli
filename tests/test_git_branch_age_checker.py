#!/usr/bin/env python3
"""Tests for git-branch-age-checker-cli. Standard library only."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "git_branch_age_checker.py"
KNOWN_GOOD_CI = 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - name: Set up Python\n        uses: actions/setup-python@v5\n        with:\n          python-version: "3.12"\n      - name: Run tests\n        run: python3 tests/test_ini_validator.py\n'


def run_cli(args, cwd=None, env=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(SRC)] + args,
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_git(repo, args, env=None):
    full_env = dict(os.environ)
    full_env["GIT_CONFIG_NOSYSTEM"] = "1"
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", "-C", str(repo)] + args,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def commit_date(days_ago):
    """A git date string N days ago, at noon UTC."""
    import datetime

    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days_ago
    )
    return when.strftime("%Y-%m-%dT%H:%M:%S")


class RepoBuilder:
    """Build a small git repo with branches at chosen ages."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        run_git(self.path, ["init", "-q", "-b", "main"])
        run_git(self.path, ["config", "user.email", "test@example.com"])
        run_git(self.path, ["config", "user.name", "Test User"])

    def commit(self, filename, content, message, days_ago):
        (self.path / filename).write_text(content)
        run_git(self.path, ["add", filename])
        stamp = commit_date(days_ago)
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        result = run_git(self.path, ["commit", "-qm", message], env=env)
        assert result.returncode == 0, result.stderr

    def branch_with_commit(self, name, filename, days_ago):
        run_git(self.path, ["checkout", "-qb", name])
        self.commit(filename, "work on " + name, "work on " + name, days_ago)
        run_git(self.path, ["checkout", "-q", "main"])

    def branch_tip_time(self, name):
        result = run_git(self.path, ["log", "-1", "--format=%ct", name])
        assert result.returncode == 0, result.stderr
        return int(result.stdout.strip())

    def expected_age_days(self, name):
        import time

        return (int(time.time()) - self.branch_tip_time(name)) // 86400

    def expected_date(self, name):
        import datetime

        tip = self.branch_tip_time(name)
        return datetime.datetime.fromtimestamp(
            tip, tz=datetime.timezone.utc
        ).date().isoformat()


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.builder = RepoBuilder(self.repo)
        self.builder.commit("README.md", "sample", "first commit", 5)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_repo_passes(self):
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)
        self.assertIn("1 branch(es) checked", result.stdout)
        self.assertIn("all branches are fresh", result.stdout)

    def test_old_branch_fails_with_exact_age_and_date(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        age = self.builder.expected_age_days("old-feature")
        date = self.builder.expected_date("old-feature")
        self.assertIn("old-feature: last commit %s, %d days ago" % (date, age), result.stdout)
        self.assertIn("Checked 2 branch(es), 1 stale branch(es).", result.stdout)

    def test_max_age_days_raises_the_limit(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli(["--max-age-days", "365", str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("all branches are fresh", result.stdout)

    def test_max_age_days_lowers_the_limit(self):
        self.builder.branch_with_commit("feature-x", "x.txt", 5)
        result = run_cli(["--max-age-days", "1", str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("feature-x: last commit", result.stdout)

    def test_max_age_days_zero_flags_everything(self):
        self.builder.branch_with_commit("feature-x", "x.txt", 5)
        result = run_cli(["--max-age-days", "0", str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("feature-x: last commit", result.stdout)

    def test_current_branch_is_never_flagged(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        run_git(self.repo, ["checkout", "-q", "old-feature"])
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("all branches are fresh", result.stdout)

    def test_current_branch_counts_as_checked(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        run_git(self.repo, ["checkout", "-q", "old-feature"])
        result = run_cli([str(self.repo)])
        self.assertIn("2 branch(es) checked", result.stdout)

    def test_repo_with_no_commits_passes(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        run_git(empty, ["init", "-q", "-b", "main"])
        result = run_cli([str(empty)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK — 0 branch(es) checked, all branches are fresh.", result.stdout)

    def test_outside_a_git_repo_exits_2(self):
        plain = Path(self.tmp.name) / "plain"
        plain.mkdir()
        result = run_cli([str(plain)])
        self.assertEqual(result.returncode, 2)
        self.assertIn("Not a git repository", result.stderr)

    def test_missing_path_exits_2(self):
        result = run_cli([str(Path(self.tmp.name) / "no-such-dir")])
        self.assertEqual(result.returncode, 2)
        self.assertIn("No such path", result.stderr)

    def test_negative_max_age_days_exits_2(self):
        result = run_cli(["--max-age-days", "-1", str(self.repo)])
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be 0 or more", result.stderr)

    def test_non_integer_max_age_days_exits_2(self):
        result = run_cli(["--max-age-days", "soon", str(self.repo)])
        self.assertEqual(result.returncode, 2)

    def test_exclude_skips_a_branch(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli(["--exclude", "old-*", str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("all branches are fresh", result.stdout)

    def test_exclude_multiple_patterns(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        self.builder.branch_with_commit("wip-thing", "wip.txt", 150)
        result = run_cli(
            ["--exclude", "old-*", "--exclude", "wip-*", str(self.repo)]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_excluded_branch_is_not_counted(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli(["--exclude", "old-*", str(self.repo)])
        self.assertIn("1 branch(es) checked", result.stdout)

    def test_branch_with_slash_in_name(self):
        self.builder.branch_with_commit("feature/old-thing", "f.txt", 120)
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("feature/old-thing: last commit", result.stdout)

    def test_multiple_stale_sorted_oldest_first(self):
        self.builder.branch_with_commit("old-a", "a.txt", 100)
        self.builder.branch_with_commit("old-b", "b.txt", 200)
        self.builder.branch_with_commit("old-c", "c.txt", 150)
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        lines = [
            line for line in result.stdout.splitlines() if "last commit" in line
        ]
        self.assertEqual(
            [line.split(":")[0] for line in lines],
            ["old-b", "old-c", "old-a"],
        )

    def test_detached_head_does_not_crash(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        run_git(self.repo, ["checkout", "-q", "--detach", "HEAD"])
        result = run_cli([str(self.repo)])
        self.assertIn(result.returncode, (0, 1))
        self.assertIn("old-feature: last commit", result.stdout)

    def test_future_dated_commit_is_fresh(self):
        self.builder.branch_with_commit("future-branch", "f.txt", -5)
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_path_is_current_folder(self):
        result = run_cli([], cwd=str(self.repo))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_json_output_parses_and_matches(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli(["--json", str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["checked"], 2)
        self.assertEqual(data["max_age_days"], 90)
        self.assertEqual(len(data["stale"]), 1)
        item = data["stale"][0]
        self.assertEqual(item["branch"], "old-feature")
        self.assertEqual(item["last_commit"], self.builder.expected_date("old-feature"))
        self.assertEqual(item["age_days"], self.builder.expected_age_days("old-feature"))

    def test_json_output_clean_repo(self):
        result = run_cli(["--json", str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["stale"], [])
        self.assertEqual(data["checked"], 1)

    def test_json_human_lines_go_to_stderr(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli(["--json", str(self.repo)])
        self.assertIn("old-feature: last commit", result.stderr)
        self.assertNotIn("old-feature: last commit", result.stdout)

    def test_remote_branches_ignored_by_default(self):
        origin = Path(self.tmp.name) / "origin"
        origin_builder = RepoBuilder(origin)
        origin_builder.commit("README.md", "origin", "origin first", 5)
        origin_builder.branch_with_commit("old-remote", "r.txt", 200)
        run_git(self.repo, ["remote", "add", "origin", str(origin)])
        run_git(self.repo, ["fetch", "-q", "origin"])
        result = run_cli([str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_remote_flag_checks_remote_tracking_branches(self):
        origin = Path(self.tmp.name) / "origin"
        origin_builder = RepoBuilder(origin)
        origin_builder.commit("README.md", "origin", "origin first", 5)
        origin_builder.branch_with_commit("old-remote", "r.txt", 200)
        run_git(self.repo, ["remote", "add", "origin", str(origin)])
        run_git(self.repo, ["fetch", "-q", "origin"])
        result = run_cli(["--remote", str(self.repo)])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("origin/old-remote: last commit", result.stdout)

    def test_remote_head_is_not_flagged(self):
        origin = Path(self.tmp.name) / "origin"
        origin_builder = RepoBuilder(origin)
        origin_builder.commit("README.md", "origin", "origin first", 5)
        run_git(self.repo, ["remote", "add", "origin", str(origin)])
        run_git(self.repo, ["fetch", "-q", "origin"])
        result = run_cli(["--remote", str(self.repo)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("origin/HEAD", result.stdout)

    def test_git_missing_exits_2(self):
        empty_path = Path(self.tmp.name) / "emptybin"
        empty_path.mkdir()
        env = {"PATH": str(empty_path)}
        result = run_cli([str(self.repo)], env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("git is not installed", result.stderr)

    def test_help_exits_0(self):
        result = run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--max-age-days", result.stdout)

    def test_version_exits_0(self):
        result = run_cli(["--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("git-branch-age-checker-cli", result.stdout)

    def test_stale_line_format(self):
        self.builder.branch_with_commit("old-feature", "old.txt", 200)
        result = run_cli([str(self.repo)])
        line = [l for l in result.stdout.splitlines() if l.startswith("old-feature")][0]
        self.assertRegex(
            line, r"^old-feature: last commit \d{4}-\d{2}-\d{2}, \d+ days ago$"
        )


class ExampleTests(unittest.TestCase):
    def test_run_example_exits_0_and_reports_both_limits(self):
        env = {"TMPDIR": self._tmpdir()}
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=str(ROOT),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("old-feature: last commit", result.stdout)
        self.assertIn("Checked 3 branch(es), 1 stale branch(es).", result.stdout)
        self.assertIn("docs-update: last commit", result.stdout)
        self.assertIn("Checked 3 branch(es), 2 stale branch(es).", result.stdout)

    def test_sample_output_matches_a_real_run(self):
        env = {"TMPDIR": self._tmpdir()}
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=str(ROOT),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        sample = (ROOT / "examples" / "sample-output.md").read_text()
        for marker in (
            "old-feature: last commit",
            "docs-update: last commit",
            "Checked 3 branch(es), 1 stale branch(es).",
            "Checked 3 branch(es), 2 stale branch(es).",
        ):
            self.assertIn(marker, sample)
            self.assertIn(marker, result.stdout)

    def test_make_sample_repo_builds_three_branches(self):
        tmpdir = self._tmpdir()
        env = {"TMPDIR": tmpdir}
        result = subprocess.run(
            ["sh", "examples/make-sample-repo.sh"],
            cwd=str(ROOT),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        repo = Path(tmpdir) / "branch-age-sample-repo"
        listing = run_git(repo, ["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
        self.assertEqual(
            sorted(listing.stdout.split()),
            ["docs-update", "main", "old-feature"],
        )

    def test_readme_examples_match_real_runs(self):
        tmpdir = self._tmpdir()
        env = {"TMPDIR": tmpdir}
        subprocess.run(
            ["sh", "examples/make-sample-repo.sh"],
            cwd=str(ROOT),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=120,
        )
        repo = str(Path(tmpdir) / "branch-age-sample-repo")
        fresh = run_cli([repo])
        self.assertEqual(fresh.returncode, 1)
        readme = (ROOT / "README.md").read_text()
        # Every stale branch name and every summary count quoted in the
        # README must appear in a fresh real run (dates and ages move
        # with the calendar, so names and counts are the stable parts).
        for name in ("old-feature", "docs-update"):
            self.assertIn(name, readme)
            self.assertIn(name, fresh.stdout + run_cli(["--max-age-days", "30", repo]).stdout)
        self.assertIn("Checked 3 branch(es), 1 stale branch(es).", readme)
        self.assertIn("Checked 3 branch(es), 2 stale branch(es).", readme)

    def _tmpdir(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmp, True)
        return self._tmp


class HygieneTests(unittest.TestCase):
    BANNED_WORDS = ("TODO", "FIXME", "coming soon", "lorem", "Lorem", "placeholder")
    SECRET_PATTERNS = (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"gho_[A-Za-z0-9]{20,}"),
        re.compile(r"sk-[A-Za-z0-9]{16,}"),
        re.compile(r"(api_key|password|passwd)\s*=", re.IGNORECASE),
    )

    def _repo_files(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(ROOT).parts
            if parts[0] in (".git", "__pycache__"):
                continue
            if "__pycache__" in parts:
                continue
            yield path

    def test_no_placeholder_text(self):
        hits = []
        for path in self._repo_files():
            if path.suffix in (".pyc",):
                continue
            if path.parent.name == "tests":
                continue
            text = path.read_text(errors="replace")
            for word in self.BANNED_WORDS:
                if word in text:
                    hits.append("%s: %s" % (path.relative_to(ROOT), word))
        self.assertEqual(hits, [])

    def test_no_secrets_or_keys(self):
        hits = []
        for path in self._repo_files():
            if path.parent.name == "tests":
                continue
            text = path.read_text(errors="replace")
            for pattern in self.SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.relative_to(ROOT), pattern.pattern))
        self.assertEqual(hits, [])

    def test_no_absolute_home_paths(self):
        hits = []
        for path in self._repo_files():
            if path.parent.name == "tests":
                continue
            text = path.read_text(errors="replace")
            if "/home/" in text:
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_no_yaml_import(self):
        hits = []
        for path in list((ROOT / "src").rglob("*.py")) + list(
            (ROOT / "tests").rglob("*.py")
        ):
            text = path.read_text()
            if ("import " + "yaml") in text or ("from " + "yaml") in text:
                hits.append(str(path.relative_to(ROOT)))
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertNotIn("yaml", ci)
        self.assertEqual(hits, [])

    def test_stdlib_only_imports(self):
        allowed = {
            "argparse", "fnmatch", "json", "subprocess", "sys", "time",
            "datetime", "pathlib", "os", "re", "shutil", "tempfile",
            "unittest",
        }
        for path in (ROOT / "src").rglob("*.py"):
            text = path.read_text()
            for match in re.finditer(r"^(?:from|import)\s+([a-z_]+)", text, re.M):
                self.assertIn(
                    match.group(1), allowed, "%s imports %s" % (path, match.group(1))
                )

    def test_ci_matches_known_good_ci_except_test_name(self):
        known_good = KNOWN_GOOD_CI
        ours = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertEqual(
            ours.replace("test_git_branch_age_checker.py", "test_ini_validator.py"),
            known_good,
        )
        for marker in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            '"3.12"',
            "python3 tests/test_git_branch_age_checker.py",
        ):
            self.assertIn(marker, ours)


if __name__ == "__main__":
    unittest.main()
