# Adaptive Comfort

**Experimental, offline comfort-planning previews—not a thermostat controller.**

Adaptive Comfort explores understandable daily temperature routines, with longer-term goals of bounded weather influence and learning from simple comfort feedback. The implemented scope is deliberately smaller: a deterministic, observe-only routine, independent weather-history validation, a display-only HTML report, and a disconnected Climate Advisor contribution candidate.

There is **no Home Assistant integration, building/occupant simulation, weather-driven target adjustment, learned comfort model or live control**. No comfort improvement, sleep benefit, energy saving or hardware-safety result has been demonstrated. Example temperatures are synthetic arithmetic fixtures, not recommended household settings.

Development is **owner-directed and AI-assisted**. Coding agents helped with design, implementation, tests, documentation and review; passing software checks is not independent evidence of physical safety.

## What exists

| Component | What it does | Boundary |
| --- | --- | --- |
| Routine preview | Evaluates an approved synthetic UTC routine with explicit bounds, rates and explanations | Observe-only; fake device rejects commands; no room response |
| Outdoor-history summary | Calculates a time-weighted mean gated by coverage and freshness | Input validation only; weather never changes routine targets |
| Browser demo | Displays precomputed routine and independent weather results in one self-contained HTML file | Playback and unit controls change display only |
| Climate Advisor candidate | Packages disconnected heat/cool band, fixed-wake local-time and synthetic mode-lifecycle modules, tests and guides | Not integrated, submitted or accepted upstream |

The original prototype and the Climate Advisor candidate are **separate implementations**. The browser does not run or display the upstream modules. The synthetic mode model does not implement live ownership detection, a live mode switch or physical hand-back; its fake readiness flags and revisions are not verified Home Assistant safety or ownership APIs. Climate Advisor is an independent project, not a sponsor or endorser.

## Quick start

Run from the source root with **Python 3.11+**. The original prototype, root tests and bundle tool use the standard library. Only **Python 3.14.5 on Windows** has recorded execution; compatibility with other versions and platforms is not established by those results.

```sh
python -m unittest discover -s tests -v
python tools/climate_advisor_bundle.py verify
python -m adaptive_comfort
```

- The recorded root checkpoint passed **109 tests: 78 original baseline/weather/report tests plus 31 bundle-tool tests**. This command does not run the separate upstream suites.
- Bundle `verify` needs **no Git, upstream checkout or third-party dependencies**. It reads and validates the bundle without applying or executing the patch. Hashes check integrity, not authenticity or behavioral correctness.
- The default CLI emits **96 JSON records**: 48 synthetic hours at 30-minute intervals, with the end instant excluded. Every record has `commands_allowed=false`. Use `--hours 2` for a shorter preview. There is no control switch or hardware adapter.

No Home Assistant installation, network service, account or AI model is needed for the offline preview.

### View the HTML report

```sh
python -m adaptive_comfort --html local/demo.html
```

Open the generated file yourself; no server is needed. The command creates the output parent directory if necessary and refuses to overwrite an existing file. Add `--force` only for deliberate replacement.

The report shows a **constant synthetic indoor reading of 22°C**, not a prediction of room temperature. Playback, Celsius/Fahrenheit selection and weather-case selection only display precomputed data. The complete, missing and stale weather examples are independent of the routine and do not change its targets. See the [browser guide](docs/WEB_DEMO.md) for controls and limitations.

## Evidence and limits

The [portfolio case study](docs/PORTFOLIO.md) preserves concrete routine and weather examples, engineering tradeoffs and the recorded validation scope. The [test guide](docs/TEST_PLAN.md) separates implemented software assertions from pending integration and safety scenarios.

An earlier reconstruction of the contribution passed **444 focused upstream cases**, reusing an existing dependency environment in an initially clean detached worktree with module import origins verified. It was not a fresh clone or dependency environment. The full upstream Windows suite remains blocked during collection by existing Unix-only `resource` imports; no successful full-suite, Linux or Home Assistant validation is claimed. Exact evidence is in the [bundle validation record](contributions/climate-advisor/VALIDATION.md).

Earlier Chrome smoke checks cover the original browser demo only. No new browser validation, cross-browser coverage or assistive-technology audit is claimed here. All results above describe recorded development checkpoints, not real equipment or a newly validated distribution.

## Guides

- [Portfolio case study](docs/PORTFOLIO.md): a short technical walkthrough and numeric examples.
- [Offline routine](docs/OFFLINE_ROUTINE.md): input assumptions, CLI behavior and withheld results.
- [Weather history](docs/WEATHER_HISTORY.md): time weighting, gaps, duplicates and freshness.
- [Browser demo](docs/WEB_DEMO.md): display controls, export behavior and report distribution.
- [Tests and limitations](docs/TEST_PLAN.md): executed checks and remaining scenarios.
- [Contribution bundle](contributions/climate-advisor/README.md): pinned eight-file patch, verification and reproduction.
- [Working with the source](CONTRIBUTING.md): small synthetic changes, privacy and licensing.

There is no established public contribution intake or deployment-support commitment. This is an experiment to inspect, not an installation guide for live HVAC.

## Licensing and distribution

The original code, assets, tests, tools and documentation use [Apache License 2.0](LICENSE). The explicit exception is `contributions/climate-advisor/`: its upstream-specific source snapshot and bundle documentation use [MIT](contributions/climate-advisor/LICENSE), Copyright (c) 2026 Amun, with the unchanged [upstream MIT notice](contributions/climate-advisor/UPSTREAM_LICENSE), Copyright (c) 2026 gunkl, retained. This is scoped licensing, not a choice of either license for every file.

Include the root Apache `LICENSE` alongside a separately distributed generated HTML report. Keep the complete contribution bundle and both MIT notices together. Extracted MIT source must carry the Amun copyright and MIT permission text as well as retain the upstream notice; applying the patch does not install those notice files in the upstream tree. See [distribution guidance](CONTRIBUTING.md#licensing-and-redistribution).
