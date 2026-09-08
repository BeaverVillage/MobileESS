# V41R2 780-GPU May-04 acceptance

**May-04: FAIL_CLOSE. Full May: HOLD; not started.**

Execution and persistence completion are reported separately from physical acceptance. A voltage limit exceedance remains a failed hard gate even when the replay receipt is COMPLETE.

## Capacity

624: [64, 32, 64, 32, 80, 64, 32, 64, 32, 64, 32, 64]
780: [80, 40, 80, 40, 100, 80, 40, 80, 40, 80, 40, 80]

ML retraining/recalibration/model changes: 0. Raw Q90/H4 prediction values and model hashes preserved. H4 physical cap: 2496 → 3120 GPUh.

## Reference scheduling

| Metric | 624 B0 | 780 B0 |
|---|---:|---:|
| job_count | 1031 | 1031 |
| RUNNING_count | 271 | 271 |
| PENDING_count | 760 | 760 |
| D00_RUNNING | 413 | 569 |
| D_day_starts | 611 | 455 |
| still_queued_at_H | 0 | 0 |
| D24_carryout | 471 | 143 |
| true_cross_H_GPUh | 6914.0 | 5076.0 |
| UNASSIGNED_count | 7 | 7 |
| UNASSIGNED_Dday_count | 0 | 0 |
| scheduled_GPUh | 14664.5 | 15535.25 |
| mean_occupancy | 0.9792000534188035 | 0.8298744658119659 |
| FULL_fraction | 0.8880208333333334 | 0.6684027777777778 |
| all_12_FULL_fraction | 0.5416666666666666 | 0.6041666666666666 |
| Capacity wait mean (hours) | 14.827631578947368 | 6.917105263157895 |
| Capacity wait P50 (hours) | 12.0 | 10.0 |
| Capacity wait P90 (hours) | 24.0 | 12.0 |
| Capacity wait P95 (hours) | 28.0 | 16.0 |

| Site | Old mean occupancy | New mean occupancy | Old FULL fraction | New FULL fraction | New mean headroom (GPU) |
|---|---:|---:|---:|---:|---:|
| AIDC01 | 0.9973958333333334 | 0.9302083333333334 | 0.9583333333333334 | 0.6666666666666666 | 5.583333333333333 |
| AIDC02 | 0.9869791666666666 | 0.7408854166666666 | 0.9479166666666666 | 0.6666666666666666 | 10.364583333333334 |
| AIDC03 | 0.994140625 | 0.8864583333333332 | 0.9583333333333334 | 0.625 | 9.083333333333334 |
| AIDC04 | 1.0 | 0.9333333333333336 | 1.0 | 0.6666666666666666 | 2.6666666666666665 |
| AIDC05 | 0.9673177083333333 | 0.8045833333333334 | 0.8020833333333334 | 0.6666666666666666 | 19.541666666666668 |
| AIDC06 | 0.95751953125 | 0.8019531249999998 | 0.8229166666666666 | 0.6875 | 15.84375 |
| AIDC07 | 0.9664713541666666 | 0.7390625000000002 | 0.7604166666666666 | 0.6666666666666666 | 10.4375 |
| AIDC08 | 0.9947916666666666 | 0.8861979166666668 | 0.9583333333333334 | 0.7083333333333334 | 9.104166666666666 |
| AIDC09 | 0.9241536458333334 | 0.734375 | 0.78125 | 0.7083333333333334 | 10.625 |
| AIDC10 | 0.998046875 | 0.8578125000000002 | 0.9583333333333334 | 0.6041666666666666 | 11.375 |
| AIDC11 | 0.955078125 | 0.75 | 0.8645833333333334 | 0.75 | 10.0 |
| AIDC12 | 0.9798177083333334 | 0.7740885416666666 | 0.84375 | 0.6041666666666666 | 18.072916666666668 |

Changed starts: 622; changed initial sites: 688. Pending readiness is issue slot 0; historical resource delays are not exogenous release times. Seven historical pre-D00-complete RUNNING records have no site and remain explicitly UNASSIGNED, with no Day-D service.

## Power and electrical

Installed idle IT: 64.9962745856014032 → 81.245343232001754 kW. Full active IT: 406.775993813819136 → 508.46999226727392 kW.
Per-GPU coefficients, C1, GFS weather, PF, hosts and 1500-kVA site transformer ratings remain frozen. New IT/PCC and May-04 AC coefficients were generated at the new B0 operating point. Static transformer P/Q flow matrices and ratings passed exact equality; constants were regenerated (differences below 5e-13). No measured-facility claim.

## B0 versus B1

| Objective | B0 | B1 | B1 − B0 | Relative |
|---|---:|---:|---:|---:|
| P1 | 0.5250007235537938 | 0.5209427744621371 | -0.004057949091656687 | -0.007729416188587201 |
| P2 | 1413.1782973988418 | 1170.086270543944 | -243.09202685489777 | -0.17201794515408542 |
| P3 | 0 | 10 | 10 | None |
| P4 | 0 | 26072 | 26072 | None |
| P5 | 1530204911 | 1472050274 | -58154637 | None |

