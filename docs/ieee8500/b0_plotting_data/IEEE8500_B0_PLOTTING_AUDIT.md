# IEEE8500 B0 plotting extraction audit

**IEEE8500 B0 PLOTTING EXTRACTION: PASS (active scientific LINE domain)**

The package was extracted and independently verified. TOPOLOGY_LINES=3703; ACTIVE_SCIENTIFIC_LINES=3698; INACTIVE_TIE_LINES=5; ACTIVE_RESULT_MATCHED_LINES=3698. The required active-line coverage is 100%. Per the user's clarified gate, five source-disabled tie lines are retained in 01 and 05 with rho_line_max=NA, loading_status=INACTIVE_TIE and plot_enabled=FALSE. They are outside the planning metric domain and do not cause extraction failure. All other mandatory gates pass. No missing loading was invented.

## Selected B0 and model authority

- Exact accepted result: C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\B0\FINAL.json
- Selection: latest archive INDEX final_DA.B0 explicitly selects the r2 FINAL.json. Its status is PASS. Earlier production FINAL and downstream B0 copy do not override this release. Candidate comparison is in the manifest.
- Actual model entry point: C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\Master_IEEE8500_PCC.dss
- Model chain: r2 common8500.py -> numerical_preflight electrical_engine.py -> stress_common.py -> screen_source_grid.py -> screen_compatible_b0.py -> operating_point run_b0_screen.engine -> PCC Master -> unchanged native source/Master-unbal.dss plus frozen IEEE8500_PCC_Overlay.dss and PCC_BusCoordinates.dss.
- B0 also references Source_1.0400_Vreg_123.5.dss -> IEEE8500_Compatibility_Adaptation.dss, B0_RESOURCE_OBJECTS.dss and the engine's additive MESS zero-control load definitions. They do not change line/transformer connectivity or bus coordinates.
- Native Lines authority: Lines.dss and Triplex_Lines.DSS. Native Transformers authority: Transformers.dss, Regulators.dss and LoadXfmrCodes.dss. Master-unbal uses LineCodes2.DSS and Triplex_Linecodes.dss. It does not redirect the balanced Master.dss, Lines-Geometry.dss, LineCodes.dss or the alternative LoadXfmrs.dss. No different variant was mixed.
- Local files used here were hashed and matched to the latest archive per-member manifest. Native DSS files additionally match the canonical extraction source_manifest. Planning coefficient files additionally match ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST. Production release binds that preflight manifest and LAUNCH_INPUTS binds the final exact AC summary.
- Archive: C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_ALL_RAW_RESULTS_20260912_205138.tar.gz. Declared SHA256: 9c5519cd182c803b75c305267ed44d617d696f8a8f7c91614897bd52e30ada6e. The full 26-GB archive was not rehashed; this task verified hashes of each local source member it used. This distinction is retained in the manifest.
- Requested older 163035 archive present: False. Its historical INDEX is retained as provenance. The later 205138 final-authority index supersedes it.

## Metric and critical time

