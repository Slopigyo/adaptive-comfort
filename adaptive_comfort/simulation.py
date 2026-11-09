"""Synthetic fixtures and a recording, strictly observe-only routine runner."""

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from .core import Anchor, ClimateState, Evaluation, IndoorReading, Routine, evaluate


@dataclass
class ManualClock:
    current: datetime

    def __post_init__(self) -> None:
        if self.current.tzinfo is None or self.current.utcoffset() != timedelta(0):
            raise ValueError("The synthetic clock must be timezone-aware UTC.")

    def now(self) -> datetime:
        return self.current

    def advance(self, elapsed: timedelta) -> None:
        if elapsed <= timedelta(0):
            raise ValueError("The synthetic clock must advance by a positive duration.")
        self.current += elapsed


@dataclass
class RecordingThermostat:
    state: ClimateState
    indoor_value: float
    indoor_unit: str
    command_attempts: list[tuple[str, object]] = field(default_factory=list)

    def read_indoor(self, now: datetime) -> IndoorReading:
        return IndoorReading(
            value=self.indoor_value, unit=self.indoor_unit,
            observed_at=now, received_at=now, source="synthetic_indoor",
        )

    def command(self, operation: str, value: object) -> None:
        self.command_attempts.append((operation, value))
        raise RuntimeError("This offline fake rejects every command; control is not implemented.")


def synthetic_routine() -> Routine:
    """Arithmetic fixture values only, never household or equipment defaults."""
    return Routine(
        anchors=(
            Anchor(-60, 22, "wind_down"),
            Anchor(120, 21, "sleeping"),
            Anchor(300, 21, "waking"),
            Anchor(420, 23, "return_to_day"),
            Anchor(540, 22, "daytime"),
        ),
        unit="C", minimum=20, maximum=24, maximum_slew_per_hour=1,
        revision="synthetic_routine_v1", approved=True, enabled=True,
    )


def synthetic_thermostat() -> RecordingThermostat:
    return RecordingThermostat(
        state=ClimateState(minimum=18, maximum=26, step=0.5, unit="C", mode="cool"),
        indoor_value=22, indoor_unit="C",
    )


def simulate(
    routine: Routine,
    thermostat: RecordingThermostat,
    clock: ManualClock,
    *,
    duration: timedelta,
    step: timedelta,
    max_sensor_age: timedelta,
) -> list[Evaluation]:
    """Preview [start, end) using synthetic observations, with no dispatch path."""
    if duration <= timedelta(0) or step <= timedelta(0):
        raise ValueError("Simulation duration and step must both be positive.")
    end = clock.now() + duration
    trace = []
    while clock.now() < end:
        now = clock.now()
        trace.append(evaluate(
            routine, thermostat.read_indoor(now), thermostat.state,
            now=now, max_sensor_age=max_sensor_age,
        ))
        clock.advance(min(step, end - now))
    return trace


def trace_records(trace: Iterable[Evaluation]) -> list[dict[str, object]]:
    records = []
    for index, result in enumerate(trace):
        record = asdict(result)
        record["timestamp"] = result.timestamp.isoformat()
        record["wake_date"] = result.wake_date.isoformat() if result.wake_date else None
        record["reason_codes"] = list(result.reason_codes)
        record["trace_id"] = f"{result.routine_revision}:{index:04d}"
        record["mode"] = "observe_only"
        record["commands_allowed"] = False
        records.append(record)
    return records
