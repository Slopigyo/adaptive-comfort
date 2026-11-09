# Working with Adaptive Comfort

This is experimental, offline comfort-planning code—not a Home Assistant integration or a supported HVAC controller. There is no established public issue tracker, submission process or support commitment. This guide describes how to inspect and work with the source; it does not request submissions or direct reports to Climate Advisor's maintainers. The contribution candidate is **not integrated, submitted or accepted upstream**, and has no upstream endorsement.

Development is owner-directed and AI-assisted. Coding agents helped with design, implementation, tests, documentation and review. Describe executed checks and remaining uncertainty honestly; generated code or a passing synthetic test is not proof of physical safety.

## Start with the implemented scope

Read the [overview](README.md), [offline routine guide](docs/OFFLINE_ROUTINE.md), [test guide](docs/TEST_PLAN.md) and [portfolio case study](docs/PORTFOLIO.md).

The routine uses synthetic inputs and an injected UTC clock. Weather summaries are independent inputs, not target adjustments. The HTML report displays precomputed data only. The separate mode-lifecycle model uses fake readiness and revision signals; it does not establish real Home Assistant ownership, safety or physical hand-back.

From the source root, using Python 3.11+ and the standard library:

```sh
python -m unittest discover -s tests -v
python tools/climate_advisor_bundle.py verify
```

Recorded execution is limited to **Python 3.14.5 on Windows**. The root checkpoint passed **109 tests: 78 original tests plus 31 bundle-tool tests**. The root command does not run Climate Advisor's separate suites; their earlier evidence and environment limits are in the [bundle validation record](contributions/climate-advisor/VALIDATION.md).

Source-free `verify` needs no Git, upstream checkout or third-party dependencies and does not apply or execute the patch. It checks bundle structure and integrity, not authenticity, physical safety or upstream compatibility.

## Keep changes small and testable

For an offline behavior change:

1. State the assumption, relevant hazards and expected fallback or withheld result.
2. Write deterministic tests, including invalid inputs, stale data and boundary cases, before implementation.
3. Keep proposed targets distinct from measured temperatures and from permission to control equipment.
4. Preserve the observe-only boundary and the separation between routine, weather evidence and presentation. Do not turn missing data into an invented fallback temperature.
5. Document changed defaults, units, explanations and limitations. Record the exact checks and environment actually used; do not describe planned tests as passing.

Prefer small typed Python modules and existing standard-library patterns. Additional dependencies need a concrete technical reason. Keep the original prototype and the separate contribution candidate distinct rather than treating their interfaces or test results as interchangeable.

## Safety and privacy

- Use injected clocks, synthetic weather and sensor data, and recording fake devices. Tests must not command real equipment or discover a home network.
- Do not add hidden network calls, telemetry or mandatory AI services. The offline preview does not need a cloud account or language model.
- Keep credentials, household records, device identifiers and personal traces out of source and fixtures. Ignored paths are not a security boundary.
- Never treat passing tests, model output or a temperature graph as evidence of achieved comfort, better sleep, energy savings or hardware safety.
- There is no supported live-deployment or emergency HVAC support path. Do not use real equipment to reproduce a preview failure.

## Useful reproduction notes

A small synthetic reproducer is more useful than a household export. Record the source version or bundle hash, Python version and OS, exact command, expected versus actual behavior, and the smallest fixture demonstrating the problem. Remove credentials, personal paths and device identifiers from errors before sharing them. Do not attach Home Assistant backups or private logs.

The [test guide](docs/TEST_PLAN.md) identifies which checks exist. The full upstream Windows suite has an existing Unix-only `resource` collection blocker; focused upstream results are not a full-suite, Linux or Home Assistant validation claim.

## Licensing and redistribution

The original code, assets, tests, tools and documentation use [Apache License 2.0](LICENSE). The explicit `contributions/climate-advisor/` exception uses [MIT](contributions/climate-advisor/LICENSE) for the new upstream-specific source snapshot and bundle documentation, with **Copyright (c) 2026 Amun**. The unchanged [upstream MIT notice](contributions/climate-advisor/UPSTREAM_LICENSE), **Copyright (c) 2026 gunkl**, is retained. No original Apache code was relicensed; the repository is not uniformly dual-licensed.

- Retain applicable license and third-party attribution notices. Do not add code or data with incompatible terms.
- For a separately distributed generated HTML report, include the root Apache `LICENSE` alongside it and identify it as covering the embedded project code and assets. The self-contained report does not contain the license text.
- Keep the complete MIT contribution bundle with its `LICENSE` and `UPSTREAM_LICENSE`, not just the patch.
- An extracted MIT source distribution must include the Amun copyright and MIT permission text and retain the upstream notice. Applying the patch alone does not install the bundle's license files in the upstream tree.

These guidelines do not add restrictions to recipients' rights under the applicable Apache 2.0 or MIT license.
