"""Only May-01 B0/B1. There is no B2/B3 or monthly execution entrypoint."""
from pathlib import Path
from copy import deepcopy
import inspect,json,time
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,sha,digest,reference
from dayahead.v40e.case_semantics import matrix,enforce
from dayahead.v40e.audit import OLD
from .authority import REL,current_context,source_lineage,seal_previous
from .optimizer import solve


def prepare(repo):
    from dayahead.v40e.smoke import evaluate
    from dayahead.v36.contracts import PF_TAN
    from dayahead.v39a.power import site_it_power_kw
    repo=Path(repo).resolve();root=repo/REL;out=root/'smoke/2025-05-01';out.mkdir(parents=True,exist_ok=True)
    if (out/'PRE_MESS_JOBS.json').exists():raise RuntimeError('PRESERVE_EXISTING_COMPLETED_V40F_SMOKE')
    preflight=read(root/'V40F_COMMON_SERVICE_PREFLIGHT.json')
    assert preflight['B0_REFERENCE_IN_COMMON_DOMAIN']=='PASS' and preflight['B0_B1_COMMON_SERVICE_IDENTITY']=='PASS'
    assert preflight.get('reported_to_user_before_solve') is True
    assert read(root/'V40F_CORRECTED_ELECTRICAL_AUTHORITY_GATE.json')['status']=='PASS'
    reference_jobs=read(root/'common_service/COMMON_B0_REFERENCE_JOBS.json')
    with np.load(root/'common_service/COMMON_B0_REFERENCE_AIDC.npz') as z:arrays0={k:z[k] for k in z.files}
    ctx=current_context(repo)
    try:
        b0=evaluate(ctx,reference_jobs,pcc_override=arrays0['pcc'])
        if b0['status']!='PASS':raise RuntimeError('B0_REFERENCE_PLANNING_FAIL')
        write_json(out/'B0_CORRECTED_PLANNING_GATE.json',b0)
        np.savez_compressed(out/'B0_PRE_OBJECTIVE_AIDC_INPUT.npz',**arrays0)
        # The reference itself is now the feasible warm start and terminal anchor.
        accepted=solve(reference_jobs,deepcopy(reference_jobs),arrays0['pcc'],ctx,out/'A0_MIN_RHO')
        if accepted['status']!='PASS':raise RuntimeError('NO_ACCEPTED_GRID_AWARE_A0')
        arrays1={'gpu':accepted['GPU'],'pcc':accepted['PCC'],'qcc':accepted['PCC']*PF_TAN}
        arrays1['it']=np.array([[float(site_it_power_kw(ctx.capacity.site_capacity[s],int(accepted['GPU'][t,k]))) for k,s in enumerate(ctx.capacity.aidc_ids)] for t in range(96)])
        if accepted['complete_RW_reference_selected']:arrays1=deepcopy(arrays0)
        jobs={'B0':reference_jobs,'B1':accepted['jobs'],'B2':deepcopy(reference_jobs),'B3':deepcopy(accepted['jobs'])}
        arrays={'B0':arrays0,'B1':arrays1,'B2':deepcopy(arrays0),'B3':deepcopy(arrays1)}
        gate=enforce(jobs,arrays)
        common_fields=['job_uid','requested_GPU','state_at_issue','qos','safe_duration_slots','safe_duration_seconds','duration_authority','common_terminal_obligation']
        service_shas={c:digest([{k:r[k] for k in common_fields} for r in sorted(js,key=lambda r:r['job_uid'])]) for c,js in jobs.items()}
        assert len(set(service_shas.values()))==1
        assert digest(sorted(jobs['B1'],key=lambda x:x['job_uid']))==digest(sorted(jobs['B3'],key=lambda x:x['job_uid']))
        gate.update(B1_PRIMARY_OBJECTIVE='MIN_RHO_MAX',ZERO_FEASIBILITY_FINAL_OBJECTIVE='NO',B1_MESS_ENABLED='NO',
            B1_REFERENCE_CANDIDATE_INCLUDED='PASS',B1_PLANNING_NONWORSENING='PASS',B1_B3_A0_IDENTITY='PASS',
            B0_B2_AIDC_REFERENCE_IDENTITY='PASS',B0_NEW_AIDC_OPTIMIZATION=0,B2_NEW_AIDC_OPTIMIZATION=0,
            COMMON_DURATION_IDENTITY='PASS',B0_B1_COMMON_SERVICE_IDENTITY='PASS',case_service_SHA=service_shas,
            B1_AIDC_DECISION_SHA=accepted['final_decision_SHA'],B3_A0_DECISION_SHA=accepted['final_decision_SHA'],
            B2_B3_EXECUTION_STARTED=False,FULL_MAY_AUTHORIZED='NO',method_SHA=source_lineage(repo))
        write_json(out/'V40F_PRE_MESS_INTEGRATED_GATE.json',gate)
        write_json(out/'PRE_MESS_JOBS.json',jobs)
        for c,a in arrays.items():np.savez_compressed(out/(c+'_PRE_MESS_AIDC.npz'),**a)
        write_json(out/'B1_CORRECTED_PLANNING_GATE.json',accepted['grid'])
        print('V40F common-service MIN_RHO A0 gates PASS',flush=True)
        return gate
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()


def physical(repo,*,resume_actual=False):
    from dayahead.v40e import smoke as previous
    repo=Path(repo).resolve();out=repo/REL
    if (out/'smoke/2025-05-01/B0/CORRECTED_ACTUAL_RESULT.json').exists():raise RuntimeError('PRESERVE_EXISTING_ACTUAL_RESULT')
    # Exactly the existing corrected two-case physics runner, with a new output
    # namespace and new corrected electrical context. Never call its old prepare.
    src=inspect.getsource(previous.b0_b1).replace('V40E_','V40F_')
    src=src.replace("'accepted_A0_assignment_and_WAN','checks')", "'accepted_A0_assignment_and_WAN','checks','common_terminal_obligation')")
    if resume_actual:
        left=src.index("        for case in ('B0','B1'):\n            dst=out/case;dst.mkdir")
        right=src.index('        # Actual inputs open',left)
        replacement="""        for case in ('B0','B1'):
            dst=out/case
            frozen=read(dst/'CORRECTED_PLANNING_DECISION_FREEZE.json')
            assert digest(frozen['decision'])==frozen['decision_SHA']
            assert digest(frozen['decision']['AIDC_decision'])==digest(jobs[case])
            fg=read(dst/'CORRECTED_FRESH_GATE.json')
            assert fg['status']=='PASS' and fg['decision_SHA']==frozen['decision_SHA']
            assert fg['fresh']['schedule_sha256']==frozen['decision_SHA']
            run_results[case]={'Planning':read(out/(case+'_CORRECTED_PLANNING_GATE.json')),'Fresh':fg['fresh']}
"""
        src=src[:left]+replacement+src[right:]
    ns=dict(previous.__dict__);ns['REL']=REL;ns['planning_context']=lambda r,d:current_context(r)
    exec(compile(src,'<V40F_same_corrected_B0_B1_physics_new_authority>','exec'),ns)
    write_json(out/'V40F_PHYSICAL_RUNNER_LINEAGE.json',{'original_source':reference(Path(inspect.getsourcefile(previous.b0_b1))),
        'adapted_source':src,'changes':['output namespace','V40F artifact prefix','freshly rebuilt corrected electrical context','terminal obligation JSON serialization'],
        'resume_actual_from_verified_fresh':resume_actual,
        'Actual_execution_method_changed':False,'B2_B3_reachable':False})
    ns['b0_b1'](repo)


def main(repo):
    prepare(repo)
    physical(repo)
