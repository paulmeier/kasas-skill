---
name: Net Worth
description: Use when the user asks "what's my net worth", "assets vs liabilities", or "net worth over time" — produces a per-currency net-worth statement from account balances plus an approximate historical trend reconstructed from transactions.
argument-hint: "[as-of date | trend]"
allowed-tools: mcp__kasas__list_accounts mcp__kasas__get_account mcp__kasas__list_transactions mcp__kasas__search_transactions mcp__kasas__list_organizations Bash Read Write
---

# Net Worth

Produce a net-worth statement (assets, liabilities, net = assets − liabilities) grouped by currency, plus a chart. With the `trend` argument, also reconstruct an approximate net-worth-by-month line by walking transaction deltas backward from today's balances.

`$1` is optional: a date like `2024-12-31` (report net worth as of a point in time — caveat below) or the literal word `trend` (also build the historical line). With no argument, report current net worth and still offer the trend.

## Step 1 — Load accounts

Call `list_accounts`. Each account has `id`, `name`, `currency`, `balance` (signed decimal string), `balance_date`, `source`. The `balance` field is the source-/user-reported point-in-time balance — use it directly. Do NOT derive balances by summing transactions. Optionally call `list_organizations` if the user wants the statement broken out by org.

## Step 2 — Classify each account (and say so)

kasas has no account `type` field, so infer:

- **ASSET** — positive balance, or a name suggesting checking, savings, cash, brokerage, investment, retirement, 401k, IRA, crypto, wallet.
- **LIABILITY** — negative balance, or a name suggesting credit card, card, loan, mortgage, line of credit, HELOC.

When the sign and the name disagree (e.g. a credit card showing a positive balance = overpaid/credit), trust the name for classification and keep the signed balance as-is. ALWAYS print your classification in a small table and invite correction: "I classified these as assets/liabilities by name and balance sign — tell me if any are wrong and I'll redo the statement." A misclassified loan flips the net-worth sign, so this confirmation matters.

## Step 3 — Build the statement, grouped BY CURRENCY

Currency is per-account; never sum or convert across currencies. For each distinct `currency`:

- Total assets = sum of asset balances (use magnitudes; an asset's balance is normally positive).
- Total liabilities = sum of liability balances as positive owed amounts (a card balance of `-1500.00` is `1500.00` owed).
- Net worth = total assets − total liabilities.

Sum as exact decimals at 2dp, never floats. In Claude Code, let the helper net the account balances per currency — accounts hold `balance` (not `amount`), so pass `--value-field balance`:

```bash
# /tmp/kasas_accounts.json = the list_accounts result
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_accounts.json \
    --group-by currency --value-field balance --metric net
```

Each `groups` row is one currency: `net` = net worth, `income` = total positive (asset) balances, `expense` = total owed (negative) balances. Ignore the cross-currency `total`. Present one block per currency and add: "Balances are in each account's own currency; FX is not converted, so these totals are not added across currencies." (Classify by name where the sign is ambiguous, per Step 2.)

If `$1` is a date, note that kasas only stores the *current* `balance` (plus `balance_date`); a true historical statement requires the trend reconstruction in Step 4, so treat a past-date request as a trend request anchored on that month and flag the approximation.

## Step 4 — Charts

**A) Accounts bar (always).** Show each account as a bar: assets positive, liabilities negative, one chart per currency.

- **Claude Code:** filter the accounts to one currency, then let the helper turn their signed balances into a ranked bar chart (assets positive, liabilities negative):
  ```bash
  # /tmp/kasas_usd_accounts.json = list_accounts filtered to currency == "USD"
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_usd_accounts.json \
      --group-by name --value-field balance --metric net \
      --as-chart hbar --title "Net worth by account (USD)" --currency USD \
    | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/kasas_networth.html
  ```
  Repeat per currency. (Or write the spec by hand: `{type:"hbar", title:"…", currency:"USD", categories:[names], series:[{name:"Balance", data:[signed balances]}]}`.)
- **Desktop:** render an interactive Artifact (HTML or React) with one labeled bar per account, asset bars green, liability bars red, grouped by currency. Use the exact balances; do not convert currencies.

**B) Net-worth trend line (when `$1` is `trend` or a past date, or if the user accepts the offer).** kasas has no balance history, so reconstruct it. This is an APPROXIMATION — state these assumptions every time:

1. It assumes today's `balance` equals the sum of all transaction history for that account (true for fully-synced accounts, often NOT true for manually-entered balances or partially-synced sources).
2. Manual balances may not reconcile against transactions, so the earliest months drift.

Method (per account, per currency): start from the current `balance`. For each month going backward, the balance at the *start* of that month = balance at end of month − sum of that month's transaction amounts (amounts are signed: inflows +, outflows −). Then net worth for a month = Σ asset balances − Σ liability-owed balances at that month. Pull the monthly transaction deltas with `list_transactions` per account (or `search_transactions` with `q="date:>=YYYY-MM-DD"`).

- **Claude Code:** save all transactions to `/tmp/kasas_txns.json`, then get signed monthly net per account to use as the backward deltas:
  ```
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_txns.json \
    --group-by month --metric net --currency USD \
    | tee /tmp/kasas_monthly_net.json
  ```
  Walk those monthly nets backward from the current total net worth in a short `python3 -c` (Decimal) to produce `{month: net_worth}`, write a line-chart spec, and render:
  ```
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py /tmp/kasas_nw_trend_spec.json -o /tmp/kasas_networth_trend.html
  ```
  Trend spec: `{type:"line", title:"Net worth trend (USD, approx.)", subtitle:"reconstructed from transactions", currency:"USD", x_label:"Month", y_label:"Net worth", categories:[months], series:[{name:"Net worth", data:[values]}]}`.
- **Desktop:** do the same backward walk yourself with exact 2dp decimals and render a line-chart Artifact, captioned with the same approximation note.

After writing any HTML in Claude Code, print the absolute path and offer to open it: `open /tmp/kasas_networth.html` on macOS.

## Step 5 — Present

In BOTH environments, always include the numbers as markdown tables, never just the picture:

1. **Statement table** per currency:

   | Currency | Total assets | Total liabilities | Net worth |
   |----------|-------------:|------------------:|----------:|
   | USD      |    42,000.00 |          8,500.00 | 33,500.00 |

2. **Classification table** (account, name, currency, balance, asset/liability) so the user can correct it.
3. The **accounts bar** chart (path or Artifact).
4. For trend: the **net-worth line** chart plus a short month-over-month table.
5. **Largest movers** — the 3–5 accounts (or months, for trend) that moved net worth the most, with their signed contribution.

## Edge cases

- **No accounts:** say the ledger is empty and point to `kasas-setup`.
- **Single currency:** drop the "per currency" framing but keep the FX note for future accounts.
- **Multiple currencies:** one statement block and one chart per currency; never a combined total.
- **Pending transactions:** for the trend, optionally pass `--exclude-pending` to the aggregator (and exclude `pending:true` in search) so unsettled amounts don't distort monthly deltas — mention which you did.
- **Manual / unsynced accounts:** flag that their reconstructed history is least reliable.
- **Wrong classification:** if the user corrects an account, re-run Steps 3–5 with the override; you don't need to re-fetch.
- For category spending or income-vs-expense views, defer to `spending-breakdown` and `cash-flow`; this skill is balances-first.
