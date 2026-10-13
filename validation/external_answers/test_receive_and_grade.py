"""Operator-tool tests; never label these fixtures as external model answers."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
import zipfile

import receive_and_grade as tool

DELIVERABLES = Path(__file__).resolve().parents[4] / "deliverables"
SYMBOLIC = DELIVERABLES / "ddi_symbolic_lineage_20261013"
FROZEN = SYMBOLIC / "frozen_v01_r1"
CONTROLS = SYMBOLIC / "quality_frozen_v01_r1"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ddi-intake-unit-")
        self.root = Path(self.temp.name)
        self.private, self.manifest = tool.verify_frozen(FROZEN)
        self.control = CONTROLS / "nop"
        self.metadata = {
            "origin": "author_control", "session_id": "unit-control", "model": "not-a-model",
            "model_version": "not-applicable", "first_answer": False,
            "independent_session": False, "feedback_before_freeze": True,
            "completion_status": "completed", "started_at": "2026-10-13T01:00:00+00:00",
            "frozen_at": "2026-10-13T01:30:00+00:00", "environment_waits": [],
            "evidence_note": "Synthetic operator-tool control, not external answer",
        }

    def tearDown(self):
        self.temp.cleanup()

    def metadata_qualified_fixture(self):
        metadata = deepcopy(self.metadata)
        metadata.update(origin="external_agent", first_answer=True, independent_session=True,
                        feedback_before_freeze=False)
        return metadata

    def intake(self, record_id="control", metadata=None):
        meta = self.root / (record_id + ".json")
        tool.write_new(meta, metadata or self.metadata)
        args = SimpleNamespace(frozen=FROZEN, root=self.root / "records", record_id=record_id,
                               answer=self.control / "answer.zip", metadata=meta)
        tool.receive(args)
        return args.root / record_id

    def add_existing_control_grade(self, record):
        grade = record / "grade"
        grade.mkdir()
        shutil.copyfile(self.control / "result.json", grade / "result.json")
        (grade / "verifier").mkdir()
        shutil.copyfile(self.control / "verifier/details.json", grade / "verifier/details.json")
        tool.write_new(record / "grade_receipt.json", {
            "status": "completed", "reward": 0.0, "record_sha256": tool.sha(record / "record.json"),
            "evidence_sha256": {name: tool.sha(record / name) for name in
                                ("grade/result.json", "grade/verifier/details.json")},
            "started_at": "2026-10-13T04:00:00+00:00",
            "finished_at": "2026-10-13T04:01:00+00:00",
        })

    def test_intake_preserves_original_bytes(self):
        before = tool.sha(self.control / "answer.zip")
        record = self.intake()
        self.assertEqual(tool.sha(record / "answer.zip"), before)
        self.assertEqual(tool.sha(self.control / "answer.zip"), before)
        self.assertTrue(tool.load_record(record)["qualification_reasons"])

    def test_intake_refuses_overwrite(self):
        record = self.intake()
        before = tool.sha(record / "record.json")
        with self.assertRaises(FileExistsError):
            self.intake()
        self.assertEqual(tool.sha(record / "record.json"), before)

    def test_author_control_is_not_qualified(self):
        reasons, _ = tool.metadata_reasons(self.metadata)
        self.assertTrue(any("origin" in reason for reason in reasons))

    def test_unknown_metadata_not_assumed_eligible(self):
        template = tool.read_json(Path(__file__).with_name("metadata_template.json"))
        reasons, _ = tool.metadata_reasons(template)
        self.assertGreaterEqual(len(reasons), 6)

    def test_valid_metadata_and_budget_boundary(self):
        data = self.metadata_qualified_fixture()
        data["frozen_at"] = "2026-10-13T02:00:00+00:00"
        self.assertEqual(tool.metadata_reasons(data), ([], 3600.0))
        data["frozen_at"] = "2026-10-13T02:00:01+00:00"
        self.assertTrue(tool.metadata_reasons(data)[0])

    def test_boolean_claims_are_not_integer_flags(self):
        data = self.metadata_qualified_fixture()
        data["first_answer"] = 1
        self.assertTrue(tool.metadata_reasons(data)[0])

    def test_time_needs_timezone(self):
        with self.assertRaises(ValueError):
            tool.timestamp("2026-10-13T01:00:00")

    def test_documented_wait_intervals(self):
        data = self.metadata_qualified_fixture()
        data["environment_waits"] = [{"started_at": "2026-10-13T01:01:00+00:00",
                                      "ended_at": "2026-10-13T01:11:00+00:00", "reason": "setup wait"}]
        self.assertEqual(tool.metadata_reasons(data), ([], 1200.0))
        data["environment_waits"].append(deepcopy(data["environment_waits"][0]))
        self.assertTrue(tool.metadata_reasons(data)[0])

    def test_zip_boundary_rejections(self):
        cases = {"traversal": "app/../../escape.py", "hidden": "tests/test_outputs.py",
                 "duplicate": "app/lineage.py", "symlink": "app/link.py",
                 "windows_drive": "app/C:escape.py", "backslash": "app\\escape.py"}
        for kind, extra in cases.items():
            with self.subTest(kind=kind), warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive_path = self.root / (kind + ".zip")
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("app/lineage.py", "pass\n")
                    archive.writestr("answer_notes.md", "synthetic boundary control\n")
                    entry = zipfile.ZipInfo(extra)
                    # ZipInfo normalizes OS separators on Windows; preserve a
                    # deliberately malformed archive name for this test.
                    entry.filename = entry.orig_filename = extra
                    entry.create_system = 3
                    entry.external_attr = ((stat.S_IFLNK if kind == "symlink" else stat.S_IFREG) | 0o644) << 16
                    archive.writestr(entry, "pass\n")
                with self.assertRaises(ValueError):
                    tool.validate_answer(archive_path)

    def test_changed_answer_is_rejected(self):
        record = self.intake()
        with (record / "answer.zip").open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "Stored answer changed"):
            tool.load_record(record)

    def test_changed_unpacked_manifest_is_rejected(self):
        copied = self.root / "frozen"
        copied.mkdir()
        checksums = tool.read_json(FROZEN / "checksums.json")
        shutil.copyfile(FROZEN / "checksums.json", copied / "checksums.json")
        for role in ("candidate", "private"):
            shutil.copyfile(FROZEN / checksums[role]["file"], copied / checksums[role]["file"])
        shutil.copytree(self.private, copied / self.private.name)
        path = copied / self.private.name / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "manifest differs"):
            tool.verify_frozen(copied)

    def test_all_four_real_control_receipts_recompute(self):
        expected = {"positive_known_fixtures": 1.0, "nop": 0.0,
                    "bad_probability": 0.8, "bad_minimal": 0.45}
        for name, reward in expected.items():
            with self.subTest(control=name):
                folder = CONTROLS / name
                result = tool.read_json(folder / "result.json")
                details = tool.read_json(folder / "verifier/details.json")
                record = {**tool.TASK, "answer_sha256": tool.sha(folder / "answer.zip")}
                self.assertEqual(tool.summarize_result(result, details, record, self.manifest)["reward"], reward)

    def test_bare_score_missing_checks_is_rejected(self):
        result = tool.read_json(self.control / "result.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        with self.assertRaises(ValueError):
            tool.summarize_result(result, {"status": "completed", "reward": 0}, record, self.manifest)

    def test_infrastructure_failure_cannot_be_zero(self):
        result = tool.read_json(self.control / "result.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        result.update(status="infrastructure_error", reward=None)
        self.assertIsNone(tool.summarize_result(result, {}, record, self.manifest)["reward"])
        result["reward"] = 0
        with self.assertRaises(ValueError):
            tool.summarize_result(result, {}, record, self.manifest)

    def test_oom_or_running_container_is_rejected(self):
        result = tool.read_json(self.control / "result.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        details = tool.read_json(self.control / "verifier/details.json")
        for key in ("OOMKilled", "Running"):
            bad = deepcopy(result)
            bad["container_state"][key] = True
            with self.assertRaises(ValueError):
                tool.summarize_result(bad, details, record, self.manifest)

    def test_changed_check_weight_is_rejected(self):
        result = tool.read_json(self.control / "result.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        details = tool.read_json(self.control / "verifier/details.json")
        details["checks"][0]["weight"] = 0.01
        with self.assertRaises(ValueError):
            tool.summarize_result(result, details, record, self.manifest)

    def test_duplicate_check_is_rejected(self):
        result = tool.read_json(self.control / "result.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        details = tool.read_json(self.control / "verifier/details.json")
        details["checks"][1] = deepcopy(details["checks"][0])
        with self.assertRaises(ValueError):
            tool.summarize_result(result, details, record, self.manifest)

    def test_exact_seventy_percent_boundary_has_no_rounding_downgrade(self):
        result = tool.read_json(self.control / "result.json")
        details = tool.read_json(self.control / "verifier/details.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        for count in (14, 15):
            for index, check in enumerate(details["checks"]):
                check["passed"] = index < count
            result["reward"] = details["reward"] = count / 20
            result["passed_checks"] = details["passed_checks"] = count
            summary = tool.summarize_result(result, details, record, self.manifest)
            self.assertEqual(summary["reward"], count / 20)
            self.assertEqual(summary["reward"] <= 0.7, count == 14)

    def test_wrong_task_receipt_is_rejected(self):
        result = tool.read_json(self.control / "result.json")
        details = tool.read_json(self.control / "verifier/details.json")
        record = {**tool.TASK, "answer_sha256": result["answer_sha256"]}
        result["version"] = "v02"
        with self.assertRaisesRegex(ValueError, "does not belong"):
            tool.summarize_result(result, details, record, self.manifest)

    def test_two_low_author_controls_do_not_complete_goal(self):
        records = [self.intake("control1"), self.intake("control2")]
        for record in records:
            self.add_existing_control_grade(record)
        out = self.root / "audit.json"
        tool.audit(SimpleNamespace(frozen=FROZEN, records=records, out=out))
        result = tool.read_json(out)
        self.assertEqual(result["status"], "INSUFFICIENT_QUALIFIED_EVIDENCE")
        self.assertFalse(result["goal_complete"])
        self.assertFalse(result["formal_platform_t1"])

    def test_stored_grading_evidence_cannot_change(self):
        record = self.intake()
        self.add_existing_control_grade(record)
        with (record / "grade/result.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "Grading evidence changed"):
            tool.audit(SimpleNamespace(frozen=FROZEN, records=[record], out=self.root / "audit.json"))

    def test_grade_adapter_preserves_normal_control_score(self):
        record = self.intake()
        def stub_frozen_grader(command, **kwargs):
            self.assertEqual(Path(command[1]), self.private / "evaluate.py")
            self.assertIn("--docker-context", command)
            output = Path(command[command.index("--out") + 1])
            output.mkdir()
            shutil.copyfile(self.control / "result.json", output / "result.json")
            shutil.copytree(self.control / "verifier", output / "verifier")
            return SimpleNamespace(returncode=0)
        args = SimpleNamespace(frozen=FROZEN, record=record, docker_context="desktop-linux")
        with patch.object(tool.subprocess, "run", side_effect=stub_frozen_grader):
            tool.grade(args)
        receipt = tool.read_json(record / "grade_receipt.json")
        self.assertEqual((receipt["status"], receipt["reward"]), ("completed", 0.0))
        self.assertFalse(receipt["model_called"])
        with self.assertRaisesRegex(ValueError, "Already graded"):
            tool.grade(args)

    def test_grade_adapter_handles_failure_before_result_without_zero_score(self):
        record = self.intake()
        args = SimpleNamespace(frozen=FROZEN, record=record, docker_context="desktop-linux")
        with patch.object(tool.subprocess, "run", return_value=SimpleNamespace(returncode=2)):
            tool.grade(args)
        receipt = tool.read_json(record / "grade_receipt.json")
        self.assertEqual(receipt["status"], "infrastructure_error")
        self.assertIsNone(receipt["reward"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
