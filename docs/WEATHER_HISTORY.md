# Offline outdoor-history summary

**Scope: weather input validation and averaging only.** This module does not change the [routine preview](OFFLINE_ROUTINE.md) or any temperature recommendation. It is an input prerequisite for weather following, not weather adaptation itself. The [test guide](TEST_PLAN.md) distinguishes the implemented input portion of W06 from complete weather-adaptive acceptance.

## Input contract and failure behavior

[`adaptive_comfort.weather.summarize_history()`](../adaptive_comfort/weather.py) accepts `OutdoorReading` records, one explicitly selected source, an injected evaluation time, and explicit `HistoryRequirements`. It returns a `WeatherHistorySummary`. There is no source discovery, weather service, network access, real-clock lookup, storage, cache, retention policy, persistence, or control side effect.

- Select one nonblank source identity. Do not mix sources or infer which source should be authoritative.
- Supply a timezone-aware UTC evaluation time. A zero-offset clock is normalized to fixed UTC before window arithmetic, even if its timezone has different offsets on other dates. The window measures elapsed time, not local calendar days.
- Each observation has a value/unit, observation time, receipt time, source identity, and explicit boolean availability. Aware observation/receipt timestamps are normalized to UTC. Missing/naive times, times that cannot be represented in UTC, observation after receipt, and future observations or receipts are invalid. The ordering is `observed_at <= received_at <= now`; an offline replay must not include events received after its evaluation time.
- Available readings use the routine core's finite-number validation and explicit `C`/`F` conversion. Missing/unsupported units, non-finite values, and numeric booleans are invalid. Receipt recency does not make an old observation fresh.
- Supply a trailing `window`, `max_sample_hold`, `max_observation_age`, and `minimum_coverage`. All three durations must be positive `timedelta` values. Minimum coverage must be a finite number in `(0, 1]`. A window outside the supported datetime range is invalid. **There are no production numeric defaults.** Hold duration and current observation age are independent limits.
- The whole supplied batch is validated, including records outside the requested window and repeated records before deduplication. One invalid record withholds the summary rather than silently discarding inconvenient data. Supply the selected source's relevant history, including a predecessor whose original hold can overlap the window's start.
- An unavailable event still requires valid source, timestamps, and availability. Its temperature/unit are ignored: it marks a coverage break, not a zero-degree observation. A later valid event resumes coverage without backfilling the gap. If the latest event is unavailable, no usable mean is returned even when historical coverage is otherwise sufficient.

## Time-weighted averaging

Sort by observation time, not receipt order. The trailing window is `[now - window, now)`. Each available measurement represents a piecewise-constant value over a half-open interval starting at its observation time and ending at the earliest of:

1. The next event, including an unavailable event.
2. Its original observation time plus `max_sample_hold`.
3. The evaluation time.

Intersect that interval with the trailing window. Do not reset an old observation's expiry at the window boundary. Uncovered time stays a gap: do not interpolate, backfill from the next measurement, or count overlapping intervals twice.

Coverage is covered elapsed duration divided by the whole window duration. The mean uses **covered duration** as its denominator, not the whole window; missing time is not a zero-degree reading. Coverage and threshold comparisons use exact elapsed durations. Weighted accumulation uses exact rational arithmetic over normalized Celsius floats so accepted finite inputs do not overflow merely from multiplication by duration.

Return `mean_c` only when all three conditions hold:

- Coverage meets the configured minimum.
- The latest event is available.
- The newest valid observation is no older than `max_observation_age`.

Coverage and freshness boundaries are inclusive. Otherwise return no mean, with reason codes and an explanation; retain meaningful coverage diagnostics when the input itself is valid. A fresh observation exactly at the window's end contributes zero duration and cannot manufacture missing history.

This is an estimate from measured samples, not proof of actual temperature between readings. Even a usable summary can contain gaps up to its declared coverage allowance.

## Duplicate and source rules

Within the selected source, the normalized observation instant identifies an event. Equal wall-clock labels with different UTC offsets can represent different instants and must not be merged merely by their local labels.

Repeated available events collapse only when their normalized Celsius floats from the shared converter are exactly equal and availability agrees. There is no approximate-equality tolerance. Equivalent `C`/`F` representations can therefore collapse, as can equivalent unavailable events whose unused temperature/unit fields differ. Valid receipt-time differences do not make a new event. Duplicates gain no extra weight and never extend the original expiry.

Conflicting values or available/unavailable states at the same observation instant withhold the batch. The function does not choose a winner by arrival order or average conflicting duplicates; the caller must resolve the conflicting source data. A valid copy cannot hide an invalid duplicate.

## Results

| Outcome | Mean | Coverage diagnostics |
| --- | --- | --- |
| `usable` | Covered-time mean in Celsius | Present; coverage and freshness gates passed |
| `unavailable`: empty, insufficient, stale, or unavailable history | `None` | Present for valid input, so the failure can be explained |
| `unavailable`: invalid input/configuration or conflicting events | `None` | No trusted coverage result; the first validation reason is reported |

`latest_observed_at` identifies the newest valid measurement, not its receipt time. `duplicate_count` counts equivalent events removed from an otherwise valid batch. An unavailable result supplies no fallback average or temperature. A usable result is only evidence for a possible future planner: it is neither a setpoint nor permission to control equipment.

## Synthetic fixture and tests

The arithmetic fixture uses a **seven-elapsed-day window**, at least **90% covered time**, at most **three hours represented by each observation**, and a newest-observation age of at most **three hours**. These are synthetic test parameters, not validated weather-adaptation, household, or equipment-safety defaults. Shorter fixtures make interval arithmetic independently checkable. The [browser report](WEB_DEMO.md) displays complete, missing-block, and stale-tail examples without connecting them to the routine.

The 24 tests in [test_weather.py](../tests/test_weather.py) cover weighted versus sample-count averages; irregular/dense samples; reorderings and duplicates; exact coverage/age boundaries; clipping at both window edges; gaps and unavailable events; mixed `C`/`F` inputs; invalid timestamps, units, values, sources, and requirements; empty history; extreme finite-value accumulation; and UTC normalization across a synthetic offset transition. These root tests need no installed timezone database.

Run just this module's tests from the repository root:

```sh
python -m unittest discover -s tests -p test_weather.py -v
```

The root targets Python 3.11+ using only the standard library. Historical execution was on Python 3.14.5 / Windows; see the [test guide](TEST_PLAN.md) for the full suite and limitations. Passing input checks does not establish target adaptation, safe fallback from a previously applied weather offset, or any comfort/energy outcome.
