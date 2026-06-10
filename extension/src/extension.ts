import * as path from "node:path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let terminal: vscode.Terminal | undefined;

function quoteShellArgument(value: string): string {
  if (process.platform === "win32") {
    return `"${value.replaceAll('"', '\\"')}"`;
  }
  return `'${value.replaceAll("'", "'\\''")}'`;
}

async function startLanguageServer(
  context: vscode.ExtensionContext,
): Promise<void> {
  if (client) {
    await client.stop();
  }

  const configuration = vscode.workspace.getConfiguration("xonsh");
  const pythonPath = configuration.get<string>("pythonPath", "python");
  const serverPath = context.asAbsolutePath(path.join("server", "server.py"));
  const pyrightPath = context.asAbsolutePath(
    path.join("pyright", "langserver.index.js"),
  );

  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: [
      serverPath,
      "--node",
      process.execPath,
      "--pyright-langserver",
      pyrightPath,
    ],
    options: {
      env: {
        ...process.env,
        ELECTRON_RUN_AS_NODE: "1",
      },
    },
  };
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "xonsh" },
      { scheme: "untitled", language: "xonsh" },
    ],
    synchronize: {
      configurationSection: ["python", "pyright", "xonsh"],
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.{py,pyi,xsh}"),
    },
    outputChannelName: "Xonsh Language Server",
  };

  client = new LanguageClient(
    "xonshLanguageServer",
    "Xonsh Language Server",
    serverOptions,
    clientOptions,
  );
  await client.start();
}

function getTerminal(): vscode.Terminal {
  if (!terminal || terminal.exitStatus) {
    terminal = vscode.window.createTerminal("Xonsh");
  }
  terminal.show();
  return terminal;
}

async function runFile(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "xonsh") {
    return;
  }
  if (editor.document.isDirty) {
    await editor.document.save();
  }
  const executable = vscode.workspace
    .getConfiguration("xonsh")
    .get<string>("executablePath", "xonsh");
  getTerminal().sendText(
    `${quoteShellArgument(executable)} ${quoteShellArgument(editor.document.fileName)}`,
  );
}

function runSelection(): void {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.selection.isEmpty) {
    return;
  }
  const selection = editor.document.getText(editor.selection);
  const executable = vscode.workspace
    .getConfiguration("xonsh")
    .get<string>("executablePath", "xonsh");
  getTerminal().sendText(
    `${quoteShellArgument(executable)} -c ${quoteShellArgument(selection)}`,
  );
}

export async function activate(
  context: vscode.ExtensionContext,
): Promise<void> {
  context.subscriptions.push(
    vscode.commands.registerCommand("xonsh.runFile", runFile),
    vscode.commands.registerCommand("xonsh.runSelection", runSelection),
    vscode.commands.registerCommand(
      "xonsh.restartLanguageServer",
      async () => startLanguageServer(context),
    ),
    vscode.workspace.onDidChangeConfiguration(async (event) => {
      if (event.affectsConfiguration("xonsh.pythonPath")) {
        await startLanguageServer(context);
      }
    }),
  );
  await startLanguageServer(context);
}

export async function deactivate(): Promise<void> {
  if (client) {
    await client.stop();
    client = undefined;
  }
  terminal?.dispose();
}
