"""One Native0 M1 preparation using frozen route and AIDC control inputs.

No solver, presolve, IIS, operational replay or campaign ledger is entered.
The structural Joint start is not a feasible incumbent or an accepted UB.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace

for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main(raw,output):
    import psutil
    for p in psutil.process_iter(['pid','cmdline']):
        argv=p.info['cmdline'] or []
        if p.pid!=os.getpid() and '--execute' in argv and any(Path(a).name=='run_v42_production_campaign.py' for a in argv):
            raise RuntimeError('CAMPAIGN_MUST_BE_STOPPED_BEFORE_FULL_NATIVE0_AUDIT')
    import gurobipy as gp
    calls=[]
    def forbidden(*a,**k):
        calls.append('FORBIDDEN_NATIVE');raise AssertionError('NATIVE0_ONLY')
    for name in ('optimize','presolve','computeIIS','feasRelax','feasRelaxS'):
        setattr(gp.Model,name,forbidden)
    import numpy as np
    from v42_integration.release_date_case import ARCHIVE,merge_same_day_physical,original_source_freeze
    from v42_integration.production_case import ProductionPhysicalContext
    from v42_may_campaign_native90.m_model import build_case
    from v42_integration.m_engine import PathGraph,direct_joint,_native_joint,file_record
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_common_mess.fixed_pattern import values_for,stationary_paths
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    output.mkdir(parents=True,exist_ok=False);began=perf_counter()
    saved=read(raw/'INPUT_AND_SOURCE_IDENTITY.json');day=saved['day']
    bundle=read(ARCHIVE/'raw'/day/'NATIVE_INPUT_TEMPLATE_B1.json')
    if any(bundle['route_table'][k]!=saved['route_table'][k] for k in ('sha256','bytes')):
        raise ValueError('FROZEN_ROUTE_BYTES_DRIFT')
    bundle['route_table']=dict(saved['route_table'])
    bundle,_,_,_=merge_same_day_physical(bundle,day)
    physical=ProductionPhysicalContext(original_source_freeze(),read(ARCHIVE/'CAMPAIGN_MANIFEST.json'),bundle)
    anchor=read(raw/'FIXED_AIDC_ANCHOR.json');sites=sorted(bundle['capacities'])
    controls=np.asarray(anchor['controls']);names=anchor['control_names']
    planning=dict(sites=sites,PCC_P_kw=np.column_stack([controls[:,names.index('aidc_load_kw['+s+']')] for s in sites]).tolist())
    identity=dict(saved['input_identity'],scope='NATIVE0_FROZEN_CASE_PREPARATION_AUDIT',production_result_promoted=False)
    def progress(value):
        value=dict(value,audit_wall_seconds=perf_counter()-began)
        (output/'PROGRESS.json').write_text(json.dumps(value,indent=2),encoding='utf8')
        print(json.dumps(value),flush=True)
    case=build_case(dict(bundle=bundle,planning=planning,identity=identity),
                    dict(day=day,arm='B2',stage='M1',output=str(output/'CURRENT_M')),progress,
                    integration_context=physical)
    prep_wall=perf_counter()-began
    reference=read(raw/'CURRENT_EXACT_C3A_PROOF.json')
    dense=read(raw/'DENSE_RESPONSE_EQUIVALENCE.json')
    checks=dict(original_matrix=matrix_sha(case.original_A)==read(raw/'SCIENTIFIC_CASE_IDENTITY.json')['original_matrix_sha'],
                C3A_matrix=matrix_sha(case.ultra.A)==reference['selected_matrix_SHA256'],
                Dense_matrix=matrix_sha(case.A)==read(raw/'SCIENTIFIC_CASE_IDENTITY.json')['selected_matrix_sha'],
                all_original_384_charge_modes=sum(str(n).startswith('charge_mode[') for n in case.d['names'])==384)
    # Construct two complete paths per unit without importing an old point.
    graph=PathGraph(case);point=np.zeros(case.A.shape[1]);fixed=case.d['lower']==case.d['upper'];point[fixed]=case.d['lower'][fixed]
    ids,values=values_for(case,stationary_paths(case),lambda u,t:False);point[ids]=values
    for j,name in enumerate(map(str,case.d['names'])):
        if name.startswith('SOC['):point[j]=case.graph[3].initial
        if name=='rho_max':point[j]=10.
    pools={u:[graph.complete(u)] for u in sorted(graph.origins)}
    packet=direct_joint(case,point,pools)
    class NoNative:
        def remaining(self):return 0.
    native,_=_native_joint(case,NoNative(),packet,output/'JOINT',0.,native0=True)
    checks['Native_readback']=native['Native_optimize_calls']==0
    report=dict(PASS=all(checks.values()) and not calls,checks=checks,Native_optimize_calls=0,
                M1_preparation_wall_seconds=prep_wall,total_with_Joint_readback_wall_seconds=perf_counter()-began,
                original_FULL_shape=list(case.original_A.shape),Dense_shape=list(case.A.shape),Joint_shape=list(packet[0].shape),
                C3A=case.ultra.proof,static_presolve=read(output/'CURRENT_M/CURRENT_STATIC_PRESOLVE_PROFILE.json'),
                all_original_matrix_bounds_and_proofs_replayed=True,
                structural_Joint_start_is_not_FULL_feasible_or_UB=True,
                stage_profiles=[str(output/'CURRENT_M/PREPARATION_PROFILE.jsonl'),str(output/'JOINT/PREPARATION_PROFILE.jsonl')],
                source_case_identity=identity,source_bundle=file_record(ARCHIVE/'raw'/day/'NATIVE_INPUT_TEMPLATE_B1.json'))
    (output/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report),flush=True)
    if not report['PASS']:raise AssertionError('FULL_NATIVE0_MATRIX_OR_READBACK_DRIFT')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--raw',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();main(a.raw,a.output)
