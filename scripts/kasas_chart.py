#!/usr/bin/env python3
"""
kasas_chart.py — render a financial chart as a self-contained HTML file.

Takes a JSON "chart spec" (a file argument or '-' for stdin) and writes a
single standalone .html file built from inline SVG. No internet, no npm, no
charting library — it opens in any browser and works fully offline, which makes
it the reliable charting path for Claude Code. (In Claude Desktop, prefer an
interactive Artifact instead; this script is the terminal-side renderer.)

Supported chart types: bar, hbar, line, area, stacked-bar, pie, donut.

Chart spec shape:
{
  "type": "bar",
  "title": "Net cash flow by month",
  "subtitle": "Checking + Savings, 2024",
  "currency": "USD",
  "x_label": "", "y_label": "",
  "categories": ["Jan 2024", "Feb 2024", ...],          // cartesian charts
  "series": [
    {"name": "Income",   "color": "#16a34a", "data": [4200, 4200, ...]},
    {"name": "Expenses", "color": "#dc2626", "data": [3810, 4055, ...]}
  ],
  "slices": [ {"label": "Rent", "value": 1800}, ... ]    // pie / donut only
}

`color` is optional (auto-assigned, with Income green / Expenses red / Net blue
by name). Aggregate kasas transactions into this shape with kasas_aggregate.py
--as-chart, or build the spec by hand.

Usage:
  python3 kasas_chart.py spec.json -o chart.html
  python3 kasas_aggregate.py txns.json --group-by label:category \
      --metric outflow --as-chart donut --currency USD | python3 kasas_chart.py -
"""

import argparse
import html
import json
import math
import sys

PALETTE = [
    "#2563eb",
    "#16a34a",
    "#dc2626",
    "#d97706",
    "#7c3aed",
    "#0891b2",
    "#db2777",
    "#65a30d",
    "#0d9488",
    "#9333ea",
    "#ca8a04",
    "#e11d48",
]

NAMED = {
    "income": "#16a34a",
    "inflow": "#16a34a",
    "deposits": "#16a34a",
    "expense": "#dc2626",
    "expenses": "#dc2626",
    "spending": "#dc2626",
    "outflow": "#dc2626",
    "withdrawals": "#dc2626",
    "net": "#2563eb",
    "balance": "#2563eb",
    "savings": "#0891b2",
}

SYMBOLS = {
    "USD": "$",
    "CAD": "$",
    "AUD": "$",
    "NZD": "$",
    "MXN": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "INR": "₹",
    "KRW": "₩",
    "BRL": "R$",
    "ZAR": "R",
    "BTC": "₿",
    "ETH": "Ξ",
}

W, H = 960, 540
M = {"top": 84, "right": 36, "bottom": 84, "left": 84}


def die(msg):
    sys.stderr.write("kasas_chart: %s\n" % msg)
    sys.exit(1)


def esc(s):
    return html.escape(str(s), quote=True)


# ---------- number / money formatting ----------


def _sym(cur):
    return SYMBOLS.get((cur or "").upper(), "")


def fmt_money(v, cur):
    sym = _sym(cur)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a == int(a):
        s = "{:,.0f}".format(a)
    else:
        s = "{:,.2f}".format(a)
    if sym:
        return "%s%s%s" % (sign, sym, s)
    if cur:
        return "%s%s %s" % (sign, s, cur.upper())
    return "%s%s" % (sign, s)


def fmt_compact(v, cur):
    sym = _sym(cur)
    sign = "-" if v < 0 else ""
    a = abs(v)
    suffix = ""
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            a, suffix = a / div, suf
            break
    if suffix:
        s = ("%.1f" % a).rstrip("0").rstrip(".")
    elif a == int(a):
        s = "%.0f" % a
    else:
        s = ("%.2f" % a).rstrip("0").rstrip(".")
    return "%s%s%s%s" % (sign, sym, s, suffix)


# ---------- nice axis ticks ----------


def nice_num(x, round_):
    if x == 0:
        return 0
    exp = math.floor(math.log10(abs(x)))
    f = abs(x) / (10**exp)
    if round_:
        nf = 1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10
    else:
        nf = 1 if f <= 1 else 2 if f <= 2 else 5 if f <= 5 else 10
    return nf * (10**exp)


