# Changelog

## 0.1.5

- Initialize Xonsh's global parser session for parser recovery helpers.
- Reuse and serialize one parser instance instead of constructing one per edit.
- Keep internal parser failures in the server log rather than showing a
  misleading warning on the first line.

## 0.1.4

- Add the Xonsh extension icon.
- Use the same icon for `.xsh`, `.xonshrc`, and other Xonsh language files.

## 0.1.3

- Highlight shell command names and all shell arguments.
- Highlight commands after pipelines and control operators.
- Preserve Python semantic highlighting inside `@(...)` command arguments.

## 0.1.2

- Add semantic highlighting for Python modules, classes, functions, parameters,
  variables, methods, properties, and decorators in Xonsh files.

## 0.1.1

- Prevent incomplete Xonsh AST location metadata from crashing the language
  server during edits.
- Fall back safely if lowering encounters unexpected parser output.

## 0.1.0

- Initial Xonsh language registration and syntax grammar.
- Position-preserving Xonsh-to-Python lowering.
- Pyright-backed Python language features.
- Xonsh syntax diagnostics and shell completion.
- Run File and Run Selection commands.