- PRIMARY metric_scope: PLANNING. Only stored COEFFICIENTS.npz['line'] baseline values are read. No Jacobian evaluation or reconstructed model prediction is performed.
- rho_line_phase = abs(stored normalized complex line current). The stored engine writes I/NormAmps, with actual ratings in AXES.json. current_A = rho_phase * the stored rating is a plotting-unit extraction, not a power-flow calculation.
- rho_max(t) = max over all stored LINE terminal/conductor axes; t_star_B0 = argmax over the 96 saved intervals. Ties use earliest stored interval and then first stored axis. Phase aggregation retains both terminals to match the objective. conductor_label preserves t1_node1, t2_node1, etc.; terminal_of_max_loading is the numeric terminal. phase_of_max_loading gives native primary phase A/B/C using the frozen secondary-to-primary map for triplex lines and explicit terminal nodes for primary lines. Ground node 0 is excluded. The 04 phase field remains the exact terminal/conductor key; its added terminal/phase columns describe that individual row, without a second aggregation. No split-phase node1/node2 is arbitrarily called primary A/B.
- Critical interval: 31 zero-based / 32 one-based.
- Interval start / critical_timestamp: 2025-05-21T07:45:00+10:00; end: 2025-05-21T08:00:00+10:00; local time: 07:45 fixed AEST UTC+10.
- The forecast timestamp at index 31 is 08:00 interval-ending. The binding explicitly defines slot [07:45,08:00); critical_timestamp consistently records the start. No Korea-time conversion is used.
- Critical line: Line.tpx21459660c0; phase-axis: t2_node1; native primary phase: C (frozen witness, not inferred from name).
- B0 rho_max: 0.8487691403696187; current magnitude: 132.40798589766052 A; current rating: 156 A.
- All-96 stored planning baseline vs stored AC anchor agreement and phase-to-line aggregation tolerance: absolute 1e-12 p.u. Final accepted controls and all 96 accepted AC slot maxima agree with these baseline arrays.
- 08_B0_stored_AC_phase_loading_at_B0_critical_time.csv is a separate auxiliary B0_REPLAY_AC extraction from the frozen ANCHORS.npz. The final production exact AC file stores slot extrema, not a complete line-current array. This auxiliary file is explicitly not relabeled as a fresh production solve.
- LINE terminal P/Q was not saved in the selected line-current authority. P_from_kW, Q_from_kvar, P_to_kW and Q_to_kvar remain NA. No electrical P/Q reconstruction was performed.
- emergamps is copied only when an explicit numeric literal is available in the selected element definition. Unstored defaults, inherited or RPN-derived emergency values remain NA with an explicit status. They are never used as the planning rating.

## Geometry and completeness

- Active model buses / output coordinate rows: 4912 / 4912. Native coordinate authority includes 17 unused bus names; these are listed in the manifest and omitted from the active-bus CSV.
- LINE elements: 3703; stored active result lines: 3698; coordinate-mapped lines: 3703; coordinate coverage: 100.000000%.
- Branch rows: 4930; types: {"LINE": 3703, "TRANSFORMER": 1214, "REGULATOR": 12, "REACTOR": 1}.
- Three-winding native service transformers have both secondary terminals on the same base bus. One geometric transformer segment is kept per element, and every raw winding bus is retained in winding_buses_raw. Regulators remain a separate type. The source reactor is preserved.
- Unmatched result lines: 0; unmatched full-topology lines: 5. Active-domain join coverage is 100%.
- Disabled, unmatched native tie lines: line.v7995_48332_sw, line.wd701_48332_sw, line.wf586_48332_sw, line.wf856_48332_sw, line.wg127_48332_sw. Their disabled state is explicit in Lines.dss and saved lines.json; no phase rows or zero-current rows were fabricated.
- Coincident XY points across distinct bus IDs are legitimate source geometry, including PCC buses co-located with their host. They are not duplicate bus-key errors and are not displaced.
- Substation SourceBus raw: (1693780.0, 12277577.7570982); plot: (1658034.03980939, 12277577.7570982).
- Horizontal reflection: True. x_plot = xmax + xmin - x_raw; xmin=1657764.13740939; xmax=1694049.9024; y_plot=y_raw.
- Raw coordinate strings are preserved verbatim. Reflection is only a plotting transform, not a scientific topology change. No rotation, layout generation, geometry interpolation or source editing occurred.

## B3 future contract

- 06 is header-only, with no data rows. Future row constants: policy=B3 and reference_critical_policy=B0.
- Join at the same B0 interval 31 and start timestamp 2025-05-21T07:45:00+10:00. Reuse identical topology, coordinates, active-line mask and one shared scalar color scale in both panels. Never use B3's own critical time for panel (b).
- No B3 loading was read for extraction, generated or estimated. Only B0 candidate records inside campaign directories were inspected.

## Execution and preservation

