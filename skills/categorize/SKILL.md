---
name: Categorize Transactions
description: Use when the user asks to "categorize my transactions", "tag these", "label spending", or "set up auto-categorization" — finds uncategorized outflows, clusters them by payee, and applies category labels (preferably via reusable kasas rules), confirming before every write.
argument-hint: "[period or merchant]"
allowed-tools: mcp__kasas__search_transactions mcp__kasas__list_transactions mcp__kasas__list_labels mcp__kasas__list_rules mcp__kasas__create_rule mcp__kasas__update_rule mcp__kasas__run_rules mcp__kasas__update_transaction mcp__kasas__set_transaction_extensions Bash Read Write
---

# Categorize Transactions

Find transactions that have no `category` label and apply one — ideally by creating reusable kasas **rules** so the categorization also auto-applies to future synced transactions. This skill **mutates the ledger**, so never write anything without showing a dry-run preview and getting explicit user approval first.

`$ARGUMENTS` may narrow scope to a period (e.g. `2024`, `2024-03`, `last quarter`) or a merchant (e.g. `Whole Foods`). If empty, categorize all uncategorized outflows.

## Steps

1. **Find uncategorized outflows.** Call `search_transactions` with `q='amount:<0 -label:category'`. If `$ARGUMENTS` is a period, AND in a date filter (e.g. `amount:<0 -label:category date:2024`); if it's a merchant, AND in `payee:<merchant>`. Use `limit` of 500 and page with `offset` if `total` exceeds it. The response is `{query, total, transactions:[...]}`. If `total` is 0, tell the user everything in scope is already categorized and stop. Also peek at `list_labels` to learn the category values already in use so your proposals match the user's existing taxonomy.

2. **Cluster by payee so the user sees the shape of the work.**
   - **Claude Code (Bash available):** save the transactions array to a temp file and group by payee.
     ```
     # write the search_transactions .transactions array to /tmp/kasas_uncat.json
     python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_aggregate.py /tmp/kasas_uncat.json \
       --group-by payee --metric outflow --sign outflow --top 25 \
       --title "Uncategorized spending by payee"
     ```
     This prints decimal-safe `{groups:[{label,value,count,...}]}` — each group is one payee cluster with its total outflow and transaction count. (Add `--as-chart hbar | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/kasas_chart.py - -o /tmp/uncat.html` only if the user wants a picture; see kasas-charts.)
   - **Claude Desktop (no Bash):** group the transactions yourself by `payee` (fall back to `description` when `payee` is empty). Sum `amount` as **exact decimals to 2dp** (outflows are negative — report magnitude), and count rows per payee. Do not use floats.

3. **Propose a category per payee cluster.** Present a markdown table: `Payee | # txns | Total | Proposed category`. Pick sensible categories (Groceries, Dining, Transport, Utilities, Subscriptions, Income, etc.), reusing existing label values from step 1 where they fit. Group payees by **currency** if accounts span more than one — never mix or convert currencies; show each currency's totals separately and note FX is not converted.

4. **Offer the two ways to apply, then CONFIRM before any write.**
   - **(a) Best — reusable rules (recommended).** A kasas rule is "if `<query>` then apply `<labels>`". For each payee cluster, propose one rule and show its **exact** `create_rule` arguments before calling:
     ```
     create_rule(
       name="Categorize Whole Foods",
       query="payee:whole foods",
       labels={"category": "Groceries"},
       enabled=true
     )
     ```
     Use the kasas query language for the rule's `query` (`payee:`, `description:`, `memo:`, boolean `AND OR NOT`, etc.). First do a **dry run**: for each proposed rule, run `search_transactions` with that exact `query` and report how many existing transactions it would match (and whether any already carry a different `category` you'd be overwriting). Show this preview, wait for the user's go-ahead, then call `create_rule` for each approved rule. After creating them, call `run_rules` once to **backfill** the matching existing transactions; the rules will also auto-apply to future synced transactions. If a rule with a similar name/query already exists in `list_rules`, prefer `update_rule` over creating a duplicate.
   - **(b) One-off — direct edits.** For payees too irregular for a clean query, edit individual transactions. To add the standard label, call `update_transaction(id=..., labels={..., "category": "Dining"})` per id (merge with existing `labels`, don't drop other keys). For namespaced/structured metadata (e.g. tax handling), use `set_transaction_extensions(id=..., extensions={"tax.category": "meal"})`. Confirm the id list with the user first.

5. **Verify and summarize.** Re-run the step-1 search (`amount:<0 -label:category` plus any scope filter) and report how the uncategorized `total` dropped. Summarize: which rules were created/updated, how many transactions each rule backfilled via `run_rules`, and any one-off edits. Offer to run `financial-review` or `spending-breakdown` now that the data is labeled.

## Important rules and edge cases

- **Never write without explicit approval.** Always show the dry-run preview (which transactions each rule or edit would touch) and wait for a clear yes before calling `create_rule`, `update_rule`, `run_rules`, `update_transaction`, or `set_transaction_extensions`.
- **Synced transactions are fine to label.** A transaction's `source` ("simplefin" vs "manual") and other synced fields are read-only, but its **`labels` are always writable** — rules and `update_transaction` can label synced rows.
- **Preserve existing labels.** When calling `update_transaction`, send the full merged `labels` map; never clobber unrelated keys. By default skip rows that already have a `category` unless the user asks to recategorize.
- **Money is exact decimals, never floats.** In Claude Code let `kasas_aggregate.py` (Decimal-based) do every sum. In Desktop, sum signed decimal strings to 2dp by hand.
- **Currency per account.** If the uncategorized set spans multiple currencies, cluster and total each currency separately and state that amounts are not FX-converted.
- **Inflows.** This skill targets outflows (`amount:<0`) by default. If the user wants income labeled too, repeat with `q='amount:>0 -label:category'` and propose an Income-style category.
- **Big result sets.** If `total` is large, page through with `offset`, or narrow scope by suggesting the user pass a period/merchant in `$ARGUMENTS`.
