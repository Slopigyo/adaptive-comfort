"""Pure outdoor-history validation and averaging; never proposes setpoints."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fractions import Fraction

from .core import ValidationError, temperature_to_celsius


@dataclass(frozen=True)
class OutdoorReading:
    value: float | None
    unit: str | None
    observed_at: datetime | None
    received_at: datetime | None
    source: str
    available: bool = True


@dataclass(frozen=True)
class HistoryRequirements:
    window: timedelta
    max_sample_hold: timedelta
    max_observation_age: timedelta
    minimum_coverage: float


@dataclass(frozen=True)
class WeatherHistorySummary:
    status: str
    reason_codes: tuple[str, ...]
    explanation: str
    source: str | None = None
    mean_c: float | None = None
    coverage_fraction: float | None = None
    covered_duration: timedelta | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    latest_observed_at: datetime | None = None
    duplicate_count: int = 0


def _validate_requirements(requirements: HistoryRequirements) -> Fraction:
    if not isinstance(requirements, HistoryRequirements):
        raise ValidationError("invalid_requirements", "Explicit history requirements are required.")
    for duration in (
        requirements.window,
        requirements.max_sample_hold,
        requirements.max_observation_age,
    ):
        if not isinstance(duration, timedelta) or duration <= timedelta(0):
            raise ValidationError("invalid_requirements", "History durations must be positive timedeltas.")
    coverage = requirements.minimum_coverage
    if type(coverage) not in (int, float) or not 0 < coverage <= 1:
        raise ValidationError("invalid_requirements", "Minimum coverage must be a finite number in (0, 1].")
    return Fraction(str(coverage))


def _observation_time(value: datetime | None) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("invalid_sensor_time", "Observation and receipt times must be timezone-aware.")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValidationError("invalid_sensor_time", "Sensor time cannot be represented in UTC.") from error


def _observations(
    readings: Iterable[OutdoorReading], source: str, now: datetime
) -> tuple[list[tuple[datetime, float | None]], int]:
    unique: dict[datetime, float | None] = {}
    duplicates = 0
    for reading in readings:
        if not isinstance(reading, OutdoorReading):
            raise ValidationError("invalid_observation", "History entries must be outdoor observation records.")
        if reading.source != source:
            raise ValidationError("source_mismatch", "History contains a source other than the selected outdoor source.")
        observed = _observation_time(reading.observed_at)
        received = _observation_time(reading.received_at)
        if not observed <= received <= now:
            raise ValidationError("invalid_sensor_time", "Sensor times are future-dated or observation follows receipt.")
        if type(reading.available) is not bool:
            raise ValidationError("invalid_availability", "Observation availability must be an explicit boolean.")
        value = temperature_to_celsius(reading.value, reading.unit) if reading.available else None
        # Validate before deduplication: a valid copy must not hide a corrupt one.
        if observed in unique:
            if unique[observed] != value:
                raise ValidationError("conflicting_observations", "One observation time has conflicting values or availability.")
            duplicates += 1
        else:
            unique[observed] = value
    return sorted(unique.items()), duplicates


def summarize_history(
    readings: Iterable[OutdoorReading],
    *,
    now: datetime,
    source: str,
    requirements: HistoryRequirements,
) -> WeatherHistorySummary:
    """Summarize received history over [now-window, now), or withhold its mean.

    Valid measurements hold forward for at most max_sample_hold. Unavailable
    events terminate preceding holds; missing intervals are never reconstructed.
    """
    start = None
    end = None
    try:
        if not isinstance(source, str) or not source.strip():
            raise ValidationError("invalid_source", "One explicit outdoor source must be selected.")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValidationError("invalid_clock", "An explicit, timezone-aware UTC evaluation time is required.")
        # A zone can be UTC-offset zero now but differ earlier in the window.
        # Use fixed UTC so subtraction always measures elapsed, not calendar, time.
        now = now.astimezone(UTC)
        end = now
        minimum_coverage = _validate_requirements(requirements)
        try:
            start = now - requirements.window
        except OverflowError as error:
            raise ValidationError("invalid_requirements", "History window exceeds the supported datetime range.") from error
        events, duplicate_count = _observations(readings, source, now)
    except ValidationError as error:
        return WeatherHistorySummary(
            status="unavailable", reason_codes=(error.code,),
            explanation=f"Outdoor average withheld: {error}",
            source=source if isinstance(source, str) else None,
            window_start=start, window_end=end,
        )

    weighted = Fraction(0)
    covered_us = 0
    for index, (observed, value) in enumerate(events):
        if value is None:
            continue
        following = events[index + 1][0] if index + 1 < len(events) else now
        # Clip the duration before adding it, including near datetime.max.
        duration = min(following - observed, requirements.max_sample_hold, now - observed)
        stop = observed + duration
        left = max(observed, start)
        if stop <= left:
            continue
        elapsed_us = (stop - left) // timedelta(microseconds=1)
        covered_us += elapsed_us
        # Exact accumulation of normalized floats avoids overflowing value * time
        # for accepted finite inputs. Conversion back to float happens after division.
        weighted += Fraction(value) * elapsed_us

    window_us = requirements.window // timedelta(microseconds=1)
    coverage = Fraction(covered_us, window_us)
    latest_valid = next((time for time, value in reversed(events) if value is not None), None)
    reasons = []
    explanations = []
    if not events:
        reasons.append("no_history")
        explanations.append("No outdoor history was supplied.")
    else:
        if events[-1][1] is None:
            reasons.append("outdoor_unavailable")
            explanations.append("The latest outdoor event is unavailable.")
        elif now - events[-1][0] > requirements.max_observation_age:
            reasons.append("stale_outdoor")
            explanations.append("The newest outdoor observation is older than the configured limit.")
        if coverage < minimum_coverage:
            reasons.append("insufficient_coverage")
            explanations.append("Covered elapsed time is below the configured minimum.")

    usable = not reasons
    return WeatherHistorySummary(
        status="usable" if usable else "unavailable",
        reason_codes=("time_weighted_history",) if usable else tuple(reasons),
        explanation=(
            "Time-weighted outdoor mean over covered time only; gaps remain unknown. This is not a setpoint."
            if usable else "Outdoor average withheld: " + " ".join(explanations)
        ),
        source=source,
        mean_c=float(weighted / covered_us) if usable else None,
        coverage_fraction=float(coverage),
        covered_duration=timedelta(microseconds=covered_us),
        window_start=start, window_end=now, latest_observed_at=latest_valid,
        duplicate_count=duplicate_count,
    )
