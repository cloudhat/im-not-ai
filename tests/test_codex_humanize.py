"""Codex single-call path의 경로·detector·산출물 회귀 테스트."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_HERE = Path(__file__).absolute().parent
_ROOT = _HERE.parent
_SCRIPTS = _ROOT / "scripts"
_SKILL = _ROOT / "codex" / "skills" / "humanize-korean" / "SKILL.md"
_FIXTURES = _HERE / "fixtures"

sys.path.insert(0, str(_SCRIPTS))
from detection_registry import DETECTOR_BY_ID, DetectionContext  # noqa: E402
from verify_change_rate import evaluate_change_rate  # noqa: E402


def _run(script: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPTS / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


class CodexRuntimePathTests(unittest.TestCase):
    def test_declared_runtime_paths_open_from_skill_directory(self) -> None:
        text = _SKILL.read_text(encoding="utf-8")
        contract = text.split("## 경로 계약", 1)[1].split("## 철칙", 1)[0]
        declared = re.findall(r"^- `([^`]+)`$", contract, re.MULTILINE)
        self.assertEqual(
            declared,
            [
                "references/quick-rules.md",
                "references/s3-rules.md",
                "../../../scripts/prepare_codex_humanize.py",
                "../../../scripts/finalize_codex_humanize.py",
            ],
        )
        for relative in declared:
            with self.subTest(relative=relative):
                path = _SKILL.parent / relative
                with path.open("rb") as file:
                    self.assertTrue(file.read(1))


class DetectionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(
            (_FIXTURES / "detection_cases.json").read_text(encoding="utf-8")
        )

    def test_every_detector_has_deterministic_positive_and_negative_cases(self) -> None:
        cases = self.fixture["cases"]
        self.assertEqual(list(cases), list(DETECTOR_BY_ID))
        for pattern_id, detector in DETECTOR_BY_ID.items():
            case = cases[pattern_id]
            context = DetectionContext(
                genre=case.get("genre", "리포트"),
                translated=case.get("translated", False),
            )
            with self.subTest(pattern_id=pattern_id, kind="positive"):
                first = detector.detect(case["text"], context)
                second = detector.detect(case["text"], context)
                self.assertEqual(first, second)
                self.assertEqual(len(first), case["count"])
            with self.subTest(pattern_id=pattern_id, kind="negative"):
                self.assertEqual(detector.detect(self.fixture["negative"], context), [])


class CodexSingleCallTests(unittest.TestCase):
    def test_fixture_preserves_input_and_creates_deterministic_final(self) -> None:
        fixture_dir = _FIXTURES / "codex_humanize"
        source_bytes = (fixture_dir / "input.md").read_bytes()
        draft_text = (fixture_dir / "draft.md").read_text(encoding="utf-8").rstrip()

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "source.md"
            source.write_bytes(source_bytes)

            prepared = _run(
                "prepare_codex_humanize.py",
                ["--input-file", str(source)],
                work,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            paths = json.loads(prepared.stdout)
            run_dir = Path(paths["run_dir"])
            input_path = Path(paths["input_path"])
            draft_path = Path(paths["draft_path"])
            review_path = Path(paths["review_path"])

            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertEqual(source.read_bytes(), source_bytes)
            shutil.copyfile(fixture_dir / "draft.md", draft_path)
            shutil.copyfile(fixture_dir / "review.json", review_path)

            reporter_args = [
                "--before",
                str(input_path),
                "--after",
                str(draft_path),
                "--genre",
                "리포트",
            ]
            first_report = _run("report_detection_counts.py", reporter_args, work)
            second_report = _run("report_detection_counts.py", reporter_args, work)
            self.assertEqual(first_report.returncode, 0, first_report.stderr)
            self.assertEqual(second_report.returncode, 0, second_report.stderr)
            self.assertEqual(first_report.stdout, second_report.stdout)
            report = json.loads(first_report.stdout)
            self.assertEqual(report["before"]["by_id"]["A-1"], 1)
            self.assertEqual(report["before"]["by_id"]["A-7"], 1)
            self.assertEqual(report["before"]["by_id"]["C-5"], 1)
            self.assertEqual(report["after"]["by_id"]["A-1"], 0)
            self.assertEqual(report["after"]["by_id"]["A-7"], 0)
            self.assertEqual(report["after"]["by_id"]["C-5"], 0)

            finalized = _run(
                "finalize_codex_humanize.py",
                ["--run-dir", str(run_dir), "--genre", "리포트"],
                work,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            result = json.loads(finalized.stdout)
            expected_rate = round(
                evaluate_change_rate(source_bytes.decode("utf-8"), draft_text)[0] * 100,
                1,
            )
            self.assertEqual(result["change_rate"], expected_rate)
            self.assertGreater(result["change_rate"], 50.0)
            self.assertEqual(result["grade"], "D")
            self.assertIsNotNone(result["warning"])
            self.assertFalse(result["original_updated"])
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(input_path.read_bytes(), source_bytes)
            self.assertEqual(
                {path.name for path in run_dir.iterdir()},
                {"01_input.md", "final.md"},
            )
            final_text = Path(result["final_path"]).read_text(encoding="utf-8")
            self.assertTrue(final_text.startswith(f"{draft_text}\n\n"))
            self.assertIn("<!-- HUMANIZE-SUMMARY v2", final_text)
            self.assertIn("  A: 2 -> 0", final_text)
            self.assertIn("  C: 1 -> 0", final_text)


if __name__ == "__main__":
    unittest.main()
