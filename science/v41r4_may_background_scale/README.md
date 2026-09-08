# V41R4 May-wide background scale decision

The common background factor **1.15** is the largest tested factor that passes
every May 2025 B0 Day-Ahead trajectory. The 1.60 development setting could not
serve as a May-wide feasible B0 reference. The user authorized three successive
screens, preserving each prior round and its predeclared selection rule.

| Round | Tested factors | PASS / FAIL days, in that order | Selection |
|---|---|---|---|
| 1 | 1.35, 1.40, 1.45, 1.50 | 20/11, 17/14, 11/20, 9/22 | FAIL_CLOSE |
| 2 | 1.30, 1.25 | 22/9, 23/8 | FAIL_CLOSE |
| 3 | 1.20, 1.15, 1.10 | 28/3, 31/0, 31/0 | **1.15** |

All **279 trajectories / 26,784 slots** converged. Each trajectory has 96
quarter-hour slots and an isolated clean OpenDSS engine. Only native/background
P and Q were scaled, using unchanged 780-GPU B0 reference decisions. PV, AIDC
power, ratings, source voltage, topology and native regulator settings were
unchanged; MESS was off. No Actual or B1/B2/B3 results informed selection, and
the screen generated no electrical coefficients or Gurobi solves.

## Selected-factor results

| Metric | alpha 1.15 |
|---|---:|
| Minimum voltage | 0.974481884 pu |
| Maximum voltage | 1.049939479 pu |
| Maximum line-phase loading | 0.849855762 |
| Maximum transformer phase-current loading | 0.976966990 |
| Maximum transformer total-kVA loading | 0.825666205 |
| Mean of 31 daily maximum line loadings | 0.717025201 |
| Median daily maximum line loading | 0.710479697 |
| P90 daily maximum line loading | 0.810452497 |

Voltage gates are inclusive `[0.95, 1.05]`; all three thermal gates are strictly
`< 1.0`, with no tolerance relaxation. Alpha 1.20 first fails on May-21 at
`transformer.reg1a::A`, slot 31, current loading `1.0188489219548178`.

## Review and validate

From this directory, using Python 3.11 or later with no third-party packages:

```console
python validate_bundle.py
python -m unittest discover -s . -p test_validate_bundle.py -v
```

The validator checks archived hashes, 31-day coverage for every candidate,
convergence and exact electrical gates for every slot, daily extrema, round
decisions and the largest-feasible-factor selection. Tests cover boundary
equality, one-ULP voltage violations, missing/duplicate coverage and fail-close.

- `rounds/` contains byte-preserved reports, authorities, verification receipts,
  protocols, protected input/source hashes and topology/control metadata.
- `DAILY_RESULTS.json` contains every day-by-factor result and limiting asset.
- `SLOT_EXTREMA.json.gz` contains exact slot-wise reductions from the original
  voltage/current/kVA arrays, plus native taps and capacitor states. Original
  full-array hashes bind each projection. Packaging performed no new solves.
- `source_snapshot/` preserves the actual screening harness and selected
  physical-runtime source files for forensic review. These are historical
  workspace-dependent scripts, **not a self-contained simulator installation**.
  Full replay still requires the original frozen inputs and runtime; their
  local paths and hashes remain in the preserved receipts.
- `BUNDLE_MANIFEST.json` binds the evidence bytes. Scoped `.gitattributes`
  prevents Git line-ending conversion from invalidating the archived hashes.

This PR records the Day-Ahead screening decision. It does not change production
runtime wiring or certify later Actual/policy campaigns. HOLD and no-Actual
fields in the archived files describe the screen's state at creation, not the
state of subsequent independent campaign work.
