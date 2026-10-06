#!/usr/bin/env python3
"""Метрики Python-кода для ЛР3: Radon, Ruff и воспроизводимый JSON-отчёт.

Запуск из корня проекта:
    python scripts/analyze_metrics.py --output reports/metrics/before.json
    python scripts/analyze_metrics.py app/routers/auth.py --details

Приложение не импортируется, исходники не изменяются. Нужны зависимости
из requirements-metrics.txt. Формулы и область измерений описаны в README.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {"__pycache__", "venv", "env", "node_modules", "build", "dist"}
RUFF_SETTINGS = {
    "select": ["E", "F", "W", "I", "C90"],
    "line_length": 100,
    "max_complexity": 10,
    "target_version": "py312",
    "isolated": True,
    "ignore_noqa": True,
}


def display_path(path: Path) -> str:
    """Пути внутри проекта сохраняются относительно его корня."""
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def discover_files(source: Path) -> list[Path]:
    """Находит .py; скрытые и служебные каталоги не обходятся."""
    if source.is_file():
        if source.suffix != ".py":
            raise ValueError("Выберите Python-файл (.py) или каталог с исходниками")
        return [source]
    if not source.is_dir():
        raise ValueError(f"Путь не найден: {source}")

    def fail(error: OSError) -> None:
        raise error

    files = []
    for root, dirs, names in os.walk(source, onerror=fail):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in EXCLUDED_DIRS)
        files.extend(Path(root) / name for name in names if name.endswith(".py"))
    for path in files:
        if path.is_symlink():
            raise ValueError(
                f"Символьная ссылка в наборе файлов: {path}. Укажите её целевой .py напрямую."
            )
    if not files:
        raise ValueError(f"В каталоге нет Python-файлов: {source}")
    return sorted(files)


def function_metrics(tree: ast.AST) -> list[dict]:
    """CC каждого именованного определения; без повторного учёта класса."""
    from radon.visitors import ComplexityVisitor

    result = []

    def visit(node: ast.AST, prefix: str = "") -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            prefix = f"{prefix}.{node.name}" if prefix else node.name
            if not isinstance(node, ast.ClassDef):
                block = ComplexityVisitor.from_ast(node).functions[0]
                result.append({"name": prefix, "line": node.lineno, "complexity": block.complexity})
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)

    visit(tree)
    return result


def analyze_file(path: Path) -> dict:
    """Читает один снимок файла; Radon анализирует текст без его выполнения."""
    from radon.metrics import mi_visit
    from radon.raw import analyze

    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    source = data.decode(encoding)
    tree = ast.parse(source, filename=str(path))
    raw = analyze(source)
    functions = function_metrics(tree)
    complexities = [function["complexity"] for function in functions]
    physical_lines = len(source.splitlines())
    return {
        "path": display_path(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "physical_lines": physical_lines,
        "source_lines": raw.sloc,
        "logical_lines": raw.lloc,
        "comment_lines": raw.comments,
        "comment_density_percent": 100 * raw.comments / physical_lines if physical_lines else 0.0,
        "maintainability_index": mi_visit(source, multi=False) if raw.sloc else None,
        "function_count": len(functions),
        "cyclomatic_complexity": {
            "average": mean(complexities) if complexities else None,
            "maximum": max(complexities) if complexities else None,
        },
        "functions": functions,
        "ruff_issues": [],
    }


def run_ruff(files: list[Path]) -> list[dict]:
    """Ruff получает тот же явный список файлов и фиксированный набор правил."""
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--isolated",
        "--no-cache",
        "--no-fix",
        "--ignore-noqa",
        "--output-format",
        "json",
        "--select",
        ",".join(RUFF_SETTINGS["select"]),
        "--line-length",
        str(RUFF_SETTINGS["line_length"]),
        "--target-version",
        RUFF_SETTINGS["target_version"],
        "--config",
        f"lint.mccabe.max-complexity = {RUFF_SETTINGS['max_complexity']}",
        "--",
        *map(str, files),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    # Код 1 означает найденные замечания, а не ошибку измерения.
    if completed.returncode not in (0, 1):
        raise ValueError(f"Ruff не завершил анализ: {completed.stderr.strip()}")
    if completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr)
    diagnostics = json.loads(completed.stdout)
    if not isinstance(diagnostics, list):
        raise ValueError("Ruff вернул некорректный JSON вместо списка замечаний")
    result = []
    for issue in diagnostics:
        if issue["code"] in ("E902", "invalid-syntax", None):
            raise ValueError(f"Ruff не смог разобрать {issue['filename']}: {issue['message']}")
        result.append(
            {
                "path": display_path(Path(issue["filename"]).resolve()),
                "code": issue["code"],
                "message": issue["message"],
                "line": issue["location"]["row"],
                "column": issue["location"]["column"],
                "fix_available": issue.get("fix") is not None,
            }
        )
    return sorted(
        result, key=lambda item: (item["path"], item["line"], item["column"], item["code"] or "")
    )


def aggregate(files: list[dict]) -> dict:
    """Средняя CC взвешена по функциям, доля комментариев — по строкам."""
    complexities = [function["complexity"] for file in files for function in file["functions"]]
    indexes = [
        file["maintainability_index"] for file in files if file["maintainability_index"] is not None
    ]
    lines = sum(file["physical_lines"] for file in files)
    comments = sum(file["comment_lines"] for file in files)
    rules = Counter(issue["code"] for file in files for issue in file["ruff_issues"])
    return {
        "file_count": len(files),
        "function_count": len(complexities),
        "cyclomatic_complexity": {
            "average": mean(complexities) if complexities else None,
            "maximum": max(complexities) if complexities else None,
        },
        "maintainability_index_average": mean(indexes) if indexes else None,
        "maintainability_index_file_count": len(indexes),
        "average_file_lines": lines / len(files),
        "physical_lines": lines,
        "comment_lines": comments,
        "comment_density_percent": 100 * comments / lines if lines else 0.0,
        "ruff_issue_count": sum(rules.values()),
        "ruff_issues_by_rule": dict(sorted(rules.items())),
    }


def git_revision() -> str | None:
    """Коммит для справки; фактические исходники идентифицируются SHA-256."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_report(source: Path) -> dict:
    """Собирает полный отчёт; при сбое ни один файл не пропускается молча."""
    versions = {name: version(name) for name in ("radon", "ruff")}
    paths = discover_files(source)
    files = []
    for path in paths:
        try:
            files.append(analyze_file(path))
        except (SyntaxError, UnicodeError, OSError, ValueError, tokenize.TokenError) as error:
            raise ValueError(
                f"Не удалось проанализировать {display_path(path)}: {error}"
            ) from error
    by_path = {file["path"]: file for file in files}
    for issue in run_ruff(paths):
        if issue["path"] not in by_path:
            raise ValueError(f"Ruff вернул замечание вне выбранного набора: {issue['path']}")
        by_path[issue["path"]]["ruff_issues"].append(issue)
    if discover_files(source) != paths:
        raise ValueError("Состав Python-файлов изменился во время измерения. Повторите запуск.")
    for path, file in zip(paths, files):
        if hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
            raise ValueError(
                f"Файл изменился во время измерения: {file['path']}. Повторите запуск."
            )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": display_path(source),
        "git_commit": git_revision(),
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "tools": {"python": platform.python_version(), **versions},
        "methodology": {
            "file_selection": "*.py recursively; hidden and service directories excluded",
            "excluded_directories": sorted(EXCLUDED_DIRS),
            "complexity": (
                "Radon per def/async def, including nested functions and methods; "
                "no class aggregates"
            ),
            "complexity_average": (
                "sum(function complexity) / function count; null when no functions"
            ),
            "maintainability_index": "radon.metrics.mi_visit(multi=False); null when SLOC=0",
            "maintainability_index_average": "arithmetic mean over files with SLOC>0",
            "physical_lines": (
                "len(source.splitlines()), including blank lines, comments and docstrings"
            ),
            "average_file_lines": "sum(physical_lines) / file_count",
            "comment_lines": (
                "Radon raw.comments: # comment tokens, including inline; "
                "excluding strings/docstrings"
            ),
            "comment_density_percent": (
                "100 * sum(comment_lines) / sum(physical_lines); 0 when no lines"
            ),
            "ruff": RUFF_SETTINGS,
        },
        "summary": aggregate(files),
        "files": files,
    }


