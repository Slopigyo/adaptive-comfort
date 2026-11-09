"""Presentation-only contract tests; no browser, server, or real equipment."""

import base64
import copy
import hashlib
import json
import math
import re
import unittest
from html.parser import HTMLParser
from typing import ClassVar

from adaptive_comfort.report_view import render_report


def fixture():
    """Independent contract fixture, deliberately not imported from report.py."""
    times = [f"2026-01-08T{hour:02d}:00:00+00:00" for hour in range(4)]
    rows = []
    for index, timestamp in enumerate(times):
        rows.append({
            "timestamp": timestamp, "wake_date": "2026-01-08",
            "phase": "wind_down" if index < 2 else "sleeping",
            "context": "sleeping", "indoor_c": 22.0,
            "baseline_c": 22.0 - min(index, 2) * 0.5,
            "candidate_c": 22.0 - min(index, 2) * 0.5,
            "device_target_c": 22.0 - min(index, 2) * 0.5,
            "allowed_minimum_c": 20.0, "allowed_maximum_c": 24.0,
            "status": "proposed", "reason_codes": ["observe_only"],
            "explanation": f"Synthetic explanation {index}.",
            "trace_id": f"fixture:{index:04d}", "mode": "observe_only",
            "commands_allowed": False,
        })
    weather = []
    for index, scenario_id in enumerate(("complete", "gaps", "stale")):
        weather.append({
            "id": scenario_id, "title": f"Weather {scenario_id}",
            "description": f"Synthetic {scenario_id} input.",
            "start": "2026-01-01T03:00:00+00:00", "end": times[-1],
            "observations": [
                {"timestamp": "2026-01-01T03:00:00+00:00", "value_c": 8.0},
                {"timestamp": "2026-01-01T04:00:00+00:00", "value_c": None},
                {"timestamp": "2026-01-01T08:00:00+00:00", "value_c": 12.0},
            ],
            "segments": [
                {"start": "2026-01-01T03:00:00+00:00",
                 "end": "2026-01-01T04:00:00+00:00", "value_c": 8.0},
                {"start": "2026-01-01T08:00:00+00:00",
                 "end": "2026-01-01T11:00:00+00:00", "value_c": 12.0},
            ],
            # Intentional sentinel numbers: the renderer must not recompute a mean
            # or coverage from these small representative segment lists.
            "summary": {
                "status": "usable" if index == 0 else "unavailable",
                "mean_c": 10.123 if index == 0 else None,
                "coverage_fraction": 0.975 if index == 0 else 0.5,
                "covered_hours": 163.8 if index == 0 else 84.0,
                "latest_observed_at": times[0],
                "reason_codes": [] if index == 0 else [f"fixture_{scenario_id}"],
                "explanation": f"Authoritative {scenario_id} summary.",
            },
            "requirements": {
                "window_hours": 168, "max_sample_hold_hours": 3,
                "max_observation_age_hours": 3, "minimum_coverage": 0.9,
            },
        })
    return {
        "version": 1,
        "routine": {
            "start": times[0], "end": times[-1], "step_minutes": 60,
            "records": rows[:-1], "plot_records": rows,
            "phase_spans": [
                {"start": times[0], "end": times[2],
                 "phase": "wind_down", "context": "sleeping"},
                {"start": times[2], "end": times[3],
                 "phase": "sleeping", "context": "sleeping"},
            ],
        },
        "weather": weather,
    }


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []

    @property
    def text(self):
        return "".join(child if isinstance(child, str) else child.text
                       for child in self.children)

    def all(self, tag=None, **attrs):
        found = []
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and all(
                    child.attrs.get(key) == value for key, value in attrs.items()
                ):
                    found.append(child)
                found.extend(child.all(tag, **attrs))
        return found


class Document(HTMLParser):
    VOID: ClassVar[set[str]] = {"meta", "link", "input", "br", "hr", "img", "source", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.current = self.root
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)

    def by_id(self, element_id):
        matches = self.root.all(id=element_id)
        if len(matches) != 1:
            raise AssertionError(f"Expected one #{element_id}, got {len(matches)}")
        return matches[0]


class ReportViewTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.html = render_report(self.data)
        self.doc = Document(self.html)

    def test_complete_deterministic_utf8_document_without_mutating_data(self):
        original = copy.deepcopy(self.data)
        self.assertEqual(self.html, render_report(self.data))
        self.assertEqual(self.data, original)
        reordered = json.loads(json.dumps(self.data, sort_keys=True))
        self.assertEqual(self.html, render_report(reordered))
        self.assertTrue(self.html.lower().startswith("<!doctype html>"))
        self.assertEqual(self.html, self.html.encode("utf-8").decode("utf-8"))
        self.assertEqual(self.doc.root.all("html")[0].attrs["lang"], "en")
        self.assertTrue(self.doc.root.all("meta", charset="utf-8"))
        self.assertTrue(self.doc.root.all("meta", name="viewport"))

    def test_payload_preserves_parent_contract_and_authoritative_summaries(self):
        payload = json.loads(self.doc.by_id("report-data").text)
        self.assertEqual(payload, self.data)
        case = self.doc.by_id("weather-case-0")
        self.assertIn("97.5%", case.text)
        self.assertIn("163.8", case.text)
        self.assertIn("Authoritative complete summary.", case.text)
        means = case.all(**{"data-series": "weather-mean"})
        self.assertEqual(len(means), 1)
        self.assertEqual(float(means[0].attrs["data-mean-c"]), 10.123)

    def test_no_script_fallback_has_all_cases_charts_and_data(self):
        self.assertEqual(len(self.doc.root.all("svg")), 4)
        self.assertTrue(self.doc.root.all("noscript"))
        for index in range(3):
            case = self.doc.by_id(f"weather-case-{index}")
            self.assertNotIn("hidden", case.attrs)
            self.assertTrue(case.all("svg"))
            self.assertGreaterEqual(len(case.all("table")), 2)
        records = self.doc.by_id("routine-records")
        for row in self.data["routine"]["records"]:
            for field in ("timestamp", "trace_id", "explanation", "wake_date"):
                self.assertIn(row[field], records.text)
        self.assertIn(self.data["routine"]["end"],
                      self.doc.by_id("routine-plot-records").text)
        self.assertTrue(self.doc.by_id("routine-phase-spans").all("tr"))
        for table in self.doc.root.all("table"):
            self.assertTrue(table.all("caption"))
            self.assertTrue(table.all("th", scope="col"))

    def test_limitations_are_prominent_and_honest(self):
        hero = self.doc.by_id("report-intro").text.lower()
        for phrase in ("synthetic", "observe-only", "no equipment", "not a building response"):
            self.assertIn(phrase, hero)
        note = self.doc.by_id("weather-independence").text.lower()
        for phrase in ("report end", "independently", "playback", "not linked", "indoor targets"):
            self.assertIn(phrase, note)
        text = self.doc.root.text.lower()
        for phrase in ("not sleep stages", "no learned comfort", "no energy or health claims",
                       "rounded display", "exclusive", "utc"):
            self.assertIn(phrase, text)

    def test_enhanced_controls_start_hidden_and_are_native_keyboard_controls(self):
        controls = self.doc.root.all(**{"data-enhanced": ""})
        self.assertGreaterEqual(len(controls), 3)
        for control in controls:
            self.assertIn("hidden", control.attrs)
        scrubber = self.doc.by_id("routine-scrubber")
        self.assertEqual(scrubber.tag, "input")
        self.assertEqual(scrubber.attrs["type"], "range")
        self.assertEqual(scrubber.attrs["min"], "0")
        self.assertEqual(scrubber.attrs["max"], "2")
        self.assertEqual(scrubber.attrs["value"], "0")
        self.assertEqual(scrubber.attrs["step"], "1")
        self.assertTrue(self.doc.root.all("label", **{"for": "routine-scrubber"}))
        play = self.doc.by_id("routine-play")
        self.assertEqual(play.tag, "button")
        self.assertEqual(play.attrs["type"], "button")
        self.assertEqual(play.attrs["aria-pressed"], "false")
        self.assertEqual(self.doc.by_id("display-unit").tag, "select")
        self.assertEqual(self.doc.by_id("weather-select").tag, "select")
        self.assertEqual(len(self.doc.by_id("weather-select").all("option")), 3)
        self.assertIn(self.data["routine"]["records"][0]["explanation"],
                      self.doc.by_id("sample-explanation").text)
        self.assertIn("UTC", self.doc.by_id("sample-time").text)

    def test_dom_ids_and_accessibility_references_are_consistent(self):
        ids = [node.attrs["id"] for node in self.doc.root.all() if "id" in node.attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for node in self.doc.root.all():
            for attr in ("aria-labelledby", "aria-describedby", "aria-controls", "for"):
                if attr in node.attrs:
                    for ref in node.attrs[attr].split():
                        self.assertIn(ref, ids)
        for svg in self.doc.root.all("svg"):
            self.assertEqual(svg.attrs["role"], "img")
            self.assertTrue(svg.all("title"))
            self.assertTrue(svg.all("desc"))
        for option in self.doc.by_id("weather-select").all("option"):
            self.doc.by_id(f"weather-case-{option.attrs['value']}")

    def test_html_and_json_injection_are_escaped(self):
        attack = '</script><img src="https://invalid.example/x" onerror="alert(1)">&\'\u2028\u2029'
        row = self.data["routine"]["records"][0]
        for field in ("explanation", "trace_id", "phase", "context", "status", "wake_date"):
            row[field] = attack
        row["reason_codes"] = [attack]
        self.data["routine"]["phase_spans"][0]["phase"] = attack
        self.data["routine"]["phase_spans"][0]["context"] = attack
        for scenario in self.data["weather"]:
            for field in ("id", "title", "description"):
                scenario[field] = attack
            scenario["summary"]["explanation"] = attack
            scenario["summary"]["reason_codes"] = [attack]
        html = render_report(self.data)
        doc = Document(html)
        self.assertEqual(len(doc.root.all("script")), 2)
        self.assertFalse(doc.root.all("img"))
        self.assertIn("&lt;/script&gt;&lt;img", html)
        self.assertIn(attack, doc.by_id("sample-explanation").text)
        raw = doc.by_id("report-data").text
        for char in ("<", ">", "&", "\u2028", "\u2029"):
            self.assertNotIn(char, raw)
        self.assertEqual(json.loads(raw), self.data)
        self.assertEqual(doc.by_id("report-script").text, self.doc.by_id("report-script").text)
        self.assertTrue(all(not key.startswith("on")
                            for node in doc.root.all() for key in node.attrs))

    def test_csp_hash_matches_only_trusted_static_script(self):
        csp = self.doc.root.all("meta", **{"http-equiv": "Content-Security-Policy"})[0]
        policy = csp.attrs["content"]
        for directive in ("default-src 'none'", "connect-src 'none'", "object-src 'none'",
                          "base-uri 'none'", "form-action 'none'"):
            self.assertIn(directive, policy)
        script = self.doc.by_id("report-script").text
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        self.assertIn(f"script-src 'sha256-{digest}'", policy)
        script_policy = next(piece for piece in policy.split(";") if "script-src" in piece)
        self.assertNotIn("unsafe-inline", script_policy)
        self.assertNotIn("unsafe-eval", policy)

    def test_no_external_assets_or_unsafe_browser_apis(self):
        for node in self.doc.root.all():
            for attr in ("src", "srcset", "href", "xlink:href", "action"):
                if attr in node.attrs:
                    self.assertTrue(node.attrs[attr].startswith("#"), (node.tag, node.attrs))
        script = self.doc.by_id("report-script").text
        for pattern in (r"\bfetch\s*\(", r"\beval\s*\(", r"new\s+Function\b", r"\.innerHTML\b",
                        r"\.outerHTML\b", r"insertAdjacentHTML", r"document\.write",
                        r"XMLHttpRequest", r"WebSocket", r"sendBeacon", r"localStorage",
                        r"sessionStorage", r"indexedDB", r"document\.cookie", r"\bimport\s*\("):
            self.assertNotRegex(script, pattern)
        self.assertIn("textContent", script)
        css = self.doc.root.all("style")[0].text
        self.assertNotRegex(css, r"@import|url\s*\(")
        self.assertIn("[hidden]", css)
        self.assertIn("system-ui", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_null_routine_values_break_each_line_and_approved_band(self):
        rows = self.data["routine"]["plot_records"]
        for field in ("candidate_c", "baseline_c", "indoor_c", "allowed_minimum_c"):
            rows[1][field] = None
        chart = Document(render_report(self.data)).by_id("routine-chart")
        for series in ("candidate", "baseline", "indoor", "approved-band"):
            paths = chart.all("path", **{"data-series": series})
            self.assertEqual(len(paths), 2, series)
            self.assertTrue(all(path.attrs["d"].count("M") == 1 for path in paths))
        self.assertTrue(chart.all("circle", **{"data-series": "candidate"}))

    def test_routine_chart_uses_exact_plot_records_not_only_playback_samples(self):
        self.data["routine"]["records"] = self.data["routine"]["records"][:1]
        chart = Document(render_report(self.data)).by_id("routine-chart")
        path = chart.all("path", **{"data-series": "candidate"})[0].attrs["d"]
        self.assertEqual(path.count("L"), 3)
        phases = chart.all("rect", **{"data-role": "phase-span"})
        self.assertEqual(len(phases), 2)
        self.assertTrue(all(float(item.attrs["width"]) > 0 for item in phases))

    def test_weather_draws_only_supplied_disjoint_held_intervals(self):
        for index in range(3):
            chart = self.doc.by_id(f"weather-chart-{index}")
            segments = chart.all("line", **{"data-series": "weather-segment"})
            self.assertEqual(len(segments), 2)
            self.assertLess(float(segments[0].attrs["x2"]), float(segments[1].attrs["x1"]))
            for segment in segments:
                self.assertEqual(segment.attrs["y1"], segment.attrs["y2"])
                self.assertLess(float(segment.attrs["x1"]), float(segment.attrs["x2"]))
            self.assertFalse(chart.all("path", **{"data-series": "weather-segment"}))
            # Null observations are neither zero-degree dots nor bridges.
            self.assertEqual(len(chart.all("circle", **{"data-series": "weather-observation"})), 2)

    def test_unavailable_weather_mean_is_never_drawn_or_replaced_with_zero(self):
        for scenario in self.data["weather"]:
            scenario["summary"]["mean_c"] = None
        doc = Document(render_report(self.data))
        self.assertFalse(doc.root.all(**{"data-series": "weather-mean"}))
        for index in range(3):
            self.assertIn("Unavailable", doc.by_id(f"weather-case-{index}").text)
        self.data["weather"][0]["summary"].update(status="unavailable", mean_c=12.0)
        doc = Document(render_report(self.data))
        self.assertFalse(doc.root.all(**{"data-series": "weather-mean"}))

    def test_zero_is_a_real_temperature_and_mean(self):
        for row in self.data["routine"]["plot_records"]:
            for field in ("candidate_c", "baseline_c", "indoor_c"):
                row[field] = 0
        self.data["weather"][0]["summary"]["mean_c"] = 0
        doc = Document(render_report(self.data))
        self.assertTrue(doc.by_id("routine-chart").all("path", **{"data-series": "candidate"}))
        mean = doc.by_id("weather-chart-0").all(**{"data-series": "weather-mean"})
        self.assertEqual(len(mean), 1)
        self.assertEqual(float(mean[0].attrs["data-mean-c"]), 0)

    def assert_finite_geometry(self, doc):
        for svg in doc.root.all("svg"):
            for node in svg.all():
                for key in ("x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "width", "height"):
                    if key in node.attrs:
                        self.assertTrue(math.isfinite(float(node.attrs[key])), (key, node.attrs))
                if "d" in node.attrs:
                    path = node.attrs["d"]
                    self.assertNotRegex(path.lower(), r"nan|inf")
                    values = re.findall(r"[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?", path)
                    self.assertTrue(all(math.isfinite(float(value)) for value in values))

    def test_single_frame_and_zero_length_horizon_have_finite_geometry(self):
        self.data["routine"]["records"] = self.data["routine"]["records"][:1]
        self.data["routine"]["plot_records"] = self.data["routine"]["plot_records"][:1]
        self.data["routine"]["phase_spans"] = []
        for end in (self.data["routine"]["end"], self.data["routine"]["start"]):
            with self.subTest(end=end):
                self.data["routine"]["end"] = end
                doc = Document(render_report(self.data))
                self.assert_finite_geometry(doc)
                self.assertIn("disabled", doc.by_id("routine-play").attrs)
                self.assertIn("disabled", doc.by_id("routine-scrubber").attrs)
                self.assertTrue(doc.by_id("routine-chart").all("circle", **{"data-series": "candidate"}))

    def test_empty_data_and_all_null_values_remain_useful_and_finite(self):
        for row in self.data["routine"]["plot_records"]:
            for key in tuple(row):
                if key.endswith("_c"):
                    row[key] = None
        self.data["routine"]["records"] = []
        self.data["weather"] = []
        doc = Document(render_report(self.data))
        self.assert_finite_geometry(doc)
        self.assertFalse(doc.by_id("routine-chart").all("path", **{"data-series": "candidate"}))
        self.assertIn("No routine samples", doc.root.text)
        self.assertIn("No weather scenarios", doc.root.text)
        self.assertIn("disabled", doc.by_id("routine-play").attrs)
        self.data["routine"]["plot_records"] = []
        self.assert_finite_geometry(Document(render_report(self.data)))

    def test_nonnumeric_temperatures_are_rejected_instead_of_coerced(self):
        for value in (True, False, "22", ""):
            with self.subTest(value=value):
                self.data["routine"]["plot_records"][0]["candidate_c"] = value
                with self.assertRaises(TypeError):
                    render_report(self.data)

    def test_unknown_version_and_nonfinite_json_are_rejected(self):
        self.data["version"] = 2
        with self.assertRaisesRegex(ValueError, "version"):
            render_report(self.data)
        self.data["version"] = 1
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.data["routine"]["plot_records"][0]["candidate_c"] = value
                with self.assertRaises(ValueError):
                    render_report(self.data)


if __name__ == "__main__":
    unittest.main()
