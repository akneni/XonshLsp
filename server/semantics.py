from __future__ import annotations

import ast
import io
import keyword
import re
import token
import tokenize
from dataclasses import dataclass


TOKEN_TYPES = [
    "namespace",
    "type",
    "class",
    "enum",
    "interface",
    "struct",
    "typeParameter",
    "parameter",
    "variable",
    "property",
    "enumMember",
    "event",
    "function",
    "method",
    "macro",
    "keyword",
    "modifier",
    "comment",
    "string",
    "number",
    "regexp",
    "operator",
    "decorator",
    "xonshCommand",
    "xonshArgument",
]
TOKEN_MODIFIERS = [
    "declaration",
    "definition",
    "readonly",
    "static",
    "deprecated",
    "abstract",
    "async",
    "modification",
    "documentation",
    "defaultLibrary",
]

_TYPE_INDEX = {name: index for index, name in enumerate(TOKEN_TYPES)}
_MODIFIER_INDEX = {name: index for index, name in enumerate(TOKEN_MODIFIERS)}


@dataclass(frozen=True, order=True)
class SemanticSpan:
    line: int
    character: int
    length: int
    token_type: str
    modifiers: tuple[str, ...] = ()


@dataclass
class Symbols:
    namespaces: set[str]
    classes: set[str]
    functions: set[str]
    parameters: set[str]
    declarations: set[tuple[int, int]]


class SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols = Symbols(set(), set(), set(), set(), set())

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.symbols.namespaces.add(alias.asname or alias.name.split(".", 1)[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name != "*":
                self.symbols.namespaces.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbols.classes.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbols.functions.add(node.name)
        self._add_parameters(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._add_parameters(node.args)
        self.generic_visit(node)

    def _add_parameters(self, arguments: ast.arguments) -> None:
        args = (
            arguments.posonlyargs
            + arguments.args
            + arguments.kwonlyargs
        )
        if arguments.vararg:
            args.append(arguments.vararg)
        if arguments.kwarg:
            args.append(arguments.kwarg)
        self.symbols.parameters.update(arg.arg for arg in args)


def _collect_symbols(source: str) -> Symbols:
    collector = SymbolCollector()
    try:
        collector.visit(ast.parse(source))
    except SyntaxError:
        pass
    return collector.symbols


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _utf16_column(line: str, character_column: int) -> int:
    return _utf16_length(line[:character_column])


def _name_tokens(source: str) -> list[tokenize.TokenInfo]:
    result: list[tokenize.TokenInfo] = []
    generator = tokenize.generate_tokens(io.StringIO(source).readline)
    try:
        for item in generator:
            if item.type == token.NAME:
                result.append(item)
    except (IndentationError, tokenize.TokenError):
        pass
    return result


def _balanced_end(line: str, start: int, opening: str = "(", closing: str = ")") -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(line)):
        character = line[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    return len(line)


def _shell_spans(
    line: str,
    line_index: int,
    start: int = 0,
    end: int | None = None,
) -> list[SemanticSpan]:
    spans: list[SemanticSpan] = []
    limit = len(line) if end is None else end
    index = start
    while index < limit and line[index].isspace():
        index += 1
    command_expected = True
    control_operators = {"|", "|&", "||", "&&", ";"}
    redirection_operators = {">", ">>", "<", "<<"}
    all_operators = sorted(
        control_operators | redirection_operators, key=len, reverse=True
    )

    while index < limit:
        if line[index].isspace():
            index += 1
            continue
        if line[index] == "#":
            spans.append(
                SemanticSpan(
                    line_index,
                    _utf16_column(line, index),
                    _utf16_length(line[index:]),
                    "comment",
                )
            )
            break
        if line.startswith("@(", index):
            index = min(limit, _balanced_end(line, index + 1))
            continue
        subproc_marker = next(
            (
                marker
                for marker in ("$(", "$[", "!(", "![")
                if line.startswith(marker, index)
            ),
            None,
        )
        if subproc_marker:
            opening = subproc_marker[1]
            closing = ")" if opening == "(" else "]"
            region_end = min(
                limit,
                _balanced_end(line, index + 1, opening, closing),
            )
            is_closed = region_end > index + 2 and line[region_end - 1] == closing
            content_end = region_end - 1 if is_closed else region_end
            spans.append(
                SemanticSpan(
                    line_index,
                    _utf16_column(line, index),
                    _utf16_length(subproc_marker),
                    "operator",
                )
            )
            spans.extend(
                _shell_spans(line, line_index, index + 2, max(index + 2, content_end))
            )
            if is_closed:
                spans.append(
                    SemanticSpan(
                        line_index,
                        _utf16_column(line, region_end - 1),
                        1,
                        "operator",
                    )
                )
            index = region_end
            continue

        operator = next(
            (value for value in all_operators if line.startswith(value, index)),
            None,
        )
        if operator:
            spans.append(
                SemanticSpan(
                    line_index,
                    _utf16_column(line, index),
                    _utf16_length(operator),
                    "operator",
                )
            )
            if operator in control_operators:
                command_expected = True
            index += len(operator)
            continue

        start = index
        quote: str | None = None
        escaped = False
        while index < limit:
            character = line[index]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                index += 1
                continue
            if character in {"'", '"'}:
                quote = character
                index += 1
                continue
            if character.isspace() or character == "#":
                break
            if line.startswith("@(", index):
                break
            if any(line.startswith(value, index) for value in all_operators):
                break
            index += 1

        if start == index:
            index += 1
            continue
        value = line[start:index]
        token_type = "xonshCommand" if command_expected else "xonshArgument"
        spans.append(
            SemanticSpan(
                line_index,
                _utf16_column(line, start),
                _utf16_length(value),
                token_type,
            )
        )
        if command_expected and "=" not in value:
            command_expected = False
    return spans


def _embedded_subprocess_spans(line: str, line_index: int) -> list[SemanticSpan]:
    spans: list[SemanticSpan] = []
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(line):
        character = line[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        marker = next(
            (
                value
                for value in ("$(", "$[", "!(", "![")
                if line.startswith(value, index)
            ),
            None,
        )
        if marker is None:
            index += 1
            continue
        opening = marker[1]
        closing = ")" if opening == "(" else "]"
        region_end = _balanced_end(line, index + 1, opening, closing)
        is_closed = region_end > index + 2 and line[region_end - 1] == closing
        content_end = region_end - 1 if is_closed else region_end
        spans.append(
            SemanticSpan(
                line_index,
                _utf16_column(line, index),
                _utf16_length(marker),
                "operator",
            )
        )
        spans.extend(
            _shell_spans(line, line_index, index + 2, max(index + 2, content_end))
        )
        if is_closed:
            spans.append(
                SemanticSpan(
                    line_index,
                    _utf16_column(line, region_end - 1),
                    1,
                    "operator",
                )
            )
        index = region_end
    return spans


def _remove_overlaps(spans: list[SemanticSpan]) -> list[SemanticSpan]:
    priorities = {
        "xonshCommand": 3,
        "xonshArgument": 3,
        "operator": 2,
        "comment": 2,
    }
    ordered = sorted(
        set(spans),
        key=lambda span: (
            span.line,
            span.character,
            -priorities.get(span.token_type, 1),
            -span.length,
        ),
    )
    result: list[SemanticSpan] = []
    last_line = -1
    last_end = -1
    for span in ordered:
        if span.line != last_line:
            last_line = span.line
            last_end = -1
        if span.character < last_end:
            continue
        result.append(span)
        last_end = span.character + span.length
    return result


def _sql_ranges(lines: list[str]) -> dict[int, list[tuple[int, int]]]:
    ranges: dict[int, list[tuple[int, int]]] = {}
    active_triple: str | None = None

    for line_index, line in enumerate(lines):
        if active_triple is not None:
            closing = line.find(active_triple)
            end = len(line) if closing < 0 else closing + len(active_triple)
            ranges.setdefault(line_index, []).append(
                (0, _utf16_column(line, end))
            )
            if closing >= 0:
                active_triple = None
            continue

        match = re.match(
            r"^\s*SQL\s+(?P<prefix>[fF]?)(?P<quote>'''|\"\"\"|'|\")",
            line,
        )
        if match is None:
            continue
        quote = match.group("quote")
        start = match.start("prefix")
        if len(quote) == 3:
            closing = line.find(quote, match.end("quote"))
            end = len(line) if closing < 0 else closing + len(quote)
            ranges.setdefault(line_index, []).append(
                (_utf16_column(line, start), _utf16_column(line, end))
            )
            if closing < 0:
                active_triple = quote
        else:
            closing = line.rfind(quote)
            end = len(line) if closing <= start else closing + 1
            ranges.setdefault(line_index, []).append(
                (_utf16_column(line, start), _utf16_column(line, end))
            )
    return ranges


def _outside_sql_ranges(
    spans: list[SemanticSpan],
    lines: list[str],
) -> list[SemanticSpan]:
    sql_ranges = _sql_ranges(lines)
    if not sql_ranges:
        return spans

    result: list[SemanticSpan] = []
    for span in spans:
        ranges = sql_ranges.get(span.line, ())
        if any(
            span.character < end and span.character + span.length > start
            for start, end in ranges
        ):
            continue
        result.append(span)
    return result


def semantic_spans(
    original: str,
    lowered: str,
    command_lines: frozenset[int] = frozenset(),
) -> list[SemanticSpan]:
    symbols = _collect_symbols(lowered)
    original_lines = original.splitlines()
    lowered_tokens = _name_tokens(lowered)
    spans: list[SemanticSpan] = []

    for index, item in enumerate(lowered_tokens):
        line_index = item.start[0] - 1
        start = item.start[1]
        end = item.end[1]
        name = item.string
        if line_index < 0 or line_index >= len(original_lines):
            continue
        original_line = original_lines[line_index]
        if original_line[start:end] != name or keyword.iskeyword(name):
            continue

        previous = lowered_tokens[index - 1] if index > 0 else None
        next_item = lowered_tokens[index + 1] if index + 1 < len(lowered_tokens) else None
        prefix = original_line[:start].rstrip()
        suffix = original_line[end:].lstrip()
        is_import_line = original_line.lstrip().startswith(("import ", "from "))
        modifiers: tuple[str, ...] = ()

        if prefix.endswith("@"):
            token_type = "decorator"
        elif is_import_line:
            token_type = "namespace"
        elif prefix.endswith("."):
            token_type = "method" if suffix.startswith("(") else "property"
        elif name in symbols.namespaces:
            token_type = "namespace"
        elif name in symbols.classes:
            token_type = "class"
        elif name in symbols.functions:
            token_type = "function"
        elif name in symbols.parameters:
            token_type = "parameter"
        else:
            token_type = "variable"

        if previous and previous.string in {"def", "class", "as"}:
            modifiers = ("declaration",)
        elif next_item and next_item.string == "=":
            modifiers = ("modification",)

        spans.append(
            SemanticSpan(
                line=line_index,
                character=_utf16_column(original_line, start),
                length=_utf16_length(name),
                token_type=token_type,
                modifiers=modifiers,
            )
        )
    for line_index, line in enumerate(original_lines):
        if line_index in command_lines:
            spans.extend(_shell_spans(original_lines[line_index], line_index))
        else:
            spans.extend(_embedded_subprocess_spans(line, line_index))
    return _remove_overlaps(_outside_sql_ranges(spans, original_lines))


def encode_semantic_tokens(spans: list[SemanticSpan]) -> list[int]:
    data: list[int] = []
    previous_line = 0
    previous_character = 0
    for span in sorted(set(spans)):
        delta_line = span.line - previous_line
        delta_character = (
            span.character - previous_character if delta_line == 0 else span.character
        )
        modifier_bits = sum(
            1 << _MODIFIER_INDEX[modifier]
            for modifier in span.modifiers
            if modifier in _MODIFIER_INDEX
        )
        data.extend(
            [
                delta_line,
                delta_character,
                span.length,
                _TYPE_INDEX[span.token_type],
                modifier_bits,
            ]
        )
        previous_line = span.line
        previous_character = span.character
    return data


def semantic_tokens(
    original: str,
    lowered: str,
    command_lines: frozenset[int] = frozenset(),
) -> dict[str, list[int]]:
    return {
        "data": encode_semantic_tokens(
            semantic_spans(original, lowered, command_lines)
        )
    }
