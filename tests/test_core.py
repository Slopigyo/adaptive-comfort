"""Executable B01/B04–B08 cases; all values are synthetic, not safety defaults."""

import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

from adaptive_comfort.core import (
    Routine,
    ValidationError,
    difference_to_celsius,
    evaluate,
    temperature_to_celsius,
)
from adaptive_comfort.simulation import synthetic_routine, synthetic_thermostat


class RoutineTests(unittest.TestCase):
    def setUp(self):
        self.routine = synthetic_routine()
        self.device = synthetic_thermostat()
        self.now = datetime(2026, 1, 2, 6, tzinfo=UTC)
        self.reading = self.device.read_indoor(self.now)

    def decision(self, **changes):
        return evaluate(
            routine=changes.get("routine", self.routine),
            reading=changes.get("reading", self.reading),
            climate=changes.get("climate", self.device.state),
            now=changes.get("now", self.now),
            max_sensor_age=changes.get("max_sensor_age", timedelta(minutes=5)),
        )

    def assert_withheld(self, result, reason):
        self.assertEqual(result.status, "withheld")
        self.assertIsNone(result.candidate_c)
        self.assertIsNone(result.device_target_c)
        self.assertIn(reason, result.reason_codes)
        self.assertTrue(result.explanation)

    def test_b01_anchors_interpolation_and_wake_date(self):
        cases = [
            (datetime(2026, 1, 1, 23, tzinfo=UTC), 22, "wind_down"),
            (datetime(2026, 1, 2, 0, 30, tzinfo=UTC), 21.5, "wind_down"),
            (datetime(2026, 1, 2, 2, tzinfo=UTC), 21, "sleeping"),
            (datetime(2026, 1, 2, 5, tzinfo=UTC), 21, "waking"),
            (datetime(2026, 1, 2, 6, tzinfo=UTC), 22, "waking"),
            (datetime(2026, 1, 2, 7, tzinfo=UTC), 23, "return_to_day"),
            (datetime(2026, 1, 2, 9, tzinfo=UTC), 22, "daytime"),
        ]
        for now, target, phase in cases:
            with self.subTest(now=now):
                result = self.decision(now=now, reading=self.device.read_indoor(now))
                self.assertEqual(result.status, "recommendation")
                self.assertAlmostEqual(result.baseline_c, target)
                self.assertAlmostEqual(result.candidate_c, target)
                self.assertEqual(result.phase, phase)
                self.assertEqual(result.wake_date, date(2026, 1, 2))

    def test_b04_disabled_unapproved_and_missing_routines(self):
        disabled = self.decision(routine=replace(self.routine, enabled=False))
        self.assertEqual(disabled.status, "disabled")
        self.assertIsNone(disabled.candidate_c)
        self.assert_withheld(
            self.decision(routine=replace(self.routine, approved=False)),
            "routine_unapproved",
        )
        self.assert_withheld(self.decision(routine=None), "routine_missing")
        defaults = Routine(
            anchors=self.routine.anchors,
            unit="C",
            minimum=20,
            maximum=24,
            maximum_slew_per_hour=1,
            revision="unapproved_example",
        )
        self.assertFalse(defaults.approved)
        self.assertFalse(defaults.enabled)

    def test_b05_invalid_routine_is_not_silently_repaired(self):
        anchors = self.routine.anchors
        cases = [
            (replace(self.routine, minimum=25, maximum=20), "invalid_bounds"),
            (replace(self.routine, unit=None), "invalid_unit"),
            (replace(self.routine, maximum_slew_per_hour=0), "invalid_slew"),
            (replace(self.routine, maximum_slew_per_hour=0.5), "excessive_slew"),
            (replace(self.routine, anchors=anchors[:4]), "invalid_schedule"),
            (replace(self.routine, anchors=(anchors[1], anchors[0], *anchors[2:])), "invalid_schedule"),
            (replace(self.routine, anchors=(anchors[0], replace(anchors[1], minute=-60), *anchors[2:])), "invalid_schedule"),
            (replace(self.routine, anchors=(replace(anchors[0], target=30), *anchors[1:])), "anchor_out_of_bounds"),
            (replace(self.routine, anchors=(replace(anchors[0], phase="waking"), *anchors[1:])), "invalid_schedule"),
        ]
        for routine, reason in cases:
            with self.subTest(reason=reason, routine=routine):
                self.assert_withheld(self.decision(routine=routine), reason)

    def test_b06_freshness_uses_observation_not_receipt_time(self):
        at_boundary = replace(self.reading, observed_at=self.now - timedelta(minutes=5))
        self.assertEqual(self.decision(reading=at_boundary).status, "recommendation")
        stale = replace(at_boundary, observed_at=self.now - timedelta(minutes=5, microseconds=1))
        self.assert_withheld(self.decision(reading=stale), "stale_indoor")

    def test_b06_invalid_indoor_values_and_availability(self):
        for value in (None, float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=value):
                self.assert_withheld(
                    self.decision(reading=replace(self.reading, value=value)),
                    "invalid_temperature",
                )
        self.assert_withheld(
            self.decision(reading=replace(self.reading, available=False)),
            "indoor_unavailable",
        )
        self.assert_withheld(self.decision(reading=None), "indoor_unavailable")

    def test_b06_invalid_timestamps(self):
        cases = [
            replace(self.reading, observed_at=None),
            replace(self.reading, received_at=None),
            replace(self.reading, observed_at=self.now.replace(tzinfo=None)),
            replace(self.reading, observed_at=self.now + timedelta(seconds=1)),
            replace(self.reading, received_at=self.now + timedelta(seconds=1)),
            replace(self.reading, received_at=self.now - timedelta(seconds=1)),
        ]
        for reading in cases:
            with self.subTest(reading=reading):
                self.assert_withheld(self.decision(reading=reading), "invalid_sensor_time")
        for now in (self.now.replace(tzinfo=None), self.now.astimezone(timezone(timedelta(hours=1)))):
            self.assert_withheld(self.decision(now=now), "invalid_clock")
        self.assert_withheld(
            self.decision(max_sensor_age=timedelta(0)), "invalid_freshness_limit"
        )

    def test_b07_absolute_and_difference_conversion(self):
        self.assertEqual(temperature_to_celsius(32, "F"), 0)
        self.assertEqual(temperature_to_celsius(68, "F"), 20)
        self.assertEqual(difference_to_celsius(1.8, "F"), 1)
        self.assertEqual(difference_to_celsius(0.9, "F"), 0.5)
        self.assertAlmostEqual(difference_to_celsius(32, "F"), 160 / 9)
        for unit in (None, "", "K"):
            with self.subTest(unit=unit), self.assertRaises(ValidationError):
                temperature_to_celsius(22, unit)

    def test_b07_equivalent_fahrenheit_inputs_and_changed_units(self):
        def fahrenheit(value):
            return value * 9 / 5 + 32

        routine_f = replace(
            self.routine,
            unit="F",
            minimum=fahrenheit(self.routine.minimum),
            maximum=fahrenheit(self.routine.maximum),
            maximum_slew_per_hour=1.8,
            anchors=tuple(replace(a, target=fahrenheit(a.target)) for a in self.routine.anchors),
        )
        climate_f = replace(
            self.device.state, unit="F", minimum=64.4, maximum=78.8, step=0.9
        )
        for hour in (0, 2, 6, 7, 9, 23):
            now = self.now.replace(hour=hour)
            reading = self.device.read_indoor(now)
            c = self.decision(now=now, reading=reading)
            f = self.decision(
                now=now,
                routine=routine_f,
                climate=climate_f,
                reading=replace(reading, value=71.6, unit="F"),
            )
            with self.subTest(hour=hour):
                self.assertEqual(c.status, f.status)
                for field in ("indoor_c", "baseline_c", "candidate_c", "device_target_c"):
                    self.assertAlmostEqual(getattr(c, field), getattr(f, field))
        self.assert_withheld(
            self.decision(reading=replace(self.reading, unit=None)), "invalid_unit"
        )
        self.assert_withheld(
            self.decision(climate=replace(self.device.state, unit="F")), "empty_bounds"
        )

    def test_b08_morning_cooling_target_is_not_achieved_warming(self):
        targets = []
        for hour in (5, 6, 7):
            now = self.now.replace(hour=hour)
            reading = replace(self.device.read_indoor(now), value=18)
            result = self.decision(now=now, reading=reading)
            targets.append(result.candidate_c)
            self.assertEqual(result.indoor_c, 18)
            self.assertIn("passive", result.explanation)
            self.assertIn("not a prediction", result.explanation)
        self.assertEqual(targets, [21, 22, 23])
        self.assertEqual(self.device.state.mode, "cool")
        self.assertEqual(self.device.command_attempts, [])

    def test_climate_constraints_and_no_representable_target(self):
        climate = replace(self.device.state, minimum=22.5, maximum=24)
        result = self.decision(climate=climate)
        self.assertEqual(result.baseline_c, 22)
        self.assertEqual(result.candidate_c, 22.5)
        self.assertIn("constrained_to_bounds", result.reason_codes)
        narrow = replace(
            self.routine,
            minimum=20.1,
            maximum=20.4,
            anchors=tuple(replace(a, target=20.2) for a in self.routine.anchors),
        )
        self.assert_withheld(self.decision(routine=narrow), "no_representable_target")
        for state, reason in (
            (replace(self.device.state, minimum=25), "empty_bounds"),
            (replace(self.device.state, minimum=30), "invalid_bounds"),
            (replace(self.device.state, step=0), "invalid_device_step"),
            (replace(self.device.state, available=False), "climate_unavailable"),
            (replace(self.device.state, mode="off"), "unsupported_mode"),
            (replace(self.device.state, mode="auto"), "unsupported_mode"),
        ):
            with self.subTest(state=state):
                self.assert_withheld(self.decision(climate=state), reason)

    def test_quantization_tie_selects_lower_allowed_step(self):
        now = self.now.replace(hour=1, minute=15)
        result = self.decision(now=now, reading=self.device.read_indoor(now))
        self.assertEqual(result.baseline_c, 21.25)
        self.assertEqual(result.device_target_c, 21)

    def test_fahrenheit_grid_preserves_endpoint_and_singleton_envelope(self):
        climate = replace(self.device.state, unit="F", minimum=50, maximum=77, step=1)
        for minimum in (20, 25):
            routine = replace(
                self.routine, minimum=minimum, maximum=25,
                anchors=tuple(replace(a, target=25) for a in self.routine.anchors),
            )
            with self.subTest(minimum=minimum):
                result = self.decision(routine=routine, climate=climate)
                self.assertEqual(result.status, "recommendation")
                self.assertEqual(result.device_target_c, 25)

    def test_fahrenheit_half_step_ties_round_down(self):
        climate = replace(self.device.state, unit="F", minimum=32, maximum=90, step=1)
        for native_target in (50.5, 68.5, 69.5, 77.5):
            routine = replace(
                self.routine, unit="F", minimum=50, maximum=90,
                maximum_slew_per_hour=1.8,
                anchors=tuple(replace(a, target=native_target) for a in self.routine.anchors),
            )
            with self.subTest(native_target=native_target):
                result = self.decision(routine=routine, climate=climate)
                self.assertEqual(result.status, "recommendation")
                self.assertEqual(
                    result.device_target_c, temperature_to_celsius(native_target - 0.5, "F")
                )

    def test_every_minute_stays_in_bounds_and_has_one_scheduled_phase(self):
        start = datetime(2026, 1, 1, 23, tzinfo=UTC)
        for minute in range(48 * 60):
            now = start + timedelta(minutes=minute)
            result = self.decision(now=now, reading=self.device.read_indoor(now))
            self.assertEqual(result.status, "recommendation")
            self.assertIn(result.phase, ("wind_down", "sleeping", "waking", "return_to_day", "daytime"))
            assert result.candidate_c is not None
            assert result.device_target_c is not None
            self.assertLessEqual(20, result.candidate_c)
            self.assertLessEqual(result.candidate_c, 24)
            self.assertLessEqual(20, result.device_target_c)
            self.assertLessEqual(result.device_target_c, 24)


if __name__ == "__main__":
    unittest.main()
