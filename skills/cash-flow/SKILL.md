---
name: Cash Flow
description: When the user asks "how's my cash flow", "income vs spending", "am I saving", or "what's my monthly burn" — analyze income vs expenses and net cash-flow over a period with month-by-month charts and a savings rate.
argument-hint: "[period, e.g. 'last 6 months' or '2024']"
allowed-tools: mcp__kasas__search_transactions mcp__kasas__list_transactions mcp__kasas__list_accounts Bash Read Write
---

Income vs. expense and net cash-flow over a period. Use this for "how's my cash flow", "income vs spending", "am I saving each month", or "what's my monthly burn". Read-only: this skill never writes to the ledger.

## Steps

### 1. Resolve the period to a date range
Default to the last 6 full months if the user gives no period. Map the request to a `date:` filter for the search query language (today is the reference point):
- "last 6 months" / "monthly burn" → `date:>=<6 months ago, 1st of month>`
- "2024" → `date:2024`  •  "this year" → `date:<current year>`  •  "Q1 2024" → `date:2024-01..2024-03`
- explicit range → `date:YYYY-MM-DD..YYYY-MM-DD`

### 2. Check currencies before aggregating
Call `list_accounts`. Cash-flow math is only valid within ONE currency. If accounts span multiple currencies, you MUST run steps 3-5 once per currency (filter the txns by the `account_id`s of that currency) and present each currency in its own section. Never sum or convert across currencies; state that FX is not converted.

### 3. Fetch transactions
Call `search_transactions` with `q` = your date filter. To drop internal transfers between the user's own accounts so they don't inflate both income and expenses, append a label/relationship filter IF the user marks them — e.g. `date:2024 -label:transfer` or `date:2024 -rel:transfer_of`. Tell the user which exclusion you applied (or that none was applied, so transfers may appear on both sides). Page with `limit`/`offset` until you have all rows (`total` is in the response). Outflows are NEGATIVE, inflows POSITIVE.

### 4a. Claude Code (Bash available) — scripts, deterministic and offline
Save the returned transaction array to a temp file, then build the charts. Reference scripts with the literal `${CLAUDE_PLUGIN_ROOT}/scripts/` prefix.

Income vs. Expenses by month (two auto-colored series, green/red):
```
# /tmp/kasas_cashflow.json holds the JSON array of transactions
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_cashflow.json \
  --group-by month --split-sign --currency USD --exclude-pending \
  --as-chart stacked-bar --title "Cash Flow" --subtitle "Income vs Expenses by month" \
| python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_cashflow.html
```
Net cash-flow line (signed sum per month — blue):
```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_cashflow.json \
  --group-by month --metric net --currency USD --exclude-pending \
  --as-chart line --title "Net Cash Flow" --subtitle "Net per month" \
| python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_net.html
```
Get the totals (income, expense, net, count) decimal-safely from the JSON form (no `--as-chart`):
```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_cashflow.json \
  --group-by month --split-sign --currency USD --exclude-pending -o /tmp/kasas_cf_data.json
```
Read `/tmp/kasas_cf_data.json`: each group carries `income`, `expense`, `net`; `total` carries the period sums. Compute the savings rate exactly: `savings_rate = total.net / total.income` (guard against `income == 0`). Then tell the user the `.html` paths and offer to open them — on macOS `open /tmp/kasas_cashflow.html /tmp/kasas_net.html`. Use `bar` instead of `stacked-bar` if the user prefers side-by-side bars.

### 4b. Claude Desktop (no Bash) — interactive Artifact
Aggregate the numbers yourself, treating each `amount` as an exact decimal to 2 dp (do NOT use floats): for each calendar month bucket, sum positive amounts → income, sum the magnitudes of negative amounts → expenses, and `net = income - expenses`. Optionally exclude `pending:true` rows. Then render an interactive HTML/React Artifact with grouped or stacked bars (Income green, Expenses red) plus a Net line, matching the same numbers. Compute `savings_rate = net / income` for the period.

### 5. Present the results
In BOTH environments, always show the underlying numbers as a compact markdown table — never the chart alone:

| Month | Income | Expenses | Net |
|-------|-------:|---------:|----:|
| 2024-01 | 5,200.00 | 4,180.30 | +1,019.70 |
| … | … | … | … |
| **Total** | … | … | … |

Then state: total income, total expenses, total net, and the **savings rate** (`net / income` as a %). Follow with 2-3 plain observations, e.g. months that ran negative (expenses > income), the expense trend (rising/falling), or an unusually high/low month. Keep currency symbols/labels per account currency; if you ran multiple currencies, repeat the table + charts + observations per currency and remind the user the sections are not comparable (FX not converted).

## Edge cases
- **Empty result / no transactions in range** — say so, suggest a wider period or running `kasas-setup` / `trigger_sync` to pull data.
- **Income == 0** — report net only and skip the savings rate (avoid divide-by-zero); note there were no inflows.
- **Pending rows** — by default exclude them (`--exclude-pending` in Code; skip `pending:true` on Desktop) for a settled view; mention you did, and that including them would shift recent months.
- **Internal transfers** — if not labeled, a transfer out of one account and into another shows as both an expense and income, distorting the picture; suggest the user label transfers (e.g. `transfer`) or link them so the `-label:transfer` / `-rel:transfer_of` exclusion in step 3 can drop them.
- **Mixed currencies** — never blend; one section per currency, FX not converted.
- For a per-category expense breakdown use `spending-breakdown`; for account totals over time see `net-worth`; for ad-hoc charts see `kasas-charts`.
