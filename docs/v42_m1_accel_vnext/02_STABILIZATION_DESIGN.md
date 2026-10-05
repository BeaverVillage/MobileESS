# One coordinate dual box-step design

For original coupling dual pi_i, append artificial primal columns +e_i and -e_i
with costs theta_i+delta_i and -theta_i+delta_i. Their dual constraints are exactly
theta_i-delta_i <= pi_i <= theta_i+delta_i. Only rows touched by pricing are boxed.
The initial theta=0.1*pi_true+0.9*pi_checkpoint_center; delta_i=max(1.05*abs(pi_true_i-theta_i),1e-8).
The current optimal true dual is inside the box, ensuring a feasible dual exists
for this first guidance problem. This is a box-constrained dual LP, not a generic
smoothing renamed as stabilization. Artificial columns exist only in a separate
guidance model. They are disposed before pricing; the true RMP is rebuilt from
original global variables and validated physical trajectories only.

Serious step (audited UB decrease >=1e-5): move center to new true dual, retain
radius. Null step: halve radius and retain center. One frozen rule, no sweep.
Only one step is screened. Later infeasible/unbounded guidance must fall back to
true RMP guidance; it cannot change certification or convergence authority.

Both variants use byte-unchanged PR152 DiscoveryController/worker: four workers,
Threads=1, 20s, at most four accepted candidates/MESS, exact true-RC validation,
no domain restriction. Baseline uses frozen alpha=0.1. Box model duals are proposal
guidance only. No box/smoothed incumbent or objective is a scientific lower bound.
