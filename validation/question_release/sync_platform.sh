#!/usr/bin/env bash
set -euo pipefail
commit=${1:?Pass the exact approved question commit}
test "${#commit}" -eq 40
git cat-file -e "$commit^{commit}"
test -z "$(git status --porcelain)" || { echo 'STOP: save existing work; workspace is not clean'; exit 1; }
case "$(git remote get-url origin)" in
  https://github.com/cpoct-hlo/*) ;;
  *) echo 'STOP: origin is not the expected platform repository'; exit 1 ;;
esac
test "$(git branch --show-current)" = main || { echo 'STOP: expected platform main branch'; exit 1; }
git fetch origin main
git merge --ff-only origin/main
before_workflows=$(git ls-tree HEAD -- .github)
before_data=$(git ls-tree -r HEAD -- environment/data)
paths=(.gitattributes README.md instruction.md agent_prompt.txt task.toml
       environment/Dockerfile environment/app environment/bin environment/packet
       solution tests validation/question_release validation/eb032_platform)
git restore --source="$commit" --staged --worktree -- "${paths[@]}"
git rm -r --ignore-unmatch -- environment/Makefile environment/src environment/upstream
git rm -r --ignore-unmatch -- validation/ddi030_platform validation/ddi031_platform validation/ddi032_platform validation/ddi031_diagnostics validation/dual_platform review
git -c core.whitespace=-blank-at-eof,cr-at-eol diff --cached --check
git diff --cached --exit-code -- .github environment/data
test "$(git ls-tree "$(git write-tree)" -- .github)" = "$before_workflows"
test "$(git ls-tree -r "$(git write-tree)" -- environment/data)" = "$before_data"
git diff --exit-code "$commit" -- "${paths[@]}"
python3 validation/question_release/preflight.py
git status --short
echo "STAGED_OK: source=$commit; platform workflow and original data retained"
echo 'Inspect the staged changes, then commit/push the platform main yourself. This command did not submit or trigger platform evaluation.'
