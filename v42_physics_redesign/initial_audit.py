"""Read-only stop/provenance audit and actual original-CSR census."""
from .common import *
from .resource import inspect
from collections import Counter
import psutil

def main():
    prior.forbid_optimize();paths_audit('redesign_initial')
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    processes=[];owned=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            if not any(s in (p.info['name'] or '').lower() for s in ('python','gurobi')):continue
            cmd=' '.join(p.info['cmdline'] or []);cwd=None
            try:cwd=p.cwd()
            except psutil.Error:pass
            belongs=str(OLD_ZF).lower() in (cmd+' '+str(cwd)).lower() or '-m v42_zf_recourse.' in cmd
            record=dict(pid=p.pid,creation_epoch=p.info['create_time'],command=cmd,cwd=cwd,belongs_to_previous_ZF=belongs,protected=not belongs);processes.append(record)
            if belongs:owned.append(record)
        except psutil.Error:pass
    assert not owned,'PREVIOUS_ZF_STILL_ACTIVE: do not terminate by guessed PID'
    files={}
    for folder in [OLD_ZF/'artifacts',OLD_ZF/'logs',OLD_ZF/'reports',OLD_ZF/'checkpoints',OLD_ZF/'repo/v42_zf_recourse']:
        for p in folder.rglob('*'):
            if p.is_file():files[str(p.relative_to(OLD_ZF)).replace('\\','/')]=dict(sha256=sha(p),bytes=p.stat().st_size)
    stop=dict(PASS=True,previous_workspace=str(OLD_ZF),status='ALREADY_COMPLETED_READ_ONLY_PRESERVATION',actual_live_owned_process_count=0,live_processes=processes,termination_requested=False,force_terminated=False,completed_native_ledger=read(OLD_ZF/'checkpoints/OPTIMIZE_CALL_LEDGER.json'),preserved_files=files,completed_PID_and_creation_time='NOT_AVAILABLE after process exit; not fabricated',source_git_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=OLD_ZF/'repo',text=True).strip(),native_status_unchanged=9,previous_last_written_classification=read(OLD_ZF/'reports/FINAL_DECISION.json')['classification'],independent_battery_certificate_present=(OLD_ZF/'reports/INDEPENDENT_BATTERY_EXACT_CERTIFICATE.json').exists(),previous_review_not_finalized_after_late_certificate_due_to_user_switch=True,May12_or_other_A_process_stopped_or_modified=False)
    write(REPORTS/'PREVIOUS_ZF_STOP_AUDIT.json',stop)
    inspect('redesign_before_readonly_analysis')
    A,d,start=hc.load();objective=prior.objective_identity(A,d);names=list(map(str,d['names']));rn=list(map(str,d['row_names']))
    vc=Counter(n.split('[')[0] for n in names);rc=Counter(n.split('[')[0] for n in rn)
    rootpath=ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz'
    with np.load(rootpath) as f:root={k:f[k].copy() for k in f.files}
    write(REPORTS/'SOURCE_CENSUS.json',dict(source_BASE=BASE,objective_identity=objective,rows=A.shape[0],columns=A.shape[1],nnz=A.nnz,variable_families=vc,row_families=rc,root_fields={k:list(v.shape) for k,v in root.items()},root_source=str(rootpath),root_source_SHA256=sha(rootpath),root_receipt=read(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/RESULT.json'),scientific_input_SHAs={n:sha(hc.PARENT/n) for n in ('C3A_A.npz','C3A_DATA.npz','C3A_VALID_START.npz')},archived_global_LB=LB,archived_valid_UB=UB,target_LB_for_0p5pct=UB*.995,M1_ACCEPTED=False,all_new_native_optimize_calls=0))
    print('SOURCE_CENSUS',json.dumps(clean(dict(variable_families=vc,row_families=rc,root_fields=list(root)))),flush=True)

if __name__=='__main__':main()
