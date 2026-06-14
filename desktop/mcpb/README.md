# kasas — Claude Desktop extension (`.mcpb`)

A one-click [MCP Bundle](https://github.com/modelcontextprotocol/mcpb) that connects
Claude Desktop to your local **kasas** ledger. It uses the tokenless local stdio
transport: a tiny zero-dependency Node launcher ([`server/index.js`](server/index.js))
runs `kasas -config <your-config> mcp` with Claude Desktop's bundled Node and pipes
MCP straight through — exposing all kasas tools in chat.

## Build

```sh
make mcpb          # -> desktop/kasas.mcpb
# or directly:
npx -y @anthropic-ai/mcpb@2 pack desktop/mcpb desktop/kasas.mcpb
```

Validate the manifest without packing:

```sh
make mcpb-validate
```

The built `*.mcpb` is gitignored — attach it to a GitHub Release rather than committing it.

## Install (end user)

1. Double-click `kasas.mcpb`, **or** in Claude Desktop go to **Settings → Extensions**
   and add the file.
2. When prompted, set the two config values:
   - **kasas binary** — path to your `kasas` executable.
   - **kasas config.toml** — path to the TOML config passed as `-config`.

   On a Sillview-managed install these are:
   - `~/Library/Application Support/Sillview/kasas/bin/kasas`
   - `~/Library/Application Support/Sillview/kasas/config.toml`
3. Start a new chat and ask, e.g., *"what kasas accounts do I have?"*

> **Skills are separate.** This extension provides the MCP **connection** only.
> To get the kasas workflow skills (cash-flow, spending-breakdown, net-worth,
> financial-review, financial-plan, categorize, kasas-charts), upload the repo's
> [`skills/`](../../skills) folders via **Settings → Capabilities**.

## Notes

- **Tokenless:** stdio is a local process, so no dashboard token is stored in
  Claude Desktop's config. (The HTTP transport — `mcp-remote` + bearer token — is
  the alternative; see [`../claude_desktop_config.example.json`](../claude_desktop_config.example.json).)
- **Concurrency:** the launcher opens the same SQLite DB as a running `kasas serve`.
  kasas uses WAL mode, so concurrent access is safe.
- **Remote kasas:** this stdio extension assumes the binary is on the same machine.
  For a kasas on another host, use the HTTP/`mcp-remote` block instead.
