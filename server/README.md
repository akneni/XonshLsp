# Xonsh LSP server

This process proxies LSP traffic to Pyright. Open Xonsh documents are lowered to
position-preserving Python before they are sent to Pyright. Xonsh parser
diagnostics and shell completions are added by the proxy.

The server requires the selected Python interpreter to have `xonsh` installed.
