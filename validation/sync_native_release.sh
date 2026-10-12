#!/bin/bash
# Run inside the TalentsAI Linux IDE after reviewing the pinned personal commit.
set -euo pipefail

approved="${1:?Pass the full 40-character approved personal-repo commit SHA}"
if [[ ! "$approved" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: expected a full lowercase Git commit SHA" >&2
  exit 1
fi

cd /home/workspace/project
test "$(git rev-parse --show-toplevel)" = /home/workspace/project
test -z "$(git status --porcelain)" || { echo "STOP: workspace is not clean" >&2; exit 1; }
case "$(git remote get-url origin)" in
  https://github.com/cpoct-hlo/229--224559|https://github.com/cpoct-hlo/229--224559.git) ;;
  *) echo "STOP: platform origin is not the expected repository" >&2; exit 1 ;;
esac

personal=https://github.com/Doerrrr/229--217673.git
if git remote get-url myrepo >/dev/null 2>&1; then
  test "$(git remote get-url myrepo)" = "$personal" || {
    echo "STOP: myrepo points somewhere unexpected" >&2; exit 1;
  }
else
  git remote add myrepo "$personal"
fi

git fetch origin main
git fetch myrepo main
test "$(git rev-parse myrepo/main)" = "$approved" || {
  echo "STOP: personal main is not the approved commit" >&2; exit 1;
}
git switch main
git merge --ff-only origin/main
test -z "$(git status --porcelain)" || { echo "STOP: platform main is not clean" >&2; exit 1; }

workflow_before="$(git hash-object .github/workflows/harbor-validation.yml)"
declare -A asset_before
for name in drug_list.csv DDI_event.csv newddi.csv; do
  asset_before["$name"]="$(sha256sum "environment/data/$name" | cut -d' ' -f1)"
done

git restore --source="$approved" --staged --worktree -- \
  README.md instruction.md task.toml environment solution tests

test "$(git hash-object .github/workflows/harbor-validation.yml)" = "$workflow_before" || {
  echo "STOP: platform workflow changed" >&2; exit 1;
}
for name in drug_list.csv DDI_event.csv newddi.csv; do
  after="$(sha256sum "environment/data/$name" | cut -d' ' -f1)"
  test "$after" = "${asset_before[$name]}" || {
    echo "STOP: original CSV changed: $name" >&2; exit 1;
  }
done
git diff --cached --quiet -- .github/workflows/harbor-validation.yml \
  environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv || {
  echo "STOP: protected files are staged" >&2; exit 1;
}
git diff --cached --quiet "$approved" -- \
  README.md instruction.md task.toml environment solution tests || {
  echo "STOP: staged task differs from the approved commit" >&2; exit 1;
}
git diff --cached --check
git diff --cached --name-status
git commit -m "Publish versioned DDI evidence library task"
git push origin HEAD:main
test -z "$(git status --porcelain)" || { echo "STOP: unexpected local changes after push" >&2; exit 1; }
echo "SYNC_OK: $(git rev-parse HEAD)"
