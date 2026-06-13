---
name: Financial Review
description: When the user asks to 'review my finances', do a 'monthly/quarterly money review', or 'see how I did this period', run a comprehensive periodic review — cash flow, spending by category, net worth, notable transactions, data hygiene, and charts — comparing against the prior comparable period.
argument-hint: "[period, e.g. 'May 2024' or 'Q1' or '2024']"
allowed-tools: mcp__kasas__* Bash Read Write
---

A comprehensive periodic financial review (monthly, quarterly, or annual). This orchestrates the techniques from the other kasas skills — cash-flow, spending-breakdown, and net-worth — into one report with several charts and a tight narrative. It is read-only analysis, not regulated financial advice.

## Step 1 — Resolve the period and the prior comparable period
Parse the `[period]` argument (default: the most recent complete calendar month). Compute an inclusive RFC3339 range and an equal-length **prior** range to compare against:
- `May 2024` → 2024-05-01..2024-05-31; prior = April 2024.
- `Q1` / `Q1 2024` → Jan–Mar; prior = Q4 of the previous year.
- `2024` → full year; prior = 2023.
State the resolved current and prior windows back to the user before fetching, so they can correct you.

## Step 2 — Fetch the transactions once, reuse everywhere
Pull every transaction in the **combined** current+prior window so a single dataset serves all sections. Call `search_transactions` with a date filter, e.g. `q: "date:2024-01..2024-06"` (use `date:2024` for an annual review), with a generous `limit` (e.g. 5000) and paginate via `offset` if `total` exceeds what you received.

- **Claude Code:** write the returned `transactions` array to `/tmp/kasas_review.json`. Also call `list_accounts` and save to `/tmp/kasas_accounts.json` for net worth (Step 5).
- **Claude Desktop:** keep the array in memory; aggregate yourself with exact-decimal math (amounts are signed decimal strings, outflows negative — never floats).

Currency is per-account. Group every number by account currency and report each currency separately; do not mix or FX-convert — note that FX is not converted.

## Step 3 — Cash flow (reuse cash-flow approach)
Compute total income, total expenses, net, and **savings rate** (net ÷ income) for current and prior periods.

**Claude Code** — split income vs expenses by month:
```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_review.json \
  --group-by month --split-sign --exclude-pending --currency USD \
  --as-chart bar --title "Income vs Expenses" --subtitle "<period> vs prior" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_cashflow.html
```
For the bare numbers (income/expense/net/count) drop `--as-chart` and read the JSON `total` block. The split-sign metric is the magnitude of income (positives) and expenses (negative magnitudes) per month.

**Desktop** — sum positives = income, magnitude of negatives = expenses, difference = net.

## Step 4 — Spending breakdown (reuse spending-breakdown)
Category mix and top merchants for the **current** period only, plus the per-category change vs prior.

**Claude Code** — categories from the `category` label (folds the long tail into Other):
```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_review.json \
  --group-by label:category --metric outflow --since <curStart> --until <curEnd> \
  --exclude-pending --top 12 --unlabeled-as "(uncategorized)" --currency USD \
  --as-chart donut --title "Spending by category" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_categories.html
```
Run the same command with `--group-by payee --metric outflow --top 10` (no chart needed) to get top merchants. To compute the per-category delta, run the aggregate once for the current window and once for the prior window and diff the `groups[].value` by key.

**Desktop** — group `outflow` magnitude by `labels.category` (fallback "(uncategorized)") for current and prior; render the current mix as a donut Artifact.

## Step 5 — Net worth and its change (reuse net-worth)
From `list_accounts`, current net worth per currency = sum of account `balance` strings (signed decimals; treat liabilities' negative balances correctly). Account `balance` is source-reported, NOT derived from transactions — do not recompute it from the ledger. kasas does not store historical balances, so estimate the period's net-worth **change** as the net cash flow from Step 3 (state this is an approximation; balances reflect today, not the period boundary). Note any account whose `balance_date` is stale.

## Step 6 — Notables
- **Largest transactions:** within the current window, rank by |amount|. Use `search_transactions` with `q: "date:<curRange> amount:<0"` for big outflows (and `amount:>0` for big inflows), then sort the returned array by absolute amount and take the top ~10.
- **New / irregular merchants:** payees present in the current period but absent from the prior period.
- **Recurring / subscriptions (inferred):** payees that appear in most months with a similar amount (e.g. ±5%). Detect by grouping `--group-by payee --metric count` and inspecting per-payee amounts. Explain you infer recurring charges from repeated payee+amount and may misclassify — this is a heuristic, not a flag from the source.

## Step 7 — Data hygiene
Count **uncategorized** transactions (`q: "date:<curRange> -label:category"`, read `total`) and **pending** ones (`q: "date:<curRange> pending:true"`). If either share is high (say >15% of count), recommend running `categorize` and note that pending amounts may still change.

## Step 8 — Produce the charts
Render at least three: income-vs-expenses bar (Step 3), category donut (Step 4), and a net-by-month line.

**Claude Code** — net line:
```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_review.json \
  --group-by month --metric net --exclude-pending --currency USD \
  --as-chart line --title "Net by month" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_net.html
```
Tell the user each `.html` path and offer to open them (macOS: `open /tmp/kasas_cashflow.html`). The files are self-contained and offline.

**Claude Desktop** — render the same three as interactive Artifacts (HTML/SVG or React) from the numbers you aggregated. One Artifact with tabs or stacked sections is fine.

In **both** environments, also print the underlying numbers as compact markdown tables — never the chart alone. Suggested tables: (a) cash-flow summary (Income, Expenses, Net, Savings rate) current vs prior; (b) top categories with current, prior, and Δ; (c) top merchants; (d) net worth by account/currency.

## Step 9 — Narrative and actions
Close with a tight write-up:
- **3–5 key observations** (e.g. "savings rate fell from 22% to 9% — driven by a $1,400 rise in Travel").
- **3–5 concrete suggested actions** (e.g. "review the 6 uncategorized transactions", "the $48 SaaS charge recurs monthly — confirm it's still wanted"). Make them specific and grounded in the data.

State plainly this is informational analysis of the user's own ledger, not regulated financial advice.

## Edge cases
- Per the data facts, keep currencies separate; if accounts span multiple currencies, produce one cash-flow/spending set per currency and say FX is not converted.
- If the period has no transactions, report that plainly and skip the charts.
- Exclude pending transactions from cash-flow and spending totals (`--exclude-pending`) but surface their count in Step 7, since pending amounts can change.
- If `search_transactions` paginates, keep fetching by `offset` until you have all `total` rows before aggregating, or the comparison will be wrong.
- If the `category` label is largely unused, the donut will be dominated by "(uncategorized)" — say so and point the user to `categorize`.
- Manual vs synced source does not change the math here, but mention if a large share of activity is still pending sync (`sync_status`).
