"""Frozen same-x pilot: no full-scale master optimize until a certified x0 cut."""
import gzip,json,time,xml.etree.ElementTree as ET
import numpy as np
import gurobipy as gp
from v42_benders.engine import configure
from v42_benders.certificates import Uncertifiable
from v42_benders_v2.recourse import Recourse
from v42_benders_v2.engine import certified
from v42_benders_fullscale.controller import snapshot
from v42_benders_fullscale.candidates import persist,load
from v42_benders_fullscale.runner import b3_validator
from .common import *
from .exact import create
from .independent import verify

def freeze_check():
    preserve();p=read('EXECUTION_FREEZE.json')
    for r in p['sources']:assert sha(ROOT/r['path'])==r['sha256'],'FROZEN_SOURCE_CHANGED'
    assert p['source_commit']==git('rev-parse','HEAD'),'EXECUTION_HEAD_CHANGED'
    committed=subprocess.check_output(['git','show',p['preregistration_commit']+':docs/v42_m1_benders_x0_certificate_repair/PREREGISTRATION.json'],cwd=ROOT)
    assert hashlib.sha256(committed).hexdigest()==sha(OUT/'PREREGISTRATION.json')
    assert read('FIXTURE_REGRESSION.json')['PASS']

def assess(n,env,x,index):
    freeze_check();directory=OUT/('X0' if index==0 else 'X1');directory.mkdir(exist_ok=True)
    xcheck,xr=load_x0() if index==0 else load(OUT,1,n)
    assert np.array_equal(x,xcheck),'SAVED_SOURCE_X_MISMATCH'
    resources=snapshot();assert not resources['other_heavy_solve'],'OTHER_HEAVY_SOLVE_STOP'
    dump('RECOURSE_STARTED.json',dict(source_x_hash=digest_arrays(x),started_UTC=stamp(),resource=resources,
        source_commit=git('rev-parse','HEAD'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        source_saved_verified_before_optimize=True,threads=4,separate_native_budget=1800,separate_PhaseI_budget=1800),directory)
    row=dict(index=index,source_x_hash=digest_arrays(x),native_status=None,native_seconds=None,native_certificate_valid=False,
        completed_certificate_valid=False,PhaseI_used=False,PhaseI_terminal=False,PhaseI_status=None,PhaseI_seconds=None,witness=False)
    start=time.perf_counter();lp=Recourse(n,env,directory/'native',threads=4,objective=False);cut=None
    try:
        raw=lp.solve(x,max(.001,1800-(time.perf_counter()-start)))
        row.update(native_status=raw['status'],native_seconds=raw['seconds'],Kappa=raw['Kappa'],warnings=raw['warnings'],native_raw=raw['persistence'])
        dump('NATIVE_RAW_RECEIPT.json',dict(status=raw['status'],persistence=raw['persistence'],vector_sha256=raw.get('vector_sha256'),
            source_x_hash=digest_arrays(x),Kappa=raw['Kappa'],warnings=raw['warnings'],seconds=raw['seconds']),directory)
        if raw['status']==2:
            check=b3_validator(None,n,n.assemble(x,np.asarray(raw['primal']))) if lp.primal_valid(raw) else dict(PASS=False)
            dump('WITNESS_VALIDATION.json',check,directory)
            row.update(witness=bool(check.get('PASS')),status='STOP_NUMERICAL_FEASIBILITY_INCONSISTENCY' if index==0 else 'VALIDATED_THRESHOLD_WITNESS' if check.get('PASS') else 'STOP_UNVALIDATED_FEASIBLE_POINT')
            row['numerical_contradiction']=bool(index==0 and check.get('PASS'))
            return row,None
        if raw['status'] in [11,12,13,4]:row['status']='STOP_UNSAFE_NATIVE';return row,None
        try:
            certified(n,raw,'native_farkas');row['native_certificate_valid']=True
        except (Uncertifiable,ValueError,TypeError,KeyError) as e:row['native_rejection']=str(e)
        try:
            cut=create(n,raw);cut['independent_validation']=verify(n,cut);row['completed_certificate_valid']=True
        except (Uncertifiable,ValueError,TypeError,KeyError) as e:
            row['completed_rejection']=str(e)
            dump('NATIVE_CERTIFICATE_REJECTION.json',row,directory)
            freeze_check();phase_start=time.perf_counter();phase=Recourse(n,env,directory/'phase1',threads=4,phase=True,objective=False)
            row['PhaseI_used']=True
            try:
                aux=phase.solve(x,max(.001,1800-(time.perf_counter()-phase_start)))
                row.update(PhaseI_status=aux['status'],PhaseI_seconds=aux['seconds'],PhaseI_terminal=aux['status']==2,
                    PhaseI_raw=aux['persistence'],PhaseI_warnings=aux['warnings'])
                dump('PHASE1_RAW_RECEIPT.json',dict(status=aux['status'],seconds=aux['seconds'],persistence=aux['persistence'],
                    source_x_hash=digest_arrays(x),warnings=aux['warnings']),directory)
                if not phase.primal_valid(aux):raise Uncertifiable('PHASE1_NONTERMINAL_OR_PRIMAL')
                cut=create(n,aux);cut['independent_validation']=verify(n,cut);row['completed_certificate_valid']=True
            except (Uncertifiable,ValueError,TypeError,KeyError) as e:row['PhaseI_rejection']=str(e)
            finally:phase.close()
        row['status']='CERTIFIED_SEPARATING_CUT' if cut is not None else 'STOP_UNCERTIFIABLE'
        return row,cut
    finally:
        row['candidate_wall_seconds']=time.perf_counter()-start;lp.close()

def save_cut(n,cut,index,master=None,xvar=None):
    validation=verify(n,cut)
    if master is not None:
        master.addConstr(cut['record']['intercept']+cut['coefficients']@xvar>=0,name='exact_completed_cut_'+str(index));master.update()
    np.savez_compressed(OUT/f'CUT_{index:03d}.npz',coefficients=cut['coefficients'],intercept=np.array([cut['record']['intercept']]))
    payload=dict(record=cut['record'],independent_validation=validation,inserted=master is not None,
        coefficients_sha256=sha(OUT/f'CUT_{index:03d}.npz'),replayed_before_insertion=True)
    dump(f'CUT_{index:03d}.json',payload)
    return dict(CUT_ID='EXACT-'+cut['record']['cut_hash'][:20],source_x_hash=cut['record']['source_x_hash'],cut_hash=cut['record']['cut_hash'],
        source_violation=cut['record']['strict_margin'],valid=True,inserted=master is not None,artifact_sha256=sha(OUT/f'CUT_{index:03d}.json'))

def master_gate(n,cut):
    if cut is None:return False
    verify(n,cut)
    return True

def run():
    freeze_check();assert not (OUT/'ISOLATED_EXPERIMENT_STARTED.json').exists(),'NO_RESULT_DRIVEN_RERUN'
    suite=ET.parse(OUT/'PREFLIGHT_TEST_RESULTS.xml').getroot().find('testsuite');assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0 and int(suite.attrib['tests'])>=825
    dump('ISOLATED_EXPERIMENT_STARTED.json',dict(created_UTC=stamp(),source_commit=git('rev-parse','HEAD'),
        freeze_sha256=sha(OUT/'EXECUTION_FREEZE.json'),new_x0_master_optimize_calls=0))
    n,old=load_native();x0,xr=load_x0();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    master=None;cuts=[];calls=[];x1=None;master_calls=0;proof=False;reason=None;status='INCONCLUSIVE'
    try:
        r0,c0=assess(n,env,x0,0);calls.append(r0);dump('X0_ISOLATED_RECOURSE.json',r0)
        dump('X0_CERTIFICATE.json',dict(valid=c0 is not None,raw_native_valid=r0['native_certificate_valid'],
            kind=None if c0 is None else c0['record']['kind'],source_x_hash=X0,reason=r0.get('completed_rejection'),
            PhaseI_used=r0['PhaseI_used'],native_raw_preserved=True))
        if master_gate(n,c0):
            freeze_check();master=gp.Model('PR117_X0_AFTER_CERTIFIED_CUT',env=env);configure(master,1,60,OUT/'master_x1.log')
            xv=master.addMVar(len(n.xi),lb=n.xlower,ub=n.xupper,vtype='B',name='complete_original_B3')
            dr=np.flatnonzero(np.diff(n.A.indptr)==0);master.addMConstr(n.B[dr],xv,n.sense[dr],n.b[dr]);master.setObjective(0.);master.update()
            cuts.append(save_cut(n,c0,0,master,xv));master.optimize();master_calls+=1
            if master.Status==3:proof=True;status='B3_POSITIVE_CERTIFIED'
            elif master.SolCount and master.Status in [2,9]:
                x1=np.rint(xv.X);assert np.max(abs(xv.X-x1),initial=0)<=1e-7
                assert digest_arrays(x1)!=X0,'MASTER_REPEAT_AFTER_VALID_CUT'
                resource=snapshot();assert not resource['other_heavy_solve']
                receipt=persist(OUT,1,n,x1,master,[cuts[0]['CUT_ID']],resource,'PILOT')
                receipt.update(repair_preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),repair_freeze_sha256=sha(OUT/'EXECUTION_FREEZE.json'),
                    parent_PR117_x0=X0,created_only_after_valid_cut=True,new_x0_created=False)
                dump('MASTER_X_001_RECEIPT.json',receipt);x1,checked=load(OUT,1,n);dump('MASTER_X1_RECEIPT.json',checked)
                print('VALID CUT #1 AND DISTINCT PERSISTED X1',receipt['vector_sha256'],flush=True)
                r1,c1=assess(n,env,x1,1);calls.append(r1);dump('X1_RECOURSE.json',r1)
                if c1 is not None:cuts.append(save_cut(n,c1,1,master,xv));status='X0_CUT_X1_SECOND_CUT'
                elif r1.get('witness'):status='X0_CUT_X1_WITNESS'
                else:status='X0_CUT_X1_STOP_UNCERTIFIABLE';reason=r1['status']
            else:status='MASTER_NO_X1';reason=str(master.Status)
        else:reason=r0['status']
    except (Uncertifiable,ValueError,AssertionError,OSError,gp.GurobiError) as e:
        reason=str(e);status='STOP_UNCERTIFIABLE'
    finally:
        if master is not None:master.dispose()
        env.dispose()
    witness=bool(len(calls)>1 and calls[1].get('witness'));contradiction=bool(calls and calls[0].get('numerical_contradiction'))
    classification='B3_POSITIVE_CERTIFIED' if proof else 'B3_NEGATIVE_CERTIFIED' if witness else 'B3_INCONCLUSIVE'
    for name in ['CUT_000.json','MASTER_X1_RECEIPT.json','X1_RECOURSE.json']:
        if not (OUT/name).exists():dump(name,dict(status='NOT_AVAILABLE' if name.startswith('CUT') else 'NOT_RUN',reason=reason or status))
    ub=.5912812634331275;lb=.5722125039436496
    flags=dict(status=status,reason=reason,exact_PR117_x0_reused=True,new_x0_created=False,new_x0_master_optimize_calls=0,
        master_optimize_calls_after_valid_cut=master_calls,valid_cut_count=len(cuts),cuts=cuts,distinct_x_count=1+int(x1 is not None),
        x1_generated=x1 is not None,recourse1_run=len(calls)>1,BENDERS_PILOT_MINIMUM_PROVEN=bool(cuts and x1 is not None),
        numerical_contradiction=contradiction,uncertified_cuts_inserted=0,B3_classification=classification,
        full_B3_progress_gate=bool(cuts and x1 is not None and not contradiction and 'STOP' not in status),
        full_B3_RUN=False,full_M1_canary_RUN=False,production_M1_RUN=False,P1_ACCEPTED=False,M1_ACCEPTED=False,
        P2_RUN=False,A2_RUN=False,M2_RUN=False,PROBLEM13_FINAL_VALIDATED=False,original_M1_UB=ub,inherited_valid_LB=lb,
        new_V2_global_LB=None,gap=(ub-lb)/ub,Actual_P_correction=False,Actual_Q_correction=False,B0_B1_RUN=False,
        fullscale_evaluations=len(calls),fullscale_recourses=calls,historical_PR115_x='NOT_AVAILABLE',causal_speedup_claim=False)
    dump('FINAL_FLAGS.json',flags);dump('FINAL_VERDICT.json',dict(verdict=classification if proof or witness else 'INCONCLUSIVE',
        pilot_result=status,minimum_pilot_completed=flags['BENDERS_PILOT_MINIMUM_PROVEN'],B3=classification,
        current_blocker=reason or 'No full B3 witness/proof or original M1 optimization in isolated certificate pilot',
        P1_ACCEPTED=False,M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))
    dump('FULL_B3_AUTHORIZATION.json',dict(progress_gate=flags['full_B3_progress_gate'],authorized=False,status='NOT_RUN',reason='This preregistered task is isolated x0/x1 certificate pilot'))
    dump('FULL_M1_CANARY_AUTHORIZATION.json',dict(progress_gate=bool(proof or witness or (len(cuts)>=2 and flags['distinct_x_count']>=3 and 'STOP' not in status)),
        authorized=False,status='NOT_RUN',reason='No expanded run in this preregistered isolated pilot'))
    print('FINAL',status,'cuts',len(cuts),'x1',x1 is not None,flush=True)

if __name__=='__main__':run()
