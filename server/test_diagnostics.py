from __future__ import annotations

import unittest

from server.server import filter_pyright_diagnostics


def diagnostic(
    name: str,
    line: int,
    character: int,
    *,
    code: str = "reportUndefinedVariable",
) -> dict:
    return {
        "range": {
            "start": {"line": line, "character": character},
            "end": {"line": line, "character": character + len(name)},
        },
        "severity": 1,
        "code": code,
        "source": "Pyright",
        "message": f'"{name}" is not defined',
    }


class DiagnosticFilterTests(unittest.TestCase):
    def test_filters_undefined_aliases_only(self) -> None:
        text = 'aliases["ll"] = "ls -la"\nprint(missing_name)\n'
        diagnostics = [
            diagnostic("aliases", 0, 0),
            diagnostic("missing_name", 1, 6),
        ]
        self.assertEqual(
            filter_pyright_diagnostics(text, diagnostics),
            [diagnostics[1]],
        )

    def test_preserves_other_aliases_diagnostics(self) -> None:
        text = "print(aliases)\n"
        item = diagnostic(
            "aliases",
            0,
            6,
            code="reportUnknownArgumentType",
        )
        self.assertEqual(filter_pyright_diagnostics(text, [item]), [item])

    def test_handles_utf16_columns(self) -> None:
        text = 'print("😀", aliases, missing_name)\n'
        aliases = diagnostic("aliases", 0, 12)
        missing = diagnostic("missing_name", 0, 21)
        self.assertEqual(
            filter_pyright_diagnostics(text, [aliases, missing]),
            [missing],
        )


if __name__ == "__main__":
    unittest.main()
