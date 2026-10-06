#!/usr/bin/env python3
"""Сравнение двух JSON-отчётов analyze_metrics.py без сторонних зависимостей.

    python scripts/compare_metrics.py reports/metrics/before.json \
        reports/metrics/after.json --output reports/metrics/comparison.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

METRICS = (
    ("cc_average", "Средняя CC", "lower"),
    ("maintainability_index", "Индекс сопровождаемости MI", "higher"),
    ("file_lines", "Средний размер файла, строки", "neutral"),
    ("ruff_issues", "Замечания Ruff", "lower"),
    ("comment_density", "Плотность комментариев, %", "neutral"),
    ("cc_maximum", "Максимальная CC", "lower"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(value, label: str, *, integer: bool = False, minimum: float = 0):
    valid = type(value) is int if integer else type(value) in (int, float)
    require(valid, f"{label}: ожидается {'целое ' if integer else ''}число")
    require(math.isfinite(value) and value >= minimum, f"{label}: недопустимое число")
    return value


def equal_number(actual, expected, label: str) -> None:
    if expected is None:
        require(actual is None, f"{label}: ожидается null")
    else:
        number(actual, label, integer=type(expected) is int)
        require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12),
                f"{label}: значение не согласуется с деталями отчёта")


def cc_values(functions: list[dict]) -> dict:
    values = [function["complexity"] for function in functions]
    return {
        "average": mean(values) if values else None,
        "maximum": max(values) if values else None,
    }


def check_cc(actual: dict, expected: dict, label: str) -> None:
    require(isinstance(actual, dict), f"{label}: ожидается объект")
    for key, value in expected.items():
        equal_number(actual[key], value, f"{label}.{key}")


def validate_file(file: dict) -> None:
    require(isinstance(file, dict), "files: ожидаются объекты файлов")
    path = file["path"]
    require(isinstance(path, str) and bool(path.strip()), "files.path: пустой или неверный путь")
    require(isinstance(file["sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", file["sha256"]) is not None,
            f"{path}: неверный sha256")
    for key in ("physical_lines", "source_lines", "logical_lines", "comment_lines",
                "function_count"):
        number(file[key], f"{path}.{key}", integer=True)
    lines = file["physical_lines"]
    require(file["source_lines"] <= lines and file["comment_lines"] <= lines,
            f"{path}: число строк кода/комментариев превышает физические строки")
    equal_number(file["comment_density_percent"],
                 100 * file["comment_lines"] / lines if lines else 0.0,
                 f"{path}.comment_density_percent")
    if file["source_lines"]:
        number(file["maintainability_index"], f"{path}.maintainability_index")
        require(file["maintainability_index"] <= 100, f"{path}: MI должен быть не выше 100")
    else:
        require(file["maintainability_index"] is None, f"{path}: при SLOC=0 MI должен быть null")
    functions = file["functions"]
    require(isinstance(functions, list), f"{path}.functions: ожидается список")
    require(file["function_count"] == len(functions), f"{path}: неверное число функций")
    identities = set()
    for function in functions:
        require(isinstance(function, dict), f"{path}: неверная структура функции")
        require(isinstance(function["name"], str) and bool(function["name"]),
                f"{path}: неверное имя функции")
        number(function["line"], f"{path}: строка функции", integer=True, minimum=1)
        number(function["complexity"], f"{path}: сложность функции", integer=True, minimum=1)
        identity = (function["name"], function["line"])
        require(identity not in identities, f"{path}: дубликат функции {identity}")
        identities.add(identity)
    check_cc(file["cyclomatic_complexity"], cc_values(functions), f"{path}.CC")
    require(isinstance(file["ruff_issues"], list), f"{path}.ruff_issues: ожидается список")
    for issue in file["ruff_issues"]:
        require(isinstance(issue, dict), f"{path}: неверная структура замечания Ruff")
        require(issue["path"] == path, f"{path}: замечание Ruff относится к другому файлу")
        require(isinstance(issue["code"], str) and bool(issue["code"]),
                f"{path}: неверный код замечания Ruff")
        require(isinstance(issue["message"], str), f"{path}: неверный текст замечания Ruff")
        for key in ("line", "column"):
            number(issue[key], f"{path}: Ruff {key}", integer=True, minimum=1)


def validate_report(report: dict) -> dict:
    """Проверяет обязательные поля и пересчитывает агрегаты без запуска анализатора."""
    require(isinstance(report, dict), "Корень отчёта должен быть JSON-объектом")
    require(type(report["schema_version"]) is int and report["schema_version"] == 1,
            "Поддерживается только schema_version=1")
    for key in ("source", "generated_at"):
        require(isinstance(report[key], str) and bool(report[key]), f"{key}: ожидается строка")
    require(report["git_commit"] is None or isinstance(report["git_commit"], str),
            "git_commit: ожидается строка или null")
    require(isinstance(report["analyzer_sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", report["analyzer_sha256"]) is not None,
            "analyzer_sha256: неверный хеш анализатора")
    require(isinstance(report["methodology"], dict) and bool(report["methodology"]),
            "methodology: ожидается непустой объект")
    require(isinstance(report["tools"], dict), "tools: ожидается объект")
    for tool in ("python", "radon", "ruff"):
        require(isinstance(report["tools"][tool], str) and bool(report["tools"][tool]),
                f"tools.{tool}: ожидается версия инструмента")
    files = report["files"]
    require(isinstance(files, list) and bool(files), "files: ожидается непустой список")
    paths = set()
    for file in files:
        validate_file(file)
        require(file["path"] not in paths, f"Дубликат пути файла: {file['path']}")
        paths.add(file["path"])
    summary = report["summary"]
    require(isinstance(summary, dict), "summary: ожидается объект")
    functions = [function for file in files for function in file["functions"]]
    indexes = [file["maintainability_index"] for file in files if file["source_lines"]]
    lines = sum(file["physical_lines"] for file in files)
    comments = sum(file["comment_lines"] for file in files)
    rules = Counter(issue["code"] for file in files for issue in file["ruff_issues"])
    expected = {
        "file_count": len(files),
        "function_count": len(functions),
        "maintainability_index_average": mean(indexes) if indexes else None,
        "maintainability_index_file_count": len(indexes),
        "physical_lines": lines,
        "comment_lines": comments,
        "average_file_lines": lines / len(files),
        "comment_density_percent": 100 * comments / lines if lines else 0.0,
        "ruff_issue_count": sum(rules.values()),
    }
    for key, value in expected.items():
        equal_number(summary[key], value, f"summary.{key}")
    check_cc(summary["cyclomatic_complexity"], cc_values(functions), "summary.CC")
    require(isinstance(summary["ruff_issues_by_rule"], dict),
            "summary.ruff_issues_by_rule: ожидается объект")
    for count in summary["ruff_issues_by_rule"].values():
        number(count, "summary.ruff_issues_by_rule", integer=True)
    require(summary["ruff_issues_by_rule"] == dict(rules),
            "summary.ruff_issues_by_rule: счётчики не согласуются с замечаниями")
    return report


def reject_nonfinite(value: str):
    raise ValueError(f"JSON содержит недопустимую константу {value}")


def load_report(path: Path) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
        return validate_report(report)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"Некорректный отчёт {path}: {error}") from error


def delta(before, after, direction: str = "neutral") -> dict:
    change = None if before is None or after is None else after - before
    percent = None if change is None or before == 0 else 100 * change / before
    if before == after == 0:
        percent = 0.0
    if change is None:
        assessment = "нет данных для сравнения"
    elif change == 0:
        assessment = "без изменений"
    elif direction == "neutral":
        assessment = "нейтральное изменение"
    elif (change < 0) == (direction == "lower"):
        assessment = "улучшение"
    else:
        assessment = "ухудшение"
    return {"before": before, "after": after, "absolute_change": change,
            "percent_change": percent, "assessment": assessment}


def values(record: dict, *, summary: bool) -> dict:
    return {
        "cc_average": record["cyclomatic_complexity"]["average"],
        "cc_maximum": record["cyclomatic_complexity"]["maximum"],
        "maintainability_index": record[
            "maintainability_index_average" if summary else "maintainability_index"
        ],
        "file_lines": record["average_file_lines" if summary else "physical_lines"],
        "comment_density": record["comment_density_percent"],
        "ruff_issues": record["ruff_issue_count"] if summary else len(record["ruff_issues"]),
    }


def compare_values(before: dict, after: dict, *, summary: bool) -> dict:
    old, new = values(before, summary=summary), values(after, summary=summary)
    return {key: delta(old[key], new[key], direction) for key, _, direction in METRICS}


def top_functions(report: dict) -> list[dict]:
    functions = [{"path": file["path"], **function}
                 for file in report["files"] for function in file["functions"]]
    return sorted(functions, key=lambda item: (-item["complexity"], item["path"],
                                              item["line"], item["name"]))[:5]


def compare_reports(before: dict, after: dict) -> dict:
    """Принимает проверенные отчёты; допускает новые функции и изменённые исходники."""
    for key in ("schema_version", "source", "tools", "methodology", "analyzer_sha256"):
        require(before[key] == after[key], f"Отчёты несопоставимы: различается {key}")
    old_files = {file["path"]: file for file in before["files"]}
    new_files = {file["path"]: file for file in after["files"]}
    require(old_files.keys() == new_files.keys(),
            "Отчёты несопоставимы: различается список путей файлов "
            f"(только до: {sorted(old_files.keys() - new_files.keys())}; "
            f"только после: {sorted(new_files.keys() - old_files.keys())})")
    files = []
    for path, old in sorted(old_files.items()):
        new = new_files[path]
        files.append({
            "path": path,
            "changed": old["sha256"] != new["sha256"],
            "before_sha256": old["sha256"],
            "after_sha256": new["sha256"],
            "function_count": delta(old["function_count"], new["function_count"]),
            "metrics": compare_values(old, new, summary=False),
        })
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": before["source"],
        "tools": before["tools"],
        "methodology": before["methodology"],
        "analyzer_sha256": before["analyzer_sha256"],
        "measurements": {name: {key: report[key] for key in ("generated_at", "git_commit")}
                         for name, report in (("before", before), ("after", after))},
        "context": {key: delta(before["summary"][key], after["summary"][key]) for key in
                    ("file_count", "function_count", "maintainability_index_file_count")},
        "metrics": compare_values(before["summary"], after["summary"], summary=True),
        "files": files,
        "top_functions": {"before": top_functions(before), "after": top_functions(after)},
    }


def formatted(value, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def print_table(rows: list[list[str]]) -> None:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    for index, row in enumerate(rows):
        print(" | ".join(cell.ljust(width) for cell, width in zip(row, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))


def print_comparison(comparison: dict) -> None:
    print(f"Сравнение метрик: {comparison['source']}")
    for key, label in (("file_count", "Файлы"), ("function_count", "Функции/методы"),
                       ("maintainability_index_file_count", "Файлы с MI")):
        item = comparison["context"][key]
        print(f"{label}: {item['before']} → {item['after']} "
              f"(изменение {item['absolute_change']:+d})")
    rows = [["Показатель", "До", "После", "Δ абсолютное", "Δ, %", "Оценка"]]
    for key, label, _ in METRICS:
        item = comparison["metrics"][key]
        rows.append([label, formatted(item["before"]), formatted(item["after"]),
                     formatted(item["absolute_change"], signed=True),
                     formatted(item["percent_change"], signed=True), item["assessment"]])
    print()
    print_table(rows)
    print("Δ = после − до; для плотности абсолютное изменение — процентные пункты.")
    print("Процентное изменение при исходном нуле не определено (0 → 0: 0%).")
    print("Оценка относится к отдельной метрике; число замечаний Ruff не равно числу багов.")
    print("\nИзменения по файлам (до → после):")
    rows = [["Файл", "Функции", "CC ср.", "CC макс.", "MI", "Строки",
             "Комм., %", "Ruff"]]
    for file in comparison["files"]:
        items = [file["function_count"]] + [file["metrics"][key] for key in
                ("cc_average", "cc_maximum", "maintainability_index", "file_lines",
                 "comment_density", "ruff_issues")]
        rows.append([file["path"]] +
                    [f"{formatted(item['before'])} → {formatted(item['after'])}" for item in items])
    print_table(rows)
    for key, label in (("before", "до"), ("after", "после")):
        print(f"\nТоп-5 функций по CC ({label}):")
        for function in comparison["top_functions"][key]:
            print(f"  CC={function['complexity']}  {function['path']}:{function['line']}  "
                  f"{function['name']}")
        if not comparison["top_functions"][key]:
            print("  Функций нет.")


def save_report(report: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("before", type=Path, help="JSON-отчёт до изменений")
    parser.add_argument("after", type=Path, help="JSON-отчёт после изменений")
    parser.add_argument("--output", type=Path, help="Сохранить сравнение в JSON")
    args = parser.parse_args(argv)
    if args.output is not None:
        if args.output.suffix.lower() != ".json":
            parser.error("Файл --output должен иметь расширение .json")
        if args.output.resolve() in (args.before.resolve(), args.after.resolve()):
            parser.error("--output не должен перезаписывать исходный отчёт")
    try:
        comparison = compare_reports(load_report(args.before), load_report(args.after))
        if args.output is not None:
            save_report(comparison, args.output)
        print_comparison(comparison)
        if args.output is not None:
            print(f"\nJSON-сравнение сохранено: {args.output}")
        return 0
    except (OSError, ValueError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
