#!/usr/bin/env python3
"""Create readable, numbered copies without changing frozen packet bytes.

This is an inventory/packaging operation, not a task run or model evaluation.
Never replace an existing numbered archive with different bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def expected_hash(data: dict, role: str) -> str:
    name = "ddi_candidate.zip" if role == "candidate" else "ddi_evaluator_private.zip"
    if name in data:
        return data[name]["sha256"]
    if role in data:
        return data[role]["sha256"]
    return data["candidate_zip_sha256" if role == "candidate" else "private_zip_sha256"]


def inspect_zip(path: Path, public: bool) -> int:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"Corrupt ZIP entry: {path}: {bad}")
        files = [entry for entry in archive.infolist() if not entry.is_dir()]
        for entry in files:
            parts = Path(entry.filename.replace("\\", "/")).parts
            if entry.filename.startswith("/") or ".." in parts:
                raise ValueError(f"Unsafe ZIP path: {path}: {entry.filename}")
            if public and (
                any(part in {"solution", "tests", ".git", "__pycache__"} for part in parts)
                or "answer.zip" in parts
                or "ddi_evaluator_private.zip" in parts
            ):
                raise ValueError(f"Private/answer entry in public packet: {entry.filename}")
        return len(files)


def copy_frozen(source: Path, destination: Path, expected: str, public: bool) -> dict:
    actual = sha256(source)
    if actual != expected:
        raise ValueError(f"Frozen source hash mismatch: {source}")
    entries = inspect_zip(source, public=public)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256(destination) != actual:
            raise ValueError(f"Refusing to overwrite changed numbered archive: {destination}")
    else:
        shutil.copy2(source, destination)
    if sha256(destination) != actual:
        raise ValueError(f"Copied archive mismatch: {destination}")
    return {"source": str(source), "file": destination.name,
            "sha256": actual, "bytes": destination.stat().st_size,
            "zip_file_entries": entries, "byte_identical_to_original": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deliverables", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    registry = json.loads(Path(__file__).with_name("registry.json").read_text(encoding="utf-8"))
    root = args.deliverables.resolve(strict=True)
    out = args.out_dir.resolve()
    if not out.is_relative_to(root) or out == root:
        raise ValueError("Output must be a dedicated subdirectory of deliverables")
    public_dir = out / "公开作答包_只选一份发给模型"
    private_dir = out / "私有评分包_不要发给作答模型"
    backups_dir = out / "恢复备份_不计入新题"
    rows = []
    for task in registry["tasks"]:
        source = root / task["source"]
        checksums = json.loads((source / "checksums.json").read_text(encoding="utf-8"))
        commit = checksums["task_commit"]
        stem = f'{task["id"]}_{task["title"]}_{task["version"]}'
        public_name = f"{stem}_作答包_{commit[:7]}.zip"
        private_name = f"{stem}_评分包_{commit[:7]}.zip"
        public_source = checksums.get("candidate", {}).get("file", "ddi_candidate.zip")
        private_source = checksums.get("private", {}).get("file", "ddi_evaluator_private.zip")
        public = copy_frozen(source / public_source, public_dir / public_name,
                             expected_hash(checksums, "candidate"), public=True)
        private = copy_frozen(source / private_source, private_dir / private_name,
                              expected_hash(checksums, "private"), public=False)
        rows.append({**task, "task_commit": commit, "task_digest": checksums["task_digest"],
                     "candidate": public, "evaluator_private": private})
    backups = []
    for backup in registry["restoration_backups"]:
        name = f'{backup["id"]}_{backup["title"]}_{backup["version"]}_恢复包_{backup["commit"][:7]}.zip'
        record = copy_frozen(root / backup["source"], backups_dir / name,
                             backup["sha256"], public=False)
        backups.append({**backup, "archive": record})
    manifest = {"schema_version": 1, "catalog_date": registry["catalog_date"],
                "counting_rule": registry["counting_rule"],
                "complete_tasks": len(rows),
                "new_after_abc_external_campaign": sum(t["after_abc_external_campaign"] for t in rows),
                "task_archive_copies": len(rows) * 2,
                "tasks": rows, "reserved_drafts": registry["reserved_drafts"],
                "restoration_backups": backups,
                "executed_task_tests": False, "spawned_answer_agents": False,
                "platform_detection_triggered": False}
    complete = len(rows)
    newer = sum(t["after_abc_external_campaign"] for t in rows)
    latest = sum(t.get("after_latest_external_agent_choice", False) for t in rows)
    copies = complete * 2 + len(backups)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8", newline="\n")
    lines = ["# DDI 编号题包目录", "", "清点日期：2026-10-13。此目录给委托人使用，不要整目录交给作答模型。", "",
             "## 数量与范围", "",
             f"- 上次 A/B/C 三份外部题包之后：新增 {newer} 道已打包题，具体题号见下表。",
             f"- 累计：{complete} 道已打包题，另有 {len(registry['reserved_drafts'])} 道登记草稿。",
             f"- 若以最近一次选择‘后续由外部 agent 作答’为起点：之后新增 {latest} 道。",
             f"- 每题含公开作答包和私有评分包，因此有 {complete * 2} 个题目 ZIP 副本，不是 {complete * 2} 道题。",
             "- 旧版恢复备份 BACKUP-001、答卷、重复复制及同题安装器修订不计为新题。",
             "- 本目录只整理此前的外部测试题包系列，不是整个项目从最早版本开始的全部平台版本。", "",
             "## 完整题包", "", "| 题号 | 名称 | 旧标号 | 目录版本 | 题包提交 |",
             "| --- | --- | --- | --- | --- |"]
    for task in rows:
        lines.append(f'| {task["id"]} | {task["title"]} | {task["legacy_id"] or "—"} | {task["version"]} | `{task["task_commit"][:7]}` |')
    lines += ["", "DDI-008 已冻结外部本地试验包，但还没有外部答卷分数、完整生产 Oracle 解或平台验收。",
              "‘已打包’与‘平台可提交并通过’是不同状态；不要把本地试验包直接上传当作平台成品。", "",
              "## 文件命名与后续约定", "", "```text",
              "DDI-题号_易读题名_v版本_用途_提交短SHA.zip",
              "DDI-007_持久证据账本与崩溃恢复_v02_作答包_54fd0ac.zip",
              "DDI-007_持久证据账本与崩溃恢复_v02_评分包_54fd0ac.zip",
              "DDI-007_v02_答卷_DeepSeek_run01.zip", "```", "",
              "1. 同一题修改后保留题号，只提高版本；更换核心任务才分配新题号。",
              "2. 作答包、评分包、答卷、恢复备份分别标用途，不能混装。",
              "3. 仅外部 ZIP 文件名增加编号；原 ZIP 及包内冻结文件保持原样。",
              "4. 只把‘公开作答包’中的一份 ZIP 发给某个模型，在全新会话和独立目录作答。",
              "5. 这些旧包大多解压为 ddi_candidate，请分目录解压，不能互相覆盖。",
              "6. 回传原始答卷并标明题号、版本、模型/版本和正常完成/超时/环境错误；答卷原字节不改。",
              "7. manifest.json 记录原路径、完整 SHA、每个 ZIP 的哈希和大小，判卷须匹配题号与版本。", "",
              "## 验证范围", "", f"已核对 {copies} 个副本（{complete * 2} 个题目 ZIP、{len(backups)} 个恢复 ZIP）的 SHA-256 与原件一致；",
              f"{complete} 个公开作答包通过 ZIP 完整性及隐藏目录/历史答案边界扫描。",
              "本目录生成操作没有运行题目或模型，没有触发平台检测，也没有更改题面、权重或远端仓库。",
              "编号整理不代表本地降分目标或正式平台 T1 已通过。", ""]
    (out / "README_题包总目录.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"complete_tasks": len(rows), "new_after_abc_external_campaign": newer,
                      "draft_tasks": len(registry["reserved_drafts"]), "verified_zip_copies": copies,
                      "out_dir": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
