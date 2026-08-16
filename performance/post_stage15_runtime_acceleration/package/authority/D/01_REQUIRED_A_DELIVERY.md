# Required A → B delivery

Return:

`A_TO_B_10_W02_4POLICY_PRODUCTION_BINDING_<timestamp>.tar.gz`
and external `.sha256`.

Archive must contain:
- `00_READ_FIRST.md`
- `A_TO_B_10_W02_4POLICY_PRODUCTION_BINDING.json`
- `RUN_W02_4POLICY_ACTUAL.sh`
- actual production adapter/factory source or exact referenced package
- four resolved controller configs + SHA-256
- exact B5 method config + SHA binding
- canonical W02 PRE authority or byte-identical copy
- result writer binding for K9H7_RESULT_V1
- F7 independent job authority binding
- Fresh Exact OpenDSS binding
- checkpoint/failure persistence implementation
- environment/source authority
- `SHA256SUMS.txt`

The launcher should:
1. fail-closed preflight all source/config/PRE hashes,
2. assign four disjoint 4-core CPU budgets,
3. launch P1-P4 concurrently,
4. save all results/evidence to `/home/jaewon/mobile_ess_work/frozen_artifacts`,
5. save logs to `/home/jaewon/mobile_ess_work/logs`,
6. preserve partial/failure artifacts,
7. produce one W02 delivery root compatible with D's included `build_B_TO_D_W02_handoff.sh`.

Do not execute the remaining 11 weeks in this A request. D requires W02 acceptance first.
