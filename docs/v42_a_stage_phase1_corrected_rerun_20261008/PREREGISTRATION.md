# Corrected PR174 May19 single rerun

Exact base: 5d88890fe7ade1afff6f9faf69cc914aa69567e0, Draft PR174.
One cold May19 run from the byte-identical initial scientific active model. Historical native solutions are not warm starts. Initial target Phi=0.006626776621085752.

Use the corrected PR174 Phase-I -> partial exact pricing -> valid concrete activation -> re-solve loop unchanged. Keep exact migration fallback, same-dual continuation after empty bounded batches, old-point inclusion witness, native raw persistence before checks, and all lookahead/failed worker accounting. Preserve all physical candidates, frozen weights, four scientific objectives, original coefficients and 1e-6 science / 1e-8 zero tolerances. No permanent deletions or parameter sweep.

Fixed trigger: 16 independently validated negative concrete class columns or 24 fully priced classes, whichever first. Activate min(16,count), exact rational rc then stable identity. STAY and migration are both eligible. Maximum four process workers with Threads=1; sequential masters; max12 masters. Qualification compares one and four workers on tiny fixtures before May19.

Three consecutive re-solves with relative Phi reduction below1% and valid negatives stop as PHASE1_ACTIVATION_STAGNATION. Preserve each previous raw solution/descriptor as an inclusion witness. A raw Phi increase with a feasible same-Phi prior point is numerical degeneracy and continues; the raw new Phi is never replaced.

One 900s cumulative budget: max(elapsed wall since RUN_STARTED, sum of every real native Runtime), including build, source checks, pricing, recovery and activation. No resets, extension or second run. Initial static copying and qualification precede the budget; final persistence/cleanup overshoot is measured and permits no extra solve.

At certified zero, replay the artificial-free original active scientific model and STOP. P1, closure, other dates, production/Planning/Actual/Fresh AC are explicitly blocked. Budget/stagnation stops remain scientifically INCONCLUSIVE unless a verified witness itself fails. Historical receipts remain immutable in their original namespaces.

Original size/factor guards remain unchanged. Freeze the actual committed source bytes, model identities, gates and policies before the sole execution. Save X/Pi/RC/slack before every assertion, even on timeout. Publication is read-only postsolve; no automatic follow-up.