Prestart relocations: 27; checkpoint migrations: 10. WAN wait hours: {'mean': 10.775, 'P95': 16.025, 'max': 16.25}. Additional post-D24 service: 1343.0 GPUh across 9 jobs.
WAN waiting is observed under unchanged UID serialization and frozen path semantics; this can move service outside D24 and is not purely a spatial-load effect.
Exact compute-segment service difference versus B0; includes the complete migration interruption (waiting, transfer, ready/restart), not an isolated counterfactual of WAN waiting alone.
Old WAN waiting (25 migrations): {'mean': 2.87, 'P95': 22.5, 'max': 22.75}. Maximum waiting reduced: True; mean reduced: False; P95 reduced: True. Newly crossing D24: 7 jobs.

Fresh B0/B1: PASS/PASS. Actual physical B0/B1: FAIL/FAIL; replay/capacity/persistence PASS, reoptimization 0. Optimization runtime: 1778.7942400999018 seconds (limit 1800). Tests: {'tests': 360, 'errors': 0, 'failures': 2, 'skipped': 0}. Failed acceptance tests are retained and not relaxed.
Full candidate universe independently re-enumerated; fixed first-improvement search source preserved; reference starts fixed and every accepted incumbent checked. No minimum benefit or new time-shifting policy imposed. The result is a bounded first-improvement feasible incumbent, with no global optimality certificate.

HOLD: May-04 Actual voltage acceptance failed; the remaining 30 days were not generated or run

All job, queue, power, objective, grid, MESS-off, Fresh, Actual and authority/hash receipts are in the adjacent JSON report and the V41R2 runtime directory.

## Initial critical line and headroom

line.sw2::A, phase A, slot 70; aggregate 501/780 GPU (64.230769%). Positive-headroom sites: 11; sites accepting empirical P50/P90 gangs: 11/11 (gang sizes 1.0/1.0 GPU).

| Site | Initial critical-slot GPU | Headroom GPU |
|---|---:|---:|
| AIDC01 | 64 | 16 |
| AIDC02 | 16 | 24 |
| AIDC03 | 55 | 25 |
| AIDC04 | 32 | 8 |
| AIDC05 | 55 | 45 |
| AIDC06 | 27 | 53 |
| AIDC07 | 10 | 30 |
| AIDC08 | 57 | 23 |
| AIDC09 | 25 | 15 |
| AIDC10 | 70 | 10 |
| AIDC11 | 40 | 0 |
| AIDC12 | 50 | 30 |

## PCC transformer audit

Old/new B0 maximum dedicated-site transformer utilization: 4.009338% / 4.924264%.

