# B2 May18 Bus81 voltage failure

Actual1.0510300258122456pu; Forecast1.0508904420339138pu, slot51 (0-based). Bus81 B phase and both IDC10/MESS PCC B phases fail the unchanged1.05pu limit. All96 AC/control checks and current/kVA/taps pass.

Original topology:78→80→81 supplies IDC10. Bus79 and Bus86 regulators are on sibling branches. Existing BUS82 regulator is downstream of81 and senses82, which remains1.00348pu. STA10 is a different site from IDC10.

Frozen-coefficient diagnostic predicts Bus81 B1.027409814pu; Forecast Fresh AC gives1.050890442pu. Local unperturbed-prefix sensitivities do not certify the optimized nonlinear automatic-tap trajectory. Observed capacitive return and changed original taps are evidence, not an isolated causal attribution.

Across49 completed same-equipment Actual trajectories, the only Bus81 B violating date is May18. Keep this physical FAIL, continue other dates/policies, and do not rerun unchanged physics or alter limits. Existing BUS82 relocation beforeLine80 is a conservative candidate only if repeated structural evidence makes it unavoidable; no installation or safety claim. A physical change requires separate common epoch and affected-result recomputation.
