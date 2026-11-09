"""Self-contained, presentation-only HTML for the version-1 offline report.

No planner, weather policy, clock, browser, or network is used here. The caller
owns the data contract; original samples drive playback and exact plot records
drive geometry. Weather segments and summaries are already evaluated by Python.
All chart geometry and data tables work without JavaScript. Checked-in assets
are embedded, never linked, and only the trusted static script receives a CSP hash.
"""

import json
import sys
from base64 import b64encode
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html import escape
from math import isfinite
from pathlib import Path

_ASSETS = Path(__file__).with_name("report_assets")
_LEFT, _RIGHT, _TOP, _BOTTOM = 68, 974, 42, 274
_PHASE_CLASSES = {
    "wind_down": "phase-wind-down",
    "sleeping": "phase-sleeping",
    "waking": "phase-waking",
    "return_to_day": "phase-return-to-day",
    "daytime": "phase-daytime",
}
_TEMPERATURE_FIELDS = (
    "indoor_c", "baseline_c", "candidate_c", "device_target_c",
    "allowed_minimum_c", "allowed_maximum_c",
)


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Report temperatures and numeric diagnostics must be numbers or null.")
    result = float(value)
    if not isfinite(result):
        raise ValueError("Report numbers must be finite.")
    return result


def _n(value: float, places: int = 2) -> str:
    if not isfinite(value):
        raise ValueError("Report display values must be finite.")
    result = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return "0" if result in ("", "-0") else result


def _coordinate(value: float) -> str:
    return _n(value, 3)


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Report timestamps must be timezone-aware UTC.")
    return parsed.astimezone(UTC)


