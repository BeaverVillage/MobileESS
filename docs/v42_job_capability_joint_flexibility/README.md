# V42 independent job capability prototype

Three independent masks and complete start/site/checkpoint-migration options are implemented and tested in an isolated bounded MILP. **Native V42 adoption and final temporal percentages are blocked** by unfinalized service/carry-over and native binding authority. No Runtime/CC4 ML, May policy evaluation, full IEEE123/IEEE8500 or alternating campaign was run.

Read [the Korean review](FINAL_REVIEW_KO.md) for all 50 answers, [capability contract](JOB_CAPABILITY_SPEC.md), [objective audit](P1_P5_CURRENT_OBJECTIVE_AUDIT.md), and [objective proposal](OBJECTIVE_REDESIGN_SPEC.md). Final readiness flags and scope are in `FINAL_VERDICT.json`.

Evidence populations are deliberately distinct:

- Historical R0: published PR75 47,009 rows; exact gate/bounds reproduction, no new May run.
- TRAIN: 439,534 persisted pre-2025 completed historical jobs, 260 cohorts; Q25 recomputed without model fitting.
- Inventory: 412 pre-May snapshot dates, 242,842 job-days on 396 nonempty dates. Unknown capability remains null.
- Post-cutoff issue validation: 90,706 job-days, Jan02–Apr30; proxy eligibility only. The full local compressed membership is SHA-bound in `POPULATION_SCOPE.json`.
- A–J canaries: 127 complete options before screen, 76 retained; synthetic shares are test coverage only. `CAPABILITY_MEMBERSHIP.csv` contains these ten fixture records, not a claim of population execution.

Reproduce from repository root:

```powershell
python -m pytest tests/test_v42_job_capability.py -q
python docs/v42_job_capability_joint_flexibility/reproduce.py --workspace 'D:/ChatGPT/Mobile ESS 2'
```

The audit runner needs the exact external files in `SOURCE_MANIFEST.json`; it imports no production optimizer or ML pipeline. Large historical row evidence remains local. Small reports/code/tests are committed. `DELIVERY_MANIFEST.json` hashes delivered files; `INPUT_PRESERVATION.json` checks original scientific evidence before/after. No evidence overwrite or authority promotion is performed.
