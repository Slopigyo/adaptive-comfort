"""Print a synthetic trace or explicitly export a local HTML demo."""

import argparse
import json
import sys
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .simulation import (
    ManualClock,
    simulate,
    synthetic_routine,
    synthetic_thermostat,
    trace_records,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview an observe-only synthetic UTC routine.")
    parser.add_argument("--hours", type=int, default=48, help="Synthetic duration, 1–168 (default: 48).")
    parser.add_argument("--step-minutes", type=int, default=30, help="Tick interval, 1–60 (default: 30).")
    parser.add_argument("--html", type=Path, help="Write a self-contained .html report instead of JSON.")
    parser.add_argument("--open", action="store_true", help="Open the generated local HTML file in your browser.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting the explicitly requested HTML file.")
    arguments = parser.parse_args()
    if not 1 <= arguments.hours <= 168:
        parser.error("--hours must be between 1 and 168")
    if not 1 <= arguments.step_minutes <= 60:
        parser.error("--step-minutes must be between 1 and 60")
    if arguments.html is None and (arguments.open or arguments.force):
        parser.error("--open and --force require --html")
    if arguments.html is not None:
        from .report import generate_report

        try:
            output = generate_report(
                arguments.html, hours=arguments.hours, step_minutes=arguments.step_minutes,
                overwrite=arguments.force,
            )
        except FileExistsError:
            parser.error("Report already exists. Use --force only if you want to replace it.")
        except (OSError, ValueError) as error:
            parser.error(str(error))
        print(f"Wrote local observe-only demo: {output}")
        if arguments.open:
            try:
                opened = webbrowser.open(output.as_uri())
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print(f"Browser launch was unavailable; open this file manually: {output}", file=sys.stderr)
        return

    trace = simulate(
        synthetic_routine(),
        synthetic_thermostat(),
        ManualClock(datetime(2026, 1, 1, 23, tzinfo=UTC)),
        duration=timedelta(hours=arguments.hours),
        step=timedelta(minutes=arguments.step_minutes),
        max_sensor_age=timedelta(minutes=5),
    )
    for record in trace_records(trace):
        print(json.dumps(record, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
