"""Verify fresh production schedule authority uses exactly one AIDC multiplier."""
from bootstrap import *


def main():
    ctx = new_context()
    paper = H.parent.parent / "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/MAY01_B0_AIDC_POWER.npz"
    with np.load(H / "MAY01_B0_AIDC_POWER.npz") as z, np.load(paper) as original:
        errors = {key: float(np.max(np.abs(ctx.power[key] - z[key]))) for key in ("pcc", "qcc")}
        paper_it_preservation_error = float(np.max(np.abs(z["it"] - original["it"])))
        planning_it_vs_B0_it_diagnostic = float(np.max(np.abs(ctx.power["it"] - z["it"])))
        input_multiplier_errors = {key: float(np.max(np.abs(z[key] - original[key] * (2.4/2.0))))
                                   for key in ("pcc", "qcc")}
    report = dict(status="PASS" if max(*errors.values(),paper_it_preservation_error,
        *input_multiplier_errors.values()) < 1e-8 else "FAIL",
                  AIDC_absolute_scale=2.4, paper_stored_array_absolute_scale=2.0,
                  applied_multiplier=1.2, reference_job_count=len(ctx.reference),
                  candidate_count=sum(map(len,ctx.options.values())),
                  candidate_stream_sha256=EXPECTED, max_errors=errors,
                  paper_IT_unchanged_error=paper_it_preservation_error,
                  input_multiplier_errors=input_multiplier_errors,
                  planning_IT_vs_B0_IT_diagnostic=planning_it_vs_B0_it_diagnostic,
                  IT_scope_note="Planning job IT array and frozen B0 IT schedule are distinct; per-GPU law is unchanged",
                  paper_power_sha256=sha(paper),
                  paper_overlay_sha256=sha(H / "IEEE8500_PCC_Overlay.dss"),
                  scaled_power_sha256=sha(H / "MAY01_B0_AIDC_POWER.npz"))
    save(H / "PRODUCTION_CONTEXT_PREFLIGHT.json", report)
    print(report)
    assert report["status"] == "PASS"


if __name__ == "__main__":
    main()
