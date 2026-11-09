"""Build and explicitly export an offline demo using existing Python decisions."""

from datetime import UTC, datetime, time, timedelta
from itertools import pairwise
from math import pi, sin
from pathlib import Path
from typing import Any

from .core import evaluate, temperature_to_celsius
from .report_view import render_report
from .simulation import (
    ManualClock,
    simulate,
    synthetic_routine,
    synthetic_thermostat,
    trace_records,
)
from .weather import HistoryRequirements, OutdoorReading, summarize_history

_START = datetime(2026, 1, 1, 23, tzinfo=UTC)
_INDOOR_MAX_AGE = timedelta(minutes=5)
_WEATHER_SOURCE = "synthetic_demo_outdoor"


def _covered_segments(
    readings: list[OutdoorReading], start: datetime, end: datetime, hold: timedelta
) -> list[dict[str, Any]]:
    """Draw only generated, ordered, unique fixtures; this is not an ingestion API.

    The caller checks the total against the authoritative weather summary, so a
    change in history policy cannot silently produce a contradictory chart.
    """
    segments = []
    for index, reading in enumerate(readings):
        observed = reading.observed_at
        assert observed is not None
        following = readings[index + 1].observed_at if index + 1 < len(readings) else end
        assert following is not None
        if not reading.available:
            continue
        left = max(start, observed)
        right = observed + min(hold, following - observed, end - observed)
        if left < right:
            segments.append({
                "start": left.isoformat(), "end": right.isoformat(),
                "value_c": temperature_to_celsius(reading.value, reading.unit),
            })
    return segments


def _weather_cases(end: datetime) -> list[dict[str, Any]]:
    requirements = HistoryRequirements(
        window=timedelta(days=7), max_sample_hold=timedelta(hours=3),
        max_observation_age=timedelta(hours=3), minimum_coverage=0.9,
    )
    start = end - requirements.window
    observations = []
    for hour in range(169):
        observed = start + timedelta(hours=hour)
        # Illustrative daily variation and a slow trend, not measured weather.
        value = round(10 + 3 * hour / 168 + 3 * sin(2 * pi * (observed.hour - 9) / 24), 2)
        observations.append(OutdoorReading(
            value=value, unit="C", observed_at=observed, received_at=observed,
            source=_WEATHER_SOURCE,
        ))
    fixtures = (
        ("complete", "Complete history", "Seven days of hourly synthetic observations, including a fresh final reading.", observations),
        ("gaps", "A missing day", "One 24-hour block of observations is missing. Limited holds leave gaps even though the latest reading is fresh.",
         [reading for index, reading in enumerate(observations) if not 48 <= index < 72]),
        ("stale", "Stale recent readings", "The latest observation is six hours old. Good overall coverage cannot substitute for current data.", observations[:-6]),
    )
    scenarios = []
    for identifier, title, description, readings in fixtures:
        summary = summarize_history(readings, now=end, source=_WEATHER_SOURCE, requirements=requirements)
        segments = _covered_segments(readings, start, end, requirements.max_sample_hold)
        represented = sum((datetime.fromisoformat(segment["end"]) - datetime.fromisoformat(segment["start"])
                           for segment in segments), timedelta(0))
        if represented != summary.covered_duration:
            raise ValueError("Demo chart intervals disagree with the authoritative weather coverage.")
        points = []
        for reading in readings:
            assert reading.observed_at is not None
            points.append({
                "timestamp": reading.observed_at.isoformat(),
                "value_c": temperature_to_celsius(reading.value, reading.unit) if reading.available else None,
            })
        scenarios.append({
            "id": identifier, "title": title, "description": description,
            "start": start.isoformat(), "end": end.isoformat(),
            "observations": points, "segments": segments,
            "summary": {
                "status": summary.status, "mean_c": summary.mean_c,
                "coverage_fraction": summary.coverage_fraction,
                "covered_hours": represented.total_seconds() / 3600,
                "latest_observed_at": summary.latest_observed_at.isoformat() if summary.latest_observed_at else None,
                "reason_codes": list(summary.reason_codes), "explanation": summary.explanation,
            },
            "requirements": {
                "window_hours": 168, "max_sample_hold_hours": 3,
                "max_observation_age_hours": 3, "minimum_coverage": requirements.minimum_coverage,
            },
        })
    return scenarios


def build_demo(hours: int = 48, step_minutes: int = 30) -> dict[str, Any]:
    """Generate report-v1 data without changing any baseline or weather policy."""
    for name, value, upper in (("hours", hours, 168), ("step_minutes", step_minutes, 60)):
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError(f"{name} must be an integer between 1 and {upper}.")
    routine = synthetic_routine()
    device = synthetic_thermostat()
    end = _START + timedelta(hours=hours)
    trace = simulate(
        routine, device, ManualClock(_START), duration=timedelta(hours=hours),
        step=timedelta(minutes=step_minutes), max_sensor_age=_INDOOR_MAX_AGE,
    )
    boundaries = {_START, end}
    for day_offset in range(-1, (end.date() - _START.date()).days + 2):
        midnight = datetime.combine(_START.date() + timedelta(days=day_offset), time.min, tzinfo=UTC)
        for anchor in routine.anchors:
            instant = midnight + timedelta(minutes=anchor.minute)
            if _START < instant < end:
                boundaries.add(instant)
    evaluations = {row.timestamp: row for row in trace}
    for instant in sorted(boundaries):
        if instant not in evaluations:
            evaluations[instant] = evaluate(
                routine, device.read_indoor(instant), device.state,
                now=instant, max_sensor_age=_INDOOR_MAX_AGE,
            )
    spans = [{
        "start": left.isoformat(), "end": right.isoformat(),
        "phase": evaluations[left].phase, "context": evaluations[left].context,
    } for left, right in pairwise(sorted(boundaries))]
    plotted = trace_records(evaluations[instant] for instant in sorted(evaluations))
    for row in plotted:
        row["trace_id"] = "plot:" + str(row["trace_id"])
    return {
        "version": 1,
        "routine": {
            "start": _START.isoformat(), "end": end.isoformat(), "step_minutes": step_minutes,
            "records": trace_records(trace), "plot_records": plotted, "phase_spans": spans,
        },
        "weather": _weather_cases(end),
    }


def generate_report(
    output: Path, *, hours: int = 48, step_minutes: int = 30, overwrite: bool = False
) -> Path:
    """Write only the explicitly requested HTML file; never launch a browser."""
    output = Path(output)
    if output.suffix.lower() not in (".html", ".htm"):
        raise ValueError("The HTML report path must end in .html or .htm.")
    document = render_report(build_demo(hours=hours, step_minutes=step_minutes))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as stream:
        stream.write(document)
    return output.resolve()
