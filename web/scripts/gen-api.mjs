// Dumps the server's OpenAPI schema OFFLINE (no server is started): imports the app factory and asks it.
// PYTHON overrides the interpreter; otherwise the repo's .venv, otherwise `python` on PATH.
import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const web = fileURLToPath(new URL("..", import.meta.url))
const root = resolve(web, "..")
const venv = [".venv/Scripts/python.exe", ".venv/bin/python"].map((p) => resolve(root, p)).find(existsSync)
const python = process.env.PYTHON ?? venv ?? "python"

// sys.path first: -I ignores the cwd, and an editable install may point at a different checkout.
const code =
  "import json,pathlib,sys; sys.path.insert(0, sys.argv[1]); " +
  "from photosorter.api.app import create_app; from photosorter.config import Paths; " +
  "pathlib.Path(sys.argv[2]).write_text(json.dumps(create_app(Paths.default()).openapi(), indent=2), encoding='utf-8')"

const r = spawnSync(python, ["-I", "-c", code, root, resolve(web, "openapi.json")], { stdio: "inherit" })
process.exit(r.status ?? 1)
