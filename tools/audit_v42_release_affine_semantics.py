"""Reproduce the legacy voltage discrepancy and identify endpoint-face semantics."""
from pathlib import Path
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
OLD=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'


def main():
    target=OUT/'FROZEN_AFFINE_ROOT_CAUSE_FINAL.json'
    if target.exists():raise FileExistsError('AFFINE_SEMANTIC_AUDIT_MUST_NOT_OVERWRITE')
    authority=json.loads((OLD/'C0/AFFINE_OBSERVED_AUTHORITY.json').read_text(encoding='utf8'))
    coefficient=authority['coefficients'];assert file_record(coefficient['path'])==coefficient
    certificate=json.loads(Path(authority['certificate']['path']).read_text(encoding='utf8'))
    with np.load(coefficient['path'],allow_pickle=False) as z:
        names=list(map(str,z['node_names']));controls=list(map(str,z['control_names']))
        half=len(names)//2;assert names[:half]==names[half:] and len(set(names))==half
        j=names.index('idc_idc11_pcc.1');t=12
        anchor=z['anchor_control'][t].copy();constant=z['voltage_constant'][t].copy();matrix=z['voltage_matrix'][t].copy()
    with np.load(OLD/'C0/AFFINE_OBSERVED_DIAGNOSTICS.npz',allow_pickle=False) as z:
        control=z['control'][t].copy();saved=z['voltage_squared'][t].copy()
    assert np.max(np.abs(saved-(constant+matrix.T@control)))<1e-12
    rows=[]
    for face,index in [('LOWER_LDC_ENDPOINT',j),('UPPER_LDC_ENDPOINT',j+half)]:
        terms=matrix[:,index]*(control-anchor)
        by_family={family:float(sum(terms[k] for k,c in enumerate(controls) if c.startswith(prefix))) for family,prefix in
            [('AIDC_PQ_PF95','aidc_load_kw['),('MESS_P','mess_p_kw['),('MESS_Q','mess_q_kvar[')]}
        point=float(saved[index]);base=float(constant[index]+matrix[:,index]@anchor)
        assert abs(base+sum(by_family.values())-point)<1e-12
        rows.append(dict(face=face,node=names[index],slot=t,constant=float(constant[index]),
            anchor_endpoint_voltage_squared=base,current_endpoint_voltage_squared=point,
            current_endpoint_sqrt_pu=float(np.sqrt(max(0.,point))),delta_voltage_squared_by_family=by_family,
            terms=[dict(control=c,signed_coefficient=float(matrix[k,index]),anchor=float(anchor[k]),
                current=float(control[k]),contribution_voltage_squared=float(terms[k])) for k,c in enumerate(controls) if abs(terms[k])>1e-5]))
    projected=any(j in c['affected_indices'] for c in certificate['LDC_contracts'])
    report=dict(status='CAUSE_REPRODUCED',scope='FROZEN_LOCAL_PLANNING_SECANTS_NOT_CURRENT_NONLINEAR_VOLTAGE_AUTHORITY',
        input_authority=authority,coefficient_source=coefficient,voltage_rows=len(names),unique_node_axes=half,
        node_axis_duplicated_for_lower_upper_LDC_faces=True,endpoint_rows=rows,
        critical_node_in_LDC_projected_affected_nodes=projected,
        critical_node_face_rows_identical=bool(np.array_equal(matrix[:,j],matrix[:,j+half]) and constant[j]==constant[j+half]),
        critical_node_semantics='UNMODIFIED_LOCAL_CENTRAL_AUTO_SECANT_DUPLICATED_IN_BOTH_FACES',
        certificate_validity_scope=certificate['validity_scope'],global_nonlinear_envelope_certified=certificate['global_nonlinear_envelope_certified'],
        independent_native_prefix_central_secants_include_discrete_AUTO_response=True,
        frozen_background='FORECAST_DEMAND_PV_WEATHER_AND_FORECAST_ANCHOR',
        previous_Fresh_same_slot_same_node_pu=1.0007719049522799,
        API_semantic_issue='Off-anchor local central AUTO secants were treated as global current admission authority. Some other nodes have LDC endpoint faces, but the critical node is unprojected and its two rows are identical.',
        supersedes_preliminary_interpretation=str(OUT/'FROZEN_AFFINE_ROOT_CAUSE.json'),
        preliminary_claim_critical_node_is_only_a_LDC_lower_bound=False,
        correction='Use same-current-state original IEEE123/11SVR candidate AC for present safety; keep invalid old faces diagnostic only, require explicit valid prediction scope before Pre-site ranking.',
        original_planning_formulation_or_voltage_limits_changed=False,AC_or_Native_calls=0,
        generation_source=file_record(ROOT/'v42_svr11/model.py'),LDC_projection_source=file_record(ROOT/'v42_svr11/ldc_interval.py'))
    _write(target,report);print(json.dumps(dict(status=report['status'],rows=rows),indent=2))


if __name__=='__main__':main()
