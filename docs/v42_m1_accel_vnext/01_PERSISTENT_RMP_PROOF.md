# Basis extension and scientific authority

Let the existing RMP be A x =/<=/>= b, with a feasible optimal LP basis. Appending
columns D y, y>=0 preserves the old basic solution by setting y=0. Its basic
matrix and all old row/slack statuses are unchanged. Set each appended variable
VBasis=-1 (nonbasic at its zero lower bound), retain every old VBasis and CBasis.
This is a primal feasible basis of exactly the appended LP; no rows or bounds
are weakened. Pricing and all true-dual certificate implementations are inherited
unchanged. LPWarmStart=2 lets native presolve crush the supplied basis; solver log
evidence, not successful attribute assignment alone, determines acceptance.

The wrapper rejects any row-axis change, any old-variable-axis change, or nonzero
new-variable lower bound. No reset is issued. A terminal optimal LP with an
available basis is required for capture. Warm dual simplex may be slower on a
degenerate master; runtime retention requires measured benefit.

Exhaustive toy CG covers three appended columns; cold/persistent matrix and
optimum agree to 1e-10. Full-scale performance is a separate gated experiment.
