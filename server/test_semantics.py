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
        lowered = lower_xonsh(source).source
        spans = semantic_spans(source, lowered)
        names = {
            source.splitlines()[span.line][span.character : span.character + span.length]
            for span in spans
        }
        self.assertNotIn("pass", names)
        self.assertIn("name", names)
        self.assertIn("upper", names)

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
