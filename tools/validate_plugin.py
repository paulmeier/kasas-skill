#!/usr/bin/env python3
"""
validate_plugin.py — structural + semantic linter for the kasas-skill plugin.

Stdlib only, so it runs in CI and via `make validate` with no install. It is the
deterministic gate that complements `claude plugin validate` (which checks the
manifest/frontmatter shape). This script additionally enforces the things that
are specific to THIS plugin and would otherwise rot silently:

  * plugin.json / marketplace.json / .mcp.json are valid JSON with the fields we rely on;
  * every ${user_config.X} used in .mcp.json is declared in plugin.json userConfig;
  * every skill SKILL.md / agent .md has frontmatter with a description (and a name for agents);
  * every mcp__kasas__<tool> referenced anywhere is a real kasas tool (tools/kasas_tools.txt);
  * every --flag used with kasas_aggregate.py / kasas_chart.py is a real flag
    (derived live from each script's --help, so it can never drift).

Exit status is 0 when clean, 1 when any problem is found.
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

errors = []
checks = 0


def err(msg):
    errors.append(msg)


def ok(label):
    global checks
    checks += 1


def rel(path):
    return os.path.relpath(path, ROOT)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        err("%s: missing" % rel(path))
    except json.JSONDecodeError as e:
        err("%s: invalid JSON (%s)" % (rel(path), e))
    return None


def read_allowlist():
    path = os.path.join(ROOT, "tools", "kasas_tools.txt")
    tools = set()
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#"):
                tools.add(line)
    except FileNotFoundError:
        err("tools/kasas_tools.txt: missing")
    return tools


def frontmatter(text):
    """Return (dict_of_top_level_keys, body) or (None, text) if no block."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None, text
    fields = {}
    for line in m.group(1).splitlines():
        fm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if fm:
            fields[fm.group(1)] = fm.group(2).strip()
    return fields, m.group(2)


def script_flags(script):
    """Derive the real --flags of a helper script from its --help output."""
    path = os.path.join(ROOT, "scripts", script)
    try:
        out = subprocess.run(
            [sys.executable, path, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception as e:  # noqa: BLE001 - report and continue
        err("scripts/%s: could not run --help (%s)" % (script, e))
        return set()
    return set(re.findall(r"(-{1,2}[A-Za-z][\w-]*)", out))


# ---- 1. Manifest + MCP wiring -------------------------------------------------

plugin = load_json(os.path.join(ROOT, ".claude-plugin", "plugin.json"))
marketplace = load_json(os.path.join(ROOT, ".claude-plugin", "marketplace.json"))
mcp = load_json(os.path.join(ROOT, ".mcp.json"))

user_config_keys = set()
if isinstance(plugin, dict):
    if not plugin.get("name"):
        err(".claude-plugin/plugin.json: missing required 'name'")
    ver = plugin.get("version", "")
    if not re.match(r"^\d+\.\d+\.\d+", str(ver)):
        err(".claude-plugin/plugin.json: 'version' must be semver, got %r" % ver)
    user_config_keys = set((plugin.get("userConfig") or {}).keys())
    ok("plugin.json")

if isinstance(marketplace, dict):
    if not marketplace.get("name"):
        err(".claude-plugin/marketplace.json: missing 'name'")
    if not marketplace.get("plugins"):
        err(".claude-plugin/marketplace.json: missing 'plugins'")
    ok("marketplace.json")

if isinstance(mcp, dict):
    servers = mcp.get("mcpServers") or {}
    if not servers:
        err(".mcp.json: no mcpServers declared")
    for ref in set(re.findall(r"\$\{user_config\.([A-Za-z0-9_]+)\}", json.dumps(mcp))):
        if ref not in user_config_keys:
            err(
                ".mcp.json: references ${user_config.%s} not declared in plugin.json userConfig"
                % ref
            )
    ok(".mcp.json")


# ---- 2. Skills + agents -------------------------------------------------------

allow_tools = read_allowlist()
agg_flags = script_flags("kasas_aggregate.py")
chart_flags = script_flags("kasas_chart.py")
all_flags = agg_flags | chart_flags

md_files = []
skills_dir = os.path.join(ROOT, "skills")
if os.path.isdir(skills_dir):
    for name in sorted(os.listdir(skills_dir)):
        p = os.path.join(skills_dir, name, "SKILL.md")
        if os.path.isfile(p):
            md_files.append(("skill", name, p))
agents_dir = os.path.join(ROOT, "agents")
if os.path.isdir(agents_dir):
    for name in sorted(os.listdir(agents_dir)):
        if name.endswith(".md"):
            md_files.append(("agent", name, os.path.join(agents_dir, name)))

if not md_files:
    err("no skills or agents found")

CODE_FENCE = re.compile(r"```.*?```", re.S)
TOOL_REF = re.compile(r"mcp__kasas__(\w+|\*)")
FLAG_TOK = re.compile(r"\s(-{1,2}[A-Za-z][\w-]*)")

for kind, name, path in md_files:
    text = open(path).read()
    fm, body = frontmatter(text)
    label = rel(path)
    if fm is None:
        err("%s: missing YAML frontmatter" % label)
        continue
    if not fm.get("description"):
        err("%s: frontmatter has no 'description'" % label)
    if kind == "agent" and not fm.get("name"):
        err("%s: agent frontmatter has no 'name'" % label)

    # Tool references must be real kasas tools.
    for tool in set(TOOL_REF.findall(text)):
        if tool != "*" and tool not in allow_tools:
            err("%s: references unknown kasas tool mcp__kasas__%s" % (label, tool))

    # Helper-script flags must exist (only inspect code fences that call them).
    for block in CODE_FENCE.findall(text):
        if "kasas_aggregate.py" not in block and "kasas_chart.py" not in block:
            continue
        for flag in set(FLAG_TOK.findall(block)):
            if flag not in all_flags:
                err("%s: code block uses unknown helper flag %s" % (label, flag))
    ok(name)


# ---- report -------------------------------------------------------------------

if errors:
    print("validate_plugin: %d problem(s):" % len(errors))
    for e in errors:
        print("  - " + e)
    sys.exit(1)

print(
    "validate_plugin: OK — %d components checked, "
    "%d skills/agents, %d kasas tools, %d helper flags."
    % (checks, len(md_files), len(allow_tools), len(all_flags))
)
