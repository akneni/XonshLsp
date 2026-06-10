# Xonsh Language Support

VS Code language support for [Xonsh](https://xon.sh/) with Python analysis
provided by Pyright.

## Features

- Syntax highlighting for `.xsh`, `.xonshrc`, and Xonsh shebang files.
- Xonsh syntax diagnostics.
- Pyright diagnostics, completion, hover, navigation, and type information for
  Python code in Xonsh files.
- Semantic coloring for shell commands, arguments, pipelines, and subprocess
  expressions.
- Command and environment-variable completion.
- Run File and Run Selection commands.

## Requirements

The Python interpreter configured in `xonsh.pythonPath` must have Xonsh
installed:

```sh
python -m pip install xonsh
```

The extension includes Pyright. It does not execute documents during analysis
or load the user's `.xonshrc`.

## Current lowering support

Ordinary Python is preserved exactly. Bare subprocess statements are masked,
while Python expressions inside `@(...)` retain their original positions.
Backtick paths, environment variables, and captured subprocess expressions are
currently lowered to `None`. More precise Xonsh runtime types will be added in
later releases.

## Development

Run:

```fish
./build.fish
```

The build writes `xonsh-language-support.vsix` to the repository root.
