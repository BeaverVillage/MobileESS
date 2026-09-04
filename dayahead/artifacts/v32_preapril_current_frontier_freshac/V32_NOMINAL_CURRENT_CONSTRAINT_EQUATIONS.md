
# V32 exact V30 nominal-current constraint

For slot `t`, V30 first selects the flattened branch/phase columns whose anchor
loading is at or above that slot's 95th percentile.  For AIDC site `i`, it then
forms `s[i,t] = max(active branch/phase) sensitivity[i,t,branch/phase]`.

Let `p` be candidate flexible AIDC site kW, `a` the B0 (for B1) or B2 (for B3)
same-slot anchor vector, `Ppeak` the normalization, and `M` the fixed margin.
The LP implements auxiliary variables `u[i] >= |p[i]-a[i]|` and

`s·p + (M/Ppeak) Σu[i] <= s·a`,

equivalently

`s·(p-a) + (M/Ppeak)||p-a||₁ <= 0`.

At `M=0`, this is `s·(p-a) <= 0`.  It is a same-slot, anchor-relative scalar
planning-surrogate constraint.  It is not an absolute-rating constraint, not
one constraint per branch/phase, not a slot-maximum constraint, and not a
whole-day peak-rho constraint.  Voltage and transformer limits are absent from
this Stage-2 LP and are evaluated only by ex-post Fresh AC.
