# Root thread paths and memory policy audit

PASS:True. KeepThreads1 and currentworker policy. NoThreads2/4 recommendation or run. Source executionSHA `146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8`; currentHEAD `497609b46faa14ea7e32a9483a333ab32fd264ef`.

Actual Native0, initialization, U4 and Full readbacks all reportThreads1. The common model forcibly resetsThreads1 after overrides, Full profile requests1, readback checks1, and ProbeBudget rejects any other value before Native. Campaign DateBudget/native/common builders also retain their existing1-thread guards. No runtime, StageBudget, A1/A2, NativeStop, userA/commonstop or worker configuration was changed.

| Current Source18 Full measurement | Recorded value |
|---|---:|
| Native Runtime / cap | 601.897000s /600s |
| Root | INCOMPLETE; interrupted elapsed528.89s; completionNULL |
| Whole-process lifetime peakRSS | 5.965GiB |
| Whole-process lifetime peakprivate commit | 8.463GiB |
| Solver MaxMemUsed | 3.263167186GB (separate solver metric) |
| System RAM available at Native return | 8.893GiB |
| System commit headroom at Native return | 18.670GiB |

Process peaks include all work in that process lifetime; system snapshots include other processes. A recorded global Commit_peak equal to limit has no Root-specific timestamp. The user’s two-worker≈90% observation is retained separately and provides no authorization to extrapolate one-process Root capacity or increase threads.

PR131 is historical reference only. Its74.080/128.812sMethod2 results were fully relaxed LPs atThreads4 on different matrices and looser precision; MIP Root was208.621s forOriginal and incomplete forCompact at300s. Concurrent jobs were allowed and resource receipts are pre-run instants. Its stopped partial study supplies neither a current controlledThreads comparison nor matched current memory peaks, and cannot override the latest1-thread policy.

Exact source line ranges and SHA records, all four actual readbacks, ledger/runtime, raw memory values, fresh read-only RAM/commit snapshot and primary PR131 references are in the JSON receipt. Native/model/source/config/paging actions by this auditor:0. Campaign remainsHOLD.

Source paths (unchanged SHA256):

- [model.py:37](D:/v42_svr11_epoch18r_20261011/v42_common_mess/model.py:37) — Builder defaultsThreads1, then resetsThreads1 after arbitrary numeric_parameters overrides. SHA256 `5462bfe7670168e4e25b97b79ee4dabacc840105bb7ad7077fc9574d0a9e99ad`
- [engine.py:23](D:/v42_svr11_epoch18r_20261011/v42_common_mess/engine.py:23) — Unrestricted Full profile explicitly setsThreads1. SHA256 `2d9ee94cb78d9dddbc0b6669809ab6a9ee0ca12ea3eb8010fc12514b1be749e3`
- [native_readback.py:7](D:/v42_svr11_epoch18r_20261011/v42_ultracompact/native_readback.py:7) — Root requested profileThreads1. SHA256 `ea3397c8d40c22c401e0846837ef5506bcfd33949bd3779153fd18b40dbe721a`
- [native_readback.py:27](D:/v42_svr11_epoch18r_20261011/v42_ultracompact/native_readback.py:27) — Actual readback must equal every ROOT_PARAMETERS value before Native entry. SHA256 `ea3397c8d40c22c401e0846837ef5506bcfd33949bd3779153fd18b40dbe721a`
- [validate_svr11_root180.py:49](D:/v42_svr11_epoch18r_20261011/tools/validate_svr11_root180.py:49) — ProbeBudget rejects actualThreads!=1; applies actual cap/readback before optimize. SHA256 `e169134b40e4cdf0dcc0c434f80ba7bfa544a5b974449a7dc88aac9b127002b9`
- [validate_svr11_dense_restore.py:321](D:/v42_svr11_epoch18r_20261011/tools/validate_svr11_dense_restore.py:321) — Native0 selected model is built with ROOT_PARAMETERS and actual readback is checked; optimize is denied. SHA256 `3a67136a044ff6bfc32fd5fffdd8c35c1824124df0f1c8af125ff513c7643c97`
- [budget.py:38](D:/v42_svr11_epoch18r_20261011/v42_common_mess/budget.py:38) — StageBudget only delegates measured time cap to parent; thread force remains builder/parent. No edits made. SHA256 `18f885cc4e5014f40c23d3d8a49ca12c7c77c9427982edbbf856838dfdc7d77a`
- [budget.py:82](D:/v42_svr11_epoch18r_20261011/v42_may_campaign_native90/budget.py:82) — Campaign DateBudget forcesThreads1 before Native; includes A and M scopes, unchanged. SHA256 `6626d770f9259df1a7f9aa7bc736ceaae43fbff9cc732b4579080533a083f4f8`
- [execution.py:65](D:/v42_svr11_epoch18r_20261011/v42_may_campaign_native90/execution.py:65) — Campaign execution guard rejects actualThreads!=1. SHA256 `dc30c43f420d72c3e00560066659694e509f125bfe5988e108c24c05d86a4862`
- [solver.py:83](D:/v42_svr11_epoch18r_20261011/v42_native/solver.py:83) — Native original solver forceThreads1 and measured remaining TimeLimit on each objective; unchanged. SHA256 `e24ece8d6557a5b4dccf30c7743d4aad03fc1157a6bdd70210dbc93385f71d4d`
- [m1.py:88](D:/v42_svr11_epoch18r_20261011/v42_bootstrap/m1.py:88) — Historical bootstrap common solve loop setsThreads1; unchanged. SHA256 `31279b85f8a69c41d80e0f19feda3cd2c9d7cd6026f1e8a4c5b046034363bae4`
- [lb.py:151](D:/v42_svr11_epoch18r_20261011/v42_m1_research/lb.py:151) — Inherited scientific builder setsThreads1; unchanged. SHA256 `3560a81f1c61a64c95163fff419e1ed2d13b07227d021a88e7104224e1edede4`
- [controller.py:20](D:/v42_svr11_epoch18r_20261011/v42_svr11/controller.py:20) — Dispatch request recordsThreads1; worker/concurrency policy unchanged. SHA256 `5e3773f37da7ed0350d0bd776b97138facdc155e12d1331122b061cccc233f2b`
- [model.py:8](D:/v42_svr11_epoch18r_20261011/v42_common_mess/model.py:8) — Process RSS/private/high-water and actual RAM/commit counters are stored separately. SHA256 `5462bfe7670168e4e25b97b79ee4dabacc840105bb7ad7077fc9574d0a9e99ad`
- [engine.py:214](D:/v42_svr11_epoch18r_20261011/v42_common_mess/engine.py:214) — Solver MemUsed/MaxMemUsed attributes differ from whole-process memory_after_native. SHA256 `2d9ee94cb78d9dddbc0b6669809ab6a9ee0ca12ea3eb8010fc12514b1be749e3`
- [resources.py:13](D:/v42_svr11_epoch18r_20261011/v42_svr11/resources.py:13) — Windows GetPerformanceInfo commit counters and new-dispatch admission, no OS paging configuration change. SHA256 `7597dfcf73aeee6b16ee0094fa95637902b639fad074aa0a16f6aac3a1207589`

Historical primary reference: [PR131](https://github.com/BeaverVillage/MobileESS/pull/131), exacthead `a16af252538774b2b2034a8722c31c0ffe5874a9`. It authorizes no current run.
