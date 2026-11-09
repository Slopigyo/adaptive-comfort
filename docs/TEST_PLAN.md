# Test evidence and remaining limits

**Implemented:** the UTC-only, observe-only routine (B01–B08), standalone outdoor-history input checks, a display-only HTML report, and contribution-bundle integrity checks. **Not implemented in the root prototype:** weather-shaped targets, local-time scheduling, daylight adaptation, learned preferences, building/occupant response, or physical control.

The [routine guide](OFFLINE_ROUTINE.md), [weather guide](WEATHER_HISTORY.md), and [browser guide](WEB_DEMO.md) document usage, synthetic fixtures, validation boundaries, and failure behavior. Their numbers are arithmetic test inputs, not household or equipment-safety defaults.

## Root tests and recorded environment

The root targets **Python 3.11+ using only the standard library**. Run the full suite from the repository root:

```sh
python -m unittest discover -s tests -v
```

Recorded execution was on **Python 3.14.5 / Windows**. At the recorded contribution-bundle checkpoint, **109 test methods passed**: the unchanged original 78 (20 routine, 24 weather, and 34 report tests) plus 31 bundle tests. These are historical results, not evidence that a newly exported copy or a fresh environment has been tested. No multi-version or cross-platform matrix is claimed.

| Scope | Test methods | Evidence |
| --- | --- | --- |
| Routine and synthetic runner | 20 | [test_core.py](../tests/test_core.py) covers B01 and B04–B08 plus validation/quantization; [test_simulation.py](../tests/test_simulation.py) covers B02–B03, fake command rejection, and CLI limits |
| Outdoor-history input | 24 | [test_weather.py](../tests/test_weather.py): time weighting, bounded holds, coverage/freshness, duplicate/conflicting/out-of-order events, sources/units/timestamps, and UTC elapsed-time arithmetic |
| Report data, export, and CLI | 16 | [test_report.py](../tests/test_report.py): unchanged original records, exact chart boundaries, weather coverage, no commands, explicit output/overwrite, and mocked browser opening |
| HTML presentation | 18 | [test_report_view.py](../tests/test_report_view.py): escaping/CSP, offline assets, accessible references, null/gap handling, finite geometry, tables, and static fallback |
| Contribution bundle | 31 | [test_contribution_bundle.py](../tests/test_contribution_bundle.py): shipped artifact, strict paths/text/status/hashes, overwrite/partial-write safeguards, and source-free/no-execution verification |
| **Total** | **109** | **78 original + 31 bundle** |

The root suite uses synthetic inputs and fake devices, not a Home Assistant installation, home network, credentials, or real HVAC hardware. It does not launch a browser, run upstream `pytest`, or execute the Python code carried in the contribution patch. Bundle integrity is not behavioral validation of that code.

The default JSON demo retained its original 96 records and recorded raw Windows digest. Exact historical commands and hashes are in the [bundle validation record](../contributions/climate-advisor/VALIDATION.md). Source-free verification instructions are in the [bundle guide](../contributions/climate-advisor/README.md); that standard-library verifier needs no source checkout or Git and does not apply or execute the patch. The [weather guide](WEATHER_HISTORY.md) also provides a focused test command when only input averaging is under review.

## B01–B08: implemented baseline acceptance

| ID | Checked behavior |
| --- | --- |
| B01 | Correct anchors, interpolation, wake date, and exactly one scheduled phase per instant |
| B02 | Identical ordered two-day traces, run-local IDs, and explanations for identical inputs; no dependence on the host clock |
| B03 | Zero fake actuator command attempts during observe-only execution, including mode/fan/schedule changes; every trace explicitly forbids commands |
| B04 | Disabled, missing, or unapproved routines do not invent a target |
| B05 | Invalid ordering, bounds, units, and other routine configuration withhold a target with an explanation, without silent repair |
| B06 | Observation age, not receipt age, controls freshness: exactly five minutes is accepted in this fixture; greater age, future/invalid times, non-finite values, and unavailable input withhold recommendations |
| B07 | Equivalent Celsius/Fahrenheit inputs yield equivalent physical targets; absolute temperatures and differences convert separately; missing/changed units are not satisfied from a cached old value |
| B08 | A rising cooling-mode morning target is described as a requested trajectory, not achieved warming or a switch to heating |

Additional checks cover allowed-bound intersections, incompatible resolution, lower-target half-step ties, 1°F endpoint/tie preservation, and every-minute bounds over two days. These validate preview arithmetic, not dispatch. The configured baseline slope and device-rounded display target do not implement ownership, hysteresis, command spacing, minimum-cycle protection, or physical rollback.