def axis_ticks(dmin, dmax, target=6):
    # Always anchor money charts at a zero baseline.
    lo = min(0.0, dmin)
    hi = max(0.0, dmax)
    if lo == hi:
        hi = lo + 1
    span = nice_num(hi - lo, False)
    step = nice_num(span / max(1, (target - 1)), True)
    if step == 0:
        step = 1
    nlo = math.floor(lo / step) * step
    nhi = math.ceil(hi / step) * step
    ticks = []
    v = nlo
    # guard against fp drift
    while v <= nhi + step * 0.5:
        ticks.append(round(v, 10))
        v += step
    return nlo, nhi, ticks


# ---------- color assignment ----------


def color_for(name, idx, explicit):
    if explicit:
        return explicit
    if name and name.strip().lower() in NAMED:
        return NAMED[name.strip().lower()]
    return PALETTE[idx % len(PALETTE)]


# ---------- SVG plumbing ----------


def svg_text(x, y, s, cls, anchor="middle", extra=""):
    return '<text x="%.2f" y="%.2f" text-anchor="%s" class="%s" %s>%s</text>' % (
        x,
        y,
        anchor,
        cls,
        extra,
        esc(s),
    )


def plot_box():
    x0 = M["left"]
    y0 = M["top"]
    x1 = W - M["right"]
    y1 = H - M["bottom"]
    return x0, y0, x1, y1, (x1 - x0), (y1 - y0)


def header_svg(spec):
    parts = []
    if spec.get("title"):
        parts.append(svg_text(W / 2, 38, spec["title"], "title"))
    if spec.get("subtitle"):
        parts.append(svg_text(W / 2, 62, spec["subtitle"], "subtitle"))
    return "".join(parts)


def legend_svg(entries):
    # entries: list of (label, color). Centered row near the bottom.
    if not entries:
        return ""
    gap = 22
    sw = 14
    widths = [sw + 6 + 7.0 * len(lbl) + gap for lbl, _ in entries]
    total = sum(widths) - gap
    x = (W - total) / 2
    y = H - 28
    out = []
    for (lbl, col), wdt in zip(entries, widths):
        out.append(
            '<rect x="%.1f" y="%.1f" width="%d" height="%d" rx="3" fill="%s"/>'
            % (x, y - sw + 2, sw, sw, col)
        )
        out.append(svg_text(x + sw + 5, y, lbl, "legend", anchor="start"))
        x += wdt
    return "".join(out)


def axis_labels_svg(spec):
    out = []
    if spec.get("y_label"):
        out.append(
            '<text transform="translate(%d,%d) rotate(-90)" '
            'text-anchor="middle" class="axislabel">%s</text>'
            % (22, (M["top"] + (H - M["bottom"])) / 2, esc(spec["y_label"]))
        )
    if spec.get("x_label"):
        out.append(svg_text(W / 2, H - 52, spec["x_label"], "axislabel"))
    return "".join(out)


# ---------- cartesian (bar / line / area / stacked) ----------


def collect_series(spec):
    series = spec.get("series") or []
    if not series:
        die("spec has no 'series' for a cartesian chart type")
    cats = spec.get("categories")
    if not cats:
        n = max(len(s.get("data", [])) for s in series)
        cats = [str(i + 1) for i in range(n)]
    norm = []
    for i, s in enumerate(series):
        data = [float(x) for x in s.get("data", [])]
        # pad/trim to category count
        data = (data + [0.0] * len(cats))[: len(cats)]
        norm.append(
            {
                "name": s.get("name", "Series %d" % (i + 1)),
                "color": color_for(s.get("name"), i, s.get("color")),
                "data": data,
            }
        )
    return cats, norm


def y_to_px(v, ymin, ymax, y0, y1):
    if ymax == ymin:
        return y1
    return y1 - (v - ymin) / (ymax - ymin) * (y1 - y0)


def grid_and_yaxis(ymin, ymax, ticks, cur):
    x0, y0, x1, y1, pw, ph = plot_box()
    out = ['<rect x="%d" y="%d" width="%.1f" height="%.1f" class="plotbg"/>' % (x0, y0, pw, ph)]
    for t in ticks:
        yp = y_to_px(t, ymin, ymax, y0, y1)
        cls = "zeroline" if abs(t) < 1e-9 else "grid"
        out.append(
            '<line x1="%d" y1="%.2f" x2="%.2f" y2="%.2f" class="%s"/>' % (x0, yp, x1, yp, cls)
        )
        out.append(svg_text(x0 - 10, yp + 4, fmt_compact(t, cur), "tick", anchor="end"))
    return "".join(out)


