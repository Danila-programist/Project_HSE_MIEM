#!/usr/bin/env python3
"""Adapt annotated assignments for Doxygen 1.9.x without importing the project.

Doxygen handles annotated function arguments but misreads PEP 526 class fields.
Only the stream sent to its parser is changed; source files stay untouched.
Line counts are preserved so source-browser links still point to original lines.
"""
import ast
import io
import tokenize
from pathlib import Path
import sys


def filter_source(source: str) -> str:
    """Replace annotated assignments with assignments understood by Doxygen."""
    raw = source.encode("utf-8")
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def position(node, end=False):
        line = node.end_lineno if end else node.lineno
        column = node.end_col_offset if end else node.col_offset
        return offsets[line - 1] + column

    # tokenize columns count characters, while AST columns count UTF-8 bytes.
    equals = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.OP and token.string == "=":
            row, col = token.start
            equals.append(offsets[row - 1] + len(lines[row - 1].decode("utf-8")[:col].encode("utf-8")))

    edits = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.AnnAssign):
            continue
        start = position(node.target, end=True)
        if node.value is None:
            end = position(node, end=True)
        else:
            # Include closing parentheses around annotations but keep the RHS,
            # including any opening parentheses before the value's AST node.
            end = next(pos for pos in equals if position(node.annotation, end=True) <= pos < position(node.value))
        # Explicit continuations retain line numbers and valid Python syntax.
        replacement = b" \\\n" * raw[start:end].count(b"\n")
        if node.value is None:
            replacement = b" = ..." + replacement
        edits.append((start, end, replacement))

    for start, end, replacement in sorted(edits, reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    return raw.decode("utf-8")


if __name__ == "__main__":
    sys.stdout.write(filter_source(Path(sys.argv[1]).read_text(encoding="utf-8")))