- SCIENTIFIC_EXECUTION_COUNT = 0
- GIT MODIFICATION COUNT = 0
- No optimization, OpenDSS invocation, compile, power flow or ML execution. Existing project Python was read as text only.
- All task writes are under IEEE8500_PLOTTING_DATA_B0. Raw result/archive and Git files were not written.
- Before/after SHA256, byte length and modification time of every tracked source: unchanged. Archive size/mtime: unchanged.
- Artifact Tool authors the CSV public cell values with exact read-back. Bundled Python independently reopens CSV files and checks phase maxima, reflection, NA handling and the empty B3 schema.
- Review 07_plotting_validation.csv: ACTIVE_LINE_LOADING_COVERAGE and INACTIVE_TIE_PRESERVATION are separate mandatory PASS gates. The optional preview was omitted because matplotlib is unavailable in the bundled runtime. No OpenDSS or other scientific software was invoked to replace it.

## Source SHA256 inventory

| Exact source path | SHA256 |
| --- | --- |
| C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_ALL_RAW_RESULTS_20260912_205138.tar.gz_INDEX.json | 0b7e90735ae3724e1fdaca1bdc1c04db1d5a58f2e5336b98164a18e0f8b57645 |
| C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_ALL_RAW_RESULTS_20260912_205138.tar.gz_FILE_MANIFEST.json | c1f0f8683efdf469a8ca87eaa6e4a833e4d598156879f482ba2a80f2c85b1fa3 |
| C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_RAW_RESULTS_20260912_163035_INDEX.json | d84da8e0a126e924d0a66cbc60f3be285302a58132e389a1d76d64889d3358df |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\B0\FINAL.json | 4fbb1883bd421b6aa61599bca051fa63bd5139860fd6b3c42d6590eaa5fa12a3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\B0\exact\AC_VALIDATION.json | ce311176e9cf37a283fd92181e79eb0fb36bb6dc222f841e159d719ce0b2ea3d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\P1_EXACT_B0_WITNESS_BINDING.json | 32f1d4d86411b84b279959a30a50cb5619f2741a7487c8f6ccb67dc5b0bef775 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json | 86d91887379cbb7b21e7e30933ff0532cc50a21416c1984c7c449aec21a535cf |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\PRODUCTION_RELEASE.json | 5f8f48e2dc26c3b135d2cfec0dcf7d937b81d79aca2440ab15de6f874bc678c4 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\LAUNCH_INPUTS.json | ab59959be9e780c3cae3a353b26f25be0646b880a202a34cc50668d2c9670984 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json | 313e6c163c07a21fbd5821336f4f3edbcee47598b5eed32624357d5574c40f12 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\ELEMENT_STATIC_ALLOWED_CHANGE_AUDIT.json | 0458003ae87f1695cec0d309db8d8659e55e65cbfaa9e69b81ec508bbf771f65 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\PCC_OVERLAY_FREEZE_MANIFEST.json | 0f33c5dd75b83a99473ddaa399e20f3c35bdf986e73ac52d95f40d9974feab60 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\PCC_OVERLAY_STRUCTURAL_VALIDATION.json | ccc58db1e66904529300b758dc8ad64ebfbf481866931bf7dc392f1a67e1b16c |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\FINAL_IMMUTABLE_TOPOLOGY_AUTHORITY.json | 564f4d6a369111ddade2edefeac81db82c8773f51d8449b10a764a997f99e3f9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\audit\compile_audit.json | 831a29b94b25047737e6cd4fdbcaf6aef8b82999669f53cda47e9ece75bf9907 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_operating_point_20260911\measurement_validation\INDEPENDENT_MEASUREMENT_VALIDATION.json | 2941c0844a344256d4db065543a75c5a843a4247dc3453633e1527c0108606d2 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_stress_calibration_20260911\IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json | 83d72b85e8804b09fdddbfe83b3cb57ed960283a54d575b82eafdcea7086f7f3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\common8500.py | 8d3934f9e876c9dbed86c941f76175af10500b84e752d2a3e8805b8b4b4ddfca |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\electrical_engine.py | f06a4418cc95ccc22f5fa67c852ad2027202638681cf0b75a075b35c2bc48845 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\numerical_coefficients.py | 24abd43ac6571cc9e89703f57aa83f9708450627aa3d5e7acdc41769d945ed76 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_stress_calibration_20260911\stress_common.py | 6e0bcec013863c7abb17fc708cff58460f400946696c7b4f6f32b2aa76fb2e5a |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_source_grid_compatibility_20260911\screen_source_grid.py | 305aa70bdfd0c504d9bd614ffa63d817fe346bc8aa8ffbde3092dde66ba5dff1 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_production_compatibility_20260911\screen_compatible_b0.py | 7bc637a196183485142cd9ffc17a8583f1ea5ed7063b3cb64d7a509d635ba599 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_operating_point_20260911\run_b0_screen.py | 8541567992d4fd1d6c69f3071561b537ce41c62c3d0cb63a4d6a1bb19b87b8bc |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\Master_IEEE8500_PCC.dss | 364948db422b808ab5075475fa4c7628817f2a115deaf843b0a848699923b437 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\IEEE8500_PCC_Overlay.dss | 0dfc0bbdbdb269fda18d88860d99fce13c28a6aca9ad1b0265c5b9a924fbb5de |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\PCC_BusCoordinates.dss | 9a35bfb1c1a21987dcc6db15a2711ae5d360d461361cc978ebe2a92094b3f27e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_stress_calibration_20260911\overlays\Source_1.0400_Vreg_123.5.dss | 38fa8754ec9af5ab817f2a0cc2b8e1107d74bf74e11d2704eaa8f3be8af6760d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_production_compatibility_20260911\IEEE8500_Compatibility_Adaptation.dss | 51f385e459f19fc925e292e7a693b38219d59c28d7d1b43136735fa0461512c3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_operating_point_20260911\B0_RESOURCE_OBJECTS.dss | 98799797c4d355b5b48fdc9aabeec6b00f658b9dca1f2c41e5d6ce00951a1540 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\audit\source_manifest.json | d14ec64e936fabc206b87faba45ac782da2f94e41c1ec420ccc3ddd0b5af3553 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Master-unbal.dss | 59bdb5e9da4bf3c063d7efdfa6b9b1e537d7786533fefa0f2c470cfb2e12622b |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\LineCodes2.DSS | 3fec9199a41696a758eaff7065f86a89477f70898b1bee3295de9c74f154121a |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Triplex_Linecodes.dss | 7dfbfc23e19d8930c9e5ac3302bd9e8e9d52aee9c333e3fc80422f15752a886d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Lines.dss | 460eb5e8179bda1926d0d70cf4fc9d8bdd29ab4dd9a101941730749f8a4a663a |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Transformers.dss | cab397f65f5de08c4d82cf794c03c432b404cd5db7db37ff827869db8344b708 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\LoadXfmrCodes.dss | 213a3c0478b33a4cb95d82d40e076d1c1ec19b22033e4aa03e6dcdd8b92fa8f9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Triplex_Lines.DSS | abf45521bc05a7f9d5c3fa4c94c4f24f7ea9bc984e7086b303ae4a143d77971d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\UnbalancedLoads.DSS | 72705438556764981d430a9148c84b783f76b977911a2284ffe9295740bddaba |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Capacitors.dss | cc05836176a6715b121619079eb6cef96e77468a3368c8ed44815f2e9d684dcf |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\CapControls.DSS | 562818b4d905f391e88ed58efcd54150d4296d6cfb355f8abac32c969a290348 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Regulators.dss | 041f353f55076feaaf751bbb20551226f8727ddfbdfc5101cf1b1f222da38617 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\source\Buscoords.dss | aa3d71873e595578f8c952dffd16b8cf74d5d811da40e16db8a4f0c72abe8c32 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_B3_production_20260912\B0\FINAL.json | 4fbb1883bd421b6aa61599bca051fa63bd5139860fd6b3c42d6590eaa5fa12a3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911\B0\FINAL.json | 4fbb1883bd421b6aa61599bca051fa63bd5139860fd6b3c42d6590eaa5fa12a3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\AXES.json | 25d8a24dac1f63c739d5b1d58fb489fec7a8aafa12fcfc94022cdc6ffb83628e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\B0_REPLAY\ANCHORS.npz | 6e4743be2382f0ea5b82f5ab34cefbf4ccc27cdfbf16c2eaec3babc846729589 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_v41r4_production_20260911_r2\B0\exact\CONTROLS.npz | c880e4969f3c3c4b40c98cbb106f3e96b5d3c8ccf7f4e1155b6f102d159458dd |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_00\COEFFICIENTS.npz | 221756360b5704b3831d9334c77a8497c96ecb9c328eb13787e4aa0a440c93f2 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_01\COEFFICIENTS.npz | 54c0701854be7723f134e425aa9ea65011107836e95d3aaaaf1e86fe1e9b5469 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_02\COEFFICIENTS.npz | 5283592941e028a9313da765dfa2050d7226f57970d059eada9f03f13bf4a218 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_03\COEFFICIENTS.npz | 903027f5f65eb1aff978f3055ca2e40d5dac16b36e4135ca6724c9660d8bac34 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_04\COEFFICIENTS.npz | ef4a75cea77877fd69a06009d176cc7ccd6bcfe3d8438314d0bc6669beafaec1 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_05\COEFFICIENTS.npz | e0ed7e4e3da7b531383e58035cb81c04d50f20ec3fb31ed8ed23b30a731e2f6d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_06\COEFFICIENTS.npz | defb251dd9ee2dbbf657d0dd41ec08f437f3fa395221518c959d617c19552f9c |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_07\COEFFICIENTS.npz | def6c2ce44188ed6405fce6f11b0ec570b7916de1595bcf1db41865c955ad9bf |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_08\COEFFICIENTS.npz | 6299cffde67689e551db2442fac9694c3d1cb7ff50b41b2353b51f1e851513e0 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_09\COEFFICIENTS.npz | 9ce7fa8c2ecb10560819f031577d4b8bfce56399e246cd9e1eaac5d14729c4b0 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_10\COEFFICIENTS.npz | 56e32db9619f9c45fdd716aa48abfc7fcf2fab7dcc7b687b96cf6d622bcc0f75 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_11\COEFFICIENTS.npz | b86c9a61e4edb56f109ae61ff38b199bf0409131f0a1fe8b64d7763cefa70dc5 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_12\COEFFICIENTS.npz | 096db4489c60e5928602c6504c918c678cf1adfa30c3fc58b49d52795161f86d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_13\COEFFICIENTS.npz | 33073c0db274c12e27ba8da8963ae9178d02801e523fd4cb1ceb61df04316baf |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_14\COEFFICIENTS.npz | 5a442f1f8a45b017d27fd7af7fc8db7879e524b91210d8b8e3da781844e225c2 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_15\COEFFICIENTS.npz | ce07db49eb7b823bf0ec1b3afab353e30c299984c26058cc86cade6438704383 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_16\COEFFICIENTS.npz | fa6c0ed3170456f935332fd185be768b3b029854a4452e5dbb57e891b6fefb03 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_17\COEFFICIENTS.npz | 73ce77dcc96897f61af97e6a9df57cc8d5fb82733b7280db5af47a58a63f7a1d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_18\COEFFICIENTS.npz | 17adb657042d8b38609714681bba05bd5fdfa26e69be7a4b8ae9225e3af7459b |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_19\COEFFICIENTS.npz | 55a4075ece56fda15149e4c044138d4cc8d48482e04d5ec073ad2a3f494d53fe |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_20\COEFFICIENTS.npz | 94c6f6bc35b804b166a22beadcf11e20c845aa6ed246eb8978f49c3e790815c7 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_21\COEFFICIENTS.npz | 162684f999e9d3a027d9af44dbd512b032b10261d9d02946fe4593993be82a7d |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_22\COEFFICIENTS.npz | 4d453de370ed39b5c7721ae6e49fca1ca90eae7e4202051344a066b7c976aef4 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_23\COEFFICIENTS.npz | 959a1cc92c6510c4ff84fa17823c4c4c1e02d0dee32a2db1104090d43c0fa296 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_24\COEFFICIENTS.npz | 3f6382831fc30857175286c6beaae8312981ba16ebc948e84a16d84e8433817e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_25\COEFFICIENTS.npz | 8756ef99146cfc2b00bd8aa769968587574a75f82c372e40d3f048900615d2b9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_26\COEFFICIENTS.npz | 54e9e0456769ae75b6fe808c253e4d0b5ab98eafbc57e2de2bfba919767f52d4 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_27\COEFFICIENTS.npz | 76c2ff4439263138d0fb9ea1d5eae4b6a8ef36dcd2b3804ee9dd6fefa4c9ba81 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_28\COEFFICIENTS.npz | 162640b6e9119a193501d696636af95617ec8d126557643f78e76fdc49b1ea04 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_29\COEFFICIENTS.npz | 4cd559b633b42850342ce767d572794d2aad3f741959f7ace7335f76a778c707 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_30\COEFFICIENTS.npz | 7f4b734ba7d84f6a807098d99558a4096f459928b46a4d68ec137b1957cdb0a8 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_31\COEFFICIENTS.npz | a3256a63770753c97244e1266060fe8a15affe14ad383680850803ed870284cf |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_32\COEFFICIENTS.npz | 392818a13502aa27f2a3bdea2a97bcb62e8ab379d1d829fb59164980767e7b4b |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_33\COEFFICIENTS.npz | 8d2afc277b7ef9fd335a0e3e4d090604d399e5c71de03524d87401321ddc6831 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_34\COEFFICIENTS.npz | 4261317648dcd1772b8f30922d4c09d6f8c1af9091a05e080082e426c5d6b310 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_35\COEFFICIENTS.npz | 2bebf8c7688e1cf714d4b09626ac7a99b5895c20e0262d2feab29a85af888a65 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_36\COEFFICIENTS.npz | 60d586b3e2469ecdfb008430df13ec18247cf9e5684f620eacbfc5c302eebfe0 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_37\COEFFICIENTS.npz | 59cced82c664825ec4e2b8060728e91ca29f192f6ef331cc597e3fd1567caff9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_38\COEFFICIENTS.npz | 616f3077303935006caeb3969c554c5b7f9fc1c2e6a2344b4fa1b6c38b2d92dc |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_39\COEFFICIENTS.npz | 579c47fe2cb5f8a7356fb0998f3987fa861fd99417bddf5939e134f732dafb3a |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_40\COEFFICIENTS.npz | 0528932dc8c2ecf784a24501e61484497db7ccec6b48ae91e658e88c63a00c5e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_41\COEFFICIENTS.npz | 8dbc7531dfe03d2e49c7dfb5050fbbd1191fb7ab2d6d3f9d2b1b367ed12bc40c |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_42\COEFFICIENTS.npz | e74b36b47a204747cb8222210cd26a500fb662e8a21112b9167f51680ac630d6 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_43\COEFFICIENTS.npz | c6880d2115931a89b70f130c0f0ed05bffd0a5827d741ee9011d5f2ee56de3fe |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_44\COEFFICIENTS.npz | a3f9c7cf262270c8f1b2dc25981acf24a339850de4178d7134f92a79c02d15b8 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_45\COEFFICIENTS.npz | 58f38a636eb0abe8dd5bd621370d5018a59f7ebb3b099d2e777bbd300f570e3a |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_46\COEFFICIENTS.npz | ec527c4318e0ca82c3e30aa73c0f49e4fa6c9ab5bcc7608dd440225b9f477bec |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_47\COEFFICIENTS.npz | f4108f7199ffe0abd244d0a62def612b63eb656523719012767227875198e593 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_48\COEFFICIENTS.npz | 70650ee1f9d5267a0b9c6e7f12c629125a795a7077dbb5ea74dd87b56ffe90bf |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_49\COEFFICIENTS.npz | 6d1d97b36ddf7700f1047bd67b09f87ffa943cdf5eb9f21230171b3a40143cf6 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_50\COEFFICIENTS.npz | a77fb17f4e0c0e56bd1d0788bd2ab8a607c1a713eef7a73b589bfe67dae942d1 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_51\COEFFICIENTS.npz | e7bffd1212aea82b64b5ce32af1ded53a718ad4ecf381dc2eb5b17ac0010dfcc |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_52\COEFFICIENTS.npz | 6dd31cd2d844c7afb7fade34a5d65b2d744e76f6f667dd7d0cacab6ea1403a18 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_53\COEFFICIENTS.npz | 240e20cc07a660af1aa69b1ddac9d3b2fadacf995b62801222ace86cf5ad0255 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_54\COEFFICIENTS.npz | a2cdec0ea6c961a877405eab40c152452bf078175e89518308a6c1a96544ec2f |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_55\COEFFICIENTS.npz | 53de34ab907a54dd0d9bf16dce00c75bfe18874aa81557101457974a399ee512 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_56\COEFFICIENTS.npz | b1be8c1bd47702db027daefe1e24d8985c7639807f7bf750b01fd1952d4f91af |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_57\COEFFICIENTS.npz | 750cebc2780c4066997733a3f1a78f00806bbc51a4f3ad9bd0f5c0c280209141 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_58\COEFFICIENTS.npz | c40b4a2ab25fa48e745fa3947121b096dfe7cae309ca10182d505e159cb2e359 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_59\COEFFICIENTS.npz | f6733c3920c989b574c92637c63797d9a8bdf10a792fa21fa4e486dcde3ff893 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_60\COEFFICIENTS.npz | 29fedd14dd780a9c839a939fef0cabb92fdaa6552e3f5b7db038763481281016 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_61\COEFFICIENTS.npz | e0ab23cf9a5f2914f30e4cf32bdc6260eebd8b230bce695106768959e9f849db |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_62\COEFFICIENTS.npz | f6427848ad9f5e5b0a48cc872f0823e885b9178c6fc421d4b8c406e64660cba6 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_63\COEFFICIENTS.npz | 12a30608c5cf8c1a6ca172eb9f96026ceae27d58575cbad0b6eac9dbd182ca05 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_64\COEFFICIENTS.npz | 75d833831ab2b405621b53bb3758e481f58c1fe30df67c619a7bb8b904bd4eba |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_65\COEFFICIENTS.npz | 150260c87a7354e49d17178aa5b4c35c977f973781ab5a45a7f549160ee0ad1e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_66\COEFFICIENTS.npz | 29fd69477655d462a4976d2241560ddc56176faa5efc275a4684d1e3bdef3d73 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_67\COEFFICIENTS.npz | 8f9738696092f03f343c696f16bebbac7fae5eb5f97c7e967f6d3367b321c64c |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_68\COEFFICIENTS.npz | e56e4cf491cf28c3cadfd35b48354dfb7cd4cb29ea45810361617510c8087db3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_69\COEFFICIENTS.npz | 25314403fc5e64470a4a462d256a051bc5650a40f5c261b5edf6af518252d999 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_70\COEFFICIENTS.npz | c9712fd3d456dee5cf0ad522d28e7c0d76c05623b02f0885d7b15bd1d95686df |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_71\COEFFICIENTS.npz | 7bb1c9404e5d085d7f6ec72d130ba942b04d943edd441576b73ffdde816fccec |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_72\COEFFICIENTS.npz | a79e4188da932220fad1d9973b6f5bf5bc046e8b46cbd1b4ec14a72990abb45b |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_73\COEFFICIENTS.npz | 302abebdd4f91e8dee54f016172645a0b0d1bee09f44d12f656e18d121ba91e9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_74\COEFFICIENTS.npz | d95439b5e6c25019f5af2de028144d4dcd1eebe58150402a5eec6eebbd9f1ce5 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_75\COEFFICIENTS.npz | 64af8a564258e5c562aa73026d983c973f1556bcff3c74437d27f4ab470466b8 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_76\COEFFICIENTS.npz | e7432177eba64db90c0f571c53daa59dfbd30e0681bc4c0eaff9acd70164da2f |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_77\COEFFICIENTS.npz | aae535d71365f4424a0342b6d23971dc3a5f6c8e27635a61127433ade6b8b50f |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_78\COEFFICIENTS.npz | ba072c3971302d6fff11d66022c848be9ca8c0b2e29d1cf48b534c2e41e2b5dd |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_79\COEFFICIENTS.npz | 6f8e61663c9324372c10f1e2d0f4a92c67662b07b9012955048f134b5d818322 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_80\COEFFICIENTS.npz | 5a0a6a11091f871260b6434cacd34e6c191dbf1d1ec7d76ca447dfbf6dad2c7e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_81\COEFFICIENTS.npz | 95f6cd4842f09960556003ec0f5ef64e6b484f1b41bafc699e21b0fb60cff9ad |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_82\COEFFICIENTS.npz | 97e027371282b2b616b64980092f4cd898fe1b1ed72a2b38bef1bc925bfd6eb8 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_83\COEFFICIENTS.npz | 1b6811d47a32bfa1758c16eea8359dc070db8ac97a818fc29db278a3ccd8cbfc |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_84\COEFFICIENTS.npz | a698851ee409c6192a83e248b0b2fc400f2ee552324c8b410de8097c0b4cc380 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_85\COEFFICIENTS.npz | 9509ecd63b35b9341643939e1811052f24446ff60a4fabf7b02e15eb2351cad9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_86\COEFFICIENTS.npz | 8e6eb96bf75bfcbe787235a926e62d5913bf46993842a2a4b665ff4f08b5abe1 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_87\COEFFICIENTS.npz | f431df414bc8ae1ac213e635d864ebe94b0657feabd56b3717a9b25c224facc4 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_88\COEFFICIENTS.npz | 2b3f78741d15d791646823f62a25ff893e94b80aa62bd9291d09cf867aa95fc6 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_89\COEFFICIENTS.npz | 3df023d6da55411feadccf0ea51ed9f92c6d4c8958f3fa105aeb97f829609fb3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_90\COEFFICIENTS.npz | e78a22dc013bd2e2618ee04580962a0e0f2c79bc50827e95df8da4f19556020f |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_91\COEFFICIENTS.npz | eff272ce1b2b02d67b8fcbc63667668d8ad65df0b4ba6c8acf97dfdd09b9b68b |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_92\COEFFICIENTS.npz | 3777ad0ce61fd5d678d76043c49ebe832ecb8ab27d19516da68dc85c9f846aab |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_93\COEFFICIENTS.npz | 73dbd76a703c50195a77a912d6115eebecc2c8b3f20c9b2016669e770be21522 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_94\COEFFICIENTS.npz | ccc4b8680b153488fb3d404e53829a6d168598917791e6adbc9f6eaf70ccd92e |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_numerical_preflight_20260911\coefficients\slot_95\COEFFICIENTS.npz | 1e0e98c1ea300162a1413d233791989e86e7eee3589c2b28d4b913a480ddf3b3 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_operating_point_20260911\D1_AEMO_VIC1_FORECAST_AUTHORITY.json | b308f52f1e85364cb8bc98f9cfb5deaf53026fe34fd6a7dd522a58ad0c7f32af |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_operating_point_20260911\FORECAST_CAUSALITY_AND_INPUT_BINDING.json | aaa43d342403e0f20bb1fd60453f892cbadab7c99f1e974da158a93d183243dc |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\audit\lines.json | bff0ab47245e05dfc06b0b82963f170285be9ee4f1ff8ee7f874d3c9b8ce81b9 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_scalability_20260910\audit\transformers.json | 8da43c940ef16a978b6167a724d0f26a136e2aa8e26444c669be195d6014c9e6 |
| C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\IEEE8500_pcc_overlay_20260911\PCC_GENERATED_TRANSFORMER_AUDIT.json | f19cf3a7d240c4b6f405d1e6ff2f070ec52b533f864075b43f4694f269664b53 |
