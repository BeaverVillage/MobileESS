"""May-01 B0/B1 only; final joint policy is frozen before any diagnostic."""
from pathlib import Path
from copy import deepcopy
import inspect
import numpy as np
from dayahead.paper_analysis.storage import read,write_json,reference,sha
from dayahead.v40a.invariants import digest
from dayahead.v40e.case_semantics import enforce
from dayahead.v39a.power import site_it_power_kw
from dayahead.v36.contracts import PF_TAN
from .authority import REL,initialize,current_context,GATES
from .optimizer import solve


def prepare(repo):
    repo=Path(repo).resolve();root=initialize(repo);out=root/'smoke/2025-05-01';out.mkdir(parents=True,exist_ok=True)
    if (out/'PRE_MESS_JOBS.json').exists():raise RuntimeError('PRESERVE_COMPLETED_JOINT_POLICY')
    jobs0=read(root/'common_service/COMMON_B0_REFERENCE_JOBS.json')
    with np.load(root/'common_service/COMMON_B0_REFERENCE_AIDC.npz') as z:arrays0={k:z[k] for k in z.files}
    context=current_context(repo)
    try:
        accepted_path=out/'JOINT_AIDC/ACCEPTED_AIDC.json'
        if accepted_path.exists():
            accepted=read(accepted_path)
            assert accepted['status']=='PASS' and accepted['diagnostic_only'] is False
            assert digest(accepted['jobs'])==accepted['final_decision_SHA']
            assert all(s['OPTIMAL'] for s in accepted['solver_stages'])
            accepted['GPU']=np.asarray(accepted['GPU']);accepted['PCC']=np.asarray(accepted['PCC'])
            print('REUSE completed B1 solve; no optimization repeated',flush=True)
        else:accepted=solve(jobs0,arrays0['pcc'],context,out/'JOINT_AIDC')
        arrays1={'gpu':accepted['GPU'],'pcc':accepted['PCC'],'qcc':accepted['PCC']*PF_TAN,
                 'it':np.array([[float(site_it_power_kw(context.capacity.site_capacity[s],int(accepted['GPU'][t,k])))
                      for k,s in enumerate(context.capacity.aidc_ids)] for t in range(96)])}
        jobs={'B0':jobs0,'B1':accepted['jobs'],'B2':deepcopy(jobs0),'B3':deepcopy(accepted['jobs'])}
        arrays={'B0':arrays0,'B1':arrays1,'B2':deepcopy(arrays0),'B3':deepcopy(arrays1)}
        gate=enforce(jobs,arrays)
        b1sha=digest(sorted(jobs['B1'],key=lambda r:r['job_uid']));b3sha=digest(sorted(jobs['B3'],key=lambda r:r['job_uid']))
        assert b1sha==b3sha==accepted['final_decision_SHA']
        fields=('job_uid','requested_GPU','state_at_issue','qos','safe_duration_slots','safe_duration_seconds','duration_authority','common_terminal_obligation')
        service={c:digest([{k:r.get(k) for k in fields} for r in sorted(js,key=lambda r:r['job_uid'])]) for c,js in jobs.items()}
        assert len(set(service.values()))==1
        gate.update(B1_AIDC_DECISION_SHA=b1sha,B3_A0_DECISION_SHA=b3sha,B1_B3_A0_IDENTITY='PASS',
                    case_service_SHA=service,COMMON_DURATION_IDENTITY='PASS',B1_PLANNING_NONWORSENING='PASS',
                    B2_B3_EXECUTED=False,FULL_MAY_EXECUTED=False,identity_scope='STATIC_PRE_M1_ONLY',**GATES)
        write_json(out/'V40G_PRE_MESS_INTEGRATED_GATE.json',gate)
        write_json(out/'PRE_MESS_JOBS.json',jobs)
        for c,a in arrays.items():np.savez_compressed(out/(c+'_PRE_MESS_AIDC.npz'),**a)
        from .reuse import accepted_b1_as_a0,persist_reuse,architecture_contract
        architecture_contract(repo)
        persist_reuse(accepted_b1_as_a0(accepted_path,out/'B1_PRE_MESS_AIDC.npz'),out/'B3_A0_STATIC_REUSE')
        write_json(out/'B0_CORRECTED_PLANNING_GATE.json',accepted['reference_grid'])
        write_json(out/'B1_CORRECTED_PLANNING_GATE.json',accepted['grid'])
        write_json(out/'PLANNING_SOURCE_SEAL.json',{'source_files':{str(p):sha(p) for p in sorted((repo/'dayahead/v40g').glob('*.py'))},
                    'policy_SHA':b1sha,'final_policy_frozen_before_diagnostic':True})
        print('V40G FINAL JOINT POLICY FROZEN '+b1sha,flush=True)
        # Diagnostic is always run after the final policy is fixed. Its output
        # has no assignment back to jobs, arrays, B1 or B3 A0.
        diagnostic=solve(jobs0,arrays0['pcc'],context,out/'TEMPORAL_ONLY_DIAGNOSTIC',temporal_only=True)
        improvement=diagnostic['primary_optimum']-accepted['primary_optimum']
        assert improvement>=-1e-9
        write_json(out/'TEMPORAL_ONLY_COMPARISON.json',{'diagnostic_only':True,'final_policy_SHA':b1sha,
            'temporal_only_primary_optimum':diagnostic['primary_optimum'],'temporal_only_primary_bound':diagnostic['primary_bound'],
            'joint_primary_optimum':accepted['primary_optimum'],'joint_primary_bound':accepted['primary_bound'],
            'additional_primary_rho_improvement_spatial_and_migration':improvement,
            'certified_improvement_interval':[diagnostic['primary_bound']-accepted['primary_optimum'],diagnostic['primary_optimum']-accepted['primary_bound']],
            'migration_used':accepted['secondary_migration_optimum']>0,'diagnostic_selected_final_policy':False})
        return gate
    finally:context.electrical.voltage.close();context.electrical.current.close()


def physical(repo):
    from .physical import run
    return run(repo)


if __name__=='__main__':
    import sys
    if sys.argv[1:] == ['prepare']:prepare(Path.cwd())
    elif sys.argv[1:] == ['physical']:physical(Path.cwd())
    else:raise SystemExit('Only prepare or physical May-01 B0/B1 is authorized')
