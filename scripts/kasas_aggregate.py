#!/usr/bin/env python3
"""
kasas_aggregate.py — decimal-safe aggregation of kasas transactions.

Reads kasas transaction JSON (the array, or a {"transactions": [...]} /
{"query","total","transactions"} envelope from search_transactions /
list_transactions) and groups it into buckets using exact decimal math, so
charts and summaries are penny-accurate. Never uses floats for money.

Typical pipeline (Claude Code):

    # 1. fetch via the kasas MCP tool, save the JSON to txns.json
    # 2. bucket it
    python3 kasas_aggregate.py txns.json --group-by month --metric net
    # 3. or emit a chart spec straight into kasas_chart.py
    python3 kasas_aggregate.py txns.json --group-by label:category \
        --metric outflow --as-chart donut --title "Spending by category" \
        --currency USD | python3 kasas_chart.py - -o chart.html

Input can come from a file argument or stdin ("-").

kasas facts this relies on:
  * transaction.amount is a SIGNED DECIMAL STRING ("-12.34"), not cents/float.
  * outflows are negative, inflows are positive.
  * currency is per-ACCOUNT, not per-transaction; pass --currency for labels.
  * date is RFC3339; labels is a {key: value} map.
"""

import argparse
import json
import sys
from collections import OrderedDict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")

