"""Weather-history input tests only; no planner adjustments or real weather."""

import math
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from itertools import permutations

from adaptive_comfort.weather import (
    HistoryRequirements,
    OutdoorReading,
    summarize_history,
)


class WeatherHistoryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 8, 12, tzinfo=UTC)
        self.source = "synthetic_outdoor"
        self.requirements = HistoryRequirements(
            window=timedelta(days=7),
            max_sample_hold=timedelta(hours=3),
            max_observation_age=timedelta(hours=3),
            minimum_coverage=0.9,
        )

    def reading(
        self, hours_ago: float, value: float | None = 10,
        unit: str | None = "C", *, available: bool = True,
    ) -> OutdoorReading:
        observed = self.now - timedelta(hours=hours_ago)
        return OutdoorReading(
            value=value, unit=unit, observed_at=observed, received_at=observed,
            source=self.source, available=available,
        )

    def full_history(self, value: float = 10):
        return [self.reading(hour, value) for hour in range(0, 169, 3)]

    def summary(self, readings, **changes):
        return summarize_history(
            readings,
            now=changes.get("now", self.now),
            source=changes.get("source", self.source),
            requirements=changes.get("requirements", self.requirements),
        )

    def assert_unavailable(self, result, reason):
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.mean_c)
        self.assertIn(reason, result.reason_codes)
        self.assertTrue(result.explanation)

    def test_constant_seven_day_history(self):
        result = self.summary(self.full_history())
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.mean_c, 10)
        self.assertEqual(result.coverage_fraction, 1)
        self.assertEqual(result.covered_duration, timedelta(days=7))
        self.assertEqual(result.latest_observed_at, self.now)
        self.assertEqual(result.window_start, self.now - timedelta(days=7))
        self.assertEqual(result.window_end, self.now)

    def test_w06_time_weighting_is_not_sample_count_weighting(self):
        requirements = replace(self.requirements, window=timedelta(hours=4), max_sample_hold=timedelta(hours=4))
        sparse = [self.reading(4, 10), self.reading(1, 20), self.reading(0, 20)]
        dense = sparse + [self.reading(minute / 60, 20) for minute in range(1, 60)]
        for readings in (sparse, dense):
            with self.subTest(count=len(readings)):
                result = self.summary(readings, requirements=requirements)
                self.assertEqual(result.status, "usable")
                self.assertEqual(result.coverage_fraction, 1)
                self.assertEqual(result.mean_c, 12.5)

    def test_gaps_are_not_zero_temperature_or_interpolated(self):
        requirements = replace(
            self.requirements, window=timedelta(hours=6),
            max_sample_hold=timedelta(minutes=90), minimum_coverage=0.5,
        )
        readings = [self.reading(6, 10), self.reading(3, 20), self.reading(0, 30)]
        result = self.summary(readings, requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.covered_duration, timedelta(hours=3))
        self.assertEqual(result.coverage_fraction, 0.5)
        self.assertEqual(result.mean_c, 15)
        self.assert_unavailable(self.summary(readings), "insufficient_coverage")

    def test_exact_coverage_boundary_and_one_microsecond_less(self):
        requirements = replace(
            self.requirements, window=timedelta(hours=10),
            max_sample_hold=timedelta(hours=9),
        )
        readings = [self.reading(10), self.reading(0)]
        boundary = self.summary(readings, requirements=requirements)
        self.assertEqual(boundary.status, "usable")
        self.assertEqual(boundary.coverage_fraction, 0.9)
        below = self.summary(readings, requirements=replace(
            requirements, max_sample_hold=timedelta(hours=9) - timedelta(microseconds=1),
        ))
        self.assert_unavailable(below, "insufficient_coverage")
        assert below.coverage_fraction is not None
        self.assertLess(below.coverage_fraction, 0.9)

    def test_freshness_and_hold_are_independent_inclusive_limits(self):
        requirements = replace(
            self.requirements, window=timedelta(hours=4),
            max_sample_hold=timedelta(hours=6),
        )
        boundary = self.reading(3)
        readings = [self.reading(6), boundary]
        result = self.summary(readings, requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.coverage_fraction, 1)
        old_time = self.now - timedelta(hours=3, microseconds=1)
        stale = replace(boundary, observed_at=old_time, received_at=self.now)
        result = self.summary([readings[0], stale], requirements=requirements)
        self.assert_unavailable(result, "stale_outdoor")
        self.assertEqual(result.coverage_fraction, 1)

    def test_w06_reordering_and_duplicates_do_not_add_weight(self):
        readings = [self.reading(4, 10), self.reading(1, 20), self.reading(0, 20)]
        requirements = replace(self.requirements, window=timedelta(hours=4), max_sample_hold=timedelta(hours=4))
        expected = self.summary(readings, requirements=requirements)
        for ordered in permutations(readings):
            self.assertEqual(self.summary(ordered, requirements=requirements), expected)
        duplicated = readings + [replace(readings[1], received_at=self.now)] * 100
        result = self.summary(duplicated, requirements=requirements)
        self.assertEqual(result.mean_c, expected.mean_c)
        self.assertEqual(result.covered_duration, expected.covered_duration)
        self.assertEqual(result.duplicate_count, 100)
        self.assertEqual(result, self.summary(reversed(duplicated), requirements=requirements))

    def test_w06_duplicate_burst_cannot_fill_missing_history(self):
        readings = [self.reading(1)] * 200 + [self.reading(0)]
        result = self.summary(readings)
        self.assert_unavailable(result, "insufficient_coverage")
        self.assertEqual(result.covered_duration, timedelta(hours=1))

    def test_duplicates_never_extend_original_expiry(self):
        requirements = replace(self.requirements, window=timedelta(hours=6), minimum_coverage=0.5)
        old = self.reading(6)
        result = self.summary(
            [old, replace(old, received_at=self.now), self.reading(0)],
            requirements=requirements,
        )
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.covered_duration, timedelta(hours=3))
        self.assertEqual(result.duplicate_count, 1)

    def test_conflicting_duplicate_values_or_availability_withhold(self):
        event = self.reading(3)
        for conflict in (replace(event, value=11), replace(event, available=False, value=None, unit=None)):
            for pair in ((event, conflict), (conflict, event)):
                self.assert_unavailable(
                    self.summary(self.full_history() + list(pair)), "conflicting_observations"
                )

    def test_equivalent_units_and_offset_times_deduplicate(self):
        event = self.reading(3)
        assert event.observed_at is not None
        shifted = event.observed_at.astimezone(timezone(timedelta(hours=2)))
        equivalent = replace(event, value=50, unit="F", observed_at=shifted, received_at=shifted)
        result = self.summary(self.full_history() + [equivalent])
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.mean_c, 10)
        self.assertEqual(result.duplicate_count, 1)
        mixed = [replace(event, value=50, unit="F") if index % 2 else event
                 for index, event in enumerate(self.full_history())]
        self.assertEqual(self.summary(mixed).mean_c, 10)

    def test_equal_wall_times_with_different_offsets_are_distinct_instants(self):
        first = self.reading(3, 10)
        second = self.reading(2, 20)
        assert first.observed_at is not None
        second = replace(
            second,
            observed_at=first.observed_at.replace(tzinfo=timezone(timedelta(hours=-1))),
            received_at=self.now,
        )
        requirements = replace(self.requirements, window=timedelta(hours=3))
        result = self.summary([first, second], requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.duplicate_count, 0)
        assert result.mean_c is not None
        self.assertAlmostEqual(result.mean_c, 50 / 3)

    def test_carry_in_uses_original_expiry_not_window_start(self):
        requirements = replace(self.requirements, window=timedelta(hours=4), minimum_coverage=0.75)
        result = self.summary([self.reading(5, 10), self.reading(1, 20)], requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.covered_duration, timedelta(hours=3))
        assert result.mean_c is not None
        self.assertAlmostEqual(result.mean_c, 40 / 3)
        expired = self.summary([self.reading(7, 10), self.reading(1, 20)], requirements=requirements)
        self.assert_unavailable(expired, "insufficient_coverage")
        self.assertEqual(expired.covered_duration, timedelta(hours=1))

    def test_right_boundary_has_no_duration_or_leading_backfill(self):
        requirements = replace(self.requirements, window=timedelta(hours=4), minimum_coverage=0.25)
        result = self.summary([self.reading(1, 20), self.reading(0, 30)], requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.mean_c, 20)
        self.assertEqual(result.covered_duration, timedelta(hours=1))
        fresh_only = self.summary([self.reading(0)])
        self.assert_unavailable(fresh_only, "insufficient_coverage")
        self.assertEqual(fresh_only.coverage_fraction, 0)

    def test_unavailable_events_stop_coverage_and_recovery_does_not_backfill(self):
        requirements = replace(
            self.requirements, window=timedelta(hours=4),
            max_sample_hold=timedelta(hours=4), minimum_coverage=0.5,
        )
        outage = self.reading(3, None, None, available=False)
        result = self.summary([self.reading(4, 10), outage, self.reading(1, 20)], requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.covered_duration, timedelta(hours=2))
        self.assertEqual(result.mean_c, 15)
        # An outage before the left boundary must also cancel a predecessor's carry-in.
        result = self.summary(
            [self.reading(5), self.reading(4.5, None, None, available=False), self.reading(1, 20)],
            requirements=requirements,
        )
        self.assert_unavailable(result, "insufficient_coverage")
        self.assertEqual(result.covered_duration, timedelta(hours=1))

    def test_latest_unavailable_blocks_even_fully_covered_history(self):
        history = self.full_history()[1:] + [self.reading(0, float("nan"), None, available=False)]
        result = self.summary(history)
        self.assert_unavailable(result, "outdoor_unavailable")
        self.assertEqual(result.coverage_fraction, 1)
        self.assertEqual(result, self.summary(reversed(history)))

    def test_empty_and_all_unavailable_histories(self):
        result = self.summary([])
        self.assert_unavailable(result, "no_history")
        self.assertEqual(result.coverage_fraction, 0)
        result = self.summary([self.reading(3, None, None, available=False), self.reading(0, None, None, available=False)])
        self.assert_unavailable(result, "outdoor_unavailable")
        self.assertEqual(result.covered_duration, timedelta(0))

    def test_invalid_available_values_and_units_withhold_entire_batch(self):
        event = self.reading(1)
        for value in (None, float("nan"), float("inf"), -float("inf"), True, "10"):
            with self.subTest(value=value):
                self.assert_unavailable(self.summary(self.full_history() + [replace(event, value=value)]), "invalid_temperature")
        for unit in (None, "", "K"):
            with self.subTest(unit=unit):
                self.assert_unavailable(self.summary([replace(event, unit=unit)]), "invalid_unit")
        for available in (None, 0, "false"):
            with self.subTest(available=available):
                self.assert_unavailable(self.summary([replace(event, available=available)]), "invalid_availability")

    def test_invalid_observation_and_receipt_times(self):
        event = self.reading(1)
        cases = [
            replace(event, observed_at=None), replace(event, received_at=None),
            replace(event, observed_at=self.now.replace(tzinfo=None)),
            replace(event, received_at=self.now.replace(tzinfo=None)),
            replace(event, observed_at=self.now + timedelta(seconds=1)),
            replace(event, received_at=self.now + timedelta(seconds=1)),
            replace(event, received_at=self.now - timedelta(hours=2)),
        ]
        for invalid in cases:
            with self.subTest(invalid=invalid):
                self.assert_unavailable(self.summary([invalid]), "invalid_sensor_time")

    def test_validation_precedes_window_filtering_and_deduplication(self):
        bad_old = self.reading(200, unit=None)
        bad_duplicate = replace(self.reading(3), received_at=self.now + timedelta(seconds=1))
        for bad, reason in ((bad_old, "invalid_unit"), (bad_duplicate, "invalid_sensor_time")):
            for history in (self.full_history() + [bad], [bad] + self.full_history()):
                self.assert_unavailable(self.summary(history), reason)
        old = self.reading(200)
        self.assert_unavailable(
            self.summary(self.full_history() + [old, replace(old, value=11)]),
            "conflicting_observations",
        )

    def test_selected_source_is_required_and_sources_cannot_be_mixed(self):
        for source in ("", " ", None):
            self.assert_unavailable(self.summary(self.full_history(), source=source), "invalid_source")
        other = replace(self.reading(1), source="another_outdoor_sensor")
        self.assert_unavailable(self.summary(self.full_history() + [other]), "source_mismatch")

    def test_invalid_requirements_and_clock_are_reported(self):
        for field in ("window", "max_sample_hold", "max_observation_age"):
            for value in (timedelta(0), timedelta(seconds=-1), None, 3):
                with self.subTest(field=field, value=value):
                    self.assert_unavailable(self.summary([], requirements=replace(self.requirements, **{field: value})), "invalid_requirements")
        for coverage in (0, -0.1, 1.01, float("nan"), float("inf"), None, True, "0.9"):
            with self.subTest(coverage=coverage):
                self.assert_unavailable(self.summary([], requirements=replace(self.requirements, minimum_coverage=coverage)), "invalid_requirements")
        for now in (self.now.replace(tzinfo=None), self.now.astimezone(timezone(timedelta(hours=1)))):
            self.assert_unavailable(self.summary([], now=now), "invalid_clock")
        self.assert_unavailable(self.summary([], requirements=replace(self.requirements, window=timedelta.max)), "invalid_requirements")

    def test_extreme_finite_values_do_not_overflow_weighted_accumulation(self):
        result = self.summary(self.full_history(1e308))
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.mean_c, 1e308)
        assert result.mean_c is not None
        self.assertTrue(math.isfinite(result.mean_c))
        requirements = replace(self.requirements, window=timedelta(hours=6))
        result = self.summary([self.reading(6, 1e308), self.reading(3, -1e308), self.reading(0, 0)], requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.mean_c, 0)

    def test_zero_offset_clock_is_normalized_before_elapsed_window_math(self):
        class SeasonalClock(tzinfo):
            """A synthetic offset change, independent of installed timezone data."""

            def utcoffset(self, dt):
                return timedelta(hours=1) if dt is not None and dt.day < 4 else timedelta(0)

            def dst(self, dt):
                return self.utcoffset(dt)

            def tzname(self, dt):
                return "synthetic_seasonal"

        clock = self.now.replace(tzinfo=SeasonalClock())
        complete = [self.reading(hour) for hour in range(170)]
        gapped = [self.reading(hour) for hour in range(170) if not 83 < hour <= 100]
        gapped.append(self.reading(100, None, None, available=False))
        for history in (complete, gapped):
            with self.subTest(events=len(history)):
                expected = self.summary(history)
                result = self.summary(history, now=clock)
                self.assertEqual(result, expected)
                assert result.window_start is not None
                self.assertIs(result.window_start.tzinfo, UTC)
        self.assertEqual(self.summary(gapped).covered_duration, timedelta(hours=151))
        self.assert_unavailable(self.summary(gapped, now=clock), "insufficient_coverage")

    def test_hold_is_clipped_before_datetime_overflow(self):
        now = datetime.max.replace(tzinfo=UTC)
        observed = now - timedelta(hours=2)
        event = replace(self.reading(0), observed_at=observed, received_at=observed)
        requirements = replace(self.requirements, window=timedelta(hours=2))
        result = self.summary([event], now=now, requirements=requirements)
        self.assertEqual(result.status, "usable")
        self.assertEqual(result.mean_c, 10)
        self.assertEqual(result.covered_duration, timedelta(hours=2))


if __name__ == "__main__":
    unittest.main()
