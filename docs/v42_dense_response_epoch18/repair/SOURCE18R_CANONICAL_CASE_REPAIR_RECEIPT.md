# Source18r canonical case repair

PASS: True. This is a serialization and saved-case restoration repair, with no scientific matrix change and no measured Root result.

Frozen Source18 (`af8b279c9c8edbd287e85275ae90fea07f1bf2fe`) failed at the first physical packet comparison. Native optimize calls and runtime are both zero; no runtime ledger exists. Physical initial/arcs tuples and grid current-control tuples serialize as JSON lists. The persisted identity already equals the persisted receipts, while the equivalent in-memory tuple representations compare unequal. Their canonical SHA values are identical.

The repair returns persisted JSON from both freezes and appends an optional PhysicalDomain to CampaignMCase. The restore helper reconstructs only saved counts/masks/nodes/SOC fractions against the actual immutable graph, verifies the complete packet and reconstructed scientific SHA, and checks the native input key. It performs no producer or BFS. Independent original-row verification remains mandatory.

Final regression validation: 40 passed, 1 solver-parameter test deselected, 37.19 seconds. The separate independent metadata review passed 25 checks. Root owns complete solver parameter readback and any authorized measurement.

Owned files:
- `D:\v42_svr11_epoch18r_20261011\v42_may_campaign_native90\m_model.py` — 1f4d556081e0814b7af1378635e2174fd2340ba245d9c67f661c0f02245405c9
- `D:\v42_svr11_epoch18r_20261011\tests\test_v42_b3_current_c3a_restore.py` — fbfb9d04e276b3ae9db26ba9d9c4db90de39326852cb8438edd189b03710151c
- `D:\v42_svr11_epoch18r_20261011\tests\test_v42_canonical_physical_restore.py` — f9b1a69d35cdf6fd39c898cf7b77dd2a11cbabac3d06c39fd74eced6161d0097

Saved-case rebind rules:
- Preserve failed Source18 source, launch seal, failure receipt and all Native0 output bytes. Create repair attempt records in a separate root.
- Use saved original FULL, C3A baseline, Dense selected matrices and their exact domain arrays/axes/plans/certificates. Do not recreate the original model.
- Rebuild graph only from the immutable current input bundle. restore_physical_domain(proof, graph) checks schema, full saved scientific state, reconstructed state and exact native graph/battery/initial/site key without producer or BFS.
- Set case.physical_domain to that result before verify_case. Independent original-row and stage proofs remain mandatory; saved producer PASS alone is insufficient.
- Rebind record paths and active scientific source authorities to repair output/source. m_model.py changed, so transport source authority and case SHA must change; original/C3A/Dense matrix and domain SHAs must remain identical.
- Use raw_point=None and case.point=None; read no old B2 incumbent, UB/LB/gap, candidate or MIP start. These saved matrices are fresh failed Native0 scientific artifacts, not old optimization results.
- Separate prior original-build wall time from repair restoration/replay wall time. Zero Native calls and absent failed runtime ledger do not establish Root success or a performance estimate.
- Freeze repair source and proofs before exactly the root-owned authorized fresh U4/Full measurement. Perform complete numerical parameter readback there; campaign remains HOLD until latest Root<=180 gate passes.

The JSON receipt inventories every frozen failed Native0 output file and both frozen launch/failure records. It records original, C3A and Dense scientific identities without importing repository code or loading matrices. Repair Root performance is UNMEASURED; campaign HOLD.