MONTH_ABBR = [
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def die(msg):
    sys.stderr.write("kasas_aggregate: %s\n" % msg)
    sys.exit(1)


def load_transactions(raw):
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        die("input is not valid JSON: %s" % e)
    if isinstance(doc, dict):
        for key in ("transactions", "accounts", "items", "results", "data"):
            if isinstance(doc.get(key), list):
                return doc[key]
        # A single transaction or account object.
        if "amount" in doc or "balance" in doc:
            return [doc]
        die("JSON object has no 'transactions'/'accounts' array")
    if isinstance(doc, list):
        return doc
    die("expected a JSON array of transactions or an object with 'transactions'")


def to_decimal(amount):
    if amount is None:
        return ZERO
    if isinstance(amount, (int, float)):
        # kasas returns strings; tolerate numbers but go through str for floats.
        amount = repr(amount) if isinstance(amount, float) else str(amount)
    try:
        return Decimal(str(amount).strip())
    except (InvalidOperation, ValueError):
        return ZERO


def parse_date(value):
    """Parse a kasas RFC3339 date (or date-only) into a datetime.date."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Fast path for date-only grouping needs.
    try:
        norm = s.replace("Z", "+00:00")
        return datetime.fromisoformat(norm).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def iso_week(d):
    y, w, _ = d.isocalendar()
    return y, w


def group_key_and_label(txn, group_by, unlabeled_as):
    """Return (sort_key, display_label) for a transaction, or None to drop it."""
    if group_by.startswith("label:"):
        lkey = group_by[len("label:") :]
        labels = txn.get("labels") or {}
        val = labels.get(lkey)
        label = val if val else unlabeled_as
        return (label.lower(), label)

    if group_by.startswith("ext:"):
        ekey = group_by[len("ext:") :]
        exts = txn.get("extensions") or {}
        val = exts.get(ekey)
        label = str(val) if val not in (None, "") else unlabeled_as
        return (label.lower(), label)

    if group_by == "account":
        key = (
            txn.get("account_id")
            or txn.get("account")
            or txn.get("name")
            or txn.get("id")
            or unlabeled_as
        )
        return (str(key), str(key))

    if group_by == "name":
        key = txn.get("name") or txn.get("id") or unlabeled_as
        return (str(key), str(key))

    if group_by == "currency":
        key = txn.get("currency") or unlabeled_as
        return (str(key), str(key))

    if group_by == "payee":
        key = txn.get("payee") or txn.get("description") or unlabeled_as
        return (str(key).lower(), str(key))

    if group_by == "source":
        key = txn.get("source") or unlabeled_as
        return (str(key), str(key))

    # Time-based groupings.
    d = parse_date(txn.get("date"))
    if d is None:
        return ("￿", unlabeled_as)  # sort undated last

    if group_by == "year":
        return ("%04d" % d.year, "%04d" % d.year)
    if group_by == "quarter":
        q = (d.month - 1) // 3 + 1
        return ("%04d-Q%d" % (d.year, q), "Q%d %04d" % (q, d.year))
    if group_by == "month":
        return ("%04d-%02d" % (d.year, d.month), "%s %04d" % (MONTH_ABBR[d.month], d.year))
    if group_by == "week":
        y, w = iso_week(d)
        return ("%04d-W%02d" % (y, w), "%04d-W%02d" % (y, w))
    if group_by == "day":
        return (d.isoformat(), d.isoformat())
    if group_by == "weekday":
        return ("%d" % d.weekday(), WEEKDAY[d.weekday()])

    die("unknown --group-by %r" % group_by)


def passes_sign(amt, sign):
    if sign == "all":
        return True
    if sign == "inflow":
        return amt > 0
    if sign == "outflow":
        return amt < 0
    die("unknown --sign %r" % sign)


def metric_value(amt, metric):
    """Per-transaction contribution to a single-series metric."""
    if metric in ("net", "sum"):
        return amt
    if metric == "abs":
        return abs(amt)
    if metric == "inflow":
        return amt if amt > 0 else ZERO
    if metric == "outflow":
        return -amt if amt < 0 else ZERO  # positive magnitude of outflows
    if metric == "count":
        return Decimal(1)
    die("unknown --metric %r" % metric)


def quantize(d, places):
    q = Decimal(1).scaleb(-places)  # 10^-places
    return d.quantize(q, rounding=ROUND_HALF_UP)


def main():
    p = argparse.ArgumentParser(description="Decimal-safe aggregation of kasas transactions.")
    p.add_argument(
        "input", nargs="?", default="-", help="transaction JSON file, or '-' for stdin (default)"
    )
    p.add_argument(
        "--group-by",
        default="month",
        help="month|week|day|year|quarter|weekday|account|name|"
        "currency|payee|source|label:<key>|ext:<key> "
        "(default: month)",
    )
    p.add_argument(
        "--value-field",
        default="amount",
        choices=["amount", "balance"],
        help="which field holds the money: 'amount' for "
        "transactions (default) or 'balance' for accounts",
    )
    p.add_argument(
        "--metric",
        default="net",
        help="net|abs|inflow|outflow|count (default: net). Ignored when --split-sign is set.",
    )
    p.add_argument(
        "--sign",
        default="all",
        choices=["all", "inflow", "outflow"],
        help="filter transactions by sign before grouping",
    )
    p.add_argument(
        "--split-sign",
        action="store_true",
        help="emit two series per group: Income (inflows) and "
        "Expenses (outflow magnitude). Overrides --metric.",
    )
    p.add_argument("--since", help="drop transactions before this ISO date")
    p.add_argument("--until", help="drop transactions after this ISO date")
    p.add_argument(
        "--exclude-pending", action="store_true", help="drop transactions where pending == true"
    )
    p.add_argument(
        "--top",
        type=int,
        default=0,
        help="keep top N groups by |metric|, fold the rest into "
        "'Other' (categorical group-by only)",
    )
    p.add_argument(
        "--unlabeled-as",
        default="(uncategorized)",
        help="bucket name for transactions missing the group field",
    )
    p.add_argument(
        "--decimals", type=int, default=2, help="decimal places in output amounts (default: 2)"
    )
    p.add_argument(
        "--currency", default="", help="currency code, carried into output/chart for labels"
    )
    p.add_argument(
        "--as-chart",
        default="",
        help="emit a kasas_chart.py spec of this type instead of "
        "raw buckets: bar|hbar|line|area|stacked-bar|pie|donut",
    )
    p.add_argument("--title", default="", help="chart title (with --as-chart)")
    p.add_argument("--subtitle", default="", help="chart subtitle (with --as-chart)")
    p.add_argument("-o", "--output", default="-", help="write JSON here instead of stdout")
    args = p.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input).read()
    txns = load_transactions(raw)

    since = parse_date(args.since) if args.since else None
    until = parse_date(args.until) if args.until else None

    is_time = (
        args.group_by in ("month", "week", "day", "year", "quarter") or args.group_by == "weekday"
    )

    # group_key -> {"label":.., "income":Dec, "expense":Dec, "value":Dec, "count":int}
    buckets = OrderedDict()
    grand_income = grand_expense = grand_value = ZERO
    grand_count = 0

    for t in txns:
        if args.exclude_pending and t.get("pending"):
            continue
        d = parse_date(t.get("date"))
        if since and d and d < since:
            continue
        if until and d and d > until:
            continue
        amt = to_decimal(t.get(args.value_field))
        if not passes_sign(amt, args.sign):
            continue

        gk = group_key_and_label(t, args.group_by, args.unlabeled_as)
        if gk is None:
            continue
        sort_key, label = gk

        b = buckets.get(sort_key)
        if b is None:
            b = {"label": label, "income": ZERO, "expense": ZERO, "value": ZERO, "count": 0}
            buckets[sort_key] = b

        b["income"] += amt if amt > 0 else ZERO
        b["expense"] += (-amt) if amt < 0 else ZERO
        b["value"] += metric_value(amt, args.metric)
        b["count"] += 1

        grand_income += amt if amt > 0 else ZERO
        grand_expense += (-amt) if amt < 0 else ZERO
        grand_value += metric_value(amt, args.metric)
        grand_count += 1

    # Order buckets: chronologically for time, by |value| desc otherwise.
    items = list(buckets.items())
    if is_time:
        items.sort(key=lambda kv: kv[0])
    else:
        items.sort(key=lambda kv: abs(kv[1]["value"]), reverse=True)

    # Top-N folding (categorical only).
    if args.top and args.top > 0 and not is_time and len(items) > args.top:
        head = items[: args.top]
        tail = items[args.top :]
        other = {"label": "Other", "income": ZERO, "expense": ZERO, "value": ZERO, "count": 0}
        for _, b in tail:
            other["income"] += b["income"]
            other["expense"] += b["expense"]
            other["value"] += b["value"]
            other["count"] += b["count"]
        items = head + [("￿Other", other)]

    dp = args.decimals

    def fmt(d):
        return str(quantize(d, dp))

    groups_out = []
    for _, b in items:
        groups_out.append(
            {
                "key": b["label"],
                "label": b["label"],
                "value": fmt(b["value"]),
                "income": fmt(b["income"]),
                "expense": fmt(b["expense"]),
                "net": fmt(b["income"] - b["expense"]),
                "count": b["count"],
            }
        )

    if not args.as_chart:
        result = {
            "group_by": args.group_by,
            "metric": "split-sign" if args.split_sign else args.metric,
            "currency": args.currency,
            "total": {
                "value": fmt(grand_value),
                "income": fmt(grand_income),
                "expense": fmt(grand_expense),
                "net": fmt(grand_income - grand_expense),
                "count": grand_count,
            },
            "groups": groups_out,
        }
        emit(result, args.output)
        return

    # Build a kasas_chart.py spec.
    ctype = args.as_chart
    labels = [b["label"] for _, b in items]

    if ctype in ("pie", "donut"):
        # Magnitude-based slices from the chosen metric (or expense magnitude).
        slices = []
        for _, b in items:
            v = b["value"]
            slices.append({"label": b["label"], "value": float(quantize(abs(v), dp))})
        spec = {
            "type": ctype,
            "title": args.title,
            "subtitle": args.subtitle,
            "currency": args.currency,
            "slices": slices,
        }
    else:
        if args.split_sign:
            series = [
                {"name": "Income", "data": [float(quantize(b["income"], dp)) for _, b in items]},
                {"name": "Expenses", "data": [float(quantize(b["expense"], dp)) for _, b in items]},
            ]
        else:
            series = [
                {
                    "name": _series_name(args),
                    "data": [float(quantize(b["value"], dp)) for _, b in items],
                },
            ]
        spec = {
            "type": ctype,
            "title": args.title,
            "subtitle": args.subtitle,
            "currency": args.currency,
            "categories": labels,
            "series": series,
        }
    emit(spec, args.output)


def _series_name(args):
    names = {
        "net": "Net",
        "abs": "Total",
        "inflow": "Income",
        "outflow": "Spending",
        "count": "Count",
        "sum": "Net",
    }
    return names.get(args.metric, args.metric.title())


def emit(obj, output):
    text = json.dumps(obj, indent=2)
    if output == "-":
        sys.stdout.write(text + "\n")
    else:
        with open(output, "w") as f:
            f.write(text + "\n")
        sys.stderr.write("kasas_aggregate: wrote %s\n" % output)


if __name__ == "__main__":
    main()
