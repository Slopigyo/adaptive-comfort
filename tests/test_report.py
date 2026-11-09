"""Report data/export tests; browser launches are always mocked."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any
from unittest.mock import patch

from adaptive_comfort.__main__ import main
from adaptive_comfort.report import build_demo, generate_report
from adaptive_comfort.simulation import (
    ManualClock,
    RecordingThermostat,
    simulate,
    synthetic_routine,
    synthetic_thermostat,
    trace_records,
)
from adaptive_comfort.weather import (
    HistoryRequirements,
    OutdoorReading,
    summarize_history,
)

ROOT = Path(__file__).resolve().parents[1]


class ReportDataTests(unittest.TestCase):
    def test_original_playback_records_match_the_existing_routine(self):
        data = build_demo()
        baseline = trace_records(simulate(
            synthetic_routine(), synthetic_thermostat(),
            ManualClock(datetime(2026, 1, 1, 23, tzinfo=UTC)),
            duration=timedelta(hours=48), step=timedelta(minutes=30),
            max_sensor_age=timedelta(minutes=5),
        ))
        self.assertEqual(data["routine"]["records"], baseline)
        self.assertEqual(len(baseline), 96)
        self.assertEqual(data["routine"]["end"], "2026-01-03T23:00:00+00:00")

    def test_plot_includes_exact_boundaries_and_endpoint_not_in_coarse_samples(self):
        routine = build_demo(hours=12, step_minutes=45)["routine"]
        original = {row["timestamp"] for row in routine["records"]}
        plotted = {row["timestamp"]: row for row in routine["plot_records"]}
        boundary = "2026-01-02T07:00:00+00:00"
        self.assertNotIn(boundary, original)
        self.assertIn(boundary, plotted)
        self.assertEqual(plotted[boundary]["phase"], "return_to_day")
        self.assertEqual(plotted[boundary]["candidate_c"], 23)
        self.assertNotIn(routine["end"], original)
        self.assertIn(routine["end"], plotted)
        self.assertTrue(original.issubset(plotted))

    def test_exact_phase_spans_cover_the_horizon_without_overlaps(self):
        routine = build_demo(hours=24, step_minutes=47)["routine"]
        spans = routine["phase_spans"]
        self.assertEqual(spans[0]["start"], routine["start"])
        self.assertEqual(spans[-1]["end"], routine["end"])
        for left, right in pairwise(spans):
            self.assertEqual(left["end"], right["start"])
        duration = sum((datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])
                        for s in spans), timedelta(0))
        self.assertEqual(duration, timedelta(hours=24))
        self.assertEqual([s["phase"] for s in spans],
                         ["wind_down", "sleeping", "waking", "return_to_day", "daytime"])

    def test_weather_summaries_come_from_the_existing_history_module(self):
        for scenario in build_demo(hours=2)["weather"]:
            with self.subTest(scenario=scenario["id"]):
                requirements = scenario["requirements"]
                readings = [OutdoorReading(
                    value=row["value_c"], unit="C",
                    observed_at=datetime.fromisoformat(row["timestamp"]),
                    received_at=datetime.fromisoformat(row["timestamp"]),
                    source="test_report", available=row["value_c"] is not None,
                ) for row in scenario["observations"]]
                expected = summarize_history(
                    readings, now=datetime.fromisoformat(scenario["end"]), source="test_report",
                    requirements=HistoryRequirements(
                        window=timedelta(hours=requirements["window_hours"]),
                        max_sample_hold=timedelta(hours=requirements["max_sample_hold_hours"]),
                        max_observation_age=timedelta(hours=requirements["max_observation_age_hours"]),
                        minimum_coverage=requirements["minimum_coverage"],
                    ),
                )
                actual = scenario["summary"]
                self.assertEqual(actual["status"], expected.status)
                self.assertEqual(actual["mean_c"], expected.mean_c)
                self.assertEqual(actual["coverage_fraction"], expected.coverage_fraction)
                self.assertEqual(actual["reason_codes"], list(expected.reason_codes))
                self.assertEqual(actual["explanation"], expected.explanation)

    def test_weather_segments_match_authoritative_coverage_and_do_not_bridge_gaps(self):
        cases = {case["id"]: case for case in build_demo()["weather"]}
        for scenario in cases.values():
            segments = scenario["segments"]
            total = timedelta(0)
            previous_end = datetime.fromisoformat(scenario["start"])
            for segment in segments:
                left = datetime.fromisoformat(segment["start"])
                right = datetime.fromisoformat(segment["end"])
                self.assertLessEqual(previous_end, left)
                self.assertLess(left, right)
                self.assertLessEqual(right, datetime.fromisoformat(scenario["end"]))
                self.assertLessEqual(right - left, timedelta(hours=3))
                total += right - left
                previous_end = right
            self.assertEqual(total.total_seconds() / 3600, scenario["summary"]["covered_hours"])
        self.assertEqual(cases["complete"]["summary"]["status"], "usable")
        self.assertEqual(cases["complete"]["summary"]["covered_hours"], 168)
        self.assertEqual(cases["gaps"]["summary"]["covered_hours"], 146)
        self.assertIn("insufficient_coverage", cases["gaps"]["summary"]["reason_codes"])
        self.assertEqual(cases["stale"]["summary"]["covered_hours"], 165)
        self.assertIn("stale_outdoor", cases["stale"]["summary"]["reason_codes"])
        self.assertIsNone(cases["gaps"]["summary"]["mean_c"])
        self.assertIsNone(cases["stale"]["summary"]["mean_c"])

    def test_dataset_is_deterministic_and_never_attempts_a_command(self):
        with patch.object(RecordingThermostat, "command", side_effect=AssertionError("No control")) as command:
            first = build_demo(hours=2)
            second = build_demo(hours=2)
        command.assert_not_called()
        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)
        for row in first["routine"]["plot_records"]:
            self.assertEqual(row["candidate_c"], row["baseline_c"])
            self.assertEqual(row["indoor_c"], 22)
            self.assertFalse(row["commands_allowed"])

    def test_single_playback_sample_still_has_a_plottable_horizon(self):
        routine = build_demo(hours=1, step_minutes=60)["routine"]
        self.assertEqual(len(routine["records"]), 1)
        self.assertEqual(len(routine["plot_records"]), 2)
        self.assertNotEqual(routine["start"], routine["end"])

    def test_invalid_demo_sizes_are_rejected(self):
        invalid_cases: tuple[dict[str, Any], ...] = (
            {"hours": 0}, {"hours": 169}, {"hours": True},
            {"step_minutes": 0}, {"step_minutes": 61}, {"step_minutes": 0.5},
        )
        for arguments in invalid_cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                build_demo(**arguments)


class ReportExportTests(unittest.TestCase):
    def test_export_creates_a_self_contained_utf8_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "demo.htm"
            result = generate_report(output, hours=1, step_minutes=60)
            self.assertEqual(result, output.resolve())
            document = output.read_text(encoding="utf-8")
            self.assertTrue(document.startswith("<!doctype html>"))
            self.assertIn('<svg id="routine-chart"', document)
            self.assertIn('id="report-data"', document)
            self.assertIn("°C", document)
            self.assertIn("not linked to indoor targets", document)

    def test_existing_files_are_preserved_unless_overwrite_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo.html"
            output.write_text("keep this file", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                generate_report(output, hours=1)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep this file")
            generate_report(output, hours=1, overwrite=True)
            self.assertTrue(output.read_text(encoding="utf-8").startswith("<!doctype html>"))

    def test_output_extension_is_checked_before_creating_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "absent" / "demo.py"
            with self.assertRaises(ValueError):
                generate_report(output, hours=1)
            self.assertFalse(output.parent.exists())

    def test_html_cli_generates_report_without_opening_browser_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo.html"
            with patch("sys.argv", ["adaptive_comfort", "--hours", "2", "--html", str(output)]), \
                 patch("webbrowser.open") as browser, redirect_stdout(io.StringIO()) as stdout:
                main()
            browser.assert_not_called()
            self.assertTrue(output.exists())
            self.assertIn(str(output.resolve()), stdout.getvalue())

    def test_open_is_opt_in_and_receives_only_the_generated_local_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report with spaces.html"
            with patch("sys.argv", ["adaptive_comfort", "--hours", "1", "--html", str(output), "--open"]), \
                 patch("webbrowser.open", return_value=True) as browser, redirect_stdout(io.StringIO()):
                main()
            browser.assert_called_once_with(output.resolve().as_uri())
            self.assertTrue(output.exists())

    def test_failed_browser_launch_keeps_the_report_and_explains_manual_opening(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo.html"
            with patch("sys.argv", ["adaptive_comfort", "--hours", "1", "--html", str(output), "--open"]), \
                 patch("webbrowser.open", return_value=False), redirect_stdout(io.StringIO()), \
                 redirect_stderr(io.StringIO()) as stderr:
                main()
            self.assertTrue(output.exists())
            self.assertIn("open", stderr.getvalue().lower())

    def test_cli_rejects_report_only_flags_without_html(self):
        for argument in ("--open", "--force"):
            with self.subTest(argument=argument):
                result = subprocess.run(
                    [sys.executable, "-m", "adaptive_comfort", argument], cwd=ROOT,
                    capture_output=True, text=True, check=False, timeout=10,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("--html", result.stderr)

    def test_cli_refuses_existing_output_and_accepts_explicit_force(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo.html"
            output.write_text("keep", encoding="utf-8")
            command = [sys.executable, "-m", "adaptive_comfort", "--hours", "1", "--html", str(output)]
            refused = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=10)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("--force", refused.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")
            accepted = subprocess.run(command + ["--force"], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10)
            self.assertIn(str(output.resolve()), accepted.stdout)
            self.assertTrue(output.read_text(encoding="utf-8").startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
