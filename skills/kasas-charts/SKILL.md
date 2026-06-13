---
name: kasas Charts
description: When the user wants to build, draw, graph, chart, or plot ANY visualization from their kasas finances, turn a request into a transaction selection + grouping + metric + chart type and render it (offline HTML in Claude Code, an interactive Artifact in Claude Desktop) alongside the underlying numbers table.
argument-hint: "[what to chart]"
allowed-tools: mcp__kasas__search_transactions mcp__kasas__list_transactions mcp__kasas__list_accounts mcp__kasas__list_labels Bash Read Write
---

# kasas Charts

The general-purpose charting engine for kasas. Other analysis skills (cash-flow, spending-breakdown, net-worth, financial-review) lean on this one. Use it whenever the user wants a picture of their money: a trend, a composition, a comparison, income vs. expenses, or net cash flow.

## Step 1 — Interpret the request into four decisions

Translate `$ARGUMENTS` (the user's ask) into a **selection**, a **grouping dimension**, a **metric**, and a **chart type**. Use this mapping:

| User intent | group-by | metric | chart type |
|---|---|---|---|
| Trend over time ("spending each month", "balance over time") | `month` / `week` / `quarter` | `outflow` or `net` | `line` or `area` |
| Composition / share of a whole ("where my money goes", "% by category") | `label:category` or `payee` | `outflow` | `pie` or `donut` |
| Comparison / ranking ("top merchants", "by account") | `payee` / `account` / `label:<key>` | `outflow` or `abs` | `hbar` (ranking) or `bar` |
| Income vs. expenses over time | `month` / `week` + `--split-sign` | (split) | `stacked-bar` or `bar` |
| Net cash flow over time | `month` / `week` | `net` | `line` |

Metric reminder: amounts are **signed decimal strings** (outflows negative). `--metric outflow` reports the positive magnitude of negative txns; `inflow` keeps positives; `net` is the signed sum; `abs` sums absolute values; `count` counts. `--split-sign` emits two series, Income and Expenses, and overrides `--metric` — ideal for cash-flow comparisons.

If the request is ambiguous (no period, no obvious dimension), pick a sensible default (last 12 months, group by month) and state your choice in one line so the user can correct it.

## Step 2 — Fetch the data and save the JSON

Pick the right source for the selection:
- Targeted query (a category, a payee, an amount/date filter, a label): **search_transactions** with the kasas `q=` language, e.g. `q="amount:<0 date:2024 -label:reimbursed"`. It returns `{query, total, transactions:[...]}`.
- A whole account or simple account+date-range pull: **list_transactions** with `account_id` and a date range.

Always call **list_accounts** first to learn each account's `currency` (currency is per-account; there is no per-transaction currency). If the selection spans more than one currency, chart each currency separately and never convert or mix them.

In Claude Code, save the returned transactions array (the `transactions` field from search, or the list from list_transactions) to a temp file, e.g. `/tmp/kasas_txns.json`.

## Step 3 — Render in Claude Code (Bash available)

Pipe the saved JSON through the bundled scripts. `kasas_aggregate.py --as-chart` emits exactly the spec `kasas_chart.py` consumes, so it's a one-line pipe to a self-contained, offline HTML file:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_txns.json \
  --group-by <DIM> --metric <METRIC> [--sign outflow] [--top N] [--exclude-pending] \
  --currency <CUR> --as-chart <TYPE> --title "..." --subtitle "..." \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas-chart.html
```

The aggregate step does all money math with `Decimal` at 2dp — never compute totals with floats yourself. Then:
1. Run the same aggregate **without** `--as-chart` (default JSON output) to get `groups[]` with `value/income/expense/net/count`, and print those as a compact markdown table.
2. Tell the user the exact `.html` path and offer to open it: on macOS `open /tmp/kasas-chart.html`.

Always pass `--currency` from the relevant account(s). For one chart per currency, filter the txns by their accounts and run the pipe once per currency, writing distinct output paths.

## Step 4 — Render in Claude Desktop (no Bash)

There is no shell, so do the aggregation yourself: treat every `amount` as an exact decimal to 2 decimal places, keep outflows negative, group by the chosen dimension, and compute the metric (for `outflow`, sum the magnitudes of negative amounts; for `net`, sum signed; for split-sign, total positives as Income and magnitudes of negatives as Expenses). Then render an **interactive Artifact** (an HTML or React chart) that shows the same series, titled with the currency. Match the chart type from Step 1.

## Step 5 — Always show the numbers, respect currency

In BOTH environments, print the underlying figures as a compact markdown table beneath the chart — never the picture alone. Include a per-group value plus a total row, and label amounts with the account currency. If multiple currencies are present, render and table them separately and note that FX is not converted.

## Worked examples

**A) Spending donut by category, this year (composition):**
```
# search_transactions q="amount:<0 date:2024"  -> save txns to /tmp/kasas_txns.json
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_txns.json \
  --group-by label:category --metric outflow --sign outflow --top 8 \
  --unlabeled-as "(uncategorized)" --currency USD \
  --as-chart donut --title "Spending by category (2024)" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas-chart.html
```

**B) Monthly net cash flow line, last 12 months (trend):**
```
# list_transactions account_id=<acct> with a 12-month date range -> /tmp/kasas_txns.json
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_txns.json \
  --group-by month --metric net --exclude-pending --currency USD \
  --as-chart line --title "Net cash flow by month" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas-chart.html
```

**C) Income vs. expenses by month (comparison, split-sign):**
```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_txns.json \
  --group-by month --split-sign --currency USD \
  --as-chart stacked-bar --title "Income vs. expenses" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas-chart.html
```

**D) Top 10 merchants by spend (ranking, hbar):**
```
# search_transactions q="amount:<0 date:>=2024-01-01"  -> /tmp/kasas_txns.json
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_txns.json \
  --group-by payee --metric outflow --sign outflow --top 10 --currency USD \
  --as-chart hbar --title "Top merchants by spend" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas-chart.html
```

## Edge cases
- **No transactions match** the selection: say so, suggest widening the date range or relaxing the `q=` filters, and skip rendering.
- **Multiple currencies** in the selection: one chart + one table per currency; state that amounts are not FX-converted.
- **Pending transactions** can distort trends — offer `--exclude-pending` (Claude Code) or drop `pending:true` rows yourself (Desktop) when the user wants settled-only figures.
- **Too many categories/payees** for pie/donut: cap with `--top N` (folds the rest into "Other"); pie/donut only read positive magnitudes, so pair them with `--metric outflow --sign outflow`.
- **Uncategorized data**: set `--unlabeled-as "(uncategorized)"` so missing-label txns get a clear bucket instead of vanishing; if categories are sparse, suggest running `categorize` first.
- **Source-locked rows**: `source:"simplefin"` txns are synced/read-only — fine to chart, never edit them here.
