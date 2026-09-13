# Fixed-candidate certification stall

The May01 IEEE8500 six-MESS B2 search stopped at MESS04 candidate
`MESS04:MOVE:STA06:IDC05:40`, parent `B2-S3-e6780a4b5770f3b0`.
The existing NumericFocus=3 retry could not certify the returned solution.

The full planning evaluation was 0.8336856146048200 pu while reduced rho
was 0.8336848854315070 pu. The difference (7.29173313e-7) matched the
reported solver constraint violation and exceeded the unchanged 2e-8
certificate threshold. All hard-limit violation counts were zero. The
required separation rows were already present.

Tightening continuous tolerances with the old solution retained reproduced
the failure. Resetting the solution and setting FeasibilityTol,
OptimalityTol and IntFeasTol to 1e-9 passed the original certificate, with
rho values 0.8336856146048269 and 0.8336856146048268. The diagnostic matrix,
RHS, bounds and objective hash was unchanged. This is a planning-model
certificate, not a completed production exact-AC or Actual result.

The attached `NUMERICAL_REPAIR_PROOF.json` is the diagnostic receipt. Its
SHA256 is `8af79e98b3fcfa479954412aded6e762934b57e95dda80987b487ed0faeda424`.
It was obtained using the existing frozen May01 inputs and a licensed
Gurobi run; those large inputs are not duplicated here.

The code adds one strict retry only when the existing retry also raises
CERTIFICATE_STALLED. It preserves the current model and separation rows,
uses the same certificate function, propagates any remaining failure, and
records the third attempt in existing repair metadata. Successful first
or second attempts and other errors follow the original paths. Candidate
generation/ranking, objectives, physical constraints and certificate
tolerances are unchanged. A strict retry can add runtime for stalled cases.

Validation: `python -B tests/test_fixed_candidate_numeric_retry.py` runs six
license-independent control-flow tests, covering success paths, same-model
reset, cut preservation, error propagation and disposal. These tests do
not substitute for the attached numerical reproduction.

Production remained in its separate namespace. Its checkpoint restoration,
supervisor and frozen authority files are not changed by this PR.
