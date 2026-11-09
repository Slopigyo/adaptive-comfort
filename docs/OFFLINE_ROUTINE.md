# Offline routine preview

This is a deterministic **routine preview**, not a building/occupant simulation, a Home Assistant integration, or a controller. It covers B01–B08 in the [test guide](TEST_PLAN.md). The independent [weather-history summary](WEATHER_HISTORY.md) does not change its targets. Weather adaptation, daylight shaping, preference learning, feedback storage, and physical control are not implemented in this routine.

## Run locally

From the repository root, using Python 3.11+ and only the standard library:

```sh
python -m adaptive_comfort --hours 2
```

No package installation, Home Assistant dependency, or external service is needed. Python 3.11+ is the compatibility target; recorded execution was on **Python 3.14.5 / Windows**, not a multi-version or cross-platform test matrix. See the [test guide](TEST_PLAN.md) for the full-suite command and evidence limits.

Without `--html`, the command emits one JSON object per tick to standard output. With no arguments, it previews 48 hours at 30-minute intervals, starting at the explicitly synthetic instant `2026-01-01T23:00:00+00:00`. The end instant is excluded, giving 96 records. `--hours` accepts integers from 1–168; `--step-minutes` accepts integers from 1–60. No trace files or household data are created automatically.

For an optional self-contained HTML visualization, follow the [browser demo guide](WEB_DEMO.md). It documents explicit file creation, overwrite protection, and opt-in browser opening. HTML generation reuses the same Python evaluations; the browser cannot evaluate policy or send commands.

## Synthetic fixture, not household defaults

The command uses the explicit fixture in [simulation.py](../adaptive_comfort/simulation.py). These values are arithmetic examples, **not recommended temperatures, equipment protections, health limits, or production freshness/rate settings**. A `Routine` defaults to `enabled=False` and `approved=False`; the synthetic fixture explicitly sets both to `True`. That approval describes the fixture, not consent to control equipment.

| Parameter | Synthetic value |
| --- | --- |
| Clock | Injected UTC, advanced without sleeping or reading the machine's current time |
| Routine revision | `synthetic_routine_v1` |
| Approved envelope | 20–24°C |
| Fake device range and step | 18–26°C; 0.5°C steps anchored at 18°C |
| Climate mode | `cool`; no switching to heating |
| Indoor measurement | Constant 22°C, with observation and receipt times refreshed at each tick |
| Maximum continuous baseline slope | 1°C per elapsed hour |
| Maximum indoor observation age | 5 minutes, inclusive |

Five ordered anchors repeat every 24 hours. Minutes are relative to midnight on the wake date; a negative minute refers to the preceding evening.

| Anchor minute | UTC time | Target | Phase beginning at that instant |
| --- | --- | --- | --- |
| −60 | Previous date, 23:00 | 22°C | `wind_down` |
| 120 | 02:00 | 21°C | `sleeping` |
| 300 | 05:00 | 21°C | `waking` |
| 420 | 07:00 | 23°C | `return_to_day` |
| 540 | 09:00 | 22°C | `daytime` |

Interpolation is linear between anchors, with a 21°C overnight hold and a 22°C daytime hold until the next wind-down. Warming starts two elapsed hours before the 07:00 wake anchor; return to daytime ends two elapsed hours after it. Phase intervals are half-open, so an exact boundary belongs to the new phase once. `wind_down`/`sleeping` use the sleeping context; `waking`/`return_to_day` use the waking context. These are scheduled windows, not detected sleep stages.

The indoor line is an independent measurement fixture, not a prediction of thermal response. A higher cooling setpoint permits passive warming; it does not request heating or demonstrate that a room warmed.

## Input and failure contract

[`adaptive_comfort.core.evaluate()`](../adaptive_comfort/core.py) accepts a routine, indoor reading, climate state, an injected timezone-aware UTC evaluation time, and an explicit positive `max_sensor_age`. It has no storage, real-clock lookup, network, or command path. Local timezone/DST scheduling is deliberately unsupported in this core.

- A routine requires exactly five anchors in the phase order shown above. Anchor minutes must be integers strictly between −1440 and 1440, strictly increasing, and span less than 1440 minutes. The wake anchor (`return_to_day`) must lie on its named date, at minute zero or later. A nonblank revision is required.
- Targets must be finite, have an explicit `C` or `F` unit, and lie inside the ordered approved bounds. The baseline slope limit must be positive. Every segment, including the daily wrap, must meet that limit. Wind-down cannot warm; pre-wake warming cannot cool. The overnight endpoints must match, as must the daytime hold endpoints.
- Indoor readings are distinct from targets. They require an identified source, availability, a finite numeric value, an explicit unit, and timezone-aware observation and receipt times. Sensor times are normalized to UTC and must satisfy `observed_at <= received_at <= now`. Missing/naive or future timestamps, or observation after receipt, are invalid. A recent receipt cannot refresh an old observation.
- Age is measured from observation time. Exactly the configured maximum age is accepted; a greater age withholds the recommendation. Five minutes is only this fixture's chosen limit, not a production default.
- Only available, single-target `heat` or `cool` climate states are supported. Missing/unsupported units, non-finite numbers, inverted bounds, nonpositive device steps, and unsupported modes withhold the recommendation. Numeric booleans are not temperatures.
- A disabled routine returns `disabled` with no target. Missing or unapproved routines and validation failures return `withheld` with a reason code and explanation. There is no invented fallback routine, automatic approval, or silent configuration repair.

## Bounds and quantization

The continuous baseline is constrained to the intersection of the approved and device bounds. An empty intersection withholds the recommendation. Device quantization then selects the nearest allowed grid point within that intersection; an exact half-step tie selects the lower numeric target. The grid is anchored at the fake device's minimum target and uses an explicit positive step. If no representable point lies within the intersection, the result is withheld rather than rounded outside the envelope.

Unit conversion, interpolation, and grid arithmetic use exact rational values derived from the inputs' decimal representations, converting to floats only for results/display. This preserves endpoints and half-step ties on 1°F grids. Temperature differences, such as steps and slopes, use scale conversion without Fahrenheit's absolute offset. Continuous Celsius baseline/candidate values remain separate from the device-rounded display target.

The baseline slope check is **not a command-rate limiter**, and rounded display values are **not command-ready**. Actual device grids, dispatch-time freshness and state checks, ownership, post-quantization command limits, hysteresis, spacing, and physical hand-back remain unimplemented integration requirements.

## Trace and observe-only boundary

Each record includes timestamp and wake date, scheduled phase/context, indoor measurement, continuous baseline and constrained candidate, allowed bounds, device-rounded display target, decision/reasons, and an explanation. Trace IDs combine the routine revision with a deterministic run-local index; they are not globally unique proposal or command identifiers. Every record states `mode="observe_only"` and `commands_allowed=False`.

There is no control option, real adapter, or dispatch queue. The fake device records and rejects any attempted command; normal routine execution makes zero attempts, including mode, fan, and schedule changes. No thermostat is touched, so no physical rollback is needed or claimed.

The HTML chart adds evaluations at exact phase boundaries and the endpoint for drawing without changing the original playback samples or JSON trace. Neither a smooth graph nor a passing baseline test establishes achieved comfort, sleep quality, health benefits, equipment safety, or energy savings.
