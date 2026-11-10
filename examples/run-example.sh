#!/bin/sh
# Run the checker on the bundled sample repo and show the report.
# The checker exits 1 because the sample repo has a stale branch;
# that is the point of the example, so this script exits 0.
cd "$(dirname "$0")/.." || exit 2
sh examples/make-sample-repo.sh
echo "--- default limit (90 days) ---"
python3 src/git_branch_age_checker.py "${TMPDIR:-/tmp}/branch-age-sample-repo" || true
echo "--- limit 30 days ---"
python3 src/git_branch_age_checker.py --max-age-days 30 "${TMPDIR:-/tmp}/branch-age-sample-repo" || true
