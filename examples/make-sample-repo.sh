#!/bin/sh
# Build a small sample git repo for the examples.
# Branches: main (fresh, commit 5 days ago), old-feature (commit 200
# days ago), docs-update (commit 31 days ago — past the 30-day limit
# in the second example, but fresh under the default 90 days).
set -e
SAMPLE_DIR="${TMPDIR:-/tmp}/branch-age-sample-repo"
rm -rf "$SAMPLE_DIR"
mkdir -p "$SAMPLE_DIR"
cd "$SAMPLE_DIR"
git init -q -b main
git config user.email "sample@example.com"
git config user.name "Sample User"
echo "sample project" > README.md
git add README.md
GIT_AUTHOR_DATE="$(date -d '5 days ago' '+%Y-%m-%dT%H:%M:%S')" \
GIT_COMMITTER_DATE="$(date -d '5 days ago' '+%Y-%m-%dT%H:%M:%S')" \
  git commit -qm "first commit on main"
git checkout -qb old-feature
echo "old work" > old.txt
git add old.txt
GIT_AUTHOR_DATE="$(date -d '200 days ago' '+%Y-%m-%dT%H:%M:%S')" \
GIT_COMMITTER_DATE="$(date -d '200 days ago' '+%Y-%m-%dT%H:%M:%S')" \
  git commit -qm "old feature work"
git checkout -q main
git checkout -qb docs-update
echo "docs" > docs.txt
git add docs.txt
GIT_AUTHOR_DATE="$(date -d '31 days ago' '+%Y-%m-%dT%H:%M:%S')" \
GIT_COMMITTER_DATE="$(date -d '31 days ago' '+%Y-%m-%dT%H:%M:%S')" \
  git commit -qm "docs update"
git checkout -q main
echo "Sample repo built at $SAMPLE_DIR"
