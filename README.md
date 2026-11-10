# git-branch-age-checker-cli

Find git branches older than your limit, fail CI on a stale branch.

[![CI](https://github.com/haiderstudio/git-branch-age-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/git-branch-age-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`git_branch_age_checker` looks at the branches in a git repo and
reports every branch whose last commit is older than the limit you
set (default 90 days). Each stale branch is listed with its name,
its last commit date, and its age in days. It exits 1 when any
stale branch is found, so it can fail a CI run. A repo with no
stale branches exits 0.

- Stale branches pile up until nobody knows which are safe to
  delete. This tool names them before they rot, with the exact
  age, so the cleanup decision is a fact, not a guess.
- The branch you are on is never flagged, even if it is old —
  you are working on it, so it is not stale.
- Branches are listed oldest first, so the worst one is on top.
- `--max-age-days` changes the limit. `--remote` also checks
  remote-tracking branches (`origin/...`). `--exclude` skips
  branches by name pattern (may be given more than once).
- A repo with no branches passes — there is nothing to flag.
- `--json` prints the result as JSON (the plain lines go to
  standard error), for scripts that read the result.
- Dates are shown in UTC, so the same repo reports the same
  date on every machine.

## Who it is for

Anyone with a git repo that has lived a while — solo developers
with ten forgotten branches, and teams whose branch list is
longer than anyone remembers. If you have ever opened your
branch list and wondered which ones are safe to delete, this
is the check that answers it.

## What it does NOT do

- It does not delete anything. It is report-only — deleting a
  branch is your decision, made after you see the list. Deleting
  merged or gone branches is repo #2's git-branch-cleanup-cli,
  a different job.
- It does not check whether a branch is merged. Age is the only
  question here — an old branch can still be unmerged work.
- It does not touch the network or any remote. It reads the
  local repo only (remote-tracking branches are already in
  your local repo after a fetch).
- It does not check anything but branch age. Repo health is a
  different job.

## How this differs

- ques0942/old_branch_checker (0 stars) is a GitLab API tool:
  it needs a GitLab host and a private token in a config file,
  and it checks merged and dev branches by fixed rules. This
  tool reads the local repo only, needs no account and no
  token, and lets you set the age limit.
- Vaibhavpisute/git_repo_health_checker (0 stars) is a broad
  health checker — stale branches are one check inside it,
  next to missing .gitignore files, large files, and exposed
  .env files. This tool does branch age only, one job, with
  a threshold flag and a CI exit code.
- There is no exact-name rival: a GitHub search for
  "git-branch-age-checker-cli" returns 0 results.

## Install

```sh
git clone https://github.com/haiderstudio/git-branch-age-checker-cli.git
cd git-branch-age-checker-cli
```

No dependencies to install — Python 3.8 or newer and git are
all it needs. (The clone step was not run here — it needs the
network — but the command is the standard one used by every
repo in this series, and everything after the clone is verified
on a fresh folder copy.)

## Usage

```sh
python3 src/git_branch_age_checker.py [path] [--max-age-days N] [--remote] [--exclude PATTERN] [--json]
```

Run it inside a repo, or give the repo path. Exit codes: 0 means
all branches are fresh, 1 means at least one stale branch was
found, 2 means a usage error (not a git repo, bad flag, git
missing).

```text
$ python3 src/git_branch_age_checker.py
old-feature: last commit 2026-04-22, 200 days ago
Checked 3 branch(es), 1 stale branch(es).
```

## Examples

### 1. The bundled sample repo (default 90-day limit)

The examples folder builds a small repo with three branches:
`main` (commit 5 days ago), `old-feature` (200 days ago), and
`docs-update` (31 days ago). Run it with:

```sh
sh examples/run-example.sh
```

Real output from a run on 2026-11-08 (dates and ages move with
the calendar — the branch names and the verdicts stay the same):

```text
Sample repo built at /tmp/branch-age-sample-repo
--- default limit (90 days) ---
old-feature: last commit 2026-04-22, 200 days ago
Checked 3 branch(es), 1 stale branch(es).
--- limit 30 days ---
old-feature: last commit 2026-04-22, 200 days ago
docs-update: last commit 2026-10-08, 31 days ago
Checked 3 branch(es), 2 stale branch(es).
```

### 2. A tighter limit, and JSON output

With `--max-age-days 30`, the 31-day-old `docs-update` branch
is stale too. With `--json`, the same result comes back as
JSON on standard output (the plain lines go to standard error):

```sh
python3 src/git_branch_age_checker.py --max-age-days 30 /tmp/branch-age-sample-repo
python3 src/git_branch_age_checker.py --json /tmp/branch-age-sample-repo
```

```text
old-feature: last commit 2026-04-22, 200 days ago
docs-update: last commit 2026-10-08, 31 days ago
Checked 3 branch(es), 2 stale branch(es).
```

```json
{
  "checked": 3,
  "max_age_days": 90,
  "repo": "/tmp/branch-age-sample-repo",
  "stale": [
    {
      "age_days": 200,
      "branch": "old-feature",
      "last_commit": "2026-04-22"
    }
  ]
}
```

### 3. A fresh repo, and a folder that is not a repo

```sh
python3 src/git_branch_age_checker.py /path/to/a/fresh/repo
python3 src/git_branch_age_checker.py /tmp
```

```text
OK — 1 branch(es) checked, all branches are fresh.
```

```text
Not a git repository: /tmp
```

The second command exits 2 — a plain message, not a crash.

## How it is tested

```sh
python3 tests/test_git_branch_age_checker.py
```

The tests build real temp git repos with commits at chosen
ages (5, 30, 100, 150, 200 days ago, and a future date) and
check the real output: fresh repos pass, old branches fail
with the exact date and age, `--max-age-days` moves the
limit both ways, the current branch is never flagged, an
empty repo passes, a non-repo exits 2, `--exclude` skips,
`--remote` checks remote-tracking branches (and only with
the flag), `--json` parses and matches, detached HEAD does
not crash, and the bundled examples run and report the same
verdicts. The same suite also runs from a fresh copy of the
repo, and checks the hygiene rules: no filler text, no
secrets, no absolute home paths, `.env` first in
`.gitignore`, and the CI file matching the known-good one
except for the test filename.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused
improvements are welcome — and the tool must stay report-only:
it never deletes a branch.

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Written from scratch for this repo. The idea — flagging old
branches by last-commit age — is a common one; the code,
the tests, and the wording here are original. The two closest
existing tools are named in "How this differs" above.
