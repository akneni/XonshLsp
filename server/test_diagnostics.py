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
        item["message"] = 'Argument type for "aliases" is unknown'
        self.assertEqual(filter_pyright_diagnostics(text, [item]), [item])

    def test_handles_utf16_columns(self) -> None:
        text = 'print("😀", aliases, missing_name)\n'
        aliases = diagnostic("aliases", 0, 12)
        missing = diagnostic("missing_name", 0, 21)
        self.assertEqual(
            filter_pyright_diagnostics(text, [aliases, missing]),
            [missing],
        )

    def test_filters_aliases_when_code_or_range_is_missing(self) -> None:
        text = "aliases['SQL'] = SQL\n"
        item = diagnostic("aliases", 0, 0)
        item.pop("code")
        item["range"] = {
            "start": {"line": 0, "character": 1},
            "end": {"line": 0, "character": 1},
        }
        self.assertEqual(filter_pyright_diagnostics(text, [item]), [])

    def test_preserves_other_undefined_messages_without_code(self) -> None:
        text = "print(missing_name)\n"
        item = diagnostic("missing_name", 0, 6)
        item.pop("code")
        self.assertEqual(filter_pyright_diagnostics(text, [item]), [item])


if __name__ == "__main__":
    unittest.main()
