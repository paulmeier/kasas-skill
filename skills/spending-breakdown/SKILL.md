---
name: Spending Breakdown
description: Use when asked "where is my money going", "spending by category", or "biggest expenses/merchants this period" — categorizes outflows for a period into a category mix (donut) and top merchants (bar), with a category table and insights, decimal-exact and per-currency.
argument-hint: "[period]"
allowed-tools: mcp__kasas__search_transactions mcp__kasas__list_transactions mcp__kasas__list_labels mcp__kasas__list_accounts Bash Read Write
---

# Spending Breakdown

Show where the money went in a period: a category mix, the top merchants, and a clean table with a few insights. Read-only — this skill never writes to the ledger. All money is summed as exact decimals at 2dp (outflows are negative `amount` strings), each currency reported separately, and FX is never converted.

## Step 1 — Resolve the period and currency

1. Parse `$ARGUMENTS` into a window. "this month" → first..last of the current month; "last month", "this quarter", "ytd", "2024", "Q2 2024", "last 30 days" similarly. With no argument, default to the **current calendar month** and say so. Build an ISO/RFC3339 range and the kasas search shorthand:
   - A full year → `date:2024`; a month → `date:2024-03`; an explicit window → `date:2024-01-01..2024-03-31`.
2. Call `list_accounts`. If accounts span **multiple currencies**, you must process each currency group on its own — money from different currencies is never mixed or summed. Pick the currency to report (default: the one with the most accounts) and tell the user you are reporting that currency; offer to repeat for the others.

## Step 2 — Fetch outflows

Call `search_transactions` with the period and a negative-amount filter (outflows only):

```
search_transactions  q="amount:<0 date:2024-03"  limit=1000
```

If you scoped to one currency, also constrain to its accounts (e.g. add `account:Checking`, or run once per account and concatenate). The result is `{query, total, transactions:[...]}`. If `total` exceeds your `limit`, page with `offset` until you have them all, or narrow the window — never analyze a truncated set silently. If `total` is 0, tell the user there were no outflows in that window and stop.

## Step 3a — Render (Claude Code, Bash available)

Save the transactions array and build TWO charts with the bundled helpers. Use `--sign outflow --metric outflow` so values are positive spend magnitudes, and `--currency` so labels are right. The aggregator buckets transactions with no `category` label as `(uncategorized)`.

Save the JSON, then pipe:

```bash
# write the transactions array returned by search_transactions to /tmp/kasas_spend.json first

# Category mix (donut)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_spend.json \
  --group-by label:category --sign outflow --metric outflow \
  --top 10 --currency USD --unlabeled-as "(uncategorized)" \
  --as-chart donut --title "Spending by category" --subtitle "Mar 2024 · USD" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_categories.html

# Top merchants (horizontal bar)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_spend.json \
  --group-by payee --sign outflow --metric outflow \
  --top 10 --currency USD \
  --as-chart hbar --title "Top merchants" --subtitle "Mar 2024 · USD" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_merchants.html
```

Run the category aggregation once more **without** `--as-chart` to get the exact JSON (`total` and per-group `value`/`count`) for your table. Tell the user both `.html` paths and offer to open them (macOS: `open /tmp/kasas_categories.html`). These files are self-contained and offline.

## Step 3b — Render (Claude Desktop, no Bash)

Aggregate the numbers yourself: group the outflows by their `labels.category` (missing → `(uncategorized)`) and separately by `payee`. Sum each group's `amount` as exact decimals to 2dp, reporting spend as a positive magnitude. Keep the top 10 of each, folding the remainder into `Other`. Then render an interactive **Artifact** with the same two views — a donut of the category mix and a horizontal bar of the top merchants — using the figures you computed (never floats, never a different number than the table).

## Step 4 — Surface the uncategorized share

Compute the `(uncategorized)` bucket's share of total spend. If it is **large (say ≥ 20%)**, call it out explicitly and recommend running **categorize** to label those transactions, then re-running this skill for a sharper picture. If labels are mostly absent across the board (`list_labels` shows no `category` key, or nearly every txn is uncategorized), note that the breakdown is merchant-driven for now.

## Step 5 — Optional prior-period comparison

If the user asks to compare to a prior period (e.g. "vs last month"), resolve the second window, repeat Steps 2–3 for it, then show a per-category delta table: each category's spend this period, last period, and the change (absolute and %). Sort by largest increase. Compare only within the same currency.

## Step 6 — Present

Always show the **numbers as a markdown table**, never the chart alone. Lead with a category table:

| Category | Spend | % of total | Txns |
|---|---:|---:|---:|
| Groceries | $612.40 | 28% | 14 |
| Dining | $441.18 | 20% | 22 |
| (uncategorized) | $327.08 | 15% | 11 |
| **Total** | **$2,180.55** | **100%** | **96** |

Then reference the donut and top-merchants bar (paths in Claude Code, Artifact in Desktop), followed by **2–3 insights**, e.g.:
- Biggest category and its share of total spend.
- Fastest-growing category vs the prior period (only if Step 5 ran).
- Notable one-offs — a single unusually large outflow that inflates a category (you can confirm it with `search_transactions q="amount:<-500 date:RANGE"`).

## Edge cases

- **Multiple currencies:** never combine. Produce a separate table + charts per currency, each clearly labeled, and state that FX is not converted.
- **Pending transactions:** included by default. Add `--exclude-pending` (Claude Code) or filter `pending == true` yourself (Desktop) if the user wants only settled spend, and say which you did.
- **Refunds / reimbursements:** these land as positive `amount`s and are excluded by the `amount:<0` filter, so a refunded purchase still shows its full outflow. If the user wants net-of-refunds, follow refund relationships (`rel:refund_of`) or exclude reimbursed items with `-label:reimbursed`, and note the adjustment.
- **Empty or truncated results:** if no outflows, say so plainly; if `total` exceeded what you fetched, page or narrow before presenting — never analyze a partial set silently.
- **No `category` labels at all:** fall back to a merchant-only breakdown and recommend **categorize**.

For income vs expenses over time use **cash-flow**; for arbitrary ad-hoc charts use **kasas-charts**; to add the missing labels use **categorize**.
