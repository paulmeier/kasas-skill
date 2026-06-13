---
name: kasas Setup & Health Check
description: Use when first installing the kasas plugin, when kasas "isn't connecting" or returns auth errors, or when the user asks "is kasas working / what's in my ledger" — probes the MCP connection, summarizes accounts and balances by currency, checks source/sync readiness, and points to the other kasas skills.
allowed-tools: mcp__kasas__* Bash Read
---

Connect-and-verify onboarding for the kasas ledger. This skill probes the MCP connection, gives clear fix-it instructions when it fails, then summarizes the ledger and its sync health so the user knows kasas is working and what data is available. It is read-only except for an optional `trigger_sync`, which you MUST confirm before calling.

## Step 1 — Probe the connection
Call `list_accounts` (and `list_organizations`). One of three things happens:

- **It returns data** → the connection works. Continue to Step 2.
- **It errors with auth / 401 / unauthorized / "missing bearer"** → the token is wrong or missing. Give the user the fix for their environment:
  - **Claude Code:** run `/plugin`, open this plugin's user-config, and set `kasas_url` (default `http://localhost:8080/mcp`) and `kasas_token`. The token is the kasas **dashboard token**, NOT an API key created via `create_api_key`. If kasas runs unauthenticated on a trusted LAN, `kasas_token` may be left blank.
  - **Claude Desktop:** add kasas as a custom connector. The simplest path for a local kasas is the stdio subprocess `kasas mcp` (no token needed — it is a local process); to use MCP-over-HTTP with a bearer token, bridge through `mcp-remote`. Point them at the plugin `README.md` and `desktop/claude_desktop_config.example.json`, which has both ready-to-merge blocks.
- **It errors with connection refused / timeout / DNS** → kasas isn't reachable at `kasas_url`. Have them confirm kasas is running and the URL/port are correct (the MCP path is `/mcp`, e.g. `http://localhost:8080/mcp`), then retry.

Report exactly which case occurred. If it failed, stop here after giving the fix — do not fabricate ledger data.

## Step 2 — Summarize the ledger
From the `list_accounts` result, build the inventory. Each account has `name`, `currency`, `balance` (signed decimal string), `balance_date`, `source` (`simplefin` or `manual`), and `org_id`. From `list_organizations` you have `name`/`domain` per org.

**CRITICAL — group balances BY CURRENCY and never sum across currencies.** There is no per-transaction currency and no FX conversion. Compute one balance subtotal per ISO currency code.

- **Claude Code (Bash available):** save the accounts JSON and let the decimal helper net the balances per currency. Pass `--value-field balance` (accounts hold `balance`, not `amount`) and `--group-by currency`:
  ```bash
  # write the list_accounts result to /tmp/kasas_accounts.json first, then:
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_accounts.json \
      --group-by currency --value-field balance --metric net
  ```
  Each row in `groups` is one currency: `net` is the net balance, `income` the asset balances, `expense` the owed (negative) balances. Ignore the blended `total` (it sums across currencies, which is meaningless) — report each currency's row separately.
- **Claude Desktop (no Bash):** add the `balance` strings as exact decimals to 2dp, bucketed by `currency`. Do not use floats.

Present a markdown table — Account, Org, Currency, Balance, Source, Balance date — then a short "Totals by currency" list with one line per currency (e.g. `USD: 12,430.18 across 3 accounts` / `EUR: 980.00 across 1 account`). Note that `simplefin` accounts are read-only (synced) and `manual` accounts are user-editable. State plainly that balances are reported by the source/user, not derived by summing transactions.

## Step 3 — Source & sync readiness
Call `list_sources` and `sync_status`.

- Report each source and whether kasas can sync it.
- Report the last sync time from `sync_status`. If it is stale (e.g. older than ~24h) or never run, say so and **offer** to refresh. `trigger_sync` is a WRITE — only call it after the user explicitly says yes. If they decline, skip it. After a sync, you may re-run `sync_status` to confirm it completed.

If there are zero sources and only `manual` accounts, that is normal — note that the ledger is manual-entry and there is nothing to sync.

## Step 4 — Transaction sanity check
Call `search_transactions` with an empty query and a small limit to confirm transactions exist:

```
search_transactions(q="", limit=5)
```

The result is `{query, total, transactions:[...]}`. Report `total` (the full count, not just the 5 returned) and show 1–2 sample rows (date, payee/description, amount with its account's currency) so the user sees real data flowing. If `total` is 0, say the ledger is empty and suggest running a sync (Step 3) or adding a manual transaction.

## Step 5 — Point to the other skills
Close with a short menu so the user knows what to do next:

- **kasas-charts** — turn any transaction query into a chart.
- **cash-flow** — income vs. expenses over time.
- **spending-breakdown** — where the money goes, by category/payee.
- **net-worth** — balances and net worth across accounts (per currency).
- **categorize** — label and tidy uncategorized transactions.
- **financial-review** — a periodic look-back over the ledger.
- **financial-plan** — forward-looking budgeting and projections.

## What to present
1. Connection verdict (working / how to fix), stated first.
2. The accounts table plus per-currency totals.
3. Source list and last-sync line (with the optional sync offer).
4. Transaction `total` and a sample row or two.
5. The next-steps menu.

## Edge cases
- **Auth vs. connection errors are different** — 401 means fix the token; refused/timeout means kasas isn't reachable. Diagnose the right one.
- **Multiple currencies** — keep them separate everywhere; never present a single blended total. Note FX is not converted.
- **Multiple organizations** — group accounts under their org and show org names from `list_organizations`.
- **Empty ledger** — accounts may exist with zero transactions; report that honestly rather than inventing activity.
- **Stale or never-run sync** — surface it and offer `trigger_sync`, but never sync without explicit confirmation.
- **No Bash (Desktop)** — all math is done inline as exact 2dp decimals; the helper scripts are Claude Code-only and must not be referenced as runnable there.
- **Read-only by default** — the only mutation this skill may perform is `trigger_sync`, and only after the user agrees.