def x_category_labels(cats, x0, pw):
    out = []
    n = len(cats)
    bw = pw / max(1, n)
    # thin labels if crowded
    step = 1
    if n > 16:
        step = max(1, int(math.ceil(n / 16.0)))
    y = H - M["bottom"] + 20
    for i, c in enumerate(cats):
        if i % step != 0:
            continue
        cx = x0 + bw * (i + 0.5)
        rot = ""
        if n > 8:
            rot = ' transform="rotate(35 %.2f %.2f)"' % (cx, y)
            out.append(
                '<text x="%.2f" y="%.2f" text-anchor="start" '
                'class="tick"%s>%s</text>' % (cx, y, rot, esc(c))
            )
        else:
            out.append(svg_text(cx, y, c, "tick"))
    return "".join(out)


def render_bars(spec, stacked):
    cats, series = collect_series(spec)
    cur = spec.get("currency", "")
    x0, y0, x1, y1, pw, ph = plot_box()

    if stacked:
        dmin = 0.0
        dmax = 0.0
        for i in range(len(cats)):
            pos = sum(s["data"][i] for s in series if s["data"][i] > 0)
            neg = sum(s["data"][i] for s in series if s["data"][i] < 0)
            dmax = max(dmax, pos)
            dmin = min(dmin, neg)
    else:
        flat = [v for s in series for v in s["data"]]
        dmin, dmax = (min(flat) if flat else 0), (max(flat) if flat else 0)

    ymin, ymax, ticks = axis_ticks(dmin, dmax)
    body = [grid_and_yaxis(ymin, ymax, ticks, cur)]

    n = len(cats)
    slot = pw / max(1, n)

    if stacked:
        bw = slot * 0.62
        for i in range(n):
            cx = x0 + slot * i + (slot - bw) / 2
            up = 0.0
            down = 0.0
            for s in series:
                v = s["data"][i]
                if v >= 0:
                    top = y_to_px(up + v, ymin, ymax, y0, y1)
                    bot = y_to_px(up, ymin, ymax, y0, y1)
                    up += v
                else:
                    top = y_to_px(down, ymin, ymax, y0, y1)
                    bot = y_to_px(down + v, ymin, ymax, y0, y1)
                    down += v
                h = max(0.0, bot - top)
                tip = "%s — %s: %s" % (cats[i], s["name"], fmt_money(v, cur))
                body.append(
                    '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                    'fill="%s" class="bar"><title>%s</title></rect>'
                    % (cx, top, bw, h, s["color"], esc(tip))
                )
    else:
        ns = len(series)
        group_w = slot * 0.72
        bw = group_w / ns
        gx0 = (slot - group_w) / 2
        for i in range(n):
            for j, s in enumerate(series):
                v = s["data"][i]
                cx = x0 + slot * i + gx0 + bw * j
                top = y_to_px(max(0, v), ymin, ymax, y0, y1)
                bot = y_to_px(min(0, v), ymin, ymax, y0, y1)
                h = max(0.0, bot - top)
                tip = "%s%s: %s" % (cats[i], " — " + s["name"] if ns > 1 else "", fmt_money(v, cur))
                body.append(
                    '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                    'fill="%s" class="bar"><title>%s</title></rect>'
                    % (cx, top, max(0.5, bw - 2), h, s["color"], esc(tip))
                )
                if ns == 1 and n <= 14:
                    ly = top - 6 if v >= 0 else bot + 14
                    body.append(svg_text(cx + bw / 2, ly, fmt_compact(v, cur), "barlabel"))

    body.append(x_category_labels(cats, x0, pw))
    body.append(axis_labels_svg(spec))
    legend = legend_svg([(s["name"], s["color"]) for s in series]) if len(series) > 1 else ""
    return "".join(body) + legend


