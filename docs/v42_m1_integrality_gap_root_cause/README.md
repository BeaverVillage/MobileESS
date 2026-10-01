# M1 integrality-gap forensic investigation

Exact base: PR110 `90efccb2dbcc1ab4557cedcf04ef479a225d4e47`; this is an independent successor of PR110, with no PR111 result or formulation inherited. Root cause class: **CASE_E_INCONCLUSIVE**. No new production formulation or cut, no production M1 or downstream run; M1 accepted=false.

Independent original-F3 coefficient/root recomputation identifies T_ACTIVE=[66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95]. P1 dual mass fraction=0.999999848163; line.sw1/A binds in 96.6667% of active slots. Largest ten slots hold only 36.5895% of dual mass; the shortest 90%-mass interval is 66–92, so a long late block dominates. All ties within 1e-7 are recorded, not only a canonical face. W_ACTIVE=[66, 95], W_BUFFER=[58, 95], frozen before new solves. The old 40–46 incumbent-root score is not a root-dual criterion.

Root unit energy is about 1080 kWh at 66, then nets about 320 kWh of discharge to terminal 760 kWh. It averages 8.1667 positive sites/unit-slot with Q dispersion 0.754982, compared with one incumbent site and Q dispersion 0.000000. These descriptive differences motivate exact tests; they alone do not establish the gap mechanism. TERM_RELAX rho=0.544918814938, decrease=0.026930645263; terminal equality material by 0.001 criterion=True.

- R_ROUTE_ONLY: restored 67316, raw BestBd 0.571849462550, certified global LB 0.571849462550, gain 0.000000002348, solver partial upper 0.669614731421, COMPUTATIONALLY_INCONCLUSIVE.
- R_ACTIVE: restored 67436, raw BestBd 0.571849462550, certified global LB 0.571849462550, gain 0.000000002348, solver partial upper 0.669614731421, COMPUTATIONALLY_INCONCLUSIVE.
- R_BUFFER: restored 85744, raw BestBd 0.571849476968, certified global LB 0.571849476968, gain 0.000000016767, solver partial upper 0.669614731421, COMPUTATIONALLY_INCONCLUSIVE.

- P_FIXED_ALL: validated original feasible UB 0.669614731429, solver status 2.
- P_FIXED_ROUTE: validated original feasible UB 0.591281263433, solver status 2.
- P_LATE_ROUTE_NEIGHBORHOOD: validated original feasible UB 0.669614731421, solver status 9.

Best independently validated full-integer UB=0.591281263433, source=P_FIXED_ROUTE, gain=0.078333467988. Best certified reference/partial global LB=0.572212503944; remaining implied gap=3.22498964%. Negative certificates available for every main arm=False. A 600-second stalled BestBd is computationally inconclusive unless a partial feasible upper within 0.001 or tight optimum interval proves nonmateriality. No failure to improve UB proves the incumbent globally good.

The same-route improvement removes 80.422666% of the retained UB-minus-S2 certified interval. P_FIXED_ALL reproduces the retained objective, while freeing original binary charge modes and continuous dispatch yields the new UB under identical routes and physics. This directly proves retained-incumbent suboptimality of at least 0.078333467988; formal CASE_E remains because required partial negative certificates are absent. It does not establish a weak mode LP hull or exclude a remaining formulation gap.

Bounded occupancy-integrality checks: 44 PASS. Full tests: 541 PASS (one inherited log1p warning). Exact default F3 identity and immutable sources/inputs pass. All runs retain original full grid/voltage/transformer/PCS/route/SOC physics except the explicitly isolated TERM_RELAX counterfactual. Read FINAL_REVIEW_KO.md for 50 answers, DIAGNOSTIC_VALIDITY.md for proofs and VERIFICATION.json for seals. Raw logs, model axis, exact original template and solution vectors permit independent checks. Private input caches are identified by SHA receipts and not bundled.

Resolve the remaining partial-integrality optimum intervals with a preregistered exact bound/certificate strategy before choosing a cut remedy. Preserve the independently validated same-route full-integer dispatch as a future MIP start with its complete 96-slot mode/PQ/SOC values. In a separately authorized experiment, use that feasible upper to seek a tight late-window partial-integrality interval before choosing route, mode or trajectory cuts; keep original terminal SOC and all full-grid constraints.
