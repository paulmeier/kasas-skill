<p align="center"><strong>kasas-skill</strong></p>

<p align="center">
Talk to your <a href="https://github.com/paulmeier/kasas">kasas</a> financial ledger from Claude — with full MCP access, on‑demand charts and graphs, and skills for periodic financial <em>review</em> and forward‑looking <em>planning</em>. Works in <strong>Claude Code</strong> and <strong>Claude Desktop</strong>.
</p>

<p align="center">
  <a href="https://github.com/paulmeier/kasas-skill/actions/workflows/ci.yml"><img src="https://github.com/paulmeier/kasas-skill/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/paulmeier/kasas-skill/actions/workflows/release-please.yml"><img src="https://github.com/paulmeier/kasas-skill/actions/workflows/release-please.yml/badge.svg" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

## What this is

[kasas](https://github.com/paulmeier/kasas) is a self‑hosted, single‑binary financial ledger with a built‑in **[MCP](https://modelcontextprotocol.io/) server** (≈50 tools over accounts, transactions, labels, rules, events, sync, and market data). This plugin wires Claude to that server and adds a layer of finance‑specific **skills**:

- 🔌 **Full MCP access** to kasas — every read/write/admin tool, as first‑class tools in Claude.
- 📊 **Charts & graphs** — an offline, dependency‑free renderer (Claude Code) or interactive Artifacts (Claude Desktop): bar, line, area, stacked bar, horizontal bar, pie, and donut.
- 🔎 **Review** — `cash-flow`, `spending-breakdown`, `net-worth`, and a comprehensive `financial-review`.
- 🧭 **Planning** — `financial-plan` for budgets, savings‑goal timelines, runway, and net‑worth projections with what‑if scenarios.
- 🏷️ **Hygiene** — `categorize` to label transactions and build reusable kasas rules.

Everything is **penny‑accurate**: kasas returns amounts as signed decimal strings, and the bundled tooling does money math with exact decimals — never floats.

## Prerequisites

1. A running **kasas** instance you can reach (e.g. `http://localhost:8080`). See the [kasas quick start](https://github.com/paulmeier/kasas#quick-start).
2. If your kasas is secured (recommended), its **dashboard token** (Settings → Dashboard security, or `KASAS_DASHBOARD_TOKEN`). The MCP‑over‑HTTP endpoint is gated by the dashboard token — **not** API keys.
3. **Python 3.8+** on your `PATH` (used by the bundled chart/aggregation scripts in Claude Code; standard library only, no pip installs).

---

## Install — Claude Code

The plugin ships its own marketplace manifest, so you can install it straight from this repo:

```text
/plugin marketplace add paulmeier/kasas-skill
/plugin install kasas@kasas
```

…or from a local checkout while developing:

```text
/plugin marketplace add /Users/paulmeier/Projects/kasas-skill
/plugin install kasas@kasas
```

On enable, Claude Code prompts for two **user‑config** values (you can change them later with `/plugin`):

| Setting | Default | Notes |
| --- | --- | --- |
| `kasas_url` | `http://localhost:8080/mcp` | Your kasas streamable‑HTTP MCP endpoint. |
| `kasas_token` | _(blank)_ | The kasas **dashboard token**. Stored in your OS keychain (it is marked `sensitive`). Leave blank only if kasas runs unauthenticated on a trusted network. |

The token is injected as `Authorization: Bearer …` on the MCP connection — see [`.mcp.json`](.mcp.json).

> Prefer a local subprocess instead of HTTP? kasas exposes both transports — `kasas mcp` over stdio needs no token. See the Claude Desktop section for the stdio block (it works for a local Claude Code setup too).

Verify it worked:

```text
/kasas:kasas-setup
```

This probes the connection, lists your accounts and balances (grouped by currency), shows sync/source status, and tells you exactly what to fix if auth fails.

---

## Install — Claude Desktop

Claude Desktop supports the two pieces of this plugin that matter for finance work: **the kasas MCP connection** and **Skills** (the [Agent Skills](https://agentskills.io) open standard). Charts render as interactive **Artifacts**.

### 1. Connect kasas (MCP)

Pick whichever fits your setup — see [`desktop/claude_desktop_config.example.json`](desktop/claude_desktop_config.example.json) for ready‑to‑paste blocks:

- **Local stdio (simplest, tokenless):** add a `kasas` server that runs the kasas binary's MCP subcommand —
  `command: /path/to/kasas`, `args: ["-config", "/path/to/config.toml", "mcp"]`. No token needed; it's a local process.
- **Remote / HTTP:** add kasas as a **custom connector** (Settings → Connectors → *Add custom connector*) pointing at `http://<host>:8080/mcp`, or bridge to it with the `mcp-remote` shim so you can pass the dashboard token as a bearer header (see the example file).

### 2. Add the Skills

Claude Desktop loads skills from the [`skills/`](skills) directory of this repo. Add them via Settings → **Capabilities/Skills** (upload the skill folder, or the whole `skills/` set). Each skill — `cash-flow`, `spending-breakdown`, `net-worth`, `financial-review`, `financial-plan`, `categorize`, `kasas-charts`, `kasas-setup` — then triggers automatically when you ask the matching question.

> Slash‑commands and subagents are Claude **Code** features; in Claude Desktop the same capabilities live in the skills, which Claude invokes by intent. The bundled Python scripts are the Claude **Code** rendering path; in Desktop, the skills render charts as Artifacts instead.

---

## What you can do

Once connected, just ask — or invoke a skill directly in Claude Code with `/kasas:<name>`:

| Skill / command | Ask it things like | Writes? |
| --- | --- | --- |
| **`kasas-setup`** | "Is kasas connected? What's in my ledger?" | trigger‑sync only (confirmed) |
| **`kasas-charts`** | "Chart my spending by category." · "Graph net cash flow by month." | read‑only |
| **`cash-flow`** | "How's my cash flow this year? Am I saving?" | read‑only |
| **`spending-breakdown`** | "Where did my money go in May? Biggest merchants?" | read‑only |
| **`net-worth`** | "What's my net worth? Assets vs liabilities, and the trend." | read‑only |
| **`financial-review`** | "Run my monthly / quarterly financial review." | read‑only |
| **`financial-plan`** | "Help me budget." · "When can I afford X?" · "Project my savings if I cut spending 10%." | optional (confirmed) |
| **`categorize`** | "Categorize my uncategorized transactions and set up rules." | yes (confirmed) |

In Claude Code there's also a **`financial-analyst`** subagent for deep, multi‑step analysis — delegate to it and it works the ledger read‑only and returns a written report with charts.

Skills that change anything in kasas (categorize, saving a budget, triggering a sync) **always show a preview and ask before writing**.

---

## Charts

The plugin renders charts two ways, chosen automatically by environment:

- **Claude Code** → the bundled offline renderer writes a single self‑contained HTML file (inline SVG, no internet, no libraries) you can open in any browser, light/dark aware.
- **Claude Desktop** → an interactive **Artifact** with the same data.

Under the hood (Claude Code), the pipeline is two small, stdlib‑only scripts in [`scripts/`](scripts):

```sh
# 1) fetch transactions with a kasas MCP tool and save the JSON, then:
python3 scripts/kasas_aggregate.py txns.json \
    --group-by label:category --sign outflow --metric outflow \
    --top 10 --as-chart donut --title "Spending by category" --currency USD \
  | python3 scripts/kasas_chart.py - -o spending.html
```

- **`kasas_aggregate.py`** — decimal‑safe grouping of kasas transactions (`--group-by month|week|day|quarter|year|account|payee|label:<key>|…`, `--metric net|abs|inflow|outflow|count`, `--split-sign` for income‑vs‑expense, `--top N`, `--since/--until`, `--as-chart <type>`). Outputs either summary JSON or a ready chart spec.
- **`kasas_chart.py`** — turns a chart spec into a standalone HTML/SVG chart (`bar`, `hbar`, `line`, `area`, `stacked-bar`, `pie`, `donut`).

Run either with `--help` for the full option list.

---

## How it's wired

```
kasas-skill/
├── .claude-plugin/
│   ├── plugin.json          # manifest + userConfig (kasas_url, kasas_token)
│   └── marketplace.json     # so `/plugin marketplace add` works from this repo
├── .mcp.json                # the kasas MCP server (HTTP /mcp + bearer token)
├── skills/                  # one folder per skill (works in Code + Desktop)
│   ├── kasas-setup/  kasas-charts/  cash-flow/  spending-breakdown/
│   ├── net-worth/  categorize/  financial-review/  financial-plan/
├── agents/
│   └── financial-analyst.md # Claude Code subagent for deep analysis
├── scripts/                 # offline chart + aggregation helpers (Python stdlib)
│   ├── kasas_aggregate.py  kasas_chart.py
├── tools/                   # CI validators (plugin + skill linting)
├── tests/                   # pipeline smoke tests + fixtures
└── desktop/
    └── claude_desktop_config.example.json
```

## Development

| Task | Command |
| --- | --- |
| Validate the plugin + skills | `make validate` |
| Lint the Python helpers | `make lint` |
| Format check | `make fmt-check` (auto-fix with `make fmt`) |
| Run the pipeline tests | `make test` |
| Everything CI runs | `make ci` |

`main` is protected: changes land through pull requests whose titles follow
[Conventional Commits](https://www.conventionalcommits.org/) and must pass CI
(Format · Lint · Validate · Test). [release-please](https://github.com/googleapis/release-please)
maintains a release PR from those commits; merging it bumps the version in
`plugin.json`, updates `CHANGELOG.md`, and tags a GitHub Release. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Security & scope notes

- The plugin is **read‑first**. Only `categorize`, the optional budget‑saving step of `financial-plan`, and the optional sync in `kasas-setup` write to kasas — and each asks before doing so. The `financial-analyst` subagent is strictly read‑only.
- The `kasas_token` is a **sensitive** user‑config value, stored in your OS keychain rather than `settings.json`.
- MCP‑over‑HTTP is gated by the kasas **dashboard token**; keep kasas on a trusted network regardless (e.g. behind Tailscale). See [kasas → Authentication](https://github.com/paulmeier/kasas/blob/main/docs/interfaces/authentication.md).
- Currencies are **never** mixed or converted — kasas tracks one currency per account, and every skill reports each currency separately.
- The planning skills produce **education/analysis, not personalized financial advice**.

## License

MIT — see [LICENSE](LICENSE).
