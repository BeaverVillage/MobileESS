"""One actual original A elastic LP, from pure Native0 math, separate ledger."""
from pathlib import Path
import gzip,pickle,time,traceback
from .stage_common import OUT,read,record,put
from .prestart_execution import atomic
from .stage_authority import diagnostic_lease,stage_scope

def certify(root,approval):
    from .stage_campaign import request,source_files
    from .stage_a_canary import scope as source_scope
    from .stage_budget import policy
    from v42_may_campaign_native90.budget import DateBudget
    from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_sign_convention
    root=Path(root);report=dict(PASS=False,role='ISOLATED_A_NUMERICAL_CANARY',official_campaign_executed=False,
        A1_or_A2_accepted_result=False,full_PhaseI_or_P1_closure_claimed=False)
    if root.exists():raise FileExistsError('NEW_A_CANARY_ROOT_REQUIRED')
    start=time.perf_counter()
    try:
        with diagnostic_lease(root,approval) as lease:
            req=request(root,'B1','A1',source_files());req['output']=str(root/'A1');req['root']=req['output']
            folder=Path(req['output']);folder.mkdir()
            class Diagnostic(DateBudget):
                def persist(self):
                    super().persist();data=read(self.path)
                    data.update(role='ISOLATED_A_NUMERICAL_CANARY',official_campaign_result=False,
                        original_official_budget_policy=policy())
                    atomic(self.path,data)
            with stage_scope(req,lease):
                budget=Diagnostic(folder/'NATIVE_RUNTIME_LEDGER.json',native_limit=30.)
                receipt=read(OUT/'A1_ORIGINAL_P1_FULL_PREPARATION.json');assert receipt['PASS']
                saved=receipt['state'];assert record(saved['path'])==saved
                with gzip.open(saved['path'],'rb') as stream:state=pickle.load(stream)
                before=time.perf_counter();master=elastic_master(state['compact'],state['grows'])
                report['elastic_model_preparation_wall_seconds']=time.perf_counter()-before
                with source_scope('A1',output_root=root,case_root=folder) as source:
                    verification=source.verify_case(state);assert verification['PASS']
                    # Real integer acceptance constructs this source physical
                    # reader with the active kernel's derived domain marker.
                    # Native0 entry binding alone did not exercise that path.
                    Physical,power=source._physical(state,Path(req['input_folder']),folder)
                    physical=Physical(state,state['compact'])
                    report['actual_original_physical_acceptance_constructor_PASS']=True
                    native=source._native(req,state,budget,None)
                    try:result,raw=native.solve(master.snapshot,folder/'PHASE_I','PHASE_I')
                    except RuntimeError:
                        path=folder/'PHASE_I/NATIVE_RESULT.json'
                        if not path.exists():raise
                        result=read(path)
                        if not (result.get('status') in (9,11) and 'BudgetStop' in str(result.get('native_error'))):raise
                        raw={}
                if result.get('status') not in (2,9,11) or budget.inflight is not None or len(budget.calls)!=1:
                    raise ValueError('ACTUAL_A_NATIVE_CANARY_FAILED')
                if result['status']==2:
                    primal=primal_replay(master.snapshot,raw['X'])
                    dual=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC'])
                    if not primal['PASS'] or not dual['PASS']:raise ValueError('A_ORIGINAL_PRIMAL_OR_DUAL_REPLAY_FAILED')
                    report.update(original_primal_replay=primal,original_dual_sign_replay=dual)
                ledger=read(budget.path)
                if abs(sum(r['Native_Runtime'] for r in ledger['calls'])-budget.used())>1e-7:
                    raise ValueError('A_CANARY_RUNTIME_RECONCILIATION')
                report.update(PASS=True,result=result,ledger=record(budget.path),Native_seconds=budget.used(),
                    diagnostic_Native_optimize_calls=1,source_native_constructor_and_original_policy_executed=True,
                    loaded_pure_Native0_state=saved,source_files=source_files(),budget_policy_unchanged=policy(),
                    current_source_independent_complete_case_verification=verification,
                    authorization=record(approval))
    except BaseException as error:
        report.update(error=repr(error),traceback=traceback.format_exc());raise
    finally:
        report['wall_seconds']=time.perf_counter()-start;report['producer']=record(__file__)
        if root.exists():atomic(root/'RESULT.json',report)
        put('A1_ISOLATED_NUMERICAL_CANARY_20261023.json',report)
    return report

if __name__=='__main__':
    import sys
    certify(sys.argv[1],sys.argv[2])
