from __future__ import annotations

import ast
import unittest
from unittest.mock import patch

from server.lowering import _xonsh_command_lines, lower_xonsh


class LoweringTests(unittest.TestCase):
    def assert_valid_lowering(self, source: str) -> str:
        result = lower_xonsh(source)
        self.assertEqual(len(result.source), len(source))
        self.assertEqual(
            [len(line) for line in result.source.splitlines(keepends=True)],
            [len(line) for line in source.splitlines(keepends=True)],
        )
        ast.parse(result.source)
        return result.source

    def test_preserves_python(self) -> None:
        source = "name: str = 'world'\nprint(name.upper())\n"
        self.assertEqual(self.assert_valid_lowering(source), source)

    def test_masks_command_and_preserves_at_expression(self) -> None:
        source = "name: str = 'world'\necho @(name.upper())\n"
        lowered = self.assert_valid_lowering(source)
        self.assertIn("name.upper()", lowered)
        self.assertEqual(source.index("name.upper()"), lowered.index("name.upper()"))

    def test_replaces_xonsh_expressions(self) -> None:
        source = "files = `*.py`\nresult = $(git status)\nhome = $HOME\n"
        lowered = self.assert_valid_lowering(source)
        self.assertIn("files = None", lowered)
        self.assertIn("result = None", lowered)
        self.assertIn("home = None", lowered)

    def test_command_inside_python_block(self) -> None:
        source = "def greet(name: str) -> None:\n    echo @(name.upper())\n"
        lowered = self.assert_valid_lowering(source)
        self.assertIn("    pass;", lowered)
        self.assertEqual(source.index("name.upper()"), lowered.index("name.upper()"))

    def test_missing_end_lineno_does_not_crash(self) -> None:
        command = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="__xonsh__", ctx=ast.Load()),
                    attr="subproc_captured_hiddenobject",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            )
        )
        command.lineno = 3
        command.end_lineno = None

        class FakeExecer:
            def __init__(self, **_: object) -> None:
                pass

            def parse(self, *_: object, **__: object) -> ast.Module:
                return ast.Module(body=[command], type_ignores=[])

        with patch("xonsh.execer.Execer", FakeExecer):
            self.assertEqual(_xonsh_command_lines("echo hi\n", "test.xsh"), {2})


if __name__ == "__main__":
    unittest.main()
