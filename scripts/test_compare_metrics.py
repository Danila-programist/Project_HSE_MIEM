"""Независимые от приложения проверки совместимости отчётов и CLI сравнения."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import compare_metrics as comparison


def sample_report():
    return {
        "schema_version": 1,
        "generated_at": "2026-10-06T12:00:00+00:00",
        "source": "fixture",
        "git_commit": "before",
        "analyzer_sha256": "a" * 64,
        "tools": {"python": "3.12.3", "radon": "6.0.1", "ruff": "0.16.10"},
        "methodology": {"complexity": "per function", "ruff": {"line_length": 100}},
        "summary": {
            "file_count": 1,
            "function_count": 2,
            "cyclomatic_complexity": {"average": 3, "maximum": 4},
            "maintainability_index_average": 60.0,
            "maintainability_index_file_count": 1,
            "average_file_lines": 100.0,
            "physical_lines": 100,
            "comment_lines": 20,
            "comment_density_percent": 20.0,
            "ruff_issue_count": 1,
            "ruff_issues_by_rule": {"E501": 1},
        },
        "files": [{
            "path": "fixture/example.py",
            "sha256": "b" * 64,
            "physical_lines": 100,
            "source_lines": 60,
            "logical_lines": 60,
            "comment_lines": 20,
            "comment_density_percent": 20.0,
            "maintainability_index": 60.0,
            "function_count": 2,
            "cyclomatic_complexity": {"average": 3, "maximum": 4},
            "functions": [
                {"name": "first", "line": 1, "complexity": 4},
                {"name": "second", "line": 20, "complexity": 2},
            ],
            "ruff_issues": [{"path": "fixture/example.py", "line": 1, "column": 101,
                             "code": "E501", "message": "Long line", "fix_available": False}],
        }],
    }


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write_report(self, name, report):
        path = self.root / name
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(Path(comparison.__file__).resolve()), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )

    def test_delta_precision_zero_and_metric_direction(self):
        result = comparison.delta(1.004, 1.003, "lower")
        self.assertAlmostEqual(result["absolute_change"], -0.001)
        self.assertAlmostEqual(result["percent_change"], -0.001 / 1.004 * 100)
        self.assertEqual(result["assessment"], "улучшение")
        self.assertEqual(comparison.delta(60, 70, "higher")["assessment"], "улучшение")
        self.assertEqual(comparison.delta(1, 2, "lower")["assessment"], "ухудшение")
        self.assertEqual(comparison.delta(100, 80)["assessment"], "нейтральное изменение")
        self.assertIsNone(comparison.delta(0, 1)["percent_change"])
        self.assertEqual(comparison.delta(0, 0)["percent_change"], 0)
        self.assertIsNone(comparison.delta(None, 1)["absolute_change"])

    def test_function_extraction_and_changed_hashes_are_allowed(self):
        before, after = sample_report(), sample_report()
        after["git_commit"] = "after"
        after["files"][0]["sha256"] = "c" * 64
        after["files"][0]["functions"].append({"name": "helper", "line": 40, "complexity": 3})
        after["files"][0]["function_count"] = 3
        after["summary"]["function_count"] = 3
        comparison.validate_report(before)
        comparison.validate_report(after)
        result = comparison.compare_reports(before, after)
        self.assertTrue(result["files"][0]["changed"])
        self.assertEqual(result["context"]["function_count"]["absolute_change"], 1)
        self.assertEqual(result["metrics"]["cc_average"]["absolute_change"], 0)
        self.assertEqual([item["name"] for item in result["top_functions"]["after"]],
                         ["first", "helper", "second"])

    def test_no_functions_and_no_source_have_null_cc_and_mi(self):
        report = sample_report()
        file, summary = report["files"][0], report["summary"]
        file.update(source_lines=0, logical_lines=0, functions=[], function_count=0,
                    maintainability_index=None,
                    cyclomatic_complexity={"average": None, "maximum": None})
        summary.update(function_count=0, maintainability_index_file_count=0,
                       maintainability_index_average=None,
                       cyclomatic_complexity={"average": None, "maximum": None})
        comparison.validate_report(report)
        result = comparison.compare_reports(report, report)
        self.assertIsNone(result["metrics"]["maintainability_index"]["absolute_change"])
        self.assertEqual(result["top_functions"], {"before": [], "after": []})
        self.assertEqual(result["metrics"]["file_lines"]["assessment"], "без изменений")

    def test_comparison_rejects_different_measurement_conditions(self):
        for field, value in (("schema_version", 2), ("source", "other"),
                             ("tools", {"python": "3.13"}), ("methodology", {"other": True}),
                             ("analyzer_sha256", "d" * 64)):
            with self.subTest(field=field):
                before, after = sample_report(), sample_report()
                after[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    comparison.compare_reports(before, after)
        before, after = sample_report(), sample_report()
        after["files"][0]["path"] = "fixture/renamed.py"
        with self.assertRaisesRegex(ValueError, "список путей"):
            comparison.compare_reports(before, after)

    def test_loader_rejects_missing_nan_wrong_types_and_inconsistent_summary(self):
        mutations = [
            lambda report: report.pop("summary"),
            lambda report: report.update(summary=[]),
            lambda report: report["summary"].update(average_file_lines=float("nan")),
            lambda report: report["summary"].update(ruff_issue_count=True),
            lambda report: report["summary"].update(function_count=None),
            lambda report: report["summary"].update(physical_lines=101),
            lambda report: report["files"][0].update(maintainability_index=None),
            lambda report: report["files"][0]["functions"][0].update(complexity=float("inf")),
            lambda report: report["files"].append(copy.deepcopy(report["files"][0])),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                report = sample_report()
                mutation(report)
                path = self.write_report("invalid.json", report)
                with self.assertRaisesRegex(ValueError, "Некорректный отчёт"):
                    comparison.load_report(path)

    def test_cli_outputs_six_metrics_file_details_and_json(self):
        before = self.write_report("before.json", sample_report())
        after_report = sample_report()
        after_report["files"][0]["ruff_issues"] = []
        after_report["summary"].update(ruff_issue_count=0, ruff_issues_by_rule={})
        after_report["files"][0]["sha256"] = "c" * 64
        after = self.write_report("after.json", after_report)
        output = self.root / "new" / "comparison.json"
        result = self.cli(before, after, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(report["metrics"]), 6)
        self.assertEqual(report["metrics"]["ruff_issues"]["percent_change"], -100)
        self.assertIn("Максимальная CC", result.stdout)
        self.assertIn("fixture/example.py", result.stdout)
        self.assertIn("Топ-5 функций по CC (после)", result.stdout)
        self.assertEqual(len(list(output.parent.iterdir())), 1)

    def test_cli_invalid_input_preserves_existing_output(self):
        before = self.write_report("before.json", sample_report())
        after_report = sample_report()
        after_report["tools"]["ruff"] = "other-version"
        after = self.write_report("after.json", after_report)
        output = self.root / "comparison.json"
        output.write_text("previous report\n", encoding="utf-8")
        result = self.cli(before, after, "--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertIn("tools", result.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "previous report\n")
        original = before.read_bytes()
        result = self.cli(before, before, "--output", before)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before.read_bytes(), original)

    def test_failed_atomic_replace_preserves_old_output_and_cleans_temporary(self):
        output = self.root / "comparison.json"
        output.write_text("original", encoding="utf-8")
        with patch.object(comparison.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                comparison.save_report({"value": 1}, output)
        self.assertEqual(output.read_text(encoding="utf-8"), "original")
        self.assertEqual(list(self.root.iterdir()), [output])

    def test_help_and_console_only_mode_need_no_dependencies(self):
        help_result = self.cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--output", help_result.stdout)
        before = self.write_report("before.json", sample_report())
        result = self.cli(before, before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("без изменений", result.stdout)
        self.assertEqual(list(self.root.iterdir()), [before])


if __name__ == "__main__":
    unittest.main()
