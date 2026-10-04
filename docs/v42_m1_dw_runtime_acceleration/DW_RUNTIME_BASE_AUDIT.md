# Lane C base authority

Repository: BeaverVillage/MobileESS. Branch: codex/v42-m1-dw-runtime-acceleration-prep.
Exact PR143 head: `ce5d30fb9bcb91ab8395d1313e868d24f5fde517`. Base selection was independently checked with `gh pr view 143`.
Parent authority retained checkpoint: 1158 columns.
Source and checkpoint Git blob identity is recorded in DW_RUNTIME_BASE_AUDIT.json.
The checkpoint pool was read for registry identity only; no historical full physical audit
or scientific matrix load was performed in this lane. Existing receipts are not silently
promoted into the new cache schema: missing matching receipts trigger re-audit on integration.

PR142/143 authority remains: actual four-way pricing PASS (historical, not rerun),
Threads=1, RAM floor=1 GiB, adaptive smoothing in Discovery only, true RC <= -1e-7,
up to 4 columns/MESS and 16/round. Warm RMP basis remains rejected.
Historical columns/minute 0.809981 -> 6.910010; Discovery median 70.334 s;
cold/warm RMP medians 33.996/38.943 s are user-provided PR142 context, not Lane C measurements.

Changes are new helper/test/evidence packages only. Production scientific modules,
pricing domain, certificates, retained pool and campaign orchestration are untouched.
No merges/rebases from other lanes, production optimization, May calls, or full pytest.