def render_line(spec, area):
    cats, series = collect_series(spec)
    cur = spec.get("currency", "")
    x0, y0, x1, y1, pw, ph = plot_box()
    flat = [v for s in series for v in s["data"]]
    dmin, dmax = (min(flat) if flat else 0), (max(flat) if flat else 0)
    ymin, ymax, ticks = axis_ticks(dmin, dmax)
    body = [grid_and_yaxis(ymin, ymax, ticks, cur)]

    n = len(cats)
    xs = [x0 + (pw * (i / (n - 1)) if n > 1 else pw / 2) for i in range(n)]
    zero_y = y_to_px(0, ymin, ymax, y0, y1)

    for s in series:
        pts = [(xs[i], y_to_px(s["data"][i], ymin, ymax, y0, y1)) for i in range(n)]
        if area:
            d = "M %.2f %.2f " % (pts[0][0], zero_y)
            d += " ".join("L %.2f %.2f" % (x, y) for x, y in pts)
            d += " L %.2f %.2f Z" % (pts[-1][0], zero_y)
            body.append(
                '<path d="%s" fill="%s" fill-opacity="0.16" stroke="none"/>' % (d, s["color"])
            )
        poly = " ".join("%.2f,%.2f" % (x, y) for x, y in pts)
        body.append(
            '<polyline points="%s" fill="none" stroke="%s" '
            'stroke-width="2.5" class="line"/>' % (poly, s["color"])
        )
        for i, (x, y) in enumerate(pts):
            tip = "%s%s: %s" % (
                cats[i],
                " — " + s["name"] if len(series) > 1 else "",
                fmt_money(s["data"][i], cur),
            )
            body.append(
                '<circle cx="%.2f" cy="%.2f" r="3.5" fill="%s" '
                'class="dot"><title>%s</title></circle>' % (x, y, s["color"], esc(tip))
            )

    body.append(x_category_labels(cats, x0, pw))
    body.append(axis_labels_svg(spec))
    legend = legend_svg([(s["name"], s["color"]) for s in series]) if len(series) > 1 else ""
    return "".join(body) + legend


def render_hbar(spec):
    cats, series = collect_series(spec)
    if len(series) != 1:
        # collapse to first series for a ranking chart
        series = series[:1]
    s = series[0]
    cur = spec.get("currency", "")
    # widen left margin for category names
    left = max(M["left"], min(260, 12 + 7 * max((len(c) for c in cats), default=4)))
    x0 = left
    y0 = M["top"]
    x1 = W - M["right"]
    y1 = H - M["bottom"]
    pw = x1 - x0
    ph = y1 - y0
    data = s["data"]
    dmin, dmax = (min(data) if data else 0), (max(data) if data else 0)
    xmin, xmax, ticks = axis_ticks(dmin, dmax)

    body = ['<rect x="%d" y="%d" width="%.1f" height="%.1f" class="plotbg"/>' % (x0, y0, pw, ph)]

    def x_to_px(v):
        return x0 + (v - xmin) / (xmax - xmin) * pw if xmax != xmin else x0

    for t in ticks:
        xp = x_to_px(t)
        cls = "zeroline" if abs(t) < 1e-9 else "grid"
        body.append(
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%.2f" class="%s"/>' % (xp, y0, xp, y1, cls)
        )
        body.append(svg_text(xp, y1 + 18, fmt_compact(t, cur), "tick"))

    n = len(cats)
    slot = ph / max(1, n)
    bh = slot * 0.62
    zero_x = x_to_px(0)
    for i, c in enumerate(cats):
        v = data[i]
        cy = y0 + slot * i + (slot - bh) / 2
        xp = x_to_px(v)
        bx = min(zero_x, xp)
        bw = abs(xp - zero_x)
        col = color_for(s.get("name"), i, None) if False else PALETTE[i % len(PALETTE)]
        body.append(
            '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
            'fill="%s" class="bar"><title>%s: %s</title></rect>'
            % (bx, cy, max(0.5, bw), bh, col, esc(c), esc(fmt_money(v, cur)))
        )
        body.append(svg_text(x0 - 8, cy + bh / 2 + 4, c, "tick", anchor="end"))
        lx = xp + 6 if v >= 0 else xp - 6
        anc = "start" if v >= 0 else "end"
        body.append(svg_text(lx, cy + bh / 2 + 4, fmt_money(v, cur), "barlabel", anchor=anc))
    body.append(axis_labels_svg(spec))
    return "".join(body)


