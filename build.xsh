#!/usr/bin/env xonsh

from pathlib import Path
import shutil
import subprocess
import sys


root = Path(__file__).resolve().parent
artifact = root / "xonsh-language-support.vsix"


def run(*command):
    print("+", " ".join(map(str, command)))
    subprocess.run([str(part) for part in command], cwd=root, check=True)


if shutil.which("npm") is None:
    print("npm is required to build the extension.", file=sys.stderr)
    raise SystemExit(1)

run("npm", "ci" if (root / "package-lock.json").is_file() else "install")
run("npm", "run", "test")
run("npm", "run", "prepare:pyright")

artifact.unlink(missing_ok=True)
run(
    "npx",
    "vsce",
    "package",
    "--allow-missing-repository",
    "--out",
    artifact,
)
print(f"Built {artifact}")

code = shutil.which("code")
if code is not None:
    run(code, "--install-extension", artifact, "--force")
