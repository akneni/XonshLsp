#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from lowering import LoweringResult, lower_xonsh
from semantics import TOKEN_MODIFIERS, TOKEN_TYPES, semantic_tokens
from xonsh_parser import compile_xonsh


Json = dict[str, Any]


class JsonRpcStream:
    def __init__(self, reader: BinaryIO, writer: BinaryIO):
        self.reader = reader
        self.writer = writer
        self.lock = threading.Lock()

    def read(self) -> Json | None:
        headers: dict[str, str] = {}
        while True:
            line = self.reader.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, value = line.decode("ascii").split(":", 1)
            headers[key.lower()] = value.strip()
        length = int(headers["content-length"])
        return json.loads(self.reader.read(length).decode("utf-8"))

    def write(self, message: Json) -> None:
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        with self.lock:
            self.writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
            self.writer.write(body)
            self.writer.flush()


@dataclass
class Document:
    uri: str
    python_uri: str
    version: int
    text: str
    lowering: LoweringResult
    xonsh_diagnostics: list[Json] = field(default_factory=list)
    pyright_diagnostics: list[Json] = field(default_factory=list)


class XonshLanguageServer:
    def __init__(self, pyright_command: list[str]):
        self.client = JsonRpcStream(sys.stdin.buffer, sys.stdout.buffer)
        self.pyright_process = subprocess.Popen(
            pyright_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
        )
        assert self.pyright_process.stdin and self.pyright_process.stdout
        self.pyright = JsonRpcStream(
            self.pyright_process.stdout, self.pyright_process.stdin
        )
        self.documents: dict[str, Document] = {}
        self.python_to_xonsh: dict[str, str] = {}
        self.pending_methods: dict[Any, str] = {}
        self.pending_completion_uris: dict[Any, str] = {}
        self.server_request_ids: set[Any] = set()
        self.running = True

    @staticmethod
    def _python_uri(uri: str) -> str:
        return uri + ".py"

    def _map_to_python(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._map_to_python(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._map_to_python(item) for item in value]
        if isinstance(value, str) and value in self.documents:
            return self.documents[value].python_uri
        return value

    def _map_to_xonsh(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._map_to_xonsh(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._map_to_xonsh(item) for item in value]
        if isinstance(value, str) and value in self.python_to_xonsh:
            return self.python_to_xonsh[value]
        return value

    @staticmethod
    def _diagnostic(error: SyntaxError) -> Json:
        line = max(0, (error.lineno or 1) - 1)
        character = max(0, (error.offset or 1) - 1)
        end_line = max(line, (error.end_lineno or error.lineno or 1) - 1)
        end_character = max(character + 1, (error.end_offset or error.offset or 1) - 1)
        return {
            "range": {
                "start": {"line": line, "character": character},
                "end": {"line": end_line, "character": end_character},
            },
            "severity": 1,
            "source": "xonsh",
            "message": error.msg,
        }

    def _xonsh_diagnostics(self, text: str, uri: str) -> list[Json]:
        try:
            compile_xonsh(text, uri)
        except SyntaxError as error:
            return [self._diagnostic(error)]
        except Exception as error:
            print(f"Xonsh parser failed for {uri}: {error}", file=sys.stderr)
        return []

    def _publish_diagnostics(self, document: Document) -> None:
        self.client.write(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {
                    "uri": document.uri,
                    "version": document.version,
                    "diagnostics": (
                        document.xonsh_diagnostics + document.pyright_diagnostics
                    ),
                },
            }
        )

    def _set_document(self, uri: str, version: int, text: str) -> Document:
        python_uri = self._python_uri(uri)
        lowering_diagnostics: list[Json] = []
        try:
            lowering = lower_xonsh(text, uri)
        except Exception as error:
            lowering = LoweringResult(text, frozenset())
            lowering_diagnostics.append(
                {
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 1},
                    },
                    "severity": 2,
                    "source": "xonsh-lsp",
                    "message": f"Lowering failed; using source unchanged: {error}",
                }
            )
        document = Document(
            uri=uri,
            python_uri=python_uri,
            version=version,
            text=text,
            lowering=lowering,
            xonsh_diagnostics=(
                lowering_diagnostics + self._xonsh_diagnostics(text, uri)
            ),
        )
        previous = self.documents.get(uri)
        if previous:
            document.pyright_diagnostics = previous.pyright_diagnostics
        self.documents[uri] = document
        self.python_to_xonsh[python_uri] = uri
        return document

    def _open_document(self, params: Json) -> None:
        item = params["textDocument"]
        document = self._set_document(item["uri"], item.get("version", 0), item["text"])
        self.pyright.write(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": document.python_uri,
                        "languageId": "python",
                        "version": document.version,
                        "text": document.lowering.source,
                    }
                },
            }
        )
        self._publish_diagnostics(document)

    def _change_document(self, params: Json) -> None:
        item = params["textDocument"]
        changes = params.get("contentChanges", [])
        if not changes:
            return
        document = self._set_document(item["uri"], item.get("version", 0), changes[-1]["text"])
        self.pyright.write(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {
                        "uri": document.python_uri,
                        "version": document.version,
                    },
                    "contentChanges": [{"text": document.lowering.source}],
                },
            }
        )
        self._publish_diagnostics(document)

    def _close_document(self, params: Json) -> None:
        uri = params["textDocument"]["uri"]
        document = self.documents.pop(uri, None)
        if not document:
            return
        self.python_to_xonsh.pop(document.python_uri, None)
        self.pyright.write(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {"textDocument": {"uri": document.python_uri}},
            }
        )

    def _shell_completions(self, uri: str, position: Json) -> list[Json]:
        document = self.documents.get(uri)
        if not document:
            return []
        lines = document.text.splitlines()
        if position["line"] >= len(lines):
            return []
        prefix_line = lines[position["line"]][: position["character"]]
        token = prefix_line.rsplit(maxsplit=1)[-1] if prefix_line.strip() else ""
        items: list[Json] = []

        if token.startswith("$"):
            prefix = token[1:]
            for name in sorted(os.environ):
                if name.startswith(prefix):
                    items.append(
                        {
                            "label": f"${name}",
                            "kind": 6,
                            "detail": "Environment variable",
                            "insertText": f"${name}",
                        }
                    )
            return items[:200]

        line_number = position["line"]
        if line_number not in document.lowering.command_lines:
            return []
        prefix = token
        seen: set[str] = set()
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            try:
                names = os.listdir(directory)
            except OSError:
                continue
            for name in names:
                if name.startswith(prefix) and name not in seen:
                    path = os.path.join(directory, name)
                    if os.access(path, os.X_OK) and not os.path.isdir(path):
                        seen.add(name)
                        items.append(
                            {
                                "label": name,
                                "kind": 3,
                                "detail": "Command",
                            }
                        )
        return sorted(items, key=lambda item: item["label"])[:300]

    def _handle_client_message(self, message: Json) -> None:
        method = message.get("method")
        message_id = message.get("id")

        if method == "textDocument/didOpen":
            self._open_document(message["params"])
            return
        if method == "textDocument/didChange":
            self._change_document(message["params"])
            return
        if method == "textDocument/didClose":
            self._close_document(message["params"])
            return
        if method == "textDocument/semanticTokens/full":
            uri = message["params"]["textDocument"]["uri"]
            document = self.documents.get(uri)
            result = (
                semantic_tokens(
                    document.text,
                    document.lowering.source,
                    document.lowering.command_lines,
                )
                if document
                else {"data": []}
            )
            self.client.write({"jsonrpc": "2.0", "id": message_id, "result": result})
            return
        if method == "exit":
            self.pyright.write(message)
            self.running = False
            return

        if method:
            self.pending_methods[message_id] = method
            if method == "textDocument/completion":
                self.pending_completion_uris[message_id] = message["params"][
                    "textDocument"
                ]["uri"]
            forwarded = self._map_to_python(message)
            if method == "initialize":
                forwarded["params"]["clientInfo"] = {
                    "name": "xonsh-lsp",
                    "version": "0.1.5",
                }
            self.pyright.write(forwarded)
            return

        if message_id in self.server_request_ids:
            self.server_request_ids.discard(message_id)
            self.pyright.write(message)

    def _handle_pyright_message(self, message: Json) -> None:
        method = message.get("method")
        message_id = message.get("id")

        if method == "textDocument/publishDiagnostics":
            python_uri = message["params"]["uri"]
            uri = self.python_to_xonsh.get(python_uri)
            if uri and uri in self.documents:
                document = self.documents[uri]
                document.pyright_diagnostics = self._map_to_xonsh(
                    message["params"].get("diagnostics", [])
                )
                self._publish_diagnostics(document)
            return

        if method:
            if message_id is not None:
                self.server_request_ids.add(message_id)
            self.client.write(self._map_to_xonsh(message))
            return

        pending_method = self.pending_methods.pop(message_id, None)
        if pending_method == "initialize" and "result" in message:
            capabilities = message["result"].setdefault("capabilities", {})
            capabilities["textDocumentSync"] = {
                "openClose": True,
                "change": 1,
                "save": {"includeText": True},
            }
            capabilities["semanticTokensProvider"] = {
                "legend": {
                    "tokenTypes": TOKEN_TYPES,
                    "tokenModifiers": TOKEN_MODIFIERS,
                },
                "full": True,
                "range": False,
            }
        elif pending_method == "textDocument/completion" and "result" in message:
            uri = self.pending_completion_uris.pop(message_id, "")
            request = getattr(self, "_completion_requests", {}).pop(message_id, None)
            position = request or {"line": 0, "character": 0}
            extras = self._shell_completions(uri, position)
            result = message["result"]
            if isinstance(result, list):
                result.extend(extras)
            elif isinstance(result, dict):
                result.setdefault("items", []).extend(extras)
            elif extras:
                message["result"] = extras
        self.client.write(self._map_to_xonsh(message))

    def run(self) -> int:
        self._completion_requests: dict[Any, Json] = {}

        def read_pyright() -> None:
            while self.running:
                message = self.pyright.read()
                if message is None:
                    break
                self._handle_pyright_message(message)

        thread = threading.Thread(target=read_pyright, name="pyright-reader", daemon=True)
        thread.start()
        try:
            while self.running:
                message = self.client.read()
                if message is None:
                    break
                if message.get("method") == "textDocument/completion":
                    self._completion_requests[message.get("id")] = message["params"][
                        "position"
                    ]
                self._handle_client_message(message)
        finally:
            self.running = False
            if self.pyright_process.poll() is None:
                self.pyright_process.terminate()
            thread.join(timeout=2)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default=shutil.which("node") or "node")
    parser.add_argument("--pyright-langserver", required=True)
    args = parser.parse_args()
    return XonshLanguageServer(
        [args.node, str(Path(args.pyright_langserver)), "--stdio"]
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
