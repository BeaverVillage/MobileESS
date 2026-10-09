"""Pre-policy capacity-bounded pair-response overlap, never a dispatch certificate."""
from __future__ import annotations

import itertools
import math
from pathlib import Path

import numpy as np

from .selection import HIGH,REPORT,ROOT,read,rows,sha,write_csv,write_json


def freeze_overlap_rule():
    rule={
        'schema':'SELECTED_JOINT_CONTROL_OVERLAP_AUDIT_V1',
        'scope':'audit selected first-witness C1/C2 before policy outcomes; overlap is audited, not optimized',
        'derivative_archive':'FINAL_SEVEN_TIME_DERIVATIVES.npz',
        'slots':[0,9,48,68,72,75,74],
        'axis_weight':'frozen critical-corridor weight equally divided over seven times',
        'AIDC_P_response':'(d_rho_dP+tan(acos(.95))*d_rho_dQ)*original source-mask relaxation bound',
        'AIDC_independent_Q':False,'AIDC_certified_flexible_P_kw':0,
        'AIDC_mask_relaxation_is_QoS_dispatch_certificate':False,
        'MESS_P_response':'d_rho_dP*(450kW MV or5kW LV)*original day0 reachable vehicle fraction',
        'MESS_Q_response':'d_rho_dQ*(300kvar MV or3kvar LV)*original day0 reachable vehicle fraction',
        'MESS_vector_is_six_vehicle_simultaneous_schedule':False,
        'MESS_actual_phase_current_and_voltage_limits':'selected nonlinear AC may tighten nominal screening bounds',
        'normalized_pair_overlap':'signed cosine of flattened response times sqrt(axis_weight/7)',
        'coverage_active_rule':'positive response exceeds max(1e-12, .01*max(abs(site response)))',
        'coverage_rule':'weighted positive-support intersection/union; both positive and negative signed effects reported',
        'Q_pair_cosine':'reported only when both sites are STA; AIDC has no independent Q degree of freedom',
        'certified_pair_cosine':'UNDEFINED when either certified vector is zero; never substitute relaxation for certified AIDC flexibility',
        'complementarity':'screening response/phase/region/path evidence only; realized AIDC-MESS complementarity UNPROVEN',
        'score_or_AC_outcome_used_to_change_locations':False,'no_local_exchange_optimizer':True,
        'B1_B2_B3_outcomes_used':False,'global_optimality_claim':False,
        'field_access_GIS_protection_ETA':'UNVERIFIED',
    }
    write_json(REPORT/'JOINT_OVERLAP_AUDIT_PREREGISTRATION.json',rule,immutable=True)
    return rule


def _cosine(a,b):
    na=float(np.linalg.norm(a));nb=float(np.linalg.norm(b))
    return float(np.clip(a@b/(na*nb),-1,1)) if na and nb else None


def response_pair_metrics(a,b,axis_weights):
    """Signed and active-support diagnostics for a capacity-bounded response."""
    w=np.broadcast_to(np.asarray(axis_weights)/len(a),np.asarray(a).shape)
    sqrtw=np.sqrt(w)
    cutoff_a=max(1e-12,.01*float(np.max(np.abs(a))))
    cutoff_b=max(1e-12,.01*float(np.max(np.abs(b))))
    active_a=a>cutoff_a;active_b=b>cutoff_b
    intersect=float(w[active_a&active_b].sum());union=float(w[active_a|active_b].sum())
    pa=np.maximum(a,0);pb=np.maximum(b,0)
    denom=min(float((pa*w).sum()),float((pb*w).sum()))
    return {'signed_P_response_cosine':_cosine((a*sqrtw).ravel(),(b*sqrtw).ravel()),
        'positive_support_weight_a':float(w[active_a].sum()),
        'positive_support_weight_b':float(w[active_b].sum()),
        'positive_support_intersection_weight':intersect,'positive_support_union_weight':union,
        'positive_support_Jaccard':intersect/union if union else None,
        'capacity_positive_response_overlap_fraction':float((np.minimum(pa,pb)*w).sum())/denom if denom else None,
        'mean_weighted_negative_P_response_a':float((np.maximum(-a,0)*w).sum()),
        'mean_weighted_negative_P_response_b':float((np.maximum(-b,0)*w).sum())}


