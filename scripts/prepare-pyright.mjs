import {
  cpSync,
  existsSync,
  readdirSync,
  rmSync,
  statSync,
} from "node:fs";
import { join, resolve } from "node:path";

const source = resolve("node_modules", "pyright");
const destination = resolve("pyright");

if (!existsSync(source)) {
  throw new Error("Pyright is not installed. Run npm install first.");
}

rmSync(destination, { recursive: true, force: true });
cpSync(source, destination, { recursive: true });

function removeSourceMaps(directory) {
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      removeSourceMaps(path);
    } else if (path.endsWith(".map")) {
      rmSync(path);
    }
  }
}

removeSourceMaps(destination);
