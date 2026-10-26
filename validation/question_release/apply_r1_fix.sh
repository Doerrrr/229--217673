#!/bin/bash
set -euo pipefail
old=${1:?Pass the original question commit}
new=${2:?Pass the exact repair commit}
test "$old" = f0e34607b5c5142a893735a11b53cc5536c26a0b
test "${#new}" -eq 40
git cat-file -e "$old^{commit}"
git cat-file -e "$new^{commit}"
git merge-base --is-ancestor "$old" "$new"
case "$(git remote get-url origin)" in
  *github.com*cpoct-hlo*228--244587*) ;;
  *) echo 'STOP: this repair is for the existing DNA question 228--244587'; exit 1 ;;
esac
test "$(git branch --show-current)" = main || { echo 'STOP: expected platform main'; exit 1; }
paths=(environment/packet/problem.md tests/common.py tests/secure_copy.py
       tests/grade.py tests/fixtures.json validation/question_release/release.json
       validation/question_release/preflight.py validation/question_release/review_form.md
       validation/question_release/apply_r1_fix.sh)
while IFS= read -r -d '' path; do
  case "$path" in
    environment/packet/problem.md|tests/common.py|tests/secure_copy.py|tests/grade.py|tests/fixtures.json|validation/question_release/release.json|validation/question_release/preflight.py|validation/question_release/review_form.md|validation/question_release/apply_r1_fix.sh) ;;
    *) echo "STOP: unexpected changed path: $path"; exit 1 ;;
  esac
done < <(git diff --name-only -z "$old" "$new")
if git diff --quiet "$new" -- "${paths[@]}" && git diff --cached --quiet "$new" -- "${paths[@]}"; then
  python3 validation/question_release/preflight.py
  echo 'ALREADY_APPLIED: repair bytes match the pinned commit'
  exit 0
fi
umask 077
backup_root=${DNA_R1_BACKUP_ROOT:-/home/workspace}
backup=$(mktemp -d "$backup_root/dna-r1-backup.XXXXXX")
git rev-parse HEAD > "$backup/head.txt"
git status --porcelain=v1 -uall > "$backup/status.txt"
git diff --binary > "$backup/unstaged.patch"
git diff --cached --binary > "$backup/staged.patch"
index_path=$(git rev-parse --git-path index)
if test -f "$index_path"; then cp -- "$index_path" "$backup/index"; fi
: > "$backup/existing-paths.z"
for path in "${paths[@]}"; do
  if test -e "$path" || test -L "$path"; then printf '%s\0' "$path" >> "$backup/existing-paths.z"; fi
done
tar -czf "$backup/affected-files.tar.gz" --null -T "$backup/existing-paths.z"
git diff --binary "$old" "$new" -- "${paths[@]}" > "$backup/repair.patch"
echo "BACKUP_OK: $backup"
if ! git diff --quiet "$old" -- "${paths[@]}" || ! git diff --cached --quiet "$old" -- "${paths[@]}"; then
  echo 'STOP: affected files contain local changes; no repair changes applied'
  git status --short
  exit 1
fi
if ! git apply --check --index "$backup/repair.patch"; then
  echo 'STOP: an affected file differs from the original release; no repair changes applied'
  git status --short
  exit 1
fi
git apply --index "$backup/repair.patch"
git -c core.whitespace=-blank-at-eof,cr-at-eol diff --cached --check -- "${paths[@]}"
git diff --exit-code "$new" -- "${paths[@]}"
git diff --cached --exit-code "$new" -- "${paths[@]}"
python3 validation/question_release/preflight.py
git diff --cached --stat -- "${paths[@]}"
echo "R1_REPAIR_STAGED_OK: source=$new; backup=$backup"
echo 'Other working-tree/index changes were preserved. Review and commit only the repair paths.'
