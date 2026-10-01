# A1 bootstrap / robust joint M1

Base: Draft PR105 `7ec7006eda9fb5ca7a1952c48391949844aef223`. Result: **M1_NOT_ACCEPTED**. A1 accepted bootstrap: True; M1 robust accepted: False; Problem13 final validated: false.

A1 uses 0.95–1.05; M1/A2/M2 use 0.955–1.045; Actual uses physical 0.95–1.05 and keeps PR105 removed P/Q repair. PR105's 145-row A1+zero-MESS robust infeasibility certificate remains byte-identical and valid for its original scope.

Exactly two scientific groups: MAX_LINE_LOADING and MIN_INTERVENTION. A1 has 1499 jobs / 117 exact classes; migration, absolute shift, prestart components. Native M1 holds the exact AIDC electrical anchor and jointly decides routes, Pch/Pdis, Q, mode and SOC; movement energy then count. Reserve/CC4 are report-only. No fabricated unknown future UIDs.

A1 scientific optimize: 762.7908469999966 s. M1 optimize: 1801.1563743999868 s; P1 UB/LB/gap: 0.6696147314213984 / 0.28011314354280115 / 0.5816801357577633. Independent incumbent physical/grid passes: True / True. P2 completed: False. Feasibility of an incumbent does not satisfy failed P1 quality. Native root: {'status': 'time limit', 'finished': False, 'iterations': 217222, 'seconds': 1600.32, 'bound_rounded': None, 'source': 'native solver log'}; measured bottleneck: ROOT_LP.

The A1 numeric export fix was recovered from FINAL_X on an identical fingerprint with zero optimize calls; see A1_EXPORT_RECOVERY_RECEIPT.json. Native logs and raw optimization/callback receipts are retained. Read-only telemetry supplements root simplex without MIP callbacks; historical RSS stays unknown.

See FINAL_REVIEW_KO.md for 50 answers, FINAL_FLAGS.json for machine-readable results, optimization/model receipts for measurements, independent physical/grid checks and preflight full P/Q voltage interval proof. No A2/M2/Actual/Fresh AC/IEEE8500 run. No scientific change follows measured results.