def audit_selected_control_overlap(folder,archive=None):
    rule=freeze_overlap_rule();folder=Path(folder)
    archive=Path(archive) if archive else REPORT/rule['derivative_archive']
    # This function runs only after final archive publication by the root.
    data=dict(np.load(archive,allow_pickle=False));slots=data['slots'].astype(int)
    assert slots.tolist()==rule['slots'],'Require complete preregistered seven-time archive'
    freeze=read(REPORT/'FINAL_CANDIDATE_SCORE_FREEZE.json')
    assert freeze['PASS'] and freeze['seven_slots']==slots.tolist()
    assert all(sha(r['path'])==r['sha256'] for r in freeze['input_archives']+[freeze['score']])
    inputs=[dict(np.load(r['path'],allow_pickle=False)) for r in freeze['input_archives']]
    assert len(inputs)==2
    assert np.array_equal(data['d_rho_d_consumption'],np.concatenate([r['d_rho_d_consumption'] for r in inputs]))
    assert all(np.array_equal(data[key],r[key]) for r in inputs for key in ('candidate_ids','line_indices','weights'))
    ids=list(map(str,data['candidate_ids']));indices={site:i for i,site in enumerate(ids)}
    derivatives=data['d_rho_d_consumption'];weights=np.asarray(data['weights'],float)
    assert derivatives.shape==(7,1783,2,len(weights)) and np.isfinite(derivatives).all()
    assert np.isclose(weights.sum(),1) and (weights>=0).all()
    mapping=rows(folder/'JOINT_LOCATION_SELECTION.csv')
    catalog={r['candidate_id']:r for r in rows(REPORT/'STA_MV_LV_CANDIDATES.csv')}
    assert ids==list(catalog) and len(indices)==1783,'Frozen candidate order and unique IDs must match'
    source=ROOT/'ieee8500_v42_high/data/facility/recomputed/C0_PLANNING_INPUTS.npz'
    facility=dict(np.load(source,allow_pickle=False));sites=list(map(str,facility['sites']))
    traffic=rows(REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv');ready={}
    for r in traffic:
        if int(r['departure_slot'])==0:ready.setdefault(r['destination_STA'],[]).append(900*int(r['earliest_day0_ready_slot']))
    qf=math.tan(math.acos(.95));P={};Q={};bounds={};reach={}
    axes=read(HIGH/'ac/E1R_C0_BG0.850/AC_AXES.json')['lines'];response_records=[]
    for site in mapping:
        name=site['location_id'];k=indices[site['candidate_id']];dp=derivatives[:,k,0];dq=derivatives[:,k,1]
        if site['role']=='AIDC':
            j=sites.index(name);bound=facility['source_mask_P_upper_bound_kw'][slots,j]
            P[name]=(dp+qf*dq)*bound[:,None];Q[name]=np.zeros_like(dp)
            bounds[name]=bound;reach[name]=np.ones(7)
        else:
            mv=site['connection_mode']=='MV_3PH';p=450 if mv else 5;q=300 if mv else 3
            fraction=np.array([sum(t0<=900*t for t0 in ready.get(name,[]))/6 for t in slots])
            P[name]=dp*p*fraction[:,None];Q[name]=dq*q*fraction[:,None]
            bounds[name]=np.full(7,p);reach[name]=fraction
        for t,slot in enumerate(slots):
            for axis,idx in enumerate(data['line_indices']):
                line=axes[int(idx)]
                response_records.append({'location_id':name,'candidate_id':site['candidate_id'],'role':site['role'],
                    'slot':int(slot),'original_line':line['element'],'original_line_phase_node':line['node'],
                    'corridor_axis_weight':float(weights[axis]),'source_mask_or_port_P_bound_kw':float(bounds[name][t]),
                    'original_ETA_reachable_vehicle_fraction':float(reach[name][t]),
                    'screening_P_relief_rho':float(P[name][t,axis]),
                    'screening_independent_Q_response_rho':float(Q[name][t,axis]),
                    'certified_AIDC_flexible_response_rho':0 if site['role']=='AIDC' else '',
                    'QoS_full_vehicle_schedule_or_field_access_certificate':False})
    write_csv(folder/'SELECTED_CAPACITY_BOUNDED_LINE_RESPONSE.csv',response_records)
    pairs={(r['location_a'],r['location_b']):r for r in rows(folder/'ELECTRICAL_PAIR_DISTANCE_SHARED_PATH.csv')}
    output=[]
    for a,b in itertools.combinations(mapping,2):
        na,nb=a['location_id'],b['location_id'];metrics=response_pair_metrics(P[na],P[nb],weights)
        qa=Q[na];qb=Q[nb];factor=np.sqrt(weights/7)
        qcos=_cosine((qa*factor).ravel(),(qb*factor).ravel()) if a['role']==b['role']=='STA' else None
        ca,cb=catalog[a['candidate_id']],catalog[b['candidate_id']]
        phases=lambda c:{1,2,3} if c['connection_mode']=='MV_3PH' else {int(c['original_service_primary_phase'])}
        p=pairs[(na,nb)]
        output.append({'case':a['case'],'location_a':na,'location_b':nb,'role_pair':'-'.join(sorted([a['role'],b['role']])),
            'candidate_id_a':a['candidate_id'],'candidate_id_b':b['candidate_id'],
            'region_a':a['electrical_region'],'region_b':b['electrical_region'],
            'different_topology_regions':a['electrical_region']!=b['electrical_region'],
            'primary_phase_set_a':','.join(map(str,sorted(phases(ca)))),
            'primary_phase_set_b':','.join(map(str,sorted(phases(cb)))),
            'disjoint_primary_phase_sets':not bool(phases(ca)&phases(cb)),
            'primary_proxy_tree_distance_ohm':p['primary_proxy_tree_distance_ohm'],
            'shared_upstream_path_weight_ratio':p['shared_upstream_path_weight_ratio'],
            **metrics,'independent_Q_response_cosine':qcos,
            'certified_AIDC_pair_response_cosine':None,
            'certified_AIDC_nonzero_flexibility':'NOT_CERTIFIED',
            'overlap_audited_not_optimized':True,
            'realized_joint_AIDC_MESS_complementarity':'UNPROVEN',
            'response_bound_is_simultaneous_physical_dispatch_certificate':False})
    assert len(output)==276
    write_csv(folder/'JOINT_CONTROL_OVERLAP_AUDIT.csv',output)
    receipt={'schema':'PRE_POLICY_SELECTED_JOINT_OVERLAP_RECEIPT_V1','case':mapping[0]['case'],
        'pair_count':276,'sample_slots':slots.tolist(),'complete_selected_line_response_rows':len(response_records),
        'sources_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [archive,source,REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv',
            folder/'JOINT_LOCATION_SELECTION.csv',REPORT/'JOINT_OVERLAP_AUDIT_PREREGISTRATION.json']},
        'no_location_or_policy_changed_by_audit':True,'certified_AIDC_flexible_P_kw':0,
        'realized_joint_AIDC_MESS_complementarity':'UNPROVEN','global_optimality_claim':False}
    write_json(folder/'JOINT_CONTROL_OVERLAP_RECEIPT.json',receipt,immutable=True)
    return receipt