| Policy / stage | Site | Max P kW | Max Q kvar | Max kVA | Rating kVA | Utilization | Violations |
|---|---|---:|---:|---:|---:|---:|---:|
| B0_actual | AIDC01 | 56.585335 | 18.598700 | 59.563510 | 1500 | 3.970901% | 0 |
| B0_actual | AIDC02 | 30.509950 | 10.028136 | 32.115737 | 1500 | 2.141049% | 0 |
| B0_actual | AIDC03 | 54.942163 | 18.058616 | 57.833856 | 1500 | 3.855590% | 0 |
| B0_actual | AIDC04 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_actual | AIDC05 | 64.145790 | 21.083701 | 67.521884 | 1500 | 4.501459% | 0 |
| B0_actual | AIDC06 | 56.037611 | 18.418672 | 58.986959 | 1500 | 3.932464% | 0 |
| B0_actual | AIDC07 | 28.319054 | 9.308023 | 29.809531 | 1500 | 1.987302% | 0 |
| B0_actual | AIDC08 | 38.510445 | 12.657771 | 40.537311 | 1500 | 2.702487% | 0 |
| B0_actual | AIDC09 | 29.962226 | 9.848107 | 31.539185 | 1500 | 2.102612% | 0 |
| B0_actual | AIDC10 | 47.821752 | 15.718250 | 50.338686 | 1500 | 3.355912% | 0 |
| B0_actual | AIDC11 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_actual | AIDC12 | 54.942163 | 18.058616 | 57.833856 | 1500 | 3.855590% | 0 |
| B0_dayahead | AIDC01 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B0_dayahead | AIDC02 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_dayahead | AIDC03 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B0_dayahead | AIDC04 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_dayahead | AIDC05 | 70.170763 | 23.064015 | 73.863962 | 1500 | 4.924264% | 0 |
| B0_dayahead | AIDC06 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B0_dayahead | AIDC07 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_dayahead | AIDC08 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B0_dayahead | AIDC09 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_dayahead | AIDC10 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B0_dayahead | AIDC11 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B0_dayahead | AIDC12 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B1_actual | AIDC01 | 46.726304 | 15.358193 | 49.185583 | 1500 | 3.279039% | 0 |
| B1_actual | AIDC02 | 30.509950 | 10.028136 | 32.115737 | 1500 | 2.141049% | 0 |
| B1_actual | AIDC03 | 54.942163 | 18.058616 | 57.833856 | 1500 | 3.855590% | 0 |
| B1_actual | AIDC04 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B1_actual | AIDC05 | 60.311721 | 19.823504 | 63.486022 | 1500 | 4.232401% | 0 |
| B1_actual | AIDC06 | 54.942163 | 18.058616 | 57.833856 | 1500 | 3.855590% | 0 |
| B1_actual | AIDC07 | 28.319054 | 9.308023 | 29.809531 | 1500 | 1.987302% | 0 |
| B1_actual | AIDC08 | 37.414997 | 12.297715 | 39.384208 | 1500 | 2.625614% | 0 |
| B1_actual | AIDC09 | 26.128159 | 8.587910 | 27.503325 | 1500 | 1.833555% | 0 |
| B1_actual | AIDC10 | 46.178580 | 15.178165 | 48.609032 | 1500 | 3.240602% | 0 |
| B1_actual | AIDC11 | 29.962226 | 9.848107 | 31.539185 | 1500 | 2.102612% | 0 |
| B1_actual | AIDC12 | 54.942163 | 18.058616 | 57.833856 | 1500 | 3.855590% | 0 |
| B1_dayahead | AIDC01 | 57.133059 | 18.778728 | 60.140062 | 1500 | 4.009337% | 0 |
| B1_dayahead | AIDC02 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B1_dayahead | AIDC03 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |
| B1_dayahead | AIDC04 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B1_dayahead | AIDC05 | 70.170763 | 23.064015 | 73.863961 | 1500 | 4.924264% | 0 |
| B1_dayahead | AIDC06 | 57.133059 | 18.778728 | 60.140062 | 1500 | 4.009337% | 0 |
| B1_dayahead | AIDC07 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B1_dayahead | AIDC08 | 57.133059 | 18.778728 | 60.140062 | 1500 | 4.009337% | 0 |
| B1_dayahead | AIDC09 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B1_dayahead | AIDC10 | 57.133059 | 18.778728 | 60.140062 | 1500 | 4.009337% | 0 |
| B1_dayahead | AIDC11 | 31.057674 | 10.208164 | 32.692288 | 1500 | 2.179486% | 0 |
| B1_dayahead | AIDC12 | 57.133059 | 18.778729 | 60.140063 | 1500 | 4.009338% | 0 |

## Fresh and Actual physics

| Policy / replay | Vmin pu | Vmax pu | Maximum line-phase loading | Transformer current loading | Transformer total kVA loading | Converged slots |
|---|---:|---:|---:|---:|---:|---:|
| B0_Fresh | 0.982917157 | 1.049207371 | 0.525000440 | 0.577633294 | 0.481438377 | 96 |
| B0_Actual | 0.982824475 | 1.050726698 | 0.525482333 | 0.575468134 | 0.473557624 | 96 |
| B1_Fresh | 0.983162368 | 1.048668839 | 0.520966541 | 0.573902645 | 0.475872130 | 96 |
| B1_Actual | 0.982946767 | 1.050999114 | 0.534386058 | 0.576728895 | 0.474733925 | 96 |

| Actual objective | B0 | B1 |
|---|---:|---:|
| P1 | 0.5254823332754668 | 0.534386057706939 |
| P2 (GPUh) | 1529.5112928669407 | 1317.08103909465 |

Historical V41R1 B0/B1 Fresh/Actual and diagnostic files were reverified against their existing sealed receipts. The invalidated metadata draft is retained separately; its conservatively charged 190 seconds are included in the 1800-second optimization cap.

## Hard physical gate

Fresh and Actual have different realized workloads and exogenous inputs. Same-slot feeder states are retained for comparison; this is observational evidence, not an isolated causal counterfactual. No regulator, capacitor, model, voltage limit, or WAN retuning was performed.

| Policy / stage | Acceptance | Worst node | Phase | Slot | UTC timestamp | Vmax pu | Excess above 1.05 pu | Violating bus-phase-slot rows |
|---|---|---|---|---:|---|---:|---:|---:|
| B0_actual | FAIL | 83.1 | A | 95 | 2025-05-04T13:45:00+00:00 | 1.050726698 | 0.000726698 | 24 |
| B0_dayahead | PASS | 83.1 | A | 83 | 2025-05-04T10:45:00+00:00 | 1.049207371 | 0.000000000 | 0 |
| B1_actual | FAIL | 83.1 | A | 51 | 2025-05-04T02:45:00+00:00 | 1.050999114 | 0.000999114 | 14 |
| B1_dayahead | PASS | 83.1 | A | 83 | 2025-05-04T10:45:00+00:00 | 1.048668839 | 0.000000000 | 0 |