# ---------- pie / donut ----------


def render_pie(spec, donut):
    slices = spec.get("slices") or []
    if not slices:
        die("spec has no 'slices' for a pie/donut chart")
    cur = spec.get("currency", "")
    vals = []
    for i, s in enumerate(slices):
        v = abs(float(s.get("value", 0)))
        vals.append(
            {
                "label": s.get("label", "Slice %d" % (i + 1)),
                "value": v,
                "color": s.get("color") or PALETTE[i % len(PALETTE)],
            }
        )
    total = sum(v["value"] for v in vals) or 1.0

    cx, cy = 320, M["top"] + (H - M["top"] - M["bottom"]) / 2
    r = min(190, (H - M["top"] - M["bottom"]) / 2 - 8)
    inner = r * 0.58 if donut else 0

    body = []
    ang = -math.pi / 2  # start at top
    for v in vals:
        frac = v["value"] / total
        a2 = ang + frac * 2 * math.pi
        large = 1 if (a2 - ang) > math.pi else 0
        x1o, y1o = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2o, y2o = cx + r * math.cos(a2), cy + r * math.sin(a2)
        if donut:
            x1i, y1i = cx + inner * math.cos(ang), cy + inner * math.sin(ang)
            x2i, y2i = cx + inner * math.cos(a2), cy + inner * math.sin(a2)
            d = (
                "M %.2f %.2f A %.2f %.2f 0 %d 1 %.2f %.2f "
                "L %.2f %.2f A %.2f %.2f 0 %d 0 %.2f %.2f Z"
                % (x1o, y1o, r, r, large, x2o, y2o, x2i, y2i, inner, inner, large, x1i, y1i)
            )
        else:
            d = "M %.2f %.2f L %.2f %.2f A %.2f %.2f 0 %d 1 %.2f %.2f Z" % (
                cx,
                cy,
                x1o,
                y1o,
                r,
                r,
                large,
                x2o,
                y2o,
            )
        pct = 100.0 * frac
        tip = "%s: %s (%.1f%%)" % (v["label"], fmt_money(v["value"], cur), pct)
        body.append(
            '<path d="%s" fill="%s" class="slice" stroke="#ffffff" '
            'stroke-width="2"><title>%s</title></path>' % (d, v["color"], esc(tip))
        )
        # leader label for slices >= 5%
        if frac >= 0.05:
            mid = (ang + a2) / 2
            lr = r + 18
            lx, ly = cx + lr * math.cos(mid), cy + lr * math.sin(mid)
            anc = "start" if math.cos(mid) >= 0 else "end"
            body.append(svg_text(lx, ly, "%.0f%%" % pct, "pct", anchor=anc))
        ang = a2

    if donut:
        body.append(svg_text(cx, cy - 4, fmt_compact(total, cur), "donuttotal"))
        body.append(svg_text(cx, cy + 18, "total", "donutsub"))

    # legend on the right with values
    lx = 560
    ly = M["top"] + 6
    body.append(
        '<text x="%d" y="%d" class="legendhdr" text-anchor="start">%s</text>'
        % (lx, ly, esc("Breakdown"))
    )
    ly += 24
    ordered = sorted(vals, key=lambda v: v["value"], reverse=True)
    shown = ordered[:14]
    for v in shown:
        pct = 100.0 * v["value"] / total
        body.append(
            '<rect x="%d" y="%.1f" width="13" height="13" rx="3" fill="%s"/>'
            % (lx, ly - 11, v["color"])
        )
        body.append(svg_text(lx + 20, ly, v["label"], "legend", anchor="start"))
        body.append(
            svg_text(
                W - M["right"],
                ly,
                "%s  (%.1f%%)" % (fmt_money(v["value"], cur), pct),
                "legendval",
                anchor="end",
            )
        )
        ly += 23
    return "".join(body)


# ---------- document ----------

