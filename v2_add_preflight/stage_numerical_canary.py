"""Real short K48 / HiGHS Beam / Joint calls, under a separate OS lease."""
from pathlib import Path
from types import SimpleNamespace
from contextlib import ExitStack
import json,time,traceback,gc
import numpy as np
from .stage_common import ROOT,OUT,WORK,SOURCE,record,read,put
from .prestart_execution import atomic
from .stage_authority import diagnostic_lease,stage_scope
from .stage_m_case import build_case,source_binding
from .stage_geometry_io import scope as geometry_scope
from .stage_native_io import readback_scope,AsciiNames
from .stage_budget import policy

def account(path,case,kind):
    from v44.budget import StageBudget
    budget=StageBudget(path,case=case,kind=kind)
    if budget.calls or budget.inflight is not None or budget.native_used!=0:
        raise PermissionError('ONLY_NEW_EMPTY_CANARY_ACCOUNT')
    budget.native_limit=30.
    budget.authorization.update(role='ISOLATED_NUMERICAL_CANARY',official_campaign_result=False,
        fresh_diagnostic_Native_ceiling_seconds=30.,official_budget_policy_unmodified=policy())
    budget.persist();return budget

def certify(root,approval):
    from .stage_campaign import request,source_files
    from v44.frozen.v43_mess.prepared import run_prepared_k48
    from v42_native.contracts import digest
    root=Path(root);report=dict(PASS=False,official_campaign_executed=False,
        role='ISOLATED_NUMERICAL_CANARY',official_UB_LB_Gap_or_plan_reused=False)
    start=time.perf_counter()
    if root.exists():raise FileExistsError('FRESH_ISOLATED_CANARY_ROOT_REQUIRED')
    try:
        with diagnostic_lease(root,approval) as lease:
            req=request(root,'B2','M1',source_files());req['output']=str(root/'CALLS');req['root']=req['output']
            Path(req['output']).mkdir()
            with stage_scope(req,lease):
                before=time.perf_counter();case=build_case();case.output=Path(req['output'])
                report['current_case_build_seconds']=time.perf_counter()-before
                report['case_sha']=case.case_sha
                with source_binding(case) as modules,geometry_scope(case,modules),ExitStack() as cleanup:
                    k=modules['table_v_k48'];engine=modules['m_engine'];candidate=modules['m_candidates']
                    global_control=modules['table_v_global_control']
                    control=global_control.GlobalGapControl(global_control.mess_scope(case),.03,root/'GLOBAL_CONTROL')
                    cleanup.callback(control.close);case.global_gap_control=control
                    K=account(root/'K48_LEDGER.json',case,'K48_SEPARATE')
                    before=time.perf_counter();packet,proof=k.prepare_k16(case,None,root/'K16')
                    report['K48_preparation_wall_seconds']=time.perf_counter()-before
                    lower=run_prepared_k48(k,case,packet,proof,K,root/'K48_EXECUTION')
                    del packet;gc.collect()
                    if not K.calls or K.inflight is not None or any(r.get('runtime_unavailable') for r in K.calls):
                        raise ValueError('ACTUAL_K48_MEASURED_RUNTIME_REQUIRED')
                    if any(r.get('Native_status') not in (2,9,11) or r.get('error') for r in K.calls):
                        raise ValueError('K48_NUMERICAL_CANARY_FAILED')
                    report['K48']=dict(result=lower,ledger=record(K.path),Native_seconds=K.used())
                    J=account(root/'JOINT_LEDGER.json',case,'PLANNING_NATIVE')
                    bank=engine.IncumbentBank(case)
                    before=time.perf_counter();pools=candidate.generate(case,None,bank,J)
                    beam_path=case.output/'COMMON_M_PR222/FRESH_BEAM_AND_REDISPATCH_ADMISSION.json'
                    beam=read(beam_path)
                    if not pools or not beam['PASS'] or beam['LP_calls']<=0:raise ValueError('ACTUAL_BEAM_LP_REQUIRED')
                    # Infeasible heuristic routes are ordinary score outcomes;
                    # they are never FULL incumbents. Unexpected numeric or
                    # Python errors still fail the diagnostic admission.
                    if (any(r.get('LP_status') not in (0,1,2) for r in beam['scores'])
                            or not any(r.get('LP_status')==0 for r in beam['scores'])):
                        raise ValueError('BEAM_LP_IMPLEMENTATION_OR_NUMERICAL_FAILURE')
                    report['Beam']=dict(wall_seconds=time.perf_counter()-before,LP_calls=beam['LP_calls'],
                        original_score_result=record(beam_path),coverage=beam['coverage'],
                        non_Native_costs=read(J.path)['costs'])
                    before=time.perf_counter();packet=engine.direct_joint(case,None,pools)
                    A,d,lift,point,proof=packet
                    for key in ('names','row_names'):d[key]=AsciiNames(d[key])
                    report['Direct_Joint_build_seconds']=time.perf_counter()-before
                    report['Direct_Joint_model']=dict(rows=A.shape[0],columns=A.shape[1],nonzeros=A.nnz,
                        binary=int(np.sum(d['types']=='B')),continuous=int(np.sum(d['types']=='C')))
                    with readback_scope(engine,root/'JOINT/READBACK'):
                        result,captures=engine._native_joint(case,engine._BudgetAdapter(J,30.),packet,root/'JOINT',30.)
                    if result.get('callback_errors') or result.get('native_status') not in (2,9,11):
                        raise ValueError('JOINT_NUMERICAL_CANARY_FAILED:'+str(result))
                    if not J.calls or J.inflight is not None:raise ValueError('JOINT_MEASURED_RUNTIME_REQUIRED')
                    validations=[]
                    for n,capture in enumerate(captures):
                        path=root/'JOINT'/f'CAPTURE_{n:03d}.npz';np.savez_compressed(path,point=capture['point'])
                        try:certificate=case.strict_validator(case,path)
                        except ValueError as error:
                            validations.append(dict(point=record(path),PASS=False,accepted=False,original_FULL_rejection=repr(error)))
                            continue
                        accepted=bank.offer(capture['point'],certificate)
                        validations.append(dict(point=record(path),PASS=certificate['PASS'],accepted=bool(accepted)))
                    if bank.best is not None:global_control.mess_upper(control,case,bank)
                    report['Joint']=dict(result=result,Native_seconds=J.used(),ledger=record(J.path),
                        original_FULL_capture_validations=validations,
                        independently_published_bounds=control.bounds(),invalid_raw_captures_never_accepted=True,
                        no_incumbent_at_short_TIME_LIMIT_is_not_infeasibility=True)
                    for budget in (K,J):
                        measured=sum(r['Native_Runtime'] for r in budget.calls)
                        if abs(measured-budget.used())>1e-7:raise ValueError('CANARY_RUNTIME_RECONCILIATION')
                    report.update(PASS=True,diagnostic_Native_optimize_calls=len(K.calls)+len(J.calls),
                        original_K48_Beam_Joint_entrypoints_executed=True,all_required_rows_built_before_optimize=True,
                        source_files=source_files(),budget_policy_unchanged=policy(),authorization=record(approval))
    except BaseException as error:
        report.update(error=repr(error),traceback=traceback.format_exc());raise
    finally:
        report['wall_seconds']=time.perf_counter()-start
        report['producer']=record(__file__)
        if root.exists():atomic(root/'RESULT.json',report)
        put('ISOLATED_NUMERICAL_CANARY_20261023.json',report)
    return report

if __name__=='__main__':
    import sys
    certify(sys.argv[1],sys.argv[2])