def format_number(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def print_report(report: dict, details: bool = False) -> None:
    """Печатает таблицу и детали, пригодные для иллюстраций в отчёте ЛР3."""
    print(f"Метрики Python-кода: {report['source']}")
    print("Инструменты: " + ", ".join(f"{name} {value}" for name, value in report["tools"].items()))
    print("Ruff: E,F,W,I,C90; строка ≤ 100; C901 > 10; Python 3.12; noqa не скрывает замечания.\n")
    rows = [["Файл", "Функции", "CC ср.", "CC макс.", "MI", "Строки", "Комм., %", "Ruff"]]
    for file in report["files"]:
        cc = file["cyclomatic_complexity"]
        rows.append(
            [
                file["path"],
                str(file["function_count"]),
                format_number(cc["average"]),
                str(cc["maximum"]) if cc["maximum"] is not None else "—",
                format_number(file["maintainability_index"]),
                str(file["physical_lines"]),
                format_number(file["comment_density_percent"]),
                str(len(file["ruff_issues"])),
            ]
        )
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    for index, row in enumerate(rows):
        print(" | ".join(cell.ljust(width) for cell, width in zip(row, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))

    summary = report["summary"]
    cc = summary["cyclomatic_complexity"]
    print(f"\nИтого файлов: {summary['file_count']}; функций/методов: {summary['function_count']}.")
    print(
        f"1. Цикломатическая сложность: средняя {format_number(cc['average'])}; "
        f"максимум {cc['maximum'] or '—'}"
    )
    print(f"2. Индекс сопровождаемости: {format_number(summary['maintainability_index_average'])}")
    print(f"3. Средний размер файла: {format_number(summary['average_file_lines'])} строк")
    print(f"4. Замечания Ruff: {summary['ruff_issue_count']}")
    print(f"5. Плотность комментариев: {format_number(summary['comment_density_percent'])}%")
    print(
        "Обозначения: CC — цикломатическая сложность; MI — индекс сопровождаемости Radon (0–100)."
    )
    print("Средняя CC — по функциям; средний MI — по файлам с SLOC > 0; строки — физические.")
    print(
        "Плотность — доля строк с #, включая inline-комментарии; "
        "docstrings не считаются комментариями."
    )
    print("Замечания Ruff зависят от правил и не равны количеству ошибок программы.")
    functions = [
        (file["path"], function) for file in report["files"] for function in file["functions"]
    ]
    if functions:
        print("\nФункции с наибольшей сложностью:")
        for path, function in sorted(functions, key=lambda item: -item[1]["complexity"])[:5]:
            print(f"  CC={function['complexity']:2}  {path}:{function['line']}  {function['name']}")
    if summary["ruff_issues_by_rule"]:
        print(
            "\nЗамечания по правилам: "
            + ", ".join(
                f"{code}: {count}" for code, count in summary["ruff_issues_by_rule"].items()
            )
        )
    if details:
        print("\nПодробные замечания Ruff:")
        for file in report["files"]:
            for issue in file["ruff_issues"]:
                print(
                    f"  {issue['path']}:{issue['line']}:{issue['column']}  "
                    f"{issue['code']}  {issue['message']}"
                )
        if not summary["ruff_issue_count"]:
            print("  Замечаний нет.")


def save_report(report: dict, output: Path) -> None:
    """Заменяет JSON атомарно только после успешного анализа всех файлов."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "app",
        help="Python-файл или каталог (по умолчанию app)",
    )
    parser.add_argument("--output", type=Path, help="Сохранить полный JSON-отчёт по этому пути")
    parser.add_argument("--details", action="store_true", help="Показать каждое замечание Ruff")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.suffix.lower() != ".json":
        parser.error("Файл --output должен иметь расширение .json")
    try:
        report = build_report(args.path.resolve())
        if args.output is not None:
            save_report(report, args.output)
        print_report(report, details=args.details)
        if args.output is not None:
            print(f"\nJSON-отчёт сохранён: {args.output}")
        return 0
    except (PackageNotFoundError, ModuleNotFoundError):
        print(
            "Установите инструменты в выбранное Python-окружение: "
            "python -m pip install -r requirements-metrics.txt",
            file=sys.stderr,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
