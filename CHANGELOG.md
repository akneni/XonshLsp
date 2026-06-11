# Changelog

## 0.1.11

- Correct shifted Xonsh AST locations after multiline f-string commands so
  consecutive SQL and shell commands are fully lowered.

## 0.1.10

- Suppress the built-in `aliases` undefined warning even when Pyright omits
  diagnostic metadata.
- Apply normal string coloring to SQL text and delimiters while retaining SQL
  keyword highlighting.

## 0.1.9

- Highlight SQL in `f`-prefixed single-, double-, and triple-quoted arguments
  to the `SQL` command.

## 0.1.8

- Lower complete multiline Xonsh command arguments so triple-quoted SQL does
  not produce false Python syntax diagnostics.

## 0.1.7

- Suppress Pyright's undefined-variable diagnostic for Xonsh's built-in
  `aliases` object without suppressing other undefined names.

## 0.1.6

- Embed SQL syntax highlighting in quoted arguments to the `SQL` command.
- Support single, double, and multiline triple-quoted SQL strings.

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
