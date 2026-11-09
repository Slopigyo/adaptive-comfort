# Local browser demo

The browser demo is a self-contained HTML report of the synthetic routine and independent weather-history examples. It is **not a building/occupant simulation, a Home Assistant interface, or a controller**. No HTTP server, internet connection, new package, account, or real equipment is needed to generate and view it.

## Assumptions and boundaries

- Python calculates every routine evaluation and weather summary. The browser only displays precomputed results; playback, unit selection, and weather-case selection cannot change policy or send commands.
- The routine uses the [explicit synthetic fixture](OFFLINE_ROUTINE.md), an injected UTC clock, and a constant indoor reading refreshed at each tick. That line is not a prediction of room response. Scheduled sleeping/waking contexts do not identify sleep stages.
- Weather is a separate seven-day history ending at the report's end, **not at the selected playback sample**. Its summary does not influence indoor targets. Missing, insufficient, or stale history never produces a fallback mean or temperature.
- Original playback samples exclude the run's end instant, just like the command-line JSON trace. Extra evaluations at exact phase boundaries and the endpoint are used only to draw the curve accurately, including when sampling misses an anchor.
- Weather charts show bounded forward-held intervals and explicit gaps, not lines interpolated across missing observations. Their covered duration is checked against the authoritative Python summary.
- Every temperature, outdoor pattern, and input threshold is a synthetic arithmetic fixture, not a recommended household setting or validated safety threshold. Rounded display targets are not command-ready.

## Generate and open

From the repository root, with Python 3.11+ and only the standard library:

```sh
python -m adaptive_comfort --html local/demo.html --open
```

The `local/` output directory is ignored by Git and is created when needed. `--open` asks the default browser to open only the newly generated local HTML file; it does not start an HTTP server. Without `--open`, open the file yourself. The report can be copied and viewed without its source tree or an internet connection; see the licensing requirements below before distributing it.

Existing files are protected. To deliberately replace the same report, add `--force`:

```sh
python -m adaptive_comfort --html local/demo.html --open --force
```

The output filename must end in `.html` or `.htm`. Both `--open` and `--force` require `--html`. Browser opening is opt-in: ordinary JSON output and the root tests do not launch a browser. If launch is unavailable, the generated file can still be opened manually.

Duration and sampling options also apply:

```sh
python -m adaptive_comfort --hours 24 --step-minutes 15 --html local/day.html
```

Defaults are 48 hours and 30-minute samples; accepted integer ranges are 1–168 hours and 1–60 minutes. The fixed start is `2026-01-01T23:00:00+00:00`. The default run has 96 original playback records. Omitting `--html` retains the JSON output described in the [routine guide](OFFLINE_ROUTINE.md).

Python 3.11+ is the root's compatibility target. Recorded execution was on **Python 3.14.5 / Windows**; other Python versions and platforms have not been validated by the recorded runs.

## What you can inspect

- **Routine chart:** continuous baseline/candidate, approved band, scheduled phases, and the distinctly labeled constant indoor fixture. In this fixture, baseline and candidate overlap; weather adaptation is not implemented.
- **Sample inspector:** play/pause or scrub through the original evaluations, with timestamp, phase, context, targets, decision, and explanation. Playback selects one recorded sample per second, does not autoplay, and stops at the end.
- **Display units:** Celsius/Fahrenheit selection changes numeric readouts and axes only. Original Python explanations retain their explicit Celsius labels. Source values, target geometry, and decisions do not change.
- **Independent weather cases:** complete history, a missing 24-hour block of observations, and a tail whose latest observation is six hours old. The requirements are a seven-day elapsed window, at least 90% coverage, a three-hour maximum hold per observation, and a three-hour maximum current observation age. The [weather guide](WEATHER_HISTORY.md) defines exact boundary, gap, and duplicate behavior. Coverage, freshness, reasons, and a mean only when usable remain separate from the routine.
- **Accessible data:** native keyboard controls and expandable tables accompany the SVG charts. On narrow screens, charts and tables scroll horizontally within their panels. With JavaScript disabled, all charts, tables, and weather cases remain visible in Celsius; enhanced controls stay hidden. These features are not a claim of a completed accessibility audit.

## Offline and output safety

Styles, scripts, data, and SVG charts are embedded in the single file. The report has no external fonts, CDN libraries, analytics, fetches, or browser storage. A restrictive content-security policy permits only the bundled script and denies network connections. Supplied text and embedded JSON are escaped rather than executed. The [report builder](../adaptive_comfort/report.py) and [renderer](../adaptive_comfort/report_view.py) keep policy evaluation in Python and presentation in the generated document.

This is a statement about the report, **not a guarantee that the browser itself is offline**: extensions, updates, and other browser background activity are outside its control. Viewing the report requires only a local file load, not HTTP.

Report creation is explicit and refuses overwrites without `--force`. It uses synthetic inputs, not real household files or configuration. A graph or passing report test establishes no comfort, sleep, health, energy, or physical HVAC-safety result.

## Sharing a generated report

The embedded project code and assets are licensed under [Apache License 2.0](../LICENSE). If distributing the HTML separately from the repository, include that license alongside it and identify it as applying to the embedded code and assets. **The HTML does not embed the license text.** Its ability to run as one file does not make it a complete standalone licensing package. Local viewing does not require a server or additional package.

## Validation scope

The historical root results include 34 report data/export/CLI/presentation tests. Browser launch is mocked in those tests; they do not execute a browser. The original baseline JSON trace was preserved. See the [test guide](TEST_PLAN.md) for the full root total and the separate historical Chrome smoke check, including desktop/narrow dimensions and JavaScript-disabled fallback.

Those results do not cover the disconnected upstream preview modules, Firefox, a screen reader, or a fresh environment. They are earlier evidence, not a newly executed browser or export validation.
