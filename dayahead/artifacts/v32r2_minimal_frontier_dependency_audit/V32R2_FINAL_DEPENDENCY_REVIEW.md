
# V32R2 final dependency review

Result: **V32R2_MINIMAL_AUTHORITY_RECONSTRUCTABLE**

The missing 2025-02-28 realized SCATS record is diagnostic-only and the day is
source-ready for both frontier paths.  B0/B1 share one fixed MESS trajectory;
B2/B3 require their own commands, but their prospective no-regret rule already
exists.  No new MESS design is required.

V30 has no assembled arbitrary-day Stage-1 entry point.  Nevertheless its
actual Apr-04 behavior is a loader/reporter over frozen lower-level scheduling
primitives, and those primitives plus the V29R2 MESS selector accept general
day data.  Wiring and serialization are therefore an engineering gap, not a
new mathematical-policy choice.  `h_REC` is exactly derived, not endogenous.

The full line/phase cache need not cross the V32 authority boundary.  Persist
the exact reduced `s[day,slot,site]` together with `M_CURRENT` and the matched
anchor injection.  The smallest workload authority is three tensors: the
byte-identical B0/B2 reference, B1, and B3.

No production behavior was changed, no missing source was filled, no Fresh
frontier was run, and no 90-day optimization was run.
