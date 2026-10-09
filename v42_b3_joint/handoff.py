"""Each edge locks the whole upstream decision, including auxiliary variables."""
from .contracts import StageRequest, WarmStartCandidate, require
from .validation import verify_stage


def next_request(previous_request, previous_result, *, a1=None, m1=None):
    verify_stage(previous_request, previous_result)
    stage = previous_request.stage
    authority = previous_request.authority
    if stage == "A1":
        return StageRequest("M1", authority, fixed_aidc=previous_result.aidc)
    if stage == "M1":
        return StageRequest("A2", authority, fixed_mess=previous_result.mess)
    if stage == "A2":
        require(m1 is not None and m1.stage == "M1" and m1.authority == authority, "SAME_AUTHORITY_M1_WARM_CANDIDATE_REQUIRED")
        # M1's old-anchor replay never proves feasibility under the new A2 PCC.
        candidate = WarmStartCandidate(authority.sha, previous_result.aidc.sha, m1.mess,
                                      eligible=False, feasibility_verified=False,
                                      reason="NOT_RUN_M1_FEASIBILITY_UNDER_NEW_A2_ANCHOR")
        return StageRequest("M2", authority, fixed_aidc=previous_result.aidc, warm_start=candidate)
    raise ValueError("M2_HAS_NO_OPTIMIZATION_SUCCESSOR")
