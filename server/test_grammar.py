from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


class SqlGrammarTests(unittest.TestCase):
    def test_sql_rules_accept_plain_and_f_prefixed_strings(self) -> None:
        grammar_path = (
            Path(__file__).resolve().parents[1]
            / "syntaxes"
            / "xonsh.tmLanguage.json"
        )
        grammar = json.loads(grammar_path.read_text())
        patterns = grammar["repository"]["xonsh"]["patterns"][:4]
        begin_patterns = [re.compile(pattern["begin"]) for pattern in patterns]

        for source in (
            "SQL 'select 1'",
            'SQL "select 1"',
            "SQL '''select 1'''",
            'SQL """select 1"""',
            "SQL f'select {value}'",
            'SQL f"select {value}"',
            "SQL f'''select {value}'''",
            'SQL f"""select {value}"""',
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    any(pattern.match(source) for pattern in begin_patterns),
                    source,
                )


if __name__ == "__main__":
    unittest.main()
