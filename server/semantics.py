from __future__ import annotations

import ast
import io
import keyword
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


def semantic_spans(original: str, lowered: str) -> list[SemanticSpan]:
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
    return spans


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


def semantic_tokens(original: str, lowered: str) -> dict[str, list[int]]:
    return {"data": encode_semantic_tokens(semantic_spans(original, lowered))}