def _milliseconds(value: datetime) -> int:
    return int((value - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds() * 1000)


def _utc(value: str | None) -> str:
    if value is None:
        return "Unavailable"
    return _instant(value).isoformat(sep=" ").removesuffix("+00:00") + " UTC"


def _phase(value: str | None) -> str:
    return value.replace("_", " ") if value else "Unavailable"


def _temp(value: object, element_id: str | None = None, *, axis: bool = False) -> str:
    number = _number(value)
    raw = "" if number is None else repr(number)
    text = "Unavailable" if number is None else _n(number, 1 if axis else 2)
    if number is not None and not axis:
        text += " °C"
    id_attr = f' id="{_e(element_id)}"' if element_id else ""
    mode = ' data-temp-mode="axis"' if axis else ""
    return f'<span{id_attr} data-temp-c="{_e(raw)}"{mode}>{_e(text)}</span>'


def _amount(value: object, *, percent: bool = False) -> str:
    number = _number(value)
    if number is None:
        return "Unavailable"
    return _e(_n(number * 100 if percent else number, 1)) + ("%" if percent else "")


def _reasons(values: list[str]) -> str:
    return _e(", ".join(values) if values else "None reported")


class _Chart:
    """Display scales only; normalized arithmetic also keeps extreme finite values finite."""

    def __init__(self, start: str, end: str, values: Iterable[object]):
        self.start = _instant(start)
        self.end = _instant(end)
        self.seconds = (self.end - self.start).total_seconds()
        if self.seconds < 0:
            raise ValueError("Report chart end must not precede its start.")
        finite = [number for value in values if (number := _number(value)) is not None]
        self.has_values = bool(finite)
        low, high = (min(finite), max(finite)) if finite else (0.0, 1.0)
        self.scale = max(abs(low), abs(high), 1.0)
        low, high = low / self.scale, high / self.scale
        padding = (high - low) * 0.12 if high > low else max(abs(low) * 0.05, 1 / self.scale)
        limit = sys.float_info.max / self.scale
        self.low = max(-limit, low - padding)
        self.high = min(limit, high + padding)

    def x(self, timestamp: str) -> float:
        fraction = ((_instant(timestamp) - self.start).total_seconds() / self.seconds
                    if self.seconds else 0.5)
        return _LEFT + max(0.0, min(1.0, fraction)) * (_RIGHT - _LEFT)

    def y(self, value: object) -> float:
        number = _number(value)
        if number is None:
            raise ValueError("Null temperatures are gaps, not chart coordinates.")
        fraction = (number / self.scale - self.low) / (self.high - self.low)
        return _BOTTOM - fraction * (_BOTTOM - _TOP)

    def axes(self) -> str:
        parts = ['<g class="axes">',
                 '<text x="18" y="26" data-unit="">°C</text>']
        for index in range(5):
            fraction = index / 4
            y = _BOTTOM - fraction * (_BOTTOM - _TOP)
            parts.append(f'<line class="grid-line" x1="{_LEFT}" x2="{_RIGHT}" '
                         f'y1="{_coordinate(y)}" y2="{_coordinate(y)}"/>')
            if self.has_values:
                value = (self.low + (self.high - self.low) * fraction) * self.scale
                parts.append(f'<text x="{_LEFT - 10}" y="{_coordinate(y + 4)}" '
                             f'text-anchor="end" data-temp-c="{_e(repr(value))}" '
                             f'data-temp-mode="axis">{_e(_n(value, 1))}</text>')
        for index in range(5 if self.seconds else 1):
            fraction = index / 4 if self.seconds else 0.5
            timestamp = self.start + timedelta(seconds=self.seconds * fraction)
            x = _LEFT + fraction * (_RIGHT - _LEFT)
            anchor = "start" if fraction == 0 else "end" if fraction == 1 else "middle"
            parts.append(f'<text class="axis-label" x="{_coordinate(x)}" y="306" '
                         f'text-anchor="{anchor}">{timestamp:%m-%d %H:%M}</text>')
        parts.append(f'<text class="axis-label" x="{_RIGHT}" y="328" text-anchor="end">UTC</text>')
        if not self.has_values:
            parts.append('<text x="520" y="150" text-anchor="middle">No numeric chart values supplied</text>')
        parts.append('</g>')
        return "".join(parts)


def _svg_open(chart: _Chart, element_id: str, title: str, description: str) -> str:
    return (
        f'<svg id="{_e(element_id)}" class="chart" viewBox="0 0 1000 342" role="img" '
        f'aria-labelledby="{_e(element_id)}-title {_e(element_id)}-desc" '
        f'data-start-ms="{_milliseconds(chart.start)}" data-end-ms="{_milliseconds(chart.end)}" '
        f'data-left="{_LEFT}" data-right="{_RIGHT}">'
        f'<title id="{_e(element_id)}-title">{_e(title)}</title>'
        f'<desc id="{_e(element_id)}-desc">{_e(description)}</desc>'
    )


def _runs(rows: list[dict], fields: tuple[str, ...]) -> Iterator[list[dict]]:
    run: list[dict] = []
    for row in rows:
        if all(_number(row[field]) is not None for field in fields):
            run.append(row)
        else:
            if run:
                yield run
                run = []
    if run:
        yield run


def _line(chart: _Chart, rows: list[dict], field: str, series: str) -> str:
    parts = []
    for run in _runs(rows, (field,)):
        points = [f'{_coordinate(chart.x(row["timestamp"]))},{_coordinate(chart.y(row[field]))}'
                  for row in run]
        path = "M" + " L".join(points)
        parts.append(f'<path class="series {series}" data-series="{series}" d="{path}"/>')
        if len(run) == 1:
            x, y = points[0].split(",")
            parts.append(f'<circle class="series-point {series}" data-series="{series}" '
                         f'cx="{x}" cy="{y}" r="3.5"/>')
    return "".join(parts)


def _routine_svg(routine: dict) -> str:
    rows = routine["plot_records"]
    chart = _Chart(routine["start"], routine["end"],
                   (row[field] for row in rows for field in _TEMPERATURE_FIELDS))
    parts = [_svg_open(
        chart, "routine-chart", "Approved routine: targets, not room response",
        "Candidate and dashed baseline use exact precomputed phase boundaries and the endpoint. "
        "The approved band and all lines break at null values. Shading shows scheduled phases, "
        "not sleep stages. The dotted synthetic indoor line is not a building response. "
        "Original samples and exact chart points are available in the tables below.",
    )]
    for span in routine["phase_spans"]:
        x1, x2 = chart.x(span["start"]), chart.x(span["end"])
        phase_class = _PHASE_CLASSES.get(span["phase"], "")
        description = f'{_phase(span["phase"])} · {span["context"]}: {_utc(span["start"])} to {_utc(span["end"])}'
        parts.append(f'<rect class="phase-span {phase_class}" data-role="phase-span" '
                     f'x="{_coordinate(x1)}" y="{_TOP}" width="{_coordinate(max(0, x2 - x1))}" '
                     f'height="{_BOTTOM - _TOP}"><title>{_e(description)}</title></rect>')
        label = _phase(span["phase"])
        if x2 - x1 >= max(65, len(label) * 6):
            parts.append(f'<text class="phase-name" x="{_coordinate((x1 + x2) / 2)}" '
                         f'y="26" text-anchor="middle">{_e(label)}</text>')
    parts.append(chart.axes())
    for run in _runs(rows, ("allowed_minimum_c", "allowed_maximum_c")):
        points = [(chart.x(row["timestamp"]), chart.y(row["allowed_minimum_c"])) for row in run]
        points.extend((chart.x(row["timestamp"]), chart.y(row["allowed_maximum_c"]))
                      for row in reversed(run))
        path = "M" + " L".join(f"{_coordinate(x)},{_coordinate(y)}" for x, y in points) + " Z"
        extra = " band-single" if len(run) == 1 else ""
        parts.append(f'<path class="approved-band{extra}" data-series="approved-band" d="{path}"/>')
    for field, series in (("indoor_c", "indoor"), ("baseline_c", "baseline"), ("candidate_c", "candidate")):
        parts.append(_line(chart, rows, field, series))
    if routine["records"]:
        x = _coordinate(chart.x(routine["records"][0]["timestamp"]))
        parts.append(f'<line id="routine-cursor" class="cursor" x1="{x}" x2="{x}" '
                     f'y1="{_TOP}" y2="{_BOTTOM}" aria-hidden="true"/>')
    parts.append('</svg>')
    return "".join(parts)


def _weather_svg(scenario: dict, index: int) -> str:
    summary = scenario["summary"]
    mean = summary["mean_c"] if summary["status"] == "usable" else None
    values = [row["value_c"] for row in scenario["segments"]]
    values.extend(row["value_c"] for row in scenario["observations"])
    values.append(mean)
    chart = _Chart(scenario["start"], scenario["end"], values)
    parts = [_svg_open(
        chart, f"weather-chart-{index}", f'{scenario["title"]}: independent outdoor history',
        "Each horizontal blue segment is a supplied, bounded forward-held covered interval. "
        "Uncovered intervals stay blank; they are not interpolated or treated as zero. "
        "Dots mark available observations. The lower strip marks actual covered time. "
        "A dashed mean is shown only for a usable Python summary. Tables follow the chart.",
    ), chart.axes(),
        f'<rect class="coverage-track" x="{_LEFT}" y="284" width="{_RIGHT - _LEFT}" height="5"/>']
    for segment in scenario["segments"]:
        x1, x2 = chart.x(segment["start"]), chart.x(segment["end"])
        y = _coordinate(chart.y(segment["value_c"]))
        title = f'{_utc(segment["start"])} to {_utc(segment["end"])}'
        parts.append(f'<line class="weather-segment" data-series="weather-segment" '
                     f'x1="{_coordinate(x1)}" x2="{_coordinate(x2)}" y1="{y}" y2="{y}">'
                     f'<title>{_e(title)}</title></line>')
        parts.append(f'<rect class="covered-interval" x="{_coordinate(x1)}" y="284" '
                     f'width="{_coordinate(max(0, x2 - x1))}" height="5"/>')
    for observation in scenario["observations"]:
        timestamp, value = observation["timestamp"], observation["value_c"]
        if value is not None and chart.start <= _instant(timestamp) <= chart.end:
            parts.append(f'<circle class="weather-observation" data-series="weather-observation" '
                         f'cx="{_coordinate(chart.x(timestamp))}" cy="{_coordinate(chart.y(value))}" r="2.4">'
                         f'<title>{_e(_utc(timestamp))}</title></circle>')
    if mean is not None:
        y = _coordinate(chart.y(mean))
        parts.append(f'<line class="weather-mean" data-series="weather-mean" data-mean-c="{_e(mean)}" '
                     f'x1="{_LEFT}" x2="{_RIGHT}" y1="{y}" y2="{y}">'
                     '<title>Authoritative Python covered-time mean</title></line>')
    parts.append('</svg>')
    return "".join(parts)


def _table(element_id: str, caption: str, headers: tuple[str, ...], rows: Iterable[list[str]]) -> str:
    # Cells are already escaped text or trusted markup from helpers, never raw input.
    parts = [f'<div class="table-scroll" role="region" tabindex="0" aria-labelledby="{element_id}-caption">',
             f'<table id="{element_id}"><caption id="{element_id}-caption">{_e(caption)}</caption>',
             '<thead><tr>', *(f'<th scope="col">{_e(header)}</th>' for header in headers),
             '</tr></thead><tbody>']
    count = 0
    for cells in rows:
        parts.append('<tr>' + ''.join(f'<td>{cell}</td>' for cell in cells) + '</tr>')
        count += 1
    if not count:
        parts.append(f'<tr><td colspan="{len(headers)}">No records supplied.</td></tr>')
    parts.append('</tbody></table></div>')
    return "".join(parts)


def _routine_tables(routine: dict) -> str:
    records = _table(
        "routine-records", "Original routine samples. Celsius values are display-convertible; no commands are allowed.",
        ("Timestamp (UTC)", "Wake date", "Phase", "Context", "Synthetic indoor", "Baseline", "Candidate",
         "Rounded display only", "Approved minimum", "Approved maximum", "Decision", "Reason codes",
         "Explanation", "Trace ID", "Mode", "Commands allowed"),
        ([_e(row["timestamp"]), _e(row["wake_date"] if row["wake_date"] is not None else "Unavailable"),
          _e(row["phase"]), _e(row["context"]), *(_temp(row[field]) for field in _TEMPERATURE_FIELDS),
          _e(row["status"]), _reasons(row["reason_codes"]), _e(row["explanation"]),
          _e(row["trace_id"]), _e(row["mode"]), _e(str(row["commands_allowed"]).lower())]
         for row in routine["records"]),
    )
    plot = _table(
        "routine-plot-records", "Exact chart points, including phase boundaries and the horizon endpoint. Not extra playback samples.",
        ("Timestamp (UTC)", "Phase", "Context", "Synthetic indoor", "Baseline", "Candidate",
         "Rounded display only", "Approved minimum", "Approved maximum"),
        ([_e(row["timestamp"]), _e(row["phase"]), _e(row["context"]),
          *(_temp(row[field]) for field in _TEMPERATURE_FIELDS)] for row in routine["plot_records"]),
    )
    phases = _table(
        "routine-phase-spans", "Scheduled phases, not sleep stages. Intervals use an exclusive end.",
        ("Start (UTC)", "End (UTC, exclusive)", "Phase", "Context"),
        ([_e(span[key]) for key in ("start", "end", "phase", "context")] for span in routine["phase_spans"]),
    )
    return (f'<details><summary>Original samples · {len(routine["records"])} records</summary>{records}</details>'
            f'<details><summary>Exact chart points + endpoint · {len(routine["plot_records"])} points</summary>{plot}</details>'
            f'<details><summary>Scheduled phase intervals</summary>{phases}</details>')


def _inspector(routine: dict) -> str:
    rows = routine["records"]
    row = rows[0] if rows else {}
    time = (f'<time id="sample-time" datetime="{_e(row["timestamp"])}">{_e(_utc(row["timestamp"]))}</time>'
            if rows else '<time id="sample-time">No routine samples</time>')
    position = f"Sample 1 of {len(rows)}" if rows else "No routine samples"
    return f'''<section class="inspector" id="sample-inspector" aria-labelledby="sample-heading">
      <h3 id="sample-heading" class="eyebrow">Selected precomputed sample</h3>
      <div class="inspector-heading">{time}<span id="sample-position">{position}</span></div>
      <p><strong id="sample-phase">{_e(_phase(row.get("phase")))}</strong>
        · Context: <span id="sample-context">{_e(row.get("context", "Unavailable"))}</span></p>
      <dl class="metrics">
        <div><dt>Candidate target</dt><dd>{_temp(row.get("candidate_c"), "sample-candidate")}</dd></div>
        <div><dt>Baseline target</dt><dd>{_temp(row.get("baseline_c"), "sample-baseline")}</dd></div>
        <div><dt>Synthetic indoor · constant fixture</dt><dd>{_temp(row.get("indoor_c"), "sample-indoor")}</dd></div>
        <div><dt>Rounded display · not a command</dt><dd>{_temp(row.get("device_target_c"), "sample-rounded")}</dd></div>
        <div><dt>Approved band</dt><dd class="small-value">{_temp(row.get("allowed_minimum_c"), "sample-minimum")}
          – {_temp(row.get("allowed_maximum_c"), "sample-maximum")}</dd></div>
      </dl>
      <p id="sample-explanation" class="explanation">{_e(row.get("explanation", "No routine samples supplied; no target is inferred."))}</p>
      <p class="reason-line">Reasons: <span id="sample-reasons">{_reasons(row.get("reason_codes", []))}</span></p>
      <dl class="metadata">
        <div><dt>Decision</dt><dd id="sample-decision">{_e(row.get("status", "Unavailable"))}</dd></div>
        <div><dt>Wake date (UTC routine)</dt><dd id="sample-wake-date">{_e(row.get("wake_date") or "Unavailable")}</dd></div>
        <div><dt>Trace ID</dt><dd><code id="sample-trace-id">{_e(row.get("trace_id", "Unavailable"))}</code></dd></div>
      </dl>
      <p class="reason-line">Observe-only · Commands allowed: false · No equipment connected</p>
    </section>'''


def _routine_section(routine: dict) -> str:
    count = len(routine["records"])
    disabled = " disabled" if count < 2 else ""
    return f'''<section class="panel" id="routine" aria-labelledby="routine-heading">
      <div class="section-heading"><div>
        <h2 id="routine-heading"><span class="section-number">01</span> A scheduled day, not a prediction</h2>
        <p>A pre-approved synthetic routine. Targets are proposals, not achieved indoor temperatures.</p>
      </div></div>
      <p class="chart-note">{_e(_utc(routine["start"]))} → {_e(_utc(routine["end"]))}.
        Original horizon end is exclusive; the chart includes its exact endpoint for context.
        Sample step: {_e(routine["step_minutes"])} minutes.</p>
      <div class="chart-scroll" role="region" tabindex="0" aria-label="Routine chart; scroll horizontally on small screens">
        {_routine_svg(routine)}
      </div>
      <div class="legend" aria-label="Routine chart legend">
        <span><i class="swatch" aria-hidden="true"></i>Candidate</span>
        <span><i class="swatch baseline-key" aria-hidden="true"></i>Baseline · dashed</span>
        <span><i class="swatch indoor-key" aria-hidden="true"></i>Constant synthetic indoor · dotted</span>
        <span><i class="swatch band-key" aria-hidden="true"></i>Approved band</span>
        <span><i class="swatch phase-key" aria-hidden="true"></i>Scheduled phases</span>
      </div>
      <p class="chart-note">Candidate and baseline may overlap. Null values break lines and bands, never become zero.
        Rounded display values appear in the sample readout and tables, not as a control trajectory.</p>
      <div class="playback" data-enhanced="" hidden>
        <button id="routine-play" type="button" aria-pressed="false" aria-controls="routine-scrubber sample-inspector"{disabled}>Play</button>
        <div class="scrubber-field"><label for="routine-scrubber">Select an original sample</label>
          <input id="routine-scrubber" type="range" min="0" max="{max(0, count - 1)}" step="1" value="0"
            aria-controls="sample-inspector" aria-describedby="playback-help"{disabled}></div>
        <p class="help" id="playback-help">Arrow keys step through samples; Home/End jump to the first/last.
          Play selects one precomputed sample per second and stops at the end. No autoplay or live evaluation.</p>
      </div>
      <p class="sr-only" id="sample-announcement" role="status" aria-live="polite" aria-atomic="true"></p>
      {_inspector(routine)}
      {_routine_tables(routine)}
    </section>'''


def _weather_case(scenario: dict, index: int) -> str:
    summary = scenario["summary"]
    requirements = scenario["requirements"]
    mean = summary["mean_c"] if summary["status"] == "usable" else None
    badge_class = "badge" if summary["status"] == "usable" else "badge warning"
    observations = _table(
        f"weather-observations-{index}", "Supplied synthetic observations. Unavailable events are not zero-degree measurements.",
        ("Timestamp (UTC)", "Outdoor temperature"),
        ([_e(row["timestamp"]), _temp(row["value_c"])] for row in scenario["observations"]),
    )
    segments = _table(
        f"weather-segments-{index}", "Actual covered intervals supplied by Python, clipped to the window. No bridging or backfilling.",
        ("Start (UTC)", "End (UTC, exclusive)", "Forward-held temperature"),
        ([_e(row["start"]), _e(row["end"]), _temp(row["value_c"])] for row in scenario["segments"]),
    )
    return f'''<article class="weather-case" id="weather-case-{index}" data-weather-case="{index}"
        data-scenario-id="{_e(scenario["id"])}" aria-labelledby="weather-heading-{index}">
      <div class="scenario-title"><h3 id="weather-heading-{index}">{_e(scenario["title"])}</h3>
        <span class="{badge_class}">{_e(summary["status"])}</span></div>
      <p>{_e(scenario["description"])}</p>
      <p class="chart-note">Window: {_e(_utc(scenario["start"]))} → {_e(_utc(scenario["end"]))}
        · Evaluated at report end, not the selected routine sample.</p>
      <div class="chart-scroll" role="region" tabindex="0" aria-label="Outdoor history chart; scroll horizontally on small screens">
        {_weather_svg(scenario, index)}
      </div>
      <div class="legend" aria-label="Weather chart legend">
        <span><i class="swatch weather-key" aria-hidden="true"></i>Bounded forward-held intervals · dots are observations</span>
        <span><i class="swatch mean-key" aria-hidden="true"></i>Usable mean only · dashed</span>
        <span>Lower strip: covered time; blank intervals remain gaps</span>
      </div>
      <dl class="metrics">
        <div><dt>Python covered-time mean</dt><dd>{_temp(mean)}</dd></div>
        <div><dt>Coverage</dt><dd>{_amount(summary["coverage_fraction"], percent=True)}</dd></div>
        <div><dt>Covered hours</dt><dd>{_amount(summary["covered_hours"])}</dd></div>
      </dl>
      <p class="explanation">{_e(summary["explanation"])}</p>
      <p class="reason-line">Reason codes: {_reasons(summary["reason_codes"])}</p>
      <dl class="metadata">
        <div><dt>Latest valid observation (UTC)</dt><dd>{_e(_utc(summary["latest_observed_at"]))}</dd></div>
        <div><dt>Freshness evaluated at</dt><dd>{_e(_utc(scenario["end"]))}</dd></div>
      </dl>
      <p class="requirements">Illustrative input requirements: {_amount(requirements["window_hours"])}-hour window;
        at least {_amount(requirements["minimum_coverage"], percent=True)} coverage;
        each sample held for at most {_amount(requirements["max_sample_hold_hours"])} hours;
        latest observation at most {_amount(requirements["max_observation_age_hours"])} hours old.
        These are fixture parameters, not production safety defaults. The Python status and reasons are authoritative.</p>
      <details><summary>Outdoor observations · {len(scenario["observations"])} events</summary>{observations}</details>
      <details><summary>Covered intervals · {len(scenario["segments"])} segments</summary>{segments}</details>
    </article>'''


def _weather_section(scenarios: list[dict]) -> str:
    options = "".join(f'<option value="{index}">{_e(scenario["title"])}</option>'
                      for index, scenario in enumerate(scenarios))
    cases = "".join(_weather_case(scenario, index) for index, scenario in enumerate(scenarios))
    disabled = " disabled" if len(scenarios) < 2 else ""
    if not cases:
        cases = '<p class="empty">No weather scenarios supplied.</p>'
    return f'''<section class="panel" id="weather" aria-labelledby="weather-heading">
      <div class="section-heading"><div>
        <h2 id="weather-heading"><span class="section-number">02</span> Seven days of outdoor evidence</h2>
        <p>Separate synthetic input checks: complete history, gaps, and stale observations.</p>
      </div>
      <div class="toolbar" data-enhanced="" hidden><label for="weather-select">Weather case</label>
        <select id="weather-select" aria-controls="weather-cases"{disabled}>{options}</select></div></div>
      <p class="independence" id="weather-independence"><strong>Independent, not adaptive.</strong>
        Weather is evaluated at report end independently of routine playback and is <strong>not linked to indoor targets</strong>.
        Changing the case changes only the displayed precomputed history. No weather mean or policy is recomputed in the browser.</p>
      <div id="weather-cases">{cases}</div>
    </section>'''


def render_report(data: dict) -> str:
    """Return a complete deterministic UTF-8-encodable HTML report for contract v1.

    Supplied dictionaries are not mutated. Timestamps must be aware UTC; numeric
    values must be finite or null. Malformed inputs fail rather than inventing a
    replacement target/mean. Unknown versions raise ValueError. No report builder
    import is needed, so the parent can call this renderer without a cycle.
    """
    if data.get("version") != 1:
        raise ValueError("Unsupported report data version; expected version 1.")
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    for character, replacement in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                                   ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        payload = payload.replace(character, replacement)
    style = (_ASSETS / "report.css").read_text(encoding="utf-8")
    script = (_ASSETS / "report.js").read_text(encoding="utf-8")
    script_hash = b64encode(sha256(script.encode("utf-8")).digest()).decode("ascii")
    policy = ("default-src 'none'; connect-src 'none'; "
              f"script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; "
              "img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{_e(policy)}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Adaptive Comfort · Local routine report</title>
<style>{style}</style>
</head>
<body>
<a class="skip-link" href="#routine">Skip to routine report</a>
<main>
  <div class="topbar"><span class="brand"><span class="brand-mark" aria-hidden="true"></span>Adaptive Comfort</span>
    <nav aria-label="Report sections"><a href="#routine">Routine</a><a href="#weather">Weather inputs</a><a href="#limitations">Limitations</a></nav>
  </div>
  <header class="hero" id="report-intro">
    <p class="eyebrow">Local report / Offline prototype</p>
    <h1>A routine you can inspect.<br>Not a room we can predict.</h1>
    <p class="lead">Explore a fixed approved temperature routine and separate outdoor-history checks.
      Everything here is precomputed synthetic data, kept in this one local file.</p>
    <div class="badges"><span class="badge">Synthetic fixtures</span><span class="badge neutral">Observe-only</span>
      <span class="badge neutral">UTC throughout</span><span class="badge warning">No equipment connected</span></div>
    <p class="boundary-note"><strong>The constant synthetic indoor line is NOT a building response.</strong>
      This is a routine preview, not a room-response simulation or a Home Assistant integration.
      It cannot send thermostat commands. Fixture temperatures are arithmetic examples, not recommendations for a home.</p>
  </header>
  <div class="toolbar" data-enhanced="" hidden><label for="display-unit">Display temperatures</label>
    <select id="display-unit" aria-describedby="unit-help"><option value="C">Celsius (°C)</option><option value="F">Fahrenheit (°F)</option></select>
    <span class="muted" id="unit-help">Display only. Targets, bounds, decisions, and source data stay unchanged.</span>
  </div>
  <noscript><p class="boundary-note">JavaScript is disabled. All charts and data tables remain available in Celsius,
    and all weather cases are shown below. Playback and display-unit controls are unavailable.</p></noscript>
  {_routine_section(data["routine"])}
  {_weather_section(data["weather"])}
  <section class="panel limitations" id="limitations" aria-labelledby="limitations-heading">
    <h2 id="limitations-heading">What this report does not establish</h2>
    <ul>
      <li>Scheduled phases are time windows, <strong>not sleep stages</strong>. A higher target does not show that a room warmed or switch equipment to heating.</li>
      <li><strong>No learned comfort</strong>, weather-shaped targets, daylight adaptation, or building/occupant response is implemented here.</li>
      <li><strong>No energy or health claims</strong> are supported by these fixtures. No comfort or physical equipment-safety result has been validated.</li>
      <li>Rounded display targets are not command-ready. This file has no control path, accounts, telemetry, storage, or network requests.</li>
      <li>Missing values stay unavailable. Weather means, coverage, and reasons are the supplied Python results; failing input checks never creates a fallback temperature.</li>
      <li>UTC-only scheduling is intentional. Local timezone and daylight-saving behavior are not demonstrated. Display values are rounded; chart geometry uses the supplied Celsius values.</li>
    </ul>
  </section>
  <footer>Self-contained local artifact · Native system fonts · Contract version 1 · No live clock or external resources</footer>
</main>
<script id="report-data" type="application/json">{payload}</script>
<script id="report-script">{script}</script>
</body>
</html>
'''
