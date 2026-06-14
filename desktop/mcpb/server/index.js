#!/usr/bin/env node
/*
 * kasas MCP launcher for Claude Desktop (.mcpb extension).
 *
 * Zero dependencies. Claude Desktop runs this with its bundled Node:
 *
 *     node <bundle>/server/index.js <kasas_binary> <kasas_config>
 *
 * It spawns the local kasas binary's stdio MCP subcommand and inherits this
 * process's stdio, so MCP JSON-RPC flows directly between Claude Desktop and
 * kasas. This is the tokenless local transport: `kasas -config <cfg> mcp`
 * (note: -config is a global flag and MUST precede the `mcp` subcommand).
 */
"use strict";

const { spawn } = require("node:child_process");

const kasasBinary = process.argv[2];
const kasasConfig = process.argv[3];

function die(msg) {
  process.stderr.write(`[kasas-mcpb] ${msg}\n`);
  process.exit(1);
}

if (!kasasBinary || kasasBinary.startsWith("${")) {
  die(
    "kasas binary path is not configured. Open the kasas extension settings " +
      "in Claude Desktop and set the path to your kasas executable.",
  );
}
if (!kasasConfig || kasasConfig.startsWith("${")) {
  die(
    "kasas config.toml path is not configured. Open the kasas extension " +
      "settings in Claude Desktop and set the path to your kasas config.toml.",
  );
}

const args = ["-config", kasasConfig, "mcp"];
const child = spawn(kasasBinary, args, { stdio: "inherit" });

child.on("error", (err) => {
  if (err && err.code === "ENOENT") {
    die(`could not find the kasas binary at: ${kasasBinary}`);
  }
  die(`failed to launch kasas: ${err && err.message ? err.message : err}`);
});

child.on("exit", (code, signal) => {
  if (signal) {
    // Re-raise so the parent reflects the child's termination signal.
    process.kill(process.pid, signal);
  } else {
    process.exit(code == null ? 0 : code);
  }
});

// Forward shutdown signals so kasas exits cleanly with Claude Desktop.
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => {
    try {
      child.kill(sig);
    } catch {
      /* already gone */
    }
  });
}
