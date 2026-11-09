"""Pure UTC routine evaluation. No clocks, storage, networks, or actuators."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
from math import ceil, floor, isfinite

DAY = timedelta(days=1)
PHASES = ("wind_down", "sleeping", "waking", "return_to_day", "daytime")
CONTEXTS = ("sleeping", "sleeping", "waking", "waking", "daytime")


class ValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Anchor:
    minute: int
    target: float
    phase: str


@dataclass(frozen=True)
class Routine:
    anchors: tuple[Anchor, ...]
    unit: str | None
    minimum: float
    maximum: float
    maximum_slew_per_hour: float
    revision: str
    approved: bool = False
    enabled: bool = False


@dataclass(frozen=True)
class IndoorReading:
    value: float | None
    unit: str | None
    observed_at: datetime | None
    received_at: datetime | None
    source: str
    available: bool = True


@dataclass(frozen=True)
class ClimateState:
    minimum: float
    maximum: float
    step: float
    unit: str | None
    mode: str
    available: bool = True


@dataclass(frozen=True)
class Evaluation:
    timestamp: datetime
    routine_revision: str | None
    status: str
    reason_codes: tuple[str, ...]
    explanation: str
    wake_date: date | None = None
    phase: str | None = None
    context: str | None = None
    indoor_c: float | None = None
    baseline_c: float | None = None
    candidate_c: float | None = None
    device_target_c: float | None = None
    allowed_minimum_c: float | None = None
    allowed_maximum_c: float | None = None


def _number(value: float | None) -> Fraction:
    if type(value) not in (int, float):
        raise ValidationError("invalid_temperature", "A finite numeric temperature is required.")
    number = Decimal(str(value))
    if not number.is_finite() or not isfinite(float(number)):
        raise ValidationError("invalid_temperature", "Non-finite temperatures are not usable.")
    return Fraction(number)


def _convert(value: float | None, unit: str | None, *, difference: bool) -> Fraction:
    if unit not in ("C", "F"):
        raise ValidationError("invalid_unit", "An explicit C or F temperature unit is required.")
    number = _number(value)
    if unit == "F":
        # A step/rate is a difference, so Fahrenheit's absolute offset must not apply.
        number = (number if difference else number - 32) * 5 / 9
    result = float(number)
    if not isfinite(result):
        raise ValidationError("invalid_temperature", "Temperature cannot be represented finitely.")
    return number


def temperature_to_celsius(value: float | None, unit: str | None) -> float:
    return float(_convert(value, unit, difference=False))


def difference_to_celsius(value: float | None, unit: str | None) -> float:
    return float(_convert(value, unit, difference=True))


def _bounds(minimum: float, maximum: float, unit: str | None) -> tuple[Fraction, Fraction]:
    lower = _convert(minimum, unit, difference=False)
    upper = _convert(maximum, unit, difference=False)
    if lower > upper:
        raise ValidationError("invalid_bounds", "The minimum temperature exceeds the maximum.")
    return lower, upper


def _validate_routine(routine: Routine) -> tuple[tuple[Fraction, ...], Fraction, Fraction]:
    lower, upper = _bounds(routine.minimum, routine.maximum, routine.unit)
    slew = _convert(routine.maximum_slew_per_hour, routine.unit, difference=True)
    if slew <= 0:
        raise ValidationError("invalid_slew", "A positive baseline slew limit is required.")
    anchors = routine.anchors
    if (
        tuple(a.phase for a in anchors) != PHASES
        or any(type(a.minute) is not int or not -1440 < a.minute < 1440 for a in anchors)
        or any(a.minute >= b.minute for a, b in pairwise(anchors))
    ):
        raise ValidationError("invalid_schedule", "Five correctly ordered, distinct phase anchors are required.")
    if anchors[-1].minute - anchors[0].minute >= 1440 or anchors[3].minute < 0:
        raise ValidationError("invalid_schedule", "The routine must fit one day and wake on its named date.")
    if not isinstance(routine.revision, str) or not routine.revision.strip():
        raise ValidationError("invalid_schedule", "A routine revision is required.")
    targets = tuple(_convert(a.target, routine.unit, difference=False) for a in anchors)
    if any(not lower <= target <= upper for target in targets):
        raise ValidationError("anchor_out_of_bounds", "An approved anchor lies outside the approved envelope.")
    if targets[0] < targets[1] or targets[2] > targets[3]:
        raise ValidationError("invalid_schedule", "Wind-down must not warm and pre-wake must not cool.")
    if targets[1] != targets[2] or targets[-1] != targets[0]:
        raise ValidationError("invalid_schedule", "The overnight and daytime holds must have equal endpoint targets.")
    for index, anchor in enumerate(anchors):
        following = (index + 1) % len(anchors)
        minutes = anchors[following].minute - anchor.minute
        if following == 0:
            minutes += 1440
        rate = abs(targets[following] - targets[index]) * 60 / minutes
        if rate > slew:
            raise ValidationError("excessive_slew", "An approved ramp exceeds its configured baseline slew limit.")
    return targets, lower, upper


def _validate_clock(now: datetime) -> None:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValidationError("invalid_clock", "This first slice requires an explicit, timezone-aware UTC clock.")


def _sensor_time(value: datetime | None) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("invalid_sensor_time", "Observation and receipt times must be timezone-aware.")
    return value.astimezone(UTC)


def _validate_reading(
    reading: IndoorReading | None, now: datetime, max_sensor_age: timedelta
) -> float:
    if reading is None or reading.available is not True:
        raise ValidationError("indoor_unavailable", "The selected indoor measurement is unavailable.")
    if not isinstance(max_sensor_age, timedelta) or max_sensor_age <= timedelta(0):
        raise ValidationError("invalid_freshness_limit", "A positive explicit sensor age limit is required.")
    observed = _sensor_time(reading.observed_at)
    received = _sensor_time(reading.received_at)
    if not observed <= received <= now:
        raise ValidationError("invalid_sensor_time", "Sensor times are future-dated or observation follows receipt.")
    if now - observed > max_sensor_age:
        raise ValidationError("stale_indoor", "The indoor observation is older than the configured limit.")
    if not reading.source:
        raise ValidationError("indoor_unavailable", "The selected indoor source must be identified.")
    return temperature_to_celsius(reading.value, reading.unit)


def _baseline(
    routine: Routine, targets: tuple[Fraction, ...], now: datetime
) -> tuple[Fraction, str, str, date]:
    midnight = datetime.combine(now.date(), time.min, tzinfo=UTC)
    start = midnight + timedelta(minutes=routine.anchors[0].minute)
    cycle = (now - start) // DAY
    start += cycle * DAY
    wake_date = (midnight + cycle * DAY).date()
    minute = Fraction((now - start) // timedelta(microseconds=1), 60_000_000)
    for index, anchor in enumerate(routine.anchors):
        following = (index + 1) % len(routine.anchors)
        left = anchor.minute - routine.anchors[0].minute
        right = (
            routine.anchors[following].minute - routine.anchors[0].minute
            if following else 1440
        )
        # Half-open intervals assign a boundary to the new phase exactly once.
        if left <= minute < right:
            fraction = (minute - left) / (right - left)
            target = targets[index] + fraction * (targets[following] - targets[index])
            return target, anchor.phase, CONTEXTS[index], wake_date
    raise ValidationError("invalid_schedule", "No phase covers this evaluation time.")


def _device_target(
    candidate: Fraction, lower: Fraction, upper: Fraction, origin: Fraction, step: Fraction
) -> Fraction:
    # Keep units, interpolation, and grid arithmetic exact until display. A 1 F
    # step is a repeating Celsius fraction; early float conversion loses ties/endpoints.
    first = ceil((lower - origin) / step)
    last = floor((upper - origin) / step)
    if first > last:
        raise ValidationError("no_representable_target", "No device step lies inside the allowed envelope.")
    position = (candidate - origin) / step
    index = floor(position)
    if position - index > Fraction(1, 2):
        index += 1
    index = min(max(index, first), last)
    return origin + index * step


def evaluate(
    routine: Routine | None,
    reading: IndoorReading | None,
    climate: ClimateState,
    *,
    now: datetime,
    max_sensor_age: timedelta,
) -> Evaluation:
    """Return an observe-only preview or a reason to withhold it; never dispatch."""
    revision = routine.revision if routine is not None else None
    if routine is not None and routine.enabled is not True:
        return Evaluation(now, revision, "disabled", ("observe_only", "routine_disabled"),
                          "Routine disabled. No recommendation and no commands.")
    try:
        if routine is None:
            raise ValidationError("routine_missing", "No approved baseline routine is available.")
        if routine.approved is not True:
            raise ValidationError("routine_unapproved", "The routine has not been explicitly approved.")
        _validate_clock(now)
        targets, approved_minimum, approved_maximum = _validate_routine(routine)
        indoor = _validate_reading(reading, now, max_sensor_age)
        if climate.available is not True:
            raise ValidationError("climate_unavailable", "The selected climate device is unavailable.")
        if climate.mode not in ("heat", "cool"):
            raise ValidationError("unsupported_mode", "Only a single-target heat or cool preview is supported.")
        device_minimum, device_maximum = _bounds(climate.minimum, climate.maximum, climate.unit)
        step = _convert(climate.step, climate.unit, difference=True)
        if step <= 0:
            raise ValidationError("invalid_device_step", "A positive device target step is required.")
        lower = max(approved_minimum, device_minimum)
        upper = min(approved_maximum, device_maximum)
        if lower > upper:
            raise ValidationError("empty_bounds", "Approved and device temperature bounds do not intersect.")
        baseline, phase, context, wake_date = _baseline(routine, targets, now)
        candidate = min(max(baseline, lower), upper)
        display_target = _device_target(candidate, lower, upper, device_minimum, step)
    except ValidationError as error:
        return Evaluation(now, revision, "withheld", ("observe_only", error.code),
                          f"Recommendation withheld: {error} No commands are available.")

    reasons = ["observe_only", "approved_routine"]
    explanation = (
        f"Observe-only: scheduled {phase.replace('_', ' ')} baseline {float(baseline):.3f} C; "
        f"bounded candidate {float(candidate):.3f} C; device-rounded display {float(display_target):.3f} C. "
        "This is a requested trajectory, not a prediction of room temperature. "
    )
    if candidate != baseline:
        reasons.append("constrained_to_bounds")
        explanation += "The device/approved bounds constrain the baseline. "
    if climate.mode == "cool":
        explanation += "A higher cooling target permits passive warming; heating is not enabled. "
    explanation += "The rounded target is not command-ready. No commands are available."
    return Evaluation(
        timestamp=now, routine_revision=revision, status="recommendation",
        reason_codes=tuple(reasons), explanation=explanation, wake_date=wake_date,
        phase=phase, context=context, indoor_c=indoor, baseline_c=float(baseline),
        candidate_c=float(candidate), device_target_c=float(display_target),
        allowed_minimum_c=float(lower), allowed_maximum_c=float(upper),
    )
