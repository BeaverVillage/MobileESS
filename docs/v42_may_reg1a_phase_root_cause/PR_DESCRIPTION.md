May B0 showed 12 `transformer.reg1a::A` nameplate-current exceedances while voltage, line current and aggregate transformer kVA remained within their frozen limits. This diagnosis reproduces the four affected days exactly and adds compiled PCC wiring, terminal-conductor P/Q/I, regulator state, downstream native/PV/AIDC/capacitor partitions and denominator provenance.

All 12 PCCs and their service transformers are correctly ABC-connected; measured PCC P/Q is approximately balanced. Native IEEE123 phase A is heavier than B/C and downstream losses increase that imbalance. H1 is NOT_SUPPORTED, H2 STRONGLY_SUPPORTED, and H3 NOT_SUPPORTED for the frozen current measurement/nameplate denominator. The 693.930612 A denominator is 5000/(sqrt(3)*4.16), distinct from CTPrim=700 and compiled NormalAmps=763.323673 A. The 12 frozen nameplate-policy exceedances are preserved; source NormalAmps exceedances are zero. No PCC/rating/tap/PQ/queue/model/margin changes or B1/B2/B3/M1/A2/M2 runs are included.

Four daily 96-slot primary reproductions and an additional 384-slot passive terminal audit match PR129 V/current/current_pu/kVA/tap arrays with zero numerical difference. The supplemental strict algebraic conservation check fails at a maximum 0.121177 kW/kvar; its FAIL receipt and finite-convergence nodal residual explanation are retained transparently. This does not change the measured 421.870092 kW peak native A-B difference. No solver retuning was applied.

Validation: full pytest and exact PR129 byte/source SHA receipts in TEST_RECEIPT.json and VERIFICATION.json; git diff --check. Detailed Korean findings: docs/v42_may_reg1a_phase_root_cause/FINAL_REVIEW_KO.md.

검증: full pytest **1362 passed, 1 inherited warning**; PR #129 기존 4525개 파일 byte/SHA 동일 및 외부 frozen source SHA 검증 PASS.
