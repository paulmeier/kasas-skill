"""
End-to-end smoke tests for the kasas-skill charting pipeline.

Invokes the real CLIs (kasas_aggregate.py | kasas_chart.py) the way the skills
do, and asserts exact-decimal money math and well-formed SVG output. Stdlib
only — run with `python -m unittest discover -s tests` or `make test`.
"""

import json
import os
import re
import subprocess
import sys
import unittest
import xml.dom.minidom as minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
AGG = os.path.join(SCRIPTS, "kasas_aggregate.py")
CHART = os.path.join(SCRIPTS, "kasas_chart.py")
TXNS = os.path.join(FIXTURES, "transactions.json")
ACCTS = os.path.join(FIXTURES, "accounts.json")


def run(args, stdin=None):
    return subprocess.run(
        [sys.executable] + args,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
    )


def aggregate(input_path, *flags):
    r = run([AGG, input_path, *flags])
    assert r.returncode == 0, "aggregate failed: %s" % r.stderr
    return json.loads(r.stdout)


class TestAggregation(unittest.TestCase):
    def test_net_by_month(self):
        out = aggregate(TXNS, "--group-by", "month", "--metric", "net")
        self.assertEqual(out["total"]["net"], "5176.82")
        self.assertEqual(out["total"]["income"], "12750.00")
        self.assertEqual(out["total"]["expense"], "7573.18")
        self.assertEqual(len(out["groups"]), 3)
        self.assertEqual(out["groups"][0]["label"], "Jan 2024")

    def test_split_sign_chart_spec(self):
        spec = aggregate(
            TXNS, "--group-by", "month", "--split-sign", "--as-chart", "bar", "--currency", "USD"
        )
        self.assertEqual(spec["type"], "bar")
        names = [s["name"] for s in spec["series"]]
        self.assertEqual(names, ["Income", "Expenses"])
        self.assertEqual(len(spec["series"][0]["data"]), 3)

    def test_category_outflow_top(self):
        out = aggregate(
            TXNS,
            "--group-by",
            "label:category",
            "--sign",
            "outflow",
            "--metric",
            "outflow",
            "--top",
            "3",
        )
        labels = [g["label"] for g in out["groups"]]
        self.assertEqual(labels[0], "Housing")  # 5400 is the largest
        self.assertIn("Other", labels)  # folded tail
        self.assertLessEqual(len(out["groups"]), 4)

    def test_exclude_pending(self):
        full = aggregate(TXNS, "--group-by", "year", "--metric", "count")
        nopend = aggregate(TXNS, "--group-by", "year", "--metric", "count", "--exclude-pending")
        self.assertEqual(full["total"]["count"], 12)
        self.assertEqual(nopend["total"]["count"], 11)  # one pending txn

    def test_account_networth_per_currency(self):
        out = aggregate(
            ACCTS, "--group-by", "currency", "--value-field", "balance", "--metric", "net"
        )
        by = {g["label"]: g["net"] for g in out["groups"]}
        self.assertEqual(by["USD"], "27579.63")  # 8420.18 + 21000.00 - 1840.55
        self.assertEqual(by["EUR"], "980.00")

    def test_decimal_is_exact(self):
        """0.10 + 0.20 must be exactly 0.30 — never 0.30000000000000004."""
        data = {
            "transactions": [
                {"amount": "0.10", "date": "2024-01-01T00:00:00Z"},
                {"amount": "0.20", "date": "2024-01-02T00:00:00Z"},
            ]
        }
        r = run([AGG, "-", "--group-by", "year", "--metric", "net"], stdin=json.dumps(data))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["total"]["net"], "0.30")


class TestCharts(unittest.TestCase):
    CARTESIAN = ["bar", "hbar", "line", "area", "stacked-bar"]
    CIRCULAR = ["pie", "donut"]

    def _render(self, spec):
        r = run([CHART, "-", "--print"], stdin=json.dumps(spec))
        self.assertEqual(r.returncode, 0, r.stderr)
        html = r.stdout
        svg = re.search(r"<svg.*</svg>", html, re.S)
        self.assertIsNotNone(svg, "no <svg> in output")
        minidom.parseString(svg.group(0))  # raises if malformed
        self.assertGreater(len(html), 1000)
        return html

    def test_cartesian_types(self):
        for t in self.CARTESIAN:
            with self.subTest(type=t):
                self._render(
                    {
                        "type": t,
                        "title": t,
                        "currency": "USD",
                        "categories": ["Jan", "Feb", "Mar"],
                        "series": [
                            {"name": "Income", "data": [4200, 4200, 4350]},
                            {"name": "Expenses", "data": [2402.33, 2568.10, 2602.75]},
                        ],
                    }
                )

    def test_circular_types(self):
        for t in self.CIRCULAR:
            with self.subTest(type=t):
                self._render(
                    {
                        "type": t,
                        "title": t,
                        "currency": "USD",
                        "slices": [
                            {"label": "Housing", "value": 5400},
                            {"label": "Groceries", "value": 1879.99},
                            {"label": "Travel", "value": 145},
                        ],
                    }
                )

    def test_pipeline_end_to_end(self):
        agg = run(
            [
                AGG,
                TXNS,
                "--group-by",
                "label:category",
                "--sign",
                "outflow",
                "--metric",
                "outflow",
                "--as-chart",
                "donut",
                "--currency",
                "USD",
            ]
        )
        self.assertEqual(agg.returncode, 0, agg.stderr)
        chart = run([CHART, "-", "--print"], stdin=agg.stdout)
        self.assertEqual(chart.returncode, 0, chart.stderr)
        self.assertIn("<svg", chart.stdout)

    def test_unknown_type_errors(self):
        r = run([CHART, "-", "--print"], stdin=json.dumps({"type": "rainbow"}))
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
