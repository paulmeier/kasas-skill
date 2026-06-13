---
name: Financial Plan
description: When the user wants forward-looking planning ("help me budget", "when can I afford X", "project my savings", "what if I cut spending 10%", "plan for a goal/retirement", "how long is my runway"), build budgets, savings-goal timelines, cash-flow forecasts, net-worth projections, and what-if scenarios from their kasas history.
argument-hint: "[goal or horizon]"
allowed-tools: mcp__kasas__list_accounts mcp__kasas__search_transactions mcp__kasas__list_transactions mcp__kasas__list_labels mcp__kasas__get_market_points mcp__kasas__list_market_series mcp__kasas__set_transaction_extensions mcp__kasas__create_rule Bash Read Write
---

Forward-looking financial planning grounded in real ledger history: budgets, savings-goal timelines, cash-flow forecast / runway, net-worth projection, and what-if scenarios. Everything below is **planning and education, not personalized financial advice** — always end with that disclaimer and state your assumptions. `$ARGUMENTS` is an optional goal or horizon (e.g. "save 20000 for a house", "5 year retirement", "what if I cut dining 20%"). If absent, ask what they want to plan.

This skill MOSTLY READS. The only writes are optional budget persistence in Step 2 — **never write without explicit user confirmation.** Currency is per-account: plan each currency separately and never convert or mix; note FX is not converted.

## Step 1 — Establish the baseline (history)
Pick a window of `N` recent months (default 6; ask if the user prefers 3 or 12). Confirm accounts and currencies first with `list_accounts`; group by currency. Then pull the history with `search_transactions` using a sign-aware, dated query, e.g. `q: "date:2024-01..2024-06"` (or `amount:<0` for expenses only), paging via `limit`/`offset` until `total` is covered.

- **Claude Code:** save the `transactions` array to `/tmp/kasas_plan.json`, then derive the three baselines with the bundled helper (Decimal-safe — never sum money yourself):
  - Cash-flow split (income vs expenses per month):
    `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_plan.json --group-by month --split-sign --exclude-pending --currency USD`
  - Expenses by category:
    `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_plan.json --group-by label:category --metric outflow --exclude-pending --top 12 --unlabeled-as "(uncategorized)" --currency USD`
  - Read `total.income`, `total.expense`, and `total.net` from the JSON; divide each by `N` for **avg monthly income**, **avg monthly expenses**, and **avg monthly net savings**.
- **Claude Desktop (no Bash):** aggregate the numbers yourself, treating each `amount` as an exact decimal to 2dp (outflows negative). Per month: income = sum of positive amounts, expenses = magnitude of negative amounts, net = income − expenses. Average over `N`.

Present a baseline markdown table: per-month income / expenses / net, plus the averages row. This is the engine for every projection below.

## Step 2 — Budget (targets + budget-vs-actual)
Propose a per-category monthly **target** = trailing `N`-month average outflow for that category (from the category aggregate above). Show them as an editable table; let the user adjust any line. Then compute **budget vs actual for the current month**: re-pull this month's expenses by category (`q: "amount:<0 date:<current-month>"`) and show target − actual per category with an over/under flag.

Optionally **persist** the budget so future runs and other skills can read it — only after the user explicitly confirms:
- As transaction extensions on a chosen marker txn: `set_transaction_extensions` writing e.g. `{ "budget.category": "dining", "budget.monthly": "300.00" }` (amounts stay decimal strings).
- Or as a rule for ongoing tagging: `create_rule` (e.g. auto-label matching payees with `category`). Echo the exact payload and confirm before writing. Never write to `source: "simplefin"` transactions — those are synced/read-only; use a `manual` txn as the marker.

## Step 3 — Savings-goal timeline
Given a goal amount `G`, current saved amount `S` (ask, or infer from a savings account balance via `list_accounts`), and monthly savings rate `R` (= avg monthly net from Step 1, or a user override): **months-to-goal = ceil((G − S) / R)**. If `R <= 0`, say the goal is unreachable at the current rate and show what monthly rate would hit it by a target date. Build the cumulative trajectory `S, S+R, S+2R, …` until it crosses `G`.

- **Claude Code:** write the trajectory rows to a small spec JSON (`{type:"area", title:"Savings to goal", currency:"USD", categories:["M1","M2",…], series:[{name:"Cumulative", data:[…]}]}`) and render:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py /tmp/savings_spec.json -o /tmp/savings.html` → tell the user the path and offer to open it (`open /tmp/savings.html`).
- **Claude Desktop:** render the same trajectory as an interactive line/area **Artifact**.

## Step 4 — Forecast / runway
Project the cash balance forward from current balances (`list_accounts`, per currency) minus average monthly burn. **Runway (months) = current liquid balance / avg monthly expenses** — the time the balance lasts if income stopped. Also project the **net** path forward (balance + k·avg_net) for the requested horizon. Chart balance over the next 12–24 months (line). Same render split as Step 3. Call out the month the balance would cross zero, if any.

## Step 5 — Net-worth projection
Project net worth forward `k` years under stated growth assumptions. Start from net worth = sum of account balances per currency (do not derive balances by summing transactions; the source/user reports them). Apply: monthly contributions (= avg net savings) plus an annual growth rate the user provides (default: ask; do not assume a market return). Compound monthly: `nw_{t+1} = nw_t * (1 + r/12) + contribution`. If investments are involved and the market tools exist, you MAY pull context via `list_market_series` then `get_market_points` to inform (not fabricate) the growth assumption — but only if those tools are available; otherwise skip. Chart the projected net-worth line and show a year-by-year table.

## Step 6 — Scenarios (what-ifs)
Re-run the Step 4/5 projection under each user what-if and overlay the lines on ONE chart so they compare directly:
- **Income ±X%** → scale avg income.
- **Expense cut X%** (e.g. "cut spending 10%") → scale avg expenses down, which raises avg net.
- **One-time cost/windfall** → subtract/add a lump at a chosen month.

Build a multi-series spec (`series: [{name:"Baseline",…}, {name:"Cut 10%",…}]`); in Claude Code pipe/render via `kasas_chart.py`, in Desktop draw a multi-line Artifact. Always show the underlying numbers as a compact markdown table beside the chart — never the picture alone — and list which assumption changed per scenario.

## Step 7 — Present & disclaim
For every chart, also print the underlying figures as a markdown table (respect per-account currency, one section per currency). Then **state assumptions explicitly** (window `N`, savings rate, growth rate, what's excluded) and close with: *"This is planning/education, not personalized financial advice."*

## Edge cases
- **No / sparse history:** if `total` is tiny or `N` months aren't covered, say projections are low-confidence and ask the user to supply income/expense estimates instead.
- **Negative or zero savings rate:** flag that no goal is reachable until net turns positive; pivot to the budget (Step 2) to find cuts.
- **Multiple currencies:** run Steps 1–6 independently per currency; never sum across currencies or convert.
- **Pending transactions:** pass `--exclude-pending` (Code) or skip `pending:true` rows (Desktop) so forecasts use settled figures.
- **Market tools absent:** if `list_market_series` / `get_market_points` aren't available, omit Step 5's market context and use a user-stated growth rate only.
- For pure spending or cash-flow questions without a forward horizon, defer to **spending-breakdown** or **cash-flow**; this skill is for forward projections.
