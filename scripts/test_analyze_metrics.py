"""Regression checks for measurement semantics and the report CLI."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import analyze_metrics as metrics
from radon.metrics import mi_visit


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_source(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode("utf-8"))
        return path

    def run_cli(self, source, output, *arguments):
        return subprocess.run(
            [
                sys.executable,
                str(Path(metrics.__file__).resolve()),
                str(source),
                "--output",
                str(output),
                *arguments,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    def test_nested_definitions_are_counted_once_without_class_scores(self):
        path = self.write_source(
            "nested.py",
            textwrap.dedent("""\
            def outer(flag):
                def inner(value):
                    if value:
                        return 1
                    return 0
                class Local:
                    def run(self):
                        return 1
                return inner(flag)

            class Container:
                async def method(self, flag):
                    def closure():
                        return 1
                    if flag:
                        return closure()
                    return 0
                class Nested:
                    def method(self):
                        return 1

            def plain():
                return 1
            """),
        )
        file = metrics.analyze_file(path)
        expected = {
            "outer": 1,
            "outer.inner": 2,
            "outer.Local.run": 1,
            "Container.method": 2,
            "Container.method.closure": 1,
            "Container.Nested.method": 1,
            "plain": 1,
        }
        self.assertEqual(file["function_count"], len(expected))
        self.assertEqual(
            {function["name"]: function["complexity"] for function in file["functions"]},
            expected,
        )
        self.assertEqual(file["cyclomatic_complexity"]["maximum"], 2)

    def test_complexity_average_is_weighted_by_functions_not_files(self):
        complex_source = "def choose(value):\n"
        for number in range(4):
            complex_source += f"    if value == {number}:\n        return {number}\n"
        complex_source += "    return -1\n"
        simple_source = "\n".join(
            f"def function_{number}():\n    return {number}\n" for number in range(3)
        )
        files = [
            metrics.analyze_file(self.write_source("complex.py", complex_source)),
            metrics.analyze_file(self.write_source("simple.py", simple_source)),
            metrics.analyze_file(self.write_source("constants.py", "VALUE = 1\n")),
        ]
        summary = metrics.aggregate(files)
        self.assertEqual(summary["function_count"], 4)
        self.assertEqual(summary["cyclomatic_complexity"], {"average": 2, "maximum": 5})

    def test_maintainability_averages_only_files_with_source_lines(self):
        sources = [
            "VALUE = 1\n",
            "def choose(value):\n    if value > 2:\n        return value * 2\n    return 0\n",
        ]
        files = [
            metrics.analyze_file(self.write_source(f"code_{index}.py", source))
            for index, source in enumerate(sources)
        ]
        for index, source in enumerate(("", " \n\t\n", "# documentation only\n")):
            file = metrics.analyze_file(self.write_source(f"empty_{index}.py", source))
            self.assertIsNone(file["maintainability_index"])
            files.append(file)
        summary = metrics.aggregate(files)
        self.assertEqual(summary["maintainability_index_file_count"], 2)
        self.assertAlmostEqual(
            summary["maintainability_index_average"],
            sum(mi_visit(source, multi=False) for source in sources) / 2,
        )

    def test_comments_exclude_strings_and_line_endings_do_not_change_counts(self):
        lines = [
            '"""Documentation.',
            "# text inside a docstring",
            '"""',
            "# full-line comment",
            'value = "# literal"  # inline comment',
            'text = "ordinary string"',
        ]
        for separator in ("\n", "\r\n"):
            for trailing_newline in (False, True):
                with self.subTest(separator=repr(separator), trailing_newline=trailing_newline):
                    source = separator.join(lines) + (separator if trailing_newline else "")
                    file = metrics.analyze_file(self.write_source("comments.py", source))
                    self.assertEqual(file["physical_lines"], 6)
                    self.assertEqual(file["comment_lines"], 2)
                    self.assertAlmostEqual(file["comment_density_percent"], 100 / 3)

    def test_sizes_and_comment_density_use_project_totals(self):
        files = [
            metrics.analyze_file(
                self.write_source("small.py", "# comment\n" * 2 + "value = 1\n" * 8)
            ),
            metrics.analyze_file(
                self.write_source("large.py", "# comment\n" * 9 + "value = 1\n" * 81)
            ),
        ]
        summary = metrics.aggregate(files)
        self.assertEqual(summary["physical_lines"], 100)
        self.assertEqual(summary["comment_lines"], 11)
        self.assertEqual(summary["average_file_lines"], 50)
        self.assertEqual(summary["comment_density_percent"], 11)
        self.assertEqual(summary["cyclomatic_complexity"], {"average": None, "maximum": None})

    def test_cli_reports_ruff_findings_despite_noqa_and_local_configuration(self):
        self.write_source("pyproject.toml", '[tool.ruff.lint]\nignore = ["F401"]\n')
        source = self.write_source("app/example.py", "import os  # noqa: F401\n")
        original = source.read_bytes()
        output = self.root / "report.json"
        result = self.run_cli(source.parent, output, "--details")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["ruff_issues_by_rule"], {"F401": 1})
        self.assertEqual(report["summary"]["ruff_issue_count"], 1)
        self.assertEqual(report["files"][0]["ruff_issues"][0]["code"], "F401")
        self.assertIn("F401", result.stdout)
        self.assertEqual(source.read_bytes(), original)

    def test_default_scope_includes_nested_app_files_and_excludes_service_directories(self):
        self.write_source("app/main.py", "VALUE = 1\n")
        self.write_source("app/nested/helper.py", "OTHER = 2\n")
        ignored = (
            "tests",
            "alembic",
            "docs/tools",
            "app/.venv",
            "app/.hidden",
            "app/venv",
            "app/env",
            "app/__pycache__",
            "app/node_modules",
            "app/build",
            "app/dist",
        )
        for directory in ignored:
            self.write_source(f"{directory}/invalid.py", "def invalid(:\n")
        self.write_source("app/readme.txt", "not Python code")
        output = self.root / "default.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(metrics, "PROJECT_ROOT", self.root):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = metrics.main(["--output", str(output)])
        self.assertEqual(status, 0, stderr.getvalue())
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            [file["path"] for file in report["files"]], ["app/main.py", "app/nested/helper.py"]
        )
        self.assertEqual(report["summary"]["ruff_issue_count"], 0)

    def test_cli_errors_preserve_existing_report(self):
        broken = self.write_source("broken.py", "def broken(:\n")
        duplicate_parameters = self.write_source(
            "duplicate_parameters.py", "def f(a, a):\n    return a\n"
        )
        empty = self.root / "empty"
        empty.mkdir()
        output = self.root / "report.json"
        original = b'{"previous": "measurement"}\n'
        for source in (broken, duplicate_parameters, empty, self.root / "missing.py"):
            with self.subTest(source=source.name):
                output.write_bytes(original)
                result = self.run_cli(source, output)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn(source.name, result.stderr)
                self.assertEqual(output.read_bytes(), original)

    def test_ruff_execution_and_protocol_errors_are_not_zero_findings(self):
        cases = ((2, "", "invalid configuration"), (0, "not JSON", ""), (0, "{}", ""))
        for code, stdout, stderr in cases:
            with self.subTest(code=code, stdout=stdout):
                completed = subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)
                with patch.object(metrics.subprocess, "run", return_value=completed):
                    with self.assertRaises(ValueError):
                        metrics.run_ruff([self.root / "example.py"])
        with patch.object(
            metrics.subprocess, "run", side_effect=FileNotFoundError("python unavailable")
        ):
            with self.assertRaises(OSError):
                metrics.run_ruff([self.root / "example.py"])


if __name__ == "__main__":
    unittest.main()