def summarize_control_overlap():
    """Summarize existing evidence without changing geometry or control policy."""
    output=[]
    for case in ('C1','C2'):
        audit=rows(REPORT/(case+'_SCORED')/'JOINT_CONTROL_OVERLAP_AUDIT.csv')
        for group in ('AIDC-AIDC','AIDC-STA','STA-STA'):
            subset=[r for r in audit if r['role_pair']==group]
            cosines=[float(r['signed_P_response_cosine']) for r in subset if r['signed_P_response_cosine']]
            jaccard=[float(r['positive_support_Jaccard']) for r in subset if r['positive_support_Jaccard']]
            output.append({'case':case,'role_pair':group,'pair_count':len(subset),
                'defined_P_response_cosines':len(cosines),
                'mean_P_response_cosine':float(np.mean(cosines)) if cosines else '',
                'median_P_response_cosine':float(np.median(cosines)) if cosines else '',
                'pairs_P_response_cosine_ge_0p95':sum(v>=.95 for v in cosines),
                'mean_positive_support_Jaccard':float(np.mean(jaccard)) if jaccard else '',
                'pairs_different_topology_regions':sum(r['different_topology_regions']=='True' for r in subset),
                'pairs_disjoint_primary_phase_sets':sum(r['disjoint_primary_phase_sets']=='True' for r in subset),
                'median_shared_upstream_path_weight_ratio':float(np.median([float(r['shared_upstream_path_weight_ratio']) for r in subset])),
                'overlap_audited_not_optimized':True,'realized_joint_complementarity':'UNPROVEN',
                'certified_AIDC_flexible_P_kw':0})
    write_csv(REPORT/'JOINT_CONTROL_OVERLAP_SUMMARY.csv',output)
    return output


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--case',choices=['C1','C2']);p.add_argument('--summary',action='store_true');args=p.parse_args()
    print(json.dumps(summarize_control_overlap() if args.summary else audit_selected_control_overlap(REPORT/(args.case+'_SCORED')) if args.case else freeze_overlap_rule(),indent=2))
