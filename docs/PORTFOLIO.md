# Adaptive Comfort — experimental comfort planning

**Software case study · offline and non-actuating**

Adaptive Comfort explores indoor comfort that follows an approved daily rhythm rather than one fixed temperature. The longer-term goals are gentle weather influence, overnight cooling and warming toward waking, with little ongoing attention. The current result is narrower: **deterministic previews, explicit failure cases and a reproducible contribution candidate—not a working thermostat integration**.

Development is **owner-directed and AI-assisted**: coding agents helped with design, implementation, tests, documentation and review. The evidence below describes executed software checks, not independent human authorship of every line or proof of physical safety.

## The engineering problem

A comfort planner must distinguish a desired temperature from an achieved room temperature, a schedule from measured sleep, and an approved proposal from permission to control equipment. Mistakes at those boundaries could produce a controller that fights its user.

There is no live HVAC testbed or hardware validation. The work instead isolates questions that can be tested offline: bounded recommendations, missing weather evidence, ambiguous local times, stale or manual mode events, and reproducible source packaging.

## What exists today

| Component | Implemented evidence | Deliberate limit |
| --- | --- | --- |
| Independent routine preview | Injected UTC clock, approved bounds/rates, synthetic indoor input, explained recommendations and a fake device that rejects commands | No room response, local-time scheduler or physical control |
| Outdoor-history summary | Time-weighted mean gated by coverage and freshness; explicit gaps, duplicates and invalid-input handling | Does not influence routine targets |
| Browser demo | One self-contained HTML file showing precomputed routine and separate weather results; playback and display-unit controls | Not an HA dashboard, configuration editor or building simulation |
| Climate Advisor candidate | Disconnected heat/cool band preview, one-wake-date timezone resolver and synthetic mode lifecycle; modules, tests and guides in an eight-file patch | Not integrated, submitted or accepted upstream |
| Reproduction tooling | Pinned base, deterministic hashes, exact file allowlist and source-free verification | Checksums establish integrity, not authenticity or behavioral correctness |

The independent prototype and Climate Advisor work are **separate implementations with different interfaces**. The browser does not display the upstream modules. The candidate is not imported by the live planner, UI or command paths; its synthetic mode model does not execute a host policy, switch a live mode or perform physical hand-back. Climate Advisor is an independent project, not a sponsor or endorser.

## A five-minute review

From the source root with Python 3.11+ and the standard library; recorded execution is limited to Python 3.14.5 on Windows:

```sh
python -m unittest discover -s tests -v
python tools/climate_advisor_bundle.py verify
python -m adaptive_comfort --hours 12
```

The first command runs the **root** tests, not Climate Advisor's separate suites. Source-free bundle verification needs no Git, upstream checkout or third-party dependencies and does not apply or execute the patch. The offline preview needs no Home Assistant installation, network service, account or AI model.

Without `--hours`, the normal CLI emits **96 JSON records** over 48 hours at 30-minute intervals, excluding the end instant. Every record has `commands_allowed=false`.

For the visualization:

```sh
python -m adaptive_comfort --html local/demo.html
```

Open the generated file yourself. Existing files are protected; add `--force` only for deliberate replacement. The [browser guide](WEB_DEMO.md) covers display controls and separate HTML distribution. Playback and unit changes select or display precomputed values; they do not evaluate control policy.

### Read the curve without mistaking it for room response

These selected records come from the original default fixture. Dates and temperatures are synthetic, not household recommendations. Values are continuous `candidate_c`, not measurements or commands.

| UTC instant | Phase | Proposed temperature |
| --- | --- | --- |
| 2026-01-01 23:00 | Wind-down starts | 22°C |
| 2026-01-02 02:00 | Overnight hold starts | 21°C |
| 2026-01-02 05:00 | Pre-wake warming starts | 21°C |
| 2026-01-02 06:00 | Pre-wake midpoint | 22°C |
| 2026-01-02 07:00 | Return toward daytime starts | 23°C |
| 2026-01-02 09:00 | Daytime | 22°C |

The synthetic indoor reading remains **22°C throughout**. Each record has `status="recommendation"` and `commands_allowed=false`. A higher cooling setpoint can permit passive warming; it does not show that a room warmed or authorize switching to heating. Scheduled overnight and waking phases do not measure sleep stages.

