from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize
from dataclasses import dataclass


_SUBPROC_METHOD_PREFIXES = (
    "subproc_captured_",
    "subproc_uncaptured",
    "subproc_check_",
)


@dataclass(frozen=True)
class LoweringResult:
    source: str
    command_lines: frozenset[int]


def _command_name(node: ast.AST) -> str | None:
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and re.fullmatch(r"[A-Za-z_][\w.-]*", child.value)
        ):
            return child.value
    return None


def _source_command_start(
    lines: list[str],
    reported_start: int,
    command_name: str | None,
    claimed_lines: set[int],
) -> int:
    if command_name is None:
        return reported_start

    candidates: list[int] = []
    for index, line in enumerate(lines):
        if index in claimed_lines:
            continue
        match = re.match(r"\s*([A-Za-z_][\w.-]*)", line)
        if match and match.group(1) == command_name:
            candidates.append(index)
    if not candidates:
        return reported_start
    return min(candidates, key=lambda index: (abs(index - reported_start), index))


def _xonsh_command_lines(source: str, filename: str) -> set[int]:
    try:
        try:
            from .xonsh_parser import parse_xonsh
        except ImportError:
            from xonsh_parser import parse_xonsh

        tree = parse_xonsh(source, filename)
    except Exception:
        return set()

    try:
        command_lines: set[int] = set()
        if tree is None:
            return command_lines
        lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr.startswith(_SUBPROC_METHOD_PREFIXES):
                lineno = getattr(node, "lineno", None) or 1
                end_lineno = max(
                    (
                        getattr(child, "end_lineno", None)
                        or getattr(child, "lineno", None)
                        or lineno
                    )
                    for child in ast.walk(node)
                )
                reported_start = max(0, lineno - 1)
                start = _source_command_start(
                    lines,
                    reported_start,
                    _command_name(node),
                    command_lines,
                )
                end = max(start, start + end_lineno - lineno)
                command_lines.update(range(start, end + 1))
        return command_lines
    except Exception:
        # Xonsh may return partially populated AST nodes for incomplete editor
        # input. Heuristic command detection is preferable to crashing the LSP.
        return set()


def _looks_like_command(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    first = re.match(r"[A-Za-z_][\w.-]*", stripped)
    if first is None:
        return False
    word = first.group(0)
    if keyword.iskeyword(word) or word in {"True", "False", "None"}:
        return False
    rest = stripped[first.end() :]
    if not rest or rest.lstrip().startswith(("=", ":", ".", "(", "[", "{")):
        return False
    return bool(re.search(r"\s|[|&<>]", rest))


def _balanced_span(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _replace_span(chars: list[str], start: int, end: int, replacement: str) -> None:
    width = end - start
    chars[start:end] = list(replacement[:width].ljust(width))


def _lower_python_line(line: str) -> str:
    chars = list(line)
    index = 0
    while index < len(line):
        if line.startswith("${", index):
            end = _balanced_span(line, index + 1, "{", "}")
            if end is not None:
                chars[index] = "("
                chars[index + 1] = " "
                chars[end - 1] = ")"
                index = end
                continue
        if line.startswith(("$(", "$[", "![", "!(", "@$("), index):
            marker_len = 3 if line.startswith("@$(", index) else 2
            opening = line[index + marker_len - 1]
            closing = ")" if opening == "(" else "]"
            end = _balanced_span(line, index + marker_len - 1, opening, closing)
            if end is not None:
                _replace_span(chars, index, end, "None")
                index = end
                continue
        if line[index] == "`":
            end = line.find("`", index + 1)
            if end >= 0:
                _replace_span(chars, index, end + 1, "None")
                index = end + 1
                continue
        if line[index] == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*", line[index:])
            if match:
                end = index + len(match.group(0))
                _replace_span(chars, index, end, "None")
                index = end
                continue
        index += 1
    return "".join(chars)


def _at_expressions(line: str) -> list[tuple[int, int, str]]:
    expressions: list[tuple[int, int, str]] = []
    index = 0
    while True:
        marker = line.find("@(", index)
        if marker < 0:
            break
        end = _balanced_span(line, marker + 1, "(", ")")
        if end is None:
            break
        expressions.append((marker + 2, end - 1, line[marker + 2 : end - 1]))
        index = end
    return expressions


def _lower_command_line(line: str) -> str:
    newline = ""
    body = line
    if body.endswith("\r\n"):
        body, newline = body[:-2], "\r\n"
    elif body.endswith("\n"):
        body, newline = body[:-1], "\n"

    indent = len(body) - len(body.lstrip())
    chars = [" "] * len(body)
    available = len(body) - indent
    prefix = " " * indent + ("pass" if available >= 4 else "")
    chars[: len(prefix)] = prefix

    expressions = _at_expressions(body)
    for expression_index, (start, end, expression) in enumerate(expressions):
        separator = indent + 4 if expression_index == 0 else start - 1
        if separator < start:
            chars[separator] = ";"
            chars[start:end] = expression
    return "".join(chars) + newline


def lower_xonsh(source: str, filename: str = "<xonsh>") -> LoweringResult:
    lines = source.splitlines(keepends=True)
    command_lines = _xonsh_command_lines(source, filename)
    if not command_lines:
        command_lines = {
            index for index, line in enumerate(lines) if _looks_like_command(line)
        }

    lowered: list[str] = []
    for index, line in enumerate(lines):
        if index in command_lines:
            lowered.append(_lower_command_line(line))
        else:
            lowered.append(_lower_python_line(line))

    result = "".join(lowered)
    if len(result) != len(source):
        raise AssertionError("Lowering must preserve source length")
    return LoweringResult(result, frozenset(command_lines))


def python_syntax_error(source: str) -> SyntaxError | None:
    try:
        ast.parse(source)
    except SyntaxError as error:
        return error
    return None


def token_at(source: str, line: int, character: int) -> str:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.start <= (line + 1, character) <= token.end:
                return token.string
    except (IndentationError, tokenize.TokenError):
        pass
    return ""
