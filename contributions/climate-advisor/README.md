# Climate Advisor preview contribution

**Experimental, disconnected code—not an installed integration or an accepted upstream feature.** This bundle contains three preview modules, their tests and two guides. It changes no existing Climate Advisor production file, dependency lock, version or golden scenario.

## Contents and provenance

- Upstream: [Climate Advisor](https://github.com/gunkl/ClimateAdvisor).
- Pinned base: `68c6c2d7ea63a921afed7a391253e448fb6a5ceb` (development manifest 0.8.61, not a tested-release claim).
- [preview.patch](preview.patch): exactly eight new regular files, listed in [manifest.json](manifest.json).
- [manifest.json](manifest.json): base revision, MIT designation, canonical patch hash and each normalized payload's byte count/SHA-256. Text is UTF-8 with LF line endings and a final newline.
- [LICENSE](LICENSE): MIT for the new contribution and bundle documentation, Copyright 2026 Amun.
- [UPSTREAM_LICENSE](UPSTREAM_LICENSE): retained upstream MIT notice, Copyright 2026 gunkl. Attribution does not imply authorship or endorsement of this contribution.
- [VALIDATION.md](VALIDATION.md): recorded reconstruction results, versions, hashes and unrun tiers.

| Module | Purpose | Not implemented |
| --- | --- | --- |
| `sleep_trajectory.py` | Interpolate an explicitly approved, bounded heat/cool band over five dated anchors | HVAC commands, device quantization, room response or mode switching |
| `sleep_timing.py` | Resolve one supplied wake date and local-time configuration into UTC anchors, with explicit gap/fold handling | A recurring scheduler, daylight anchors or host-clock integration |
| `adaptive_mode_preview.py` | Model policy selection, manual holds, stale requests and logical return using synthetic host snapshots | Real ownership detection, safety validation, host-policy execution or physical restoration |

No existing production path imports these modules. The three modules are not a connected controller, and the independent [Adaptive Comfort browser demo](../../docs/WEB_DEMO.md) does not display them. Weather adaptation, learned human comfort and measured comfort/energy benefits are absent.

## Verify without Git or an upstream checkout

From the Adaptive Comfort root, using Python 3.11+ and only the standard library:

```sh
python tools/climate_advisor_bundle.py verify
python -m unittest discover -s tests -p test_contribution_bundle.py -v
```

Verification checks the fixed addition-only patch format, pinned metadata and every manifest hash. It does **not** apply, import or execute the payload, and needs no network, Home Assistant or third-party package. Checksums detect corruption/drift, not coordinated replacement of both files; they are not signatures or a security audit.

The bundle's `.gitattributes` preserves LF for `preview.patch` and `manifest.json`, including on Windows. Do not hand-edit the generated pair.

## Reconstruct the contribution

Use a disposable checkout, never a live Home Assistant configuration. The commands below are a **reader setup recipe**, not evidence that a fresh clone/environment has been validated. Obtaining upstream source requires GitHub access; running its tests requires separate tooling. Neither is necessary to run the independent prototype or verify this bundle.

From the Adaptive Comfort root, with an unused destination:

```sh
git clone --no-checkout https://github.com/gunkl/ClimateAdvisor.git local/ClimateAdvisor
git -C local/ClimateAdvisor checkout --detach 68c6c2d7ea63a921afed7a391253e448fb6a5ceb
git --no-pager -C local/ClimateAdvisor rev-parse HEAD
git --no-pager --no-optional-locks -C local/ClimateAdvisor status --porcelain
```

Confirm that HEAD equals the pinned base and status is empty. If the revision is unavailable, stop rather than substituting a newer revision. An existing disposable checkout at exactly this base can be used instead; the maintenance tool never clones or fetches for you.

Then, still from the Adaptive Comfort root:

```sh
git --no-pager -C local/ClimateAdvisor apply --check --whitespace=error-all ../../contributions/climate-advisor/preview.patch
git -C local/ClimateAdvisor apply --whitespace=error-all ../../contributions/climate-advisor/preview.patch
python tools/climate_advisor_bundle.py verify --source local/ClimateAdvisor
```

Git refuses additions over existing files. Do not force application or conceal an incorrect base with a three-way merge. Source verification additionally requires the actual checkout root, pinned HEAD and exactly the eight expected untracked files—no tracked/staged modifications or unrelated untracked files. Ignored caches/environments are not exported.

The two included guides become `docs/sleep-trajectory-preview.md` and `docs/adaptive-mode-preview.md` in that checkout. They explain the implemented contracts and remaining integration gates.

### Optional upstream tests

The pinned upstream project requires Python **3.14.2+** and its separate locked `test` dependency group. Follow `docs/DEVELOPMENT.md` in the reconstructed checkout for its unit-only tooling. Setup may download packages; the root prototype's standard-library-only claim does not apply to these pytest suites.

From the reconstructed checkout, after that tooling is available:

```sh
python scripts/test.py unit tests/test_adaptive_mode_preview.py tests/test_sleep_timing.py tests/test_sleep_trajectory.py tests/test_thermostat_program.py tests/test_target_band.py tests/test_desired_state.py tests/test_restore_resolved_band.py tests/test_startup_coalesce.py tests/test_observe_only_gates.py -q
```

Keep `unit`: omitting it selects both test tiers. The recorded 444-case check reused an existing unit environment in an initially clean detached worktree, not a fresh dependency setup. The full Windows unit suite has a pre-existing Unix-only `resource` collection blocker; no skip or portability fix is included. Linux, the real-HA tier and live equipment were not validated. See [the evidence record](VALIDATION.md).

## Refresh after deliberate source changes

From the Adaptive Comfort root, for the example checkout above:

```sh
python tools/climate_advisor_bundle.py verify --source local/ClimateAdvisor
python tools/climate_advisor_bundle.py build --source local/ClimateAdvisor --replace
```

The builder reads only the fixed eight-file allowlist, rejects linked/redirected or nonregular paths and malformed text, and normalizes CRLF to LF. It writes only `preview.patch` and `manifest.json`, never the checkout. Without `--replace`, identical output is a no-op and different existing output is protected.

Both destinations are checked before writing. An interrupted write can leave an incomplete pair that verification rejects; the two-file update is not atomic. Use a stable local checkout without concurrent edits; these path checks are not a defense against hostile filesystem races. The tool has no apply, install, commit, push or deployment operation.

A changed payload requires renewed reproduction/testing and an updated validation record. Matching hashes do not rerun behavioral tests, and this pinned snapshot does not track later changes to a checkout automatically.

## License and redistribution

Distribute the **complete bundle**, including both license files, not `preview.patch` alone. The six Python payload files have MIT SPDX headers, but the patch does not carry the full MIT text or Amun copyright notice. Applying it adds only the eight payload files; it does not install the bundle's licenses in the upstream tree.

If extracted source is distributed or submitted upstream, ensure the Amun copyright and MIT permission notice accompany it and retain the upstream notice. The existing upstream copyright credit alone does not preserve the contribution notice. These requirements follow the license terms; there is no additional approval restriction on downstream MIT rights.

The independent prototype and maintenance tool/tests remain [Apache 2.0](../../LICENSE). No original Apache runtime was relicensed into this contribution. Climate Advisor is an independent project; no affiliation, endorsement, submission or acceptance is claimed.
