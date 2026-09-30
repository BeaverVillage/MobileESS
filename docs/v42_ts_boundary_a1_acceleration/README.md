# V42 service-boundary TS and exact-safe A1 generation

Base: PR97 `cde230b1be83cfe8fa4114a372b92ed564c98574`. All 279 pre-existing files remain byte-identical. The source rules and conditional compact fallback were preregistered in commit `efe806b5` before May membership evaluation.

Known TS is now a finite source-authorized start window with frozen Q50 service: **1024/1,605 candidate jobs (63.800623%), 76.922350% nominal GPUh**. This is 73.405018% of 1,395 known PENDING jobs. All 1024 candidates also have an individual complete physical later-start option. No globally executable or selected TS share is claimed. RUNNING jobs retain physical gang semantics and cannot TS. R0 requested-walltime planning completions are audited separately from actual realized ends; original authorized post-midnight service is preserved.

The live submitted-job rule uses Q25 (`higher`), N_window>=100, and the frozen four-level QoS/protection-preserving backoff. It is implemented and tested with the inherited submit/Q50/depletion/PENDING event path. The audited historical TRAIN reference ledger has no R0 temporal authority: the empirical distribution is empty, and live TS correctly fails closed. Raw queue waits and May R0 windows are not substituted. Initial May future-job identities remain absent.

The exact generator completed **all 1,499 positive-service jobs in 36.802924s** (external generation wall 39.078000s). Its complete physical set contains **349,215,815 options**, represented by 117 shared exact templates and 1,198,395 lazy blocks. No Option objects are needed during domain construction. The existing synthetic fixtures, 30 additional varied physical fixtures, and eight deterministic real complete domains agree with legacy option sets; ordering is deterministic. Earlier zero-WAN-rate rejection was caught by supplementary tests, its run was stopped, and all invalidated evidence is retained separately.

Prescreening uses only site/rack/residency authority, immutable fixed occupancy, arithmetic checkpoints and exact cached WAN/restart predicates. A failed full STAY mask never removes a feasible migration prefix. Zero-rate waiting slots inside a transfer remain valid exactly as in legacy. No Top-K, objective ranking, sampling or movable-reference occupancy is used. Raw candidate-attempt reduction is 9.815435%; deletion of valid physical options is zero. PR97's partial 92,656 options are never used as a full-domain denominator.

The resource consistency recheck remains **PASS**, explicitly with zero achieved reserve only as a diagnostic. The unchanged real Runtime/CC4 Planning targets are bound in the A1 model. The next blocker is **A1_COMPLETE_OPTION_MODEL_CONSTRUCTION_600S_TIMEOUT**. A1's separate model attempt used 600.313000s and produced no accepted incumbent. Domain construction succeeded; full model construction did not. Partial model counts are labeled in A1_MODEL_STATS.json; final counts, optimize time, gap, nodes and presolve are null. M1/A2/M2 and Fresh AC are NOT_RUN; no final response kernel exists.

The compact fallback was **not activated**: its preregistered condition was failure to complete the exact domain within 600s. Model size alone does not meet that trigger. Problem 8 remains open. Future exact representation work must not be misreported as solved by this domain benchmark.

Verification: **354 tests pass**, source hashes and preserved evidence verify, and the original CC4 envelope/provider/gamma90=2.423057443558147/780 GPU/MESS/PCS/Event30/local-repair files are untouched.

```powershell
$env:PYTHONUTF8='1'
python -m pytest v42_boundary/tests.py tests/test_v42_temporal.py tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q
python -m v42_boundary.verify
git diff --check
```

The large lazy domain, full per-job profiles, failed attempts and supervised process logs remain local and SHA-bound. Fresh generation requires a new empty output directory and the frozen native source files; do not overwrite one-shot receipts. See FINAL_REVIEW_KO.md for the 50 requested answers and the authority audits for source limitations.