### Inspect failure cases, not just a smooth line

The independent seven-day weather examples make missing evidence visible:

| Example | Covered time | Result |
| --- | --- | --- |
| Complete history | 168 of 168 hours | A usable time-weighted mean |
| Missing observations | 146 of 168 hours | No mean: `insufficient_coverage` |
| Stale latest reading | 165 of 168 hours | No mean: `stale_outdoor`, despite high coverage |

These are fixed report examples, not live weather or histories ending at each playback tick. **None changes the temperature curve.** A withheld result is an intended output, not a hidden fallback temperature. The separate upstream tests also exercise invalid band slopes, DST ordering and stale/manual mode events.

## Engineering choices and tradeoffs

1. **Deterministic policy before learning.** Injected time, explicit units and rational arithmetic make boundaries inspectable. There is no learned comfort estimator or LLM in the implemented routine.
2. **Separate input evidence from decisions.** Weather averaging is tested independently rather than immediately adding another offset. Missing weather cannot manufacture a recommendation.
3. **Model authority before touching devices.** The mode model requests evaluation using current settings rather than restoring captured setpoints. Fake revisions and readiness flags let tests explore stale work and manual holds; they are not verified Home Assistant ownership or safety APIs.
4. **Explore a contribution, not a competing controller.** Climate Advisor's default automation, manual-grace, startup and persistent-hold policies differ from the proposed contract. The candidate leaves existing production paths unchanged instead of silently rewriting those policies.
5. **Make the experiment reviewable.** The pinned eight-file patch preserves the candidate without bundling an upstream repository or dependency environment. Source-free verification cannot install or execute it; patch reapplication refuses existing files.

## Recorded evidence and limitations

- **109 root tests passed at the recorded checkpoint:** 78 original baseline/weather/report tests plus 31 bundle-tool tests, on Python 3.14.5 / Windows.
- **444 focused upstream cases passed at an earlier reconstruction checkpoint:** 77 band, 70 timing, 101 mode and 196 existing regressions. The three module import origins were verified inside the reconstructed tree. This used an **initially clean detached worktree** and reused the existing uv 0.13.7 / locked test dependency environment on Python 3.14.5 / Windows; it was **not a fresh clone or dependency environment**.
- The full upstream Windows unit suite remains blocked during collection by existing Unix-only `resource` imports. No successful full upstream suite, Linux or Home Assistant run is claimed.
- Earlier Chrome smoke checks cover the original demo. No new browser validation, cross-browser coverage or assistive-technology audit is claimed here.

These are recorded development checks, not validation of a new distribution. Exact reproduction commands, versions and hashes are in the [bundle validation record](../contributions/climate-advisor/VALIDATION.md). The [test guide](TEST_PLAN.md) distinguishes implemented checks from pending scenarios.

Passing synthetic tests establishes only their software assertions. There is no building/occupant simulation, learned comfort result, user study, demonstrated comfort improvement, sleep benefit, energy saving or hardware-safety result.

## Remaining questions

Bounded weather influence, daylight timing and context-specific preference learning still need their own experiments. Any future live integration would additionally need verified host-policy compatibility, manual authority, ownership, sensor/device limits, startup behavior and physical hand-back. The synthetic mode tests do not answer those integration questions. There is no promised delivery date, deployment support or upstream acceptance.

## Licensing

The original code, assets, tests, tools and documentation use [Apache 2.0](../LICENSE). The upstream-specific snapshot and documentation in `contributions/climate-advisor/` use [MIT](../contributions/climate-advisor/LICENSE), Copyright (c) 2026 Amun, retaining the unchanged [upstream MIT notice](../contributions/climate-advisor/UPSTREAM_LICENSE), Copyright (c) 2026 gunkl. This is a scoped exception, not a choice of either license for every file.

Separately distributed HTML needs the root Apache `LICENSE`. Keep the complete MIT bundle and both notices together; extracted MIT source needs the Amun copyright and permission text plus the retained upstream notice. See [licensing and redistribution](../CONTRIBUTING.md#licensing-and-redistribution).
