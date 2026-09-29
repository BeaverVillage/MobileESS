# V42 May-01 IEEE123 native canary — fail-closed resource infeasibility

The corrected native known population and current C0 were assembled, but A1 is provably infeasible before full complete-option enumeration. The requested A1→M1→A2→M2 computational benchmark and Fresh AC validation are **not completed**. This is a development/native-integration result, not an untouched holdout or policy benefit test.

At 02:45 AEST, known occupancy is at least 494 GPU even after erasing the full service of the 120 largest live jobs. C0 Q50 is 742.6726 equivalent GPU, exceeding the 780-GPU total by **456.6726 GPU**. A source-bound continuous superset independently returned INFEASIBLE; 28 necessary rows violate capacity. See [the proof](A1_RESOURCE_INFEASIBILITY_PROOF.md) and [certificate](MAY01_A1_RESOURCE_CERTIFICATE.json).

- Physical PENDING=0 and RUNNING=full gang; current future reservations and full carry-out remain intact.
- PR79: 321 apparent physical conflicts resolve under separated accounting; **321 original future-plan collisions remain recorded**, with no claim of schedule repair.
- T2-Q25 uses unmodified TRAIN statistics, N>=100 and Q25>=900, without standby exception. May-01 TS=0. No May outcome tuning.
- 1,649 source records are preserved; 1,605 source-admitted known jobs enter the necessary model, and 44 unassigned pre-D00 RUNNING records remain unresolved outside the feeder mapping.
- IEEE123 final alpha_BG=1.15, 780-GPU sites/racks, MESS initial state, all native traffic routes, and C0 source hashes are bound. Numeric source binding is distinct from executing a full grid/MESS model.
- The projection used 1605 continuous variables and 97 rows, 5.062s external wall, and 0.012000s solver time. These are not full-A1 model sizes or performance claims. All full-model gaps/counts are null.
- M1/A2/M2, warm-start measurements, Fresh AC, response-kernel regeneration, IEEE rounds, full May campaigns, and new ML work were not run.

One pre-optimize Unicode-path diagnostic-output failure was retained; the corrected file adapter then executed the resource optimization once. Caps stayed at 600 seconds and MIPGap=.001. No service, gang, C0, capacity, date, trust/epsilon, or physical limit was changed.

Implementation is isolated in `v42_may01/` and a supervised native worker. PR90/91 scientific artifacts are preserved. [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md) answers all 50 requested questions; [FINAL_FLAGS.json](FINAL_FLAGS.json) distinguishes source readiness from model execution. Local LP/IIS and original sources are SHA-bound; portability requires those local authorities.

Reproduction: `python -m v42_may01.prepare` assembles exact frozen sources, `python -m v42_may01.run` permits one optimization (plus the narrowly checked pre-solve I/O repair), and `python -m v42_may01.report` builds this report without solving. Existing receipts deliberately prevent a silent rerun. Delivery validation uses `python -m v42_may01.verify --staged` after staging; unit tests are listed in TEST_RESULTS.xml.

Next dependency: a source-authorized resolution of the known-service/C0 nominal resource incompatibility. The current task does not choose a new service rule, rescale predictions, or tune T2 to obtain feasibility.
