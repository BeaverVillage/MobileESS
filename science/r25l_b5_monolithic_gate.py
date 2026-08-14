#!/usr/bin/env python3
from __future__ import annotations

def cert_bound_for_gap(incumbent: float, target_gap: float=0.03) -> float:
    """For the observed minimization case with best bound <= incumbent.
    Return the least-negative bound that is sufficient for |inc-bound|/|inc| <= target_gap.
    """
    inc=float(incumbent); g=float(target_gap)
    return inc - g*abs(inc)

def evaluate_b5(metrics: dict) -> dict:
    gap=metrics.get('gap'); runtime=metrics.get('runtime_s'); nodes=metrics.get('nodes')
    root=metrics.get('root_bound'); bound=metrics.get('bound'); inc=metrics.get('incumbent')
    exit_s=metrics.get('root_exit_s'); nps=metrics.get('nodes_per_second')
    certified=isinstance(gap,(int,float)) and float(gap) <= 0.03 + 1e-12
    closure=None; cert_bound=None; projected_remaining_s=None
    if all(isinstance(x,(int,float)) for x in (root,bound,inc)):
        cert_bound=cert_bound_for_gap(float(inc),0.03)
        need=cert_bound-float(root)
        done=float(bound)-float(root)
        if need>1e-12:
            closure=done/need
            if isinstance(runtime,(int,float)) and done>1e-12 and closure<1.0:
                slope=done/float(runtime)
                if slope>0: projected_remaining_s=max(0.0,(cert_bound-float(bound))/slope)
    root_exit_ok=isinstance(exit_s,(int,float)) and float(exit_s) <= 120.0
    branch_volume_ok=isinstance(nodes,(int,float)) and float(nodes) >= 300.0
    throughput_ok=isinstance(nps,(int,float)) and float(nps) >= 0.5
    near_cert=isinstance(gap,(int,float)) and float(gap) <= 0.0310 + 1e-12
    closure_ok=isinstance(closure,(int,float)) and float(closure) >= 0.80
    projected_ok=isinstance(projected_remaining_s,(int,float)) and float(projected_remaining_s) <= 300.0
    if certified:
        decision='GO_MONOLITHIC_STAGE1'
        reason='3% certificate achieved inside the 600 s B5 screen.'
    elif root_exit_ok and branch_volume_ok and throughput_ok and near_cert and closure_ok and projected_ok:
        decision='GO_MONOLITHIC_PROMISING'
        reason='Not yet certified, but root exit, branch throughput, certificate-closure fraction, and projected remaining time all pass the frozen B5 gate.'
    else:
        decision='NO_GO_MONOLITHIC_ADVANCE_B6_EXACT_DECOMPOSITION'
        reason='The frozen production-oriented B5 gate is not satisfied; no further monolithic parameter tuning is authorized.'
    return {
      'decision':decision,'reason':reason,'certified_3pct':certified,
      'root_exit_ok_le_120s':root_exit_ok,'branch_volume_ok_ge_300_nodes':branch_volume_ok,
      'throughput_ok_ge_0p5_nodes_per_s':throughput_ok,'near_certificate_gap_le_3p10pct':near_cert,
      'certificate_closure_fraction':closure,'closure_fraction_ok_ge_0p80':closure_ok,
      'certificate_bound_required_for_final_incumbent':cert_bound,
      'linear_bound_slope_projected_remaining_s':projected_remaining_s,
      'projected_remaining_ok_le_300s':projected_ok,
      'production_SLA_certified':False,
      'production_SLA_note':'Even GO_MONOLITHIC_STAGE1 does not certify annual production throughput; B7 measures that separately.'
    }
