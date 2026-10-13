"""Freeze numbered public/operator packets; no solution or model-score leakage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

from fixtures import CHECKS

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
TASK = ROOT / "runtime_task_v01"


def digest(body):
    return hashlib.sha256(body).hexdigest()


def files_in(folder):
    return [p for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]


def zip_folder(folder, target):
    with target.open("xb") as stream, zipfile.ZipFile(stream, "w") as archive:
        for path in files_in(folder):
            assert not path.is_symlink()
            name = folder.name + "/" + path.relative_to(folder).as_posix()
            info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | (0o755 if "bin" in path.parts or path.suffix == ".sh" else 0o644)) << 16
            archive.writestr(info, path.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    assert not args.out.exists(), "Choose a fresh freeze folder"
    subprocess.run([sys.executable, str(ROOT / "preflight.py")], check=True)
    assert not subprocess.check_output(["git", "status", "--porcelain", "--", "validation/symbolic_lineage"], cwd=REPO), "Commit task source before freeze"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    for path in files_in(ROOT):
        name = path.relative_to(REPO).as_posix()
        assert subprocess.check_output(["git", "show", "HEAD:" + name], cwd=REPO) == path.read_bytes(), "Working bytes differ: " + name
    task_files = {p.relative_to(TASK).as_posix(): digest(p.read_bytes()) for p in files_in(TASK)}
    task_digest = digest(json.dumps(task_files, sort_keys=True, separators=(",", ":")).encode())
    public = args.out / "DDI-008_v01_candidate"
    private = args.out / "DDI-008_v01_evaluator_private"
    public.mkdir(parents=True)
    private.mkdir()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(TASK / "environment", public / "environment", ignore=ignore)
    shutil.copyfile(TASK / "instruction.md", public / "instruction.md")
    shutil.copyfile(ROOT / "public_pack_answer.py", public / "pack_answer.py")
    (public / "answer_notes.md").write_text(
        "# First answer metadata\n\n- Displayed model/version: unknown\n- Start UTC / freeze UTC:\n"
        "- Environment-only waits (with evidence):\n- Completed / timeout / infrastructure error:\n"
        "- Builds and own tests actually run:\n- Known omissions:\n"
        "- Prior answers, hidden tests or related repository history accessed: no\n",
        encoding="utf-8", newline="\n")
    (public / "start_here.md").write_text(
        "# DDI-008 v01\n\nRead instruction.md completely. Repair only Python sources in environment/app.\n"
        "Build with `docker build -t ddi-008-local environment`; an example command is\n"
        "`docker run --rm ddi-008-local ddi-lineage --input /data/evidence_graph.json --out-dir /output`.\n"
        "Run the stress_graph.json input as well. To inspect output use a disposable container\n"
        "and docker cp, or a dedicated output directory mount. Do not repair host Docker/WSL services.\n"
        "If Docker is unavailable, Python 3.11 can execute environment/app/lineage.py directly\n"
        "with the same arguments and explicit local input/output paths; record this limitation.\n\n"
        "No hidden evaluator, reference solver or earlier answer is included. Do not browse\n"
        "related Git repositories or unrelated local projects for a solution.\n"
        "Use a fresh conversation and independent directory. Freeze one first answer within\n"
        "3600 seconds of coding, excluding separately recorded environment-only waiting.\n"
        "Complete answer_notes.md and run `python pack_answer.py --out answer.zip`. Return\n"
        "the original ZIP and its hash; do not incorporate grader feedback into this first answer.\n\n"
        f"Frozen source commit: {commit}\nTask digest: {task_digest}\n",
        encoding="utf-8", newline="\n")
    (public / "agent_prompt.txt").write_text(
        "Please solve the attached DDI-008 v01 task in a fresh workspace. Read instruction.md\n"
        "and start_here.md fully, implement the required behavior and test it independently.\n"
        "Use only this public packet and ordinary language/runtime documentation, not hidden\n"
        "evaluators, related repository history or prior answers. Do not change task inputs,\n"
        "launcher or dependencies. Work within the 3600-second coding budget and record\n"
        "actual model/version, coding start/freeze times, environment waits and tests.\n"
        "Return the first immutable answer.zip from pack_answer.py, not only a plan or outputs.\n",
        encoding="utf-8", newline="\n")
    public_files = {p.relative_to(public).as_posix(): digest(p.read_bytes()) for p in files_in(public)}
    (public / "public_manifest.json").write_text(json.dumps({
        "task_id": "DDI-008", "version": "v01", "task_commit": commit, "task_digest": task_digest,
        "agent_budget_sec": 3600, "files": public_files}, indent=2) + "\n", encoding="utf-8", newline="\n")
    shutil.copytree(TASK, private / "task", ignore=ignore)
    shutil.copyfile(ROOT / "frozen_evaluator.py", private / "evaluate.py")
    (private / "README_评分操作.md").write_text(
        "# DDI-008 v01 私有评分包\n\n不要发给作答模型。先封存两份独立首答，再运行评分。\n"
        "需要可运行的 Linux Docker 引擎；不要为此脚本修改宿主服务。\n\n"
        "```bash\npython evaluate.py --answer /path/to/answer.zip --out /path/to/fresh_score_directory\n```\n\n"
        "Windows 的 Docker Desktop 可追加 `--docker-context desktop-linux`。输出目录必须不存在。\n"
        "脚本核对冻结文件，安装答卷到公开应用目录，在无网络的新容器里按规则评分。\n"
        "不调用任何模型，不导入参考解；候选进程使用 UID/GID 10001，不能读隐藏 tests 或 reward。\n"
        "保存 result.json、verifier/details.json、container_id.txt 和原答卷哈希。\n"
        "运行异常、OOM、缺少分数与正常低分分开记录。模型首答和用时资格需要另附证据。\n\n"
        "这是外部本地试验包，没有完整生产 Oracle 解，不可当作已通过 Harbor/TalentsAI 的平台提交包。\n",
        encoding="utf-8", newline="\n")
    private_files = {p.relative_to(private).as_posix(): digest(p.read_bytes()) for p in files_in(private)}
    (private / "manifest.json").write_text(json.dumps({
        "task_id": "DDI-008", "version": "v01", "task_commit": commit, "task_digest": task_digest,
        "agent_budget_sec": 3600, "verifier_budget_sec": 3600,
        "checks": [{"name": name, "section": section, "weight": weight} for name, section, weight in CHECKS],
        "files": private_files, "general_oracle_solution": False}, indent=2) + "\n", encoding="utf-8", newline="\n")
    public_name = f"DDI-008_符号化证据来源与精确可靠性_v01_作答包_{commit[:7]}.zip"
    private_name = f"DDI-008_符号化证据来源与精确可靠性_v01_评分包_{commit[:7]}.zip"
    zip_folder(public, args.out / public_name)
    zip_folder(private, args.out / private_name)
    result = {"task_id": "DDI-008", "version": "v01", "task_commit": commit,
              "task_digest": task_digest, "checks": 20,
              "candidate": {"file": public_name, "sha256": digest((args.out / public_name).read_bytes())},
              "private": {"file": private_name, "sha256": digest((args.out / private_name).read_bytes())},
              "external_answer_scores": [], "general_oracle_solution": False, "platform_validated": False}
    (args.out / "checksums.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
