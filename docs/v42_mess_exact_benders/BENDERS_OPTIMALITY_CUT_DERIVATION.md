# P1 lower approximation, before cut implementation

For min c^T y with free y and A y<=h(x), dual pi<=0, A^T pi=c gives Q(x)>=pi^T(b-Bx). Thus theta>=pi^T b-pi^T Bx and min theta is the master relaxation of min rho. It is not a feasibility-only proof of P1. The original rho column alone has objective coefficient one.

For numerical residual r=c-A^T pi, c^T y >= pi^T h(x)+L(r), with L the exact finite-bound minimum used in the feasibility derivation. Infinite required support means STOP, NO CUT. This completes the dual using existing bound rows, preserving exact lower validity even when floating stationarity is imperfect. Compute all arithmetic exactly on IEEE stored doubles. Round affine intercept downward and account for every coefficient error over x bounds, producing a weaker globally valid lower approximation. Require source tightness<=1e-7 and residual<=1e-7; record both exact correction and outward rounding. Enumeration tests every feasible assignment against its independently computed Q(x).

Valid accumulated cuts bound all original assignments, so master ObjBound supplies a global lower bound. Only independently validated assembled x/y supplies UB. Relative gap=(UB-LB)/max(abs(UB),1e-10); LB>UB+tolerance is a contradiction and STOP. P2 instead locks rho<=accepted P1+1e-7 in recourse and uses movement energy then movement count in the master, with inherited component tolerance 1e-8. P2 and downstream gates remain explicit.

Official sign and ray reference: [Gurobi linear constraint attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html).
