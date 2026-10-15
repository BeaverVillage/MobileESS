"""Explicit user-authorized saved-S0 diagnostics; carry E08 costs, keep HOLD."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import argparse
from copy import deepcopy
import gzip,json,pickle,re,shutil,sys,threading,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.a_engine import digest
read=lambda p:json.loads(p.read_text(encoding='utf8'))


def predecessor(head,e08):
    """A completed descendant is mandatory; never branch from spent E08."""
    if head.exists():
        current=read(head)
        if current.get('state')!='COMPLETE':raise RuntimeError('DIAGNOSTIC_HEAD_REQUIRES_RECONCILIATION')
        row=current['ledger']
        if file_record(row['path'])!=row:raise RuntimeError('DIAGNOSTIC_CANONICAL_LEDGER_DRIFT')
    else:row=file_record(e08)
    prior=read(Path(row['path']))
    if prior.get('inflight') or prior.get('active_stage_context'):raise RuntimeError('PREDECESSOR_MUST_BE_RECONCILED')
    return row,prior


def run(output):
    from v42_integration.table_v_budget import TableVStageBudget
    from v42_integration.table_v_run import HISTORY
    from v42_integration.table_v_phase_policy import SOURCE18R_FAST,FAST_B,allowance
    from v42_integration.table_v_phase_diagnostics import residual_report
    from v42_integration.table_v_resources import admit_resources
    from v42_integration.table_v_memory import memory_sample
    from v42_integration.table_v_launch import release_identity
    from v42_integration.d0_resource import native_binding
    from types import SimpleNamespace
    import gurobipy as gp
    import psutil
    from v42_a_stage_domain_v2.stress_backend import materialize
    from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
    E=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION08'
    E07=E.with_name('EXECUTION07')
    saved=Path('D:/v42_mess_prep_fix_20261015/PHASE_POLICY_MATRIX03')
    receipt=read(saved/'RECEIPT.json');matrix=receipt['snapshots'][0]['record']
    original_e08=file_record(E/'PLANNING_NATIVE_LEDGER.json')
    head=ROOT/'docs/v42_source18r_phase_20261015/DIAGNOSTIC_HEAD.json'
    oldledger,old=predecessor(head,E/'PLANNING_NATIVE_LEDGER.json')
    same_stage=lambda r:all(r.get('stage_context',{}).get(k)==v for k,v in dict(day='2025-05-01',arm='B1',stage='A1').items())
    phase_used=sum(r['Native_Runtime'] for r in old['calls'] if r.get('solver')=='GUROBI' and same_stage(r)
        and r.get('label','').startswith('RELEASE_P1:A1:DW:PHASE_I:'))
    stage_used=sum(r['Native_Runtime'] for r in old['calls'] if r.get('solver')=='GUROBI' and same_stage(r))
    if allowance(5400.-stage_used,phase_used)<=0:
        print(json.dumps(dict(status='NO_PHASE_I_BUDGET_NO_NATIVE_EXECUTED',predecessor=oldledger,
            phase_used=phase_used,phase_remaining=0.,A1_remaining=5400.-stage_used)),flush=True)
        return
    if not (E/'CAMPAIGN_STOP_REQUEST.json').exists():raise RuntimeError('CAMPAIGN_HOLD_REQUIRED')
    if file_record(matrix['path'])!=matrix:raise ValueError('SAVED_S0_BYTES_DRIFT')
    with gzip.open(matrix['path'],'rb') as stream:master=pickle.load(stream)
    if master.snapshot.fingerprint()!=receipt['snapshots'][0]['snapshot_sha']:raise ValueError('SAVED_S0_IDENTITY')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(E07/'INPUTS',output/'INPUTS')
    manifest=read(output/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json')
    sources=[file_record(__file__)]+[file_record(ROOT/p) for p in (
        'v42_integration/table_v_phase_policy.py','v42_integration/table_v_phase_diagnostics.py',
        'v42_integration/table_v_dw.py','v42_integration/table_v_budget.py')]
    human=dict(authority='DIRECT_USER_IN_THIS_THREAD',
        request='Restore Source18r parameters and test saved May01 S0 against FAST_B within existing remaining Native/Phase-I budget; keep campaign HOLD',
        sources=sources,Native_reset=False,new_cycle=False,Worker=1,Threads=1,P2_calls=0,R2='HOLD')
    admit_resources(SimpleNamespace(path=output/'PLANNING_NATIVE_LEDGER.json',
        worker_lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),authorization={}),phase='SAVED_S0_DIAGNOSTIC_BUILD')
    model,objectives=materialize(master.snapshot,'2025-05-01')
    model.setObjective(objectives[0][1],gp.GRB.MINIMIZE);model.Params.Threads=1;model.update()
    context=dict(day=manifest['day'],arm='B1',stage='A1',stage_case_sha=receipt['case_sha'],
        source_sha=manifest['source_sha'],parent_result_sha=digest(manifest))
    diagnostic=dict(schema='TABLE_V_SAVED_PHASE_DIAGNOSTIC_V1',approved=True,production_result_promoted=False,
        current_release=release_identity(),snapshot_sha=master.snapshot.fingerprint(),native_binding=native_binding(model),
        frozen_records=sources+[matrix,file_record(E07/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json')],
        context=context,allowed_labels=['RELEASE_P1:A1:DW:PHASE_I:SOURCE18R_AUDIT:'+p.name for p in (SOURCE18R_FAST,FAST_B)])
    auth=deepcopy(read(E/'PLANNING_AUTHORIZATION.json'));auth.pop('fresh_native_cycle',None)
    auth.update(authorization_id='E08_REMAINING_SOURCE18R_'+output.name,
        authorized_ledger_path=str((output/'PLANNING_NATIVE_LEDGER.json').resolve()),
        carry_forward_ledgers=[oldledger],source_cases=[dict(day=manifest['day'],source_sha=manifest['source_sha'],source_identity=manifest['identity'])],
        human_approval_reference=human,authorized_arm_stages=['B1:A1'],saved_phase_i_diagnostic=diagnostic)
    _write(output/'PLANNING_AUTHORIZATION.json',auth)
    budget=TableVStageBudget(auth['authorized_ledger_path'],authorization=auth,historical_ledgers=HISTORY)
    budget.bind_saved_phase_diagnostic(master.snapshot)
    _write(output/'SAVED_DIAGNOSTIC_GATE.json',dict(PASS=True,authority=diagnostic,
        campaign_launch_authorized=False,historical_case_not_current_production=True))
    _write(head,dict(state='IN_PROGRESS',ledger_path=str(budget.path),authorization_sha=digest(auth),
        predecessor=oldledger,original_E08_ledger=original_e08))
    phase_used=sum(r['Native_Runtime'] for r in old['calls'] if r.get('solver')=='GUROBI'
        and r.get('label','').startswith('RELEASE_P1:A1:DW:PHASE_I:')
        and all(r.get('stage_context',{}).get(k)==v for k,v in dict(day='2025-05-01',arm='B1',stage='A1').items()))
    results=[]
    with budget.arm_context('B1'),budget.phase('A1',receipt['case_sha'],manifest['source_sha'],digest(manifest)),budget.capture_native_methods():
        cap=allowance(budget.remaining(),phase_used)
        _write(output/'BUDGET_BEFORE.json',dict(phase_used=phase_used,phase_remaining=cap,A1_remaining=budget.remaining(),
            predecessor=oldledger,saved_matrix=matrix,snapshot_sha=master.snapshot.fingerprint(),campaign_HOLD=True))
        if cap<=0:raise RuntimeError('NO_APPROVED_PHASE_I_REMAINDER_REPORT_BEFORE_NATIVE')
        try:
            model.setObjective(objectives[0][1],gp.GRB.MINIMIZE)
            for profile in (SOURCE18R_FAST,FAST_B):
                cap=allowance(budget.remaining(),phase_used)
                if cap<1.:break
                if any(file_record(r['path'])!=r for r in sources):raise RuntimeError('DIAGNOSTIC_SOURCE_FREEZE_DRIFT')
                folder=output/profile.name;folder.mkdir();model.reset();apply_policy(model,solver_policy(gp),gp)
                for key,value in profile.parameters().items():model.setParam(key,value)
                model.Params.LogFile=str(folder/'NATIVE_GUROBI.log')
                samples=[];stop=threading.Event();progress=[]
                def sample():
                    while True:
                        samples.append(memory_sample())
                        if stop.wait(.2):break
                def callback(m,where):
                    if where==gp.GRB.Callback.BARRIER:
                        progress.append(dict(iteration=m.cbGet(gp.GRB.Callback.BARRIER_ITRCNT),
                            primal=m.cbGet(gp.GRB.Callback.BARRIER_PRIMOBJ),dual=m.cbGet(gp.GRB.Callback.BARRIER_DUALOBJ),
                            primal_residual=m.cbGet(gp.GRB.Callback.BARRIER_PRIMINF),
                            dual_residual=m.cbGet(gp.GRB.Callback.BARRIER_DUALINF),
                            complementarity=m.cbGet(gp.GRB.Callback.BARRIER_COMPL),runtime=m.cbGet(gp.GRB.Callback.RUNTIME)))
                thread=threading.Thread(target=sample,daemon=True);thread.start()
                try:call=budget.solve(model,label='RELEASE_P1:A1:DW:PHASE_I:SOURCE18R_AUDIT:'+profile.name,cap=cap,callback=callback)
                finally:stop.set();thread.join()
                phase_used+=call['Native_Runtime'];raw={}
                if model.SolCount:raw['X']=np.asarray(model.getAttr('X'))
                if model.Status==gp.GRB.OPTIMAL:
                    raw.update(Pi=np.asarray(model.getAttr('Pi')),RC=np.asarray(model.getAttr('RC')))
                    try:raw.update(VBasis=np.asarray(model.getAttr('VBasis')),CBasis=np.asarray(model.getAttr('CBasis')))
                    except gp.GurobiError:pass
                np.savez_compressed(folder/'RAW_ATTRIBUTES.npz',**raw)
                diagnostics=residual_report(master.snapshot,raw,folder,master=master)
                log=(folder/'NATIVE_GUROBI.log').read_text(encoding='utf8',errors='replace')
                row=dict(profile=profile.name,parameters=profile.parameters(),status=int(model.Status),
                    Native_Runtime=float(model.Runtime),Work=float(model.Work),IterCount=float(model.IterCount),
                    BarIterCount=float(model.BarIterCount),snapshot_sha=master.snapshot.fingerprint(),
                    ledger_call=call,residuals=diagnostics,barrier_progress=progress,
                    presolve_lines=re.findall(r'Presolved:.*|Presolve removed.*|Presolve time:.*|Factor NZ.*|Factor Ops.*',log),
                    peak_sampled_RSS_bytes=max(s.get('RSS_bytes') or 0 for s in samples),
                    process_lifetime_peak_RSS_bytes=getattr(psutil.Process().memory_info(),'peak_wset',None),
                    certified_Global_LB=None,FULL_Phase_I_complete=False)
                _write(folder/'RESULT.json',row);results.append(row)
                _write(output/'RESULTS.json',dict(results=results,phase_used=phase_used,phase_remaining=allowance(budget.remaining(),phase_used),
                    A1_remaining=budget.remaining(),Native_reset=False,campaign_HOLD=True,old_E08_ledger_preserved=file_record(original_e08['path'])==original_e08))
                print(json.dumps({k:row[k] for k in ('profile','status','Native_Runtime','BarIterCount')}),flush=True)
        finally:model.dispose()
    # This descendant, rather than E08, is the only valid budget predecessor
    # for future work; E08 and its original Source Freeze stay immutable.
    _write(output/'CARRY_FORWARD_REQUIRED.json',dict(ledger=file_record(output/'PLANNING_NATIVE_LEDGER.json'),
        automatic_campaign_resume=False,new_budget=False,original_E08_ledger=original_e08))
    _write(head,dict(state='COMPLETE',ledger=file_record(budget.path),predecessor=oldledger,original_E08_ledger=original_e08))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
