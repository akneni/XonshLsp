from __future__ import annotations

import unittest

from server.lowering import lower_xonsh
from server.semantics import semantic_spans


class SemanticTokenTests(unittest.TestCase):
    def test_classifies_python_symbols(self) -> None:
        source = (
            "import pathlib as paths\n"
            "from collections import Counter\n"
            "value = 1\n"
            "def greet(name: str) -> str:\n"
            "    return name.upper()\n"
            "result = paths.Path(str(value))\n"
        )
        spans = semantic_spans(source, lower_xonsh(source).source)
        classified = {(span.token_type, source.splitlines()[span.line][span.character : span.character + span.length]) for span in spans}
        self.assertIn(("namespace", "pathlib"), classified)
        self.assertIn(("namespace", "paths"), classified)
        self.assertIn(("namespace", "Counter"), classified)
        self.assertIn(("variable", "value"), classified)
        self.assertIn(("function", "greet"), classified)
        self.assertIn(("parameter", "name"), classified)
        self.assertIn(("method", "upper"), classified)
        self.assertIn(("method", "Path"), classified)

    def test_ignores_generated_command_placeholders(self) -> None:
        source = "name = 'world'\necho @(name.upper())\n"
        lowering = lower_xonsh(source)
        spans = semantic_spans(source, lowering.source, lowering.command_lines)
        names = {
            source.splitlines()[span.line][span.character : span.character + span.length]
            for span in spans
        }
        self.assertNotIn("pass", names)
        self.assertIn("name", names)
        self.assertIn("upper", names)

    def test_classifies_shell_commands_and_arguments(self) -> None:
        source = (
            "git status --short\n"
            "cat 'input file.txt' | grep foo > out.txt\n"
            "env FOO=bar python -m tool\n"
        )
        lowering = lower_xonsh(source)
        spans = semantic_spans(source, lowering.source, lowering.command_lines)
        classified = [
            (
                span.token_type,
                source.splitlines()[span.line][
                    span.character : span.character + span.length
                ],
            )
            for span in spans
            if span.token_type.startswith("xonsh")
        ]
        self.assertIn(("xonshCommand", "git"), classified)
        self.assertIn(("xonshArgument", "status"), classified)
        self.assertIn(("xonshArgument", "--short"), classified)
        self.assertIn(("xonshCommand", "cat"), classified)
        self.assertIn(("xonshArgument", "'input file.txt'"), classified)
        self.assertIn(("xonshCommand", "grep"), classified)
        self.assertIn(("xonshArgument", "out.txt"), classified)
        self.assertIn(("xonshCommand", "env"), classified)
        self.assertIn(("xonshArgument", "python"), classified)

    def test_shell_tokens_do_not_overlap_at_expression(self) -> None:
        source = "echo before @(name.upper()) after\n"
        lowering = lower_xonsh(source)
        spans = semantic_spans(source, lowering.source, lowering.command_lines)
        classified = {
            (
                span.token_type,
                source[span.character : span.character + span.length],
            )
            for span in spans
        }
        self.assertIn(("xonshCommand", "echo"), classified)
        self.assertIn(("xonshArgument", "before"), classified)
        self.assertIn(("variable", "name"), classified)
        self.assertIn(("method", "upper"), classified)
        self.assertIn(("xonshArgument", "after"), classified)
        self.assertNotIn(("xonshArgument", "@(name.upper())"), classified)

    def test_classifies_commands_in_subprocess_expressions(self) -> None:
        source = (
            "result = $(git status --short)\n"
            "items = $[echo hello | grep ell]\n"
        )
        lowering = lower_xonsh(source)
        spans = semantic_spans(source, lowering.source, lowering.command_lines)
        classified = {
            (
                span.token_type,
                source.splitlines()[span.line][
                    span.character : span.character + span.length
                ],
            )
            for span in spans
        }
        self.assertIn(("xonshCommand", "git"), classified)
        self.assertIn(("xonshArgument", "status"), classified)
        self.assertIn(("xonshArgument", "--short"), classified)
        self.assertIn(("xonshCommand", "echo"), classified)
        self.assertIn(("xonshArgument", "hello"), classified)
        self.assertIn(("xonshCommand", "grep"), classified)
        self.assertIn(("xonshArgument", "ell"), classified)

    def test_incomplete_subprocess_does_not_mark_last_argument_as_operator(self) -> None:
        source = "result = $(git status\n"
        lowering = lower_xonsh(source)
        spans = semantic_spans(source, lowering.source, lowering.command_lines)
        classified = {
            (span.token_type, source[span.character : span.character + span.length])
            for span in spans
        }
        self.assertIn(("xonshCommand", "git"), classified)
        self.assertIn(("xonshArgument", "status"), classified)
        self.assertNotIn(("operator", "s"), classified)

    def test_uses_utf16_columns(self) -> None:
        source = 'text = "😀"; value = 1\n'
        spans = semantic_spans(source, source)
        value = next(
            span
            for span in spans
            if span.line == 0
            and span.token_type == "variable"
            and span.character > 0
        )
        self.assertEqual(value.character, 13)


if __name__ == "__main__":
    unittest.main()
