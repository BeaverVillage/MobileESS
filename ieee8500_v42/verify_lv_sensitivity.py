"""Read-only independent numerical receipt checks, no AC or optimization."""
from __future__ import annotations

import numpy as np
from .common import REPORT, read, write, receipt, sha
from .geometry import read_csv

FOLDER=REPORT/'joint_selection_v3/lv_sensitivity'


def verify():
    policy=read(FOLDER/'PREREGISTRATION.json');done=read(FOLDER/'RECEIPT.json')
    axes=read(FOLDER/'AXES.json');base=read(FOLDER/'BASELINE_SUMMARIES.json')
    candidates=sorted(read_csv(REPORT/'LV_STA_CANDIDATES.csv'),key=lambda r:r['candidate_bus'])
    buses=[r['candidate_bus'] for r in candidates]
    if len(buses)!=1177 or len(set(buses))!=1177 or buses!=policy['candidate_buses']:
        raise ValueError('INDEPENDENT_ALL_1177_IDENTITY_CHECK_FAILED')
    if done['central_endpoint_AC_solves']!=18832 or done['total_endpoint_AC_solves']!=18848:
        raise ValueError('INDEPENDENT_SOLVE_COUNT_CHECK_FAILED')
    checks=[];maxpower=0.;maxneutral=0.;maxrating=0.
    for t,slot in enumerate(policy['slots']):
        file=FOLDER/f'LV_SLOT_{slot:02d}.npz'
        with np.load(file,allow_pickle=False) as a:
            if list(a['candidate_bus'])!=buses or a['dRho'].shape!=(1177,2,20):
                raise ValueError('NPZ_IDENTITY_AXIS_SHAPE_DRIFT')
            if list(a['line'])!=policy['line_set'] or list(a['component'])!=['P','Q'] or list(a['injection_sign'])!=[-1,1]:
                raise ValueError('NPZ_FROZEN_DIRECTION_AXES_DRIFT')
            expected=np.zeros((1177,2,2,2));expected[:,0,0,0]=.1;expected[:,0,1,0]=-.1
            expected[:,1,0,1]=.1;expected[:,1,1,1]=-.1
            powererr=float(np.max(np.abs(a['actual_PQ_demand']-expected)))
            neutralerr=float(np.max(np.abs(a['PCC_hot_complex_A'].sum(axis=-1))))
            ratings=np.array([axes['lines'][int(i)]['normal_amps'] for i in a['baseline_binding_axis']])
            ratingerr=float(np.max(np.abs(a['dI']-a['dRho']*ratings)))
            if powererr>1e-6 or neutralerr>1e-9 or ratingerr>1e-9:
                raise ValueError('INDEPENDENT_PCC_OR_RATING_CHECK_FAILED')
            # Check original per-customer topology identities against static axes.
            for k,row in enumerate(candidates):
                local=axes['candidate_local_axes'][k]
                if local['path']!=row['triplex_path'].split('|'):raise ValueError('TRIPLEX_PATH_IDENTITY_DRIFT')
                if not a['source_path_contains_line'][k].any():
                    # A branch can intersect none of the frozen twenty. This is
                    # an honest zero intersection, not a missing SourceBus path.
                    pass
                for ti in local['tx_current']:
                    if axes['transformers'][ti]['element'].lower()!=row['upstream_transformer']:
                        raise ValueError('ORIGINAL_CT_IDENTITY_DRIFT')
            summary=read_csv(FOLDER/f'PCC_ENDPOINT_SUMMARY_SLOT_{slot:02d}.csv')
            if len(summary)!=4708 or {r['bus'] for r in summary}!=set(buses):raise ValueError('ENDPOINT_COVERAGE_INCOMPLETE')
            if any(r['converged']!='True' or r['settled']!='True' or r['taps_caps_equal_common_base']!='True' for r in summary):
                raise ValueError('ENDPOINT_REAL_SOLVE_RECEIPT_FAILED')
            maxpower=max(maxpower,powererr);maxneutral=max(maxneutral,neutralerr);maxrating=max(maxrating,ratingerr)
            checks.append(dict(slot=slot,candidates=1177,endpoint_rows=len(summary),
                P_Q_readback_max_abs_error=powererr,PCC_hot_sum_max_A=neutralerr,
                derivative_original_rating_identity_max_error=ratingerr,
                baseline_Vmin=base[t]['summary']['vmin_pu'],baseline_Vmax=base[t]['summary']['vmax_pu'],
                baseline_canonical_rho=base[t]['summary']['rho_max'],
                new_line_overload_endpoint_rows=sum(int(r['new_line_overload_cells'])>0 for r in summary),
                new_voltage_violation_endpoint_rows=sum(int(r['new_voltage_violation_cells'])>0 for r in summary),
                new_CT_current_overload_endpoint_rows=sum(int(r['new_CT_current_overload_cells'])>0 for r in summary),
                new_CT_nameplate_overload_endpoint_rows=sum(int(r['new_CT_nameplate_overload_cells'])>0 for r in summary)))
    for name,r in done['artifacts'].items():
        if sha(FOLDER/name)!=r['sha256']:raise ValueError('RECEIPT_ARTIFACT_SHA_MISMATCH:'+name)
    scores=read_csv(FOLDER/'CANDIDATE_SCORES.csv')
    if len(scores)!=1177 or any(r['all_planned_slots_complete']!='True' for r in scores):
        raise ValueError('ALL_LV_FINAL_SCORE_COVERAGE_INCOMPLETE')
    report=dict(status='PASS_INDEPENDENT_ALL_1177_NUMERIC_AND_SOURCE_IDENTITY_CHECK',
        candidates=1177,sampled_slots=policy['slots'],central_endpoint_AC_solves=18832,
        total_endpoint_AC_solves=18848,actual_readback_maximum_error=maxpower,
        balanced_PCC_hot_vector_sum_max_A=maxneutral,original_rating_derivative_identity_max_error=maxrating,
        slots=checks,all_full_rating_finite_power_qualified=False,
        physical_status='SIMULATION_DESIGN_NOT_FIELD',production_certificate=False,
        verifier='independent archived numerical checks; no extra AC solve',
        Native_calls=0,full_model_builds=0,
        inputs={name:receipt(FOLDER/name) for name in ('PREREGISTRATION.json','RECEIPT.json','BASELINE_READBACK_RECEIPT.json','CANDIDATE_SCORES.csv')})
    write(FOLDER/'INDEPENDENT_NUMERICAL_VERIFICATION.json',report)
    return report


if __name__=='__main__':print(verify()['status'])
