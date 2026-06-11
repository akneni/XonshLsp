from __future__ import annotations

import concurrent.futures
import unittest

from server.xonsh_parser import compile_xonsh, parse_xonsh


class XonshParserTests(unittest.TestCase):
    def test_shebang_followed_by_command_compiles(self) -> None:
        source = "#!/usr/bin/env xonsh\necho hi\n"
        self.assertIsNotNone(compile_xonsh(source, "test.xsh"))

    def test_global_execer_is_initialized_for_recovery_helpers(self) -> None:
        from xonsh.built_ins import XSH

        parse_xonsh("echo hi\n", "test.xsh")
        self.assertIsNotNone(XSH.execer)
        self.assertIsNotNone(XSH.execer.parser)

    def test_concurrent_requests_are_serialized(self) -> None:
        sources = [
            "#!/usr/bin/env xonsh\necho hi\n",
            "value = 1\n",
            "echo @(value)\n",
            "git status && echo ok\n",
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda item: compile_xonsh(item[1], f"test-{item[0]}.xsh"),
                    enumerate(sources * 10),
                )
            )
        self.assertTrue(all(result is not None for result in results))


if __name__ == "__main__":
    unittest.main()