## W06: input prerequisite, not complete weather acceptance

The historical W06 requirement combines two distinct ideas: reordered/duplicated/gappy readings must produce observation-time, duration-weighted history; insufficient history must block new weather adaptation.

Only the **input portion** is implemented. The 24 weather tests establish validation, time weighting, coverage/freshness gates, and no usable mean when those gates fail. They do not establish adaptation-blocking behavior in a planner, because no weather adjustment exists. Bounded target displacement, gradual removal of an applied offset after weather loss, phase-direction preservation, and combined weather/routine limits remain unimplemented. Passing W06 input tests is not completion of a weather-adaptive acceptance suite.

## Historical upstream reconstruction evidence

The [complete contribution bundle](../contributions/climate-advisor/README.md) contains eight new upstream-specific files pinned to Climate Advisor base `68c6c2d7ea63a921afed7a391253e448fb6a5ceb`. Its band preview, fixed-wake local-time resolver, and synthetic mode-lifecycle modules are disconnected additions, not production integrations or a live mode switch.

An initially clean reconstructed pinned tree passed **444 focused upstream cases** with warnings-as-errors:

- 77 band-preview cases.
- 70 local-time resolution cases.
- 101 synthetic mode-lifecycle cases.
- 196 existing upstream regressions.

Module import origins were checked inside the reconstructed tree. This reused **uv 0.13.7 and the existing locked unit-test dependency environment on Python 3.14.5 / Windows**. It was **not a fresh clone or a fresh dependency environment**. See the [validation record](../contributions/climate-advisor/VALIDATION.md) for exact reproduction details; these counts are not additional root `unittest` tests or a renewed upstream run.

Before implementation, the full upstream Windows unit suite stopped during collection because existing code imports Unix-only `resource`. That full suite remains unvalidated; no workaround is claimed. Linux, the real-HA tier, fresh-environment reproduction, and hardware validation were not run.

The local-time cases resolve explicit dated routines, including gap/fold behavior; they do not establish a recurring executor, duplicate-action prevention, or lifecycle invalidation. Synthetic mode tests exercise holds, current-settings selection, revisions, restarts, and hand-back outcome bookkeeping. Their fake ownership revisions and readiness flags are **not actual Home Assistant ownership or safety APIs**. Live release behavior and the host's existing automation, manual-grace, startup, and persistent-hold policies remain separate integration concerns.

## Historical browser check

The original report was smoke-tested in **Chrome 153.0.8010.12**, loaded as a local HTML file, not over HTTP. **36 interaction assertions passed at each viewport: 1440×1800 and 390×844.** Checks included no autoplay, C/F readouts, scrubbing/cursor/accessibility text, all weather cases, missing means, unchanged source data and target geometry, expandable tables, playback/pause/end/replay, and no page resource requests or script/CSP errors.

Separate loads with and without JavaScript confirmed static charts/tables and all weather cases remained available when scripting was disabled. This was a Chrome smoke check, not a cross-browser or assistive-technology audit. Firefox and screen-reader behavior were not independently verified. No page requests does not guarantee that browser background activity is offline.

These are earlier report checks, not part of the root unit-test command, not a renewed browser run, and not evidence for the upstream preview modules. No pre-generated HTML, screenshots, or private test tooling is needed to run the root suite or generate the report.

## Remaining integration and outcome limits

- **Timing and adaptation:** the root routine is UTC-only. Recurring local-time/DST execution, daylight shaping, weather-driven targets, temporary activity behavior, and preference learning are not validated features.
- **Authority and hand-back:** real manual/external-change detection, explicit resume, dispatch-time revision/freshness checks, restart reconciliation, and return to the prior policy evaluated for current state/time remain unimplemented. Restoring a captured old target is not evidence of safe hand-back.
- **Device behavior:** actual units/resolution, operating modes, command rate/spacing/hysteresis, minimum-cycle protection, acknowledgment failures, persistent holds, stale sensors, and race conditions need device-specific integration tests before any control claim. A synthetic readiness flag cannot establish physical safety.
- **Outcomes:** there is no building/occupant model, household study, hardware trial, learned comfort result, or measured sleep, health, comfort, or energy-savings outcome. Scheduled phases are not sleep stages, and target trajectories are not measured room response.

Future tests must retain deterministic injected clocks, explicit units/timestamps/bounds, full trace explanations, and zero commands in observe-only mode. Fake-device tests can reveal logic errors; they cannot establish Home Assistant compatibility or authorize a real actuator path.
