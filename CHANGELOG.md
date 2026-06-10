# Changelog

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