CSS = """
  :root { color-scheme: light dark; }
  body { margin:0; background:#f7f8fa; font-family:-apple-system,BlinkMacSystemFont,
         'Segoe UI',Roboto,Helvetica,Arial,sans-serif; color:#0f172a; }
  .wrap { max-width:1000px; margin:24px auto; padding:0 16px; }
  .card { background:#ffffff; border:1px solid #e6e8ec; border-radius:14px;
          box-shadow:0 1px 3px rgba(15,23,42,.06); padding:8px 8px 4px; }
  svg { width:100%; height:auto; display:block; }
  .title { font-size:22px; font-weight:700; fill:#0f172a; }
  .subtitle { font-size:13px; fill:#64748b; }
  .plotbg { fill:#fcfcfd; }
  .grid { stroke:#eceef1; stroke-width:1; }
  .zeroline { stroke:#cbd5e1; stroke-width:1.5; }
  .tick { font-size:11.5px; fill:#64748b; }
  .axislabel { font-size:12.5px; fill:#475569; font-weight:600; }
  .barlabel { font-size:11px; fill:#334155; font-weight:600; }
  .legend { font-size:12.5px; fill:#334155; }
  .legendhdr { font-size:13px; fill:#0f172a; font-weight:700; }
  .legendval { font-size:12.5px; fill:#475569; }
  .pct { font-size:11.5px; fill:#475569; font-weight:600; }
  .donuttotal { font-size:20px; font-weight:700; fill:#0f172a; }
  .donutsub { font-size:11px; fill:#94a3b8; letter-spacing:.08em; text-transform:uppercase; }
  .bar:hover, .slice:hover { filter:brightness(1.07); }
  .dot:hover { r:5; }
  .foot { font-size:11px; color:#94a3b8; text-align:right; margin:6px 8px 14px; }
  @media (prefers-color-scheme: dark) {
    body { background:#0b1220; color:#e2e8f0; }
    .card { background:#0f172a; border-color:#1e293b; }
    .title { fill:#f1f5f9; } .plotbg { fill:#0b1324; }
    .grid { stroke:#1e293b; } .zeroline { stroke:#334155; }
    .tick,.subtitle { fill:#94a3b8; } .barlabel,.legend { fill:#cbd5e1; }
    .axislabel,.legendval,.pct { fill:#94a3b8; } .legendhdr,.donuttotal { fill:#f1f5f9; }
    .slice { stroke:#0f172a; }
  }
"""

RENDERERS = {
    "bar": lambda s: render_bars(s, stacked=False),
    "stacked-bar": lambda s: render_bars(s, stacked=True),
    "stacked": lambda s: render_bars(s, stacked=True),
    "line": lambda s: render_line(s, area=False),
    "area": lambda s: render_line(s, area=True),
    "hbar": render_hbar,
    "barh": render_hbar,
    "pie": lambda s: render_pie(s, donut=False),
    "donut": lambda s: render_pie(s, donut=True),
    "doughnut": lambda s: render_pie(s, donut=True),
}


def build_html(spec):
    ctype = (spec.get("type") or "bar").lower()
    if ctype not in RENDERERS:
        die("unknown chart type %r (want: %s)" % (ctype, ", ".join(sorted(RENDERERS))))
    inner = header_svg(spec) + RENDERERS[ctype](spec)
    svg = '<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" role="img">%s</svg>' % (
        W,
        H,
        inner,
    )
    title = esc(spec.get("title") or "kasas chart")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s</title><style>%s</style></head><body><div class="wrap">'
        '<div class="card">%s</div>'
        '<div class="foot">Generated by kasas-skill</div>'
        "</div></body></html>" % (title, CSS, svg)
    )


def main():
    ap = argparse.ArgumentParser(
        description="Render a kasas chart spec to a self-contained HTML file."
    )
    ap.add_argument(
        "input", nargs="?", default="-", help="chart-spec JSON file, or '-' for stdin (default)"
    )
    ap.add_argument(
        "-o",
        "--output",
        default="kasas-chart.html",
        help="output HTML path (default: kasas-chart.html)",
    )
    ap.add_argument(
        "--print", action="store_true", help="write the HTML to stdout instead of a file"
    )
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input).read()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        die("input is not valid JSON: %s" % e)
    if not isinstance(spec, dict):
        die("chart spec must be a JSON object")

    doc = build_html(spec)
    if args.print:
        sys.stdout.write(doc)
    else:
        with open(args.output, "w") as f:
            f.write(doc)
        sys.stderr.write("kasas_chart: wrote %s\n" % args.output)
        print(args.output)


if __name__ == "__main__":
    main()
