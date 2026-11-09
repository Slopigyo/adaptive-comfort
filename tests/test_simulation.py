"""B02/B03 and offline entry-point tests; never contact a real device."""

import json
import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from adaptive_comfort.simulation import (
    ManualClock,
    simulate,
    synthetic_routine,
    synthetic_thermostat,
    trace_records,
)

ROOT = Path(__file__).resolve().parents[1]


class SimulationTests(unittest.TestCase):
    def run_fixture(self):
        device = synthetic_thermostat()
        clock = ManualClock(datetime(2026, 1, 1, 23, tzinfo=UTC))
        with patch("time.sleep", side_effect=AssertionError("No real-time waiting")):
            trace = simulate(
                synthetic_routine(),
                device,
                clock,
                duration=timedelta(hours=48),
                step=timedelta(minutes=30),
                max_sensor_age=timedelta(minutes=5),
            )
        return trace_records(trace), device, clock

    def test_b02_two_day_trace_is_reproducible(self):
        first, _, clock = self.run_fixture()
        second, _, _ = self.run_fixture()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 96)
        self.assertEqual(len({row["trace_id"] for row in first}), 96)
        self.assertEqual(clock.now(), datetime(2026, 1, 3, 23, tzinfo=UTC))
        self.assertEqual(json.dumps(first, allow_nan=False), json.dumps(second, allow_nan=False))

    def test_b03_observe_only_never_attempts_any_command(self):
        records, device, _ = self.run_fixture()
        self.assertEqual(device.command_attempts, [])
        for record in records:
            self.assertEqual(record["mode"], "observe_only")
            self.assertFalse(record["commands_allowed"])
            self.assertTrue(record["explanation"])
            reasons = record["reason_codes"]
            assert isinstance(reasons, list)
            self.assertIn("observe_only", reasons)
        self.assertEqual(device.state.mode, "cool")

    def test_fake_records_and_rejects_accidental_commands(self):
        for operation in ("set_temperature", "set_hvac_mode", "set_fan_mode", "set_schedule"):
            device = synthetic_thermostat()
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                device.command(operation, 22)
            self.assertEqual(device.command_attempts, [(operation, 22)])

    def test_simulation_rejects_nonpositive_duration_or_step(self):
        for duration, step in (
            (timedelta(0), timedelta(minutes=30)),
            (timedelta(hours=1), timedelta(0)),
            (timedelta(hours=1), timedelta(minutes=-1)),
        ):
            with self.subTest(duration=duration, step=step), self.assertRaises(ValueError):
                simulate(
                    synthetic_routine(),
                    synthetic_thermostat(),
                    ManualClock(datetime(2026, 1, 1, tzinfo=UTC)),
                    duration=duration,
                    step=step,
                    max_sensor_age=timedelta(minutes=5),
                )

    def test_cli_emits_only_deterministic_json_records(self):
        result = subprocess.run(
            [sys.executable, "-m", "adaptive_comfort", "--hours", "2"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=10,
        )
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(records), 4)
        self.assertEqual(result.stderr, "")
        self.assertEqual(records[0]["baseline_c"], 22)
        self.assertEqual(records[-1]["baseline_c"], 21.5)
        self.assertTrue(all(not record["commands_allowed"] for record in records))

    def test_cli_rejects_control_and_invalid_sizes(self):
        for arguments in (("--control",), ("--hours", "0"), ("--hours", "169"), ("--step-minutes", "0")):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable, "-m", "adaptive_comfort", *arguments],
                    cwd=ROOT, capture_output=True, text=True, check=False, timeout=10,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
