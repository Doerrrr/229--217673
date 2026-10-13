#!/bin/bash
# Review, then run inside the TalentsAI Linux IDE. No workflow import.
set -euo pipefail
approved="${1:?Pass the full approved personal commit SHA}"
[[ "$approved" =~ ^[0-9a-f]{40}$ ]] || { echo 'STOP: invalid SHA' >&2; exit 1; }
cd /home/workspace/project
test "$(git rev-parse --show-toplevel)" = /home/workspace/project
test -z "$(git status --porcelain)" || { echo 'STOP: workspace has uncommitted edits' >&2; exit 1; }
platform_url="$(git remote get-url origin)"
[[ "$platform_url" =~ ^https://github\.com/cpoct-hlo/229--[0-9]+(\.git)?$ ]] || {
  echo "STOP: unexpected platform origin: $platform_url" >&2; exit 1;
}
echo "Platform target: $platform_url"
personal=https://github.com/Doerrrr/229--217673.git
if git remote get-url myrepo >/dev/null 2>&1; then
  case "$(git remote get-url myrepo)" in
    https://github.com/Doerrrr/229--217673|https://github.com/Doerrrr/229--217673.git) ;;
    *) echo 'STOP: unexpected myrepo URL' >&2; exit 1 ;;
  esac
else
  git remote add myrepo "$personal"
fi
git fetch origin main:refs/remotes/origin/main
git fetch myrepo submission/ddi-symbolic-platform-20261013:refs/remotes/myrepo/ddi008-platform
test "$(git rev-parse myrepo/ddi008-platform)" = "$approved" || {
  echo 'STOP: remote source no longer equals approved SHA' >&2; exit 1;
}
git switch main
git merge --ff-only origin/main
test -z "$(git status --porcelain)" || { echo 'STOP: main not clean' >&2; exit 1; }

# Compare no workflow bytes across repos; preserve the platform version exactly.
workflow=.github/workflows/harbor-validation.yml
workflow_before=ABSENT
if git cat-file -e "HEAD:$workflow" 2>/dev/null; then
  workflow_before="$(git rev-parse "HEAD:$workflow")"
fi
protected=()
for name in drug_list.csv DDI_event.csv newddi.csv; do
  path="environment/data/$name"
  if git cat-file -e "HEAD:$path" 2>/dev/null; then protected+=("$path"); fi
done
git restore --source="$approved" --staged --worktree -- \
  .gitattributes README.md instruction.md task.toml environment solution tests
if ((${#protected[@]})); then
  git restore --source=HEAD --staged --worktree -- "${protected[@]}"
fi
git diff --cached --quiet -- .github || { echo 'STOP: workflow staged' >&2; exit 1; }
if ((${#protected[@]})); then
  git diff --cached --quiet -- "${protected[@]}" || { echo 'STOP: original CSV staged' >&2; exit 1; }
fi
workflow_after=ABSENT
if git cat-file -e ":$workflow" 2>/dev/null; then workflow_after="$(git rev-parse ":$workflow")"; fi
test "$workflow_before" = "$workflow_after" || { echo 'STOP: workflow changed' >&2; exit 1; }
git diff --cached --quiet "$approved" -- \
  .gitattributes README.md instruction.md task.toml environment solution tests \
  ':(exclude)environment/data/drug_list.csv' \
  ':(exclude)environment/data/DDI_event.csv' \
  ':(exclude)environment/data/newddi.csv' || { echo 'STOP: task differs from approved source' >&2; exit 1; }
git diff --cached --check
git diff --cached --name-status
if git diff --cached --quiet; then
  echo 'DDI-008 task already synchronized; no duplicate commit.'
else
  git commit -m 'Publish DDI-008 symbolic lineage with validated Oracle'
fi
git push origin HEAD:main
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git ls-remote origin refs/heads/main | cut -f1)"
test "$local_sha" = "$remote_sha" || { echo 'STOP: remote SHA differs' >&2; exit 1; }
test -z "$(git status --porcelain)" || { echo 'STOP: workspace not clean' >&2; exit 1; }
echo "SYNC_OK: DDI-008 source=$approved platform=$local_sha; platform workflow preserved"
