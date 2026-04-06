#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const env = { ...process.env };
const pythonPath = path.join(root, "src");

env.PYTHONPATH = env.PYTHONPATH
  ? `${pythonPath}${path.delimiter}${env.PYTHONPATH}`
  : pythonPath;

const candidates = process.platform === "win32"
  ? ["python", "py"]
  : ["python3", "python"];

for (const candidate of candidates) {
  const probe = spawnSync(candidate, ["-c", "import pymongo"], {
    cwd: root,
    env,
    stdio: "ignore"
  });
  if (probe.status !== 0) {
    continue;
  }

  const result = spawnSync(
    candidate,
    ["-m", "rocketchat_exporter.cli", ...process.argv.slice(2)],
    {
      cwd: root,
      env,
      stdio: "inherit"
    }
  );
  process.exit(result.status ?? 1);
}

console.error(
  "Python 3.11+ with pymongo is required. Install Python dependencies before using this npm wrapper."
);
console.error("Example: pip install rocketchat-exporter or pip install -e .");
process.exit(1);
