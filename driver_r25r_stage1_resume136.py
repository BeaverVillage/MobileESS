#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
HOME=Path.home();WORK=HOME/'mobile_ess_work';ART=WORK/'frozen_artifacts'
ROOT=WORK/'build7c_r25r_stage1_resume136_retained_optimal_dual'
SCI_BUNDLE=HERE/'R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz'
EXPECTED_SCI_SHA='4c2e39b4f136f36a6d3c13f61acb93a7f32b256cfc75d06404cef8fe9ddf312d'
MAIN_SHA='911abe18479524b8e48cc058c4a6ed3b8ab9ce673d4de78780a71ca3b7f0a5cd'
DECOMP_SHA='cab1b8cef906b08eaaa75d5e044fcb34ffc45183b24c5c4d8cfddb3508c58795'
PROOF_SHA='d63ff9e0592d364b5e0928d95e7d345152c42470d7f8a4bb780eac7f869057e6'
R25Q_PROOF_SHA='15df79c2e9c5c648e5a6dec275b32aa0cdb973bff31b4535b09ef9298b084f4c'
R25R_PROOF_SHA='afbb09a77fb5ca15e7f683a3c3ab984048558ca29e28c2f3cc391a078eef66b5'
UNLIMITED_SMOKE_SHA='cda5bb6f18a52b595f63a5e882a0ac8aa99de8edb5f49d5e2a544d742a5e7ca8'
UNIT_SMOKE_SHA='dee2ab62d8366dfce6247f90ca41a0cf479b4e34ddd732a51aa5de6dc3d3ec87'
POLISH_SMOKE_SHA='201f6c21a65bb1f72091715ed621eb5cf47d001e489795081d7e5162f6296426'
PARENT_R25P_NAME='ConversationA_R25P_STAGE1_54_OF_54_RUNTIME_RESULT_20260814T021940.tar.gz'
PARENT_R25P_SHA='0ed41aa7bdc1f055dde5fd7c50e4ceffb4d4cc0a1795d0ec1b37d49481fa9833'
PARENT_R25Q_NAME='ConversationA_R25Q_STAGE1_54_OF_54_RUNTIME_RESULT_20260814T101350.tar.gz'
PARENT_R25Q_SHA='8d8c8f15bdfbc3e9200aeebb88f8a262f4da2e727d1155ac76b989f42b7cc2b0'
RESUME_WRAPPER_SHA='9800ab463f99727ecf551f228953dbe1467f9e748ef1727e2bad92673568e66a'
RESUME_STATE_SHA='94eb40044d0089ce26fcc298675952a5a154277e48371412c4871edb447b7625'
VALIDATE_ROOT_ONLY=(os.environ.get('MOBILEESS_R25R_VALIDATE_ISSUE136_ROOT_ONLY','0')=='1')
THREADS=4

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def finite_json(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {k:finite_json(v) for k,v in value.items()}
    if isinstance(value,list):return [finite_json(v) for v in value]
    return value

def jw(path,value):
    Path(path).write_text(json.dumps(finite_json(value),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def loadj(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:return {}

def parse_last_json(text):
    for i in range(len(text)-1,-1,-1):
        if text[i]!='{':continue
        try:
            value=json.loads(text[i:])
            if isinstance(value,dict):return value
        except Exception:pass
    return {}

def run_json(script,cwd):
    cp=subprocess.run([sys.executable,str(script)],cwd=cwd,capture_output=True,text=True)
    value=parse_last_json(cp.stdout)
    if cp.returncode!=0 or value.get('PASS') is not True:
        raise RuntimeError(f'preflight failed: {Path(script).name}\n{cp.stdout[-5000:]}\n{cp.stderr[-3000:]}')
    return value

ART.mkdir(parents=True,exist_ok=True)
if ROOT.exists():shutil.rmtree(ROOT)
ROOT.mkdir(parents=True)

if sha(SCI_BUNDLE)!=EXPECTED_SCI_SHA:raise RuntimeError('R25R science bundle SHA drift')
SCI=ROOT/'science';SCI.mkdir()
with tarfile.open(SCI_BUNDLE,'r:gz') as tf:
    try:tf.extractall(SCI,filter='data')
    except TypeError:tf.extractall(SCI)

checksum_rows=[]
for line in (SCI/'CHECKSUMS.sha256').read_text(encoding='utf-8').splitlines():
    if not line.strip():continue
    digest,rel=line.split('  ',1);path=SCI/rel
    checksum_rows.append((rel,path.is_file() and sha(path)==digest))
if not checksum_rows or not all(ok for _,ok in checksum_rows):
    raise RuntimeError('R25R CHECKSUMS mismatch '+repr([rel for rel,ok in checksum_rows if not ok][:10]))
if any((actual!=expected) for actual,expected in [
    (sha(SCI/'main.py'),MAIN_SHA),
    (sha(SCI/'r25m_b6_exact_path_decomposition.py'),DECOMP_SHA),
    (sha(SCI/'r25p_stage1_unlimited_completion_proof_test.py'),PROOF_SHA),
    (sha(SCI/'r25q_numerical_envelope_resume_proof_test.py'),R25Q_PROOF_SHA),
    (sha(SCI/'r25r_retained_optimal_dual_resume_proof_test.py'),R25R_PROOF_SHA),
    (sha(SCI/'r25p_unlimited_gurobi_policy_smoke.py'),UNLIMITED_SMOKE_SHA),
    (sha(SCI/'r25o_b6c5r4r1_gurobi_unit_equivalence_smoke.py'),UNIT_SMOKE_SHA),
    (sha(SCI/'r25n_b6c5r4_gurobi_polish_smoke.py'),POLISH_SMOKE_SHA),
]):raise RuntimeError('R25R source hash drift')

compile_files=[
    'main.py','r25m_b6_exact_path_decomposition.py',
    'r25p_stage1_unlimited_completion_proof_test.py',
    'r25q_numerical_envelope_resume_proof_test.py',
    'r25r_retained_optimal_dual_resume_proof_test.py',
    'r25p_unlimited_gurobi_policy_smoke.py',
    'r25o_b6c5r4r1_gurobi_unit_equivalence_smoke.py',
    'r25n_b6c5r4_gurobi_polish_smoke.py',
]
subprocess.run([sys.executable,'-m','py_compile',*[str(SCI/name) for name in compile_files]],check=True)
self_test=subprocess.run([sys.executable,str(SCI/'release_self_test.py')],cwd=SCI,capture_output=True,text=True)
if self_test.returncode!=0:
    raise RuntimeError('R25R release_self_test failed '+self_test.stdout[-6000:]+self_test.stderr[-4000:])
proof=run_json(SCI/'r25p_stage1_unlimited_completion_proof_test.py',SCI)
r25q_proof=run_json(SCI/'r25q_numerical_envelope_resume_proof_test.py',SCI)
r25r_proof=run_json(SCI/'r25r_retained_optimal_dual_resume_proof_test.py',SCI)
unlimited_smoke=run_json(SCI/'r25p_unlimited_gurobi_policy_smoke.py',SCI)
unit_smoke=run_json(SCI/'r25o_b6c5r4r1_gurobi_unit_equivalence_smoke.py',SCI)
polish_smoke=run_json(SCI/'r25n_b6c5r4_gurobi_polish_smoke.py',SCI)

preflight={
    'release':'R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME136',
    'status':'PASS_PREFLIGHT','checksums':len(checksum_rows),
    'release_self_test_rc':self_test.returncode,'unlimited_proof':proof,'R25Q_proof':r25q_proof,'R25R_proof':r25r_proof,
    'unlimited_Gurobi_smoke':unlimited_smoke,
    'unit_equivalence_Gurobi_smoke':unit_smoke,
    'fixed_QCP_polish_Gurobi_smoke':polish_smoke,
    'parent_R25P_chain_sha256':PARENT_R25P_SHA,'parent_R25Q_failed_run_sha256':PARENT_R25Q_SHA,
    'science_bundle_sha256':EXPECTED_SCI_SHA,
    'runtime_policy':{
        'authoritative_issue_axis':[113,166],'issue_count':54,'verified_prefix_issues':23,'resume_issue':136,
        'processes':1,'threads':THREADS,'global_gap_target':0.03,
        'root_CG_time_limit_s':None,'root_CG_iteration_limit':None,
        'restricted_integer_time_limit_s':None,'polish_time_limit_s':None,
        'branch_price_time_limit_s':None,'branch_price_node_limit':None,
        'child_CG_time_limit_s':None,'child_CG_iteration_limit':None,
        'complete_MW_MWh_normalization':True,'fixed_integer_continuous_QCP_polish':True,
        'exact_child_QCP_and_pricing':True,'certificate_fail_closed_before_commit':True,
        'bounded_RC_envelope_hard_cap':5e-4,'measured_envelope_subtracted_from_lower_bound':True,
    },
    'scientific_model_changed':False,'objective_changed':False,
    'causality_changed':False,'gap_semantics_changed':False,'long_solver_run':False,
}
jw(ROOT/'R25R_STAGE1_RESUME136_BOOTSTRAP_PREFLIGHT.json',preflight)
if os.environ.get('MOBILEESS_B6_PREFLIGHT_ONLY','0')=='1':
    print('PASS_R25R_STAGE1_RESUME136_PREFLIGHT_ONLY');raise SystemExit(0)

# Cryptographically bind the full verified issue113..135 prefix.  The first
# three records chain to R25P; issue116..135 are re-audited from the R25Q tree.
r25p_archive=ART/PARENT_R25P_NAME
if not r25p_archive.is_file() or sha(r25p_archive)!=PARENT_R25P_SHA:
    raise RuntimeError('R25R R25P chain archive missing or SHA drift')
parent_archive=ART/PARENT_R25Q_NAME
if not parent_archive.is_file() or sha(parent_archive)!=PARENT_R25Q_SHA:
    raise RuntimeError('R25R verified R25Q parent archive missing or SHA drift')
RESUME=ROOT/'verified_parent_prefix';RESUME.mkdir()
required={
    'summary':'ConversationA_R25Q_STAGE1_54_OF_54_RUNTIME_RESULT.json',
    'state':'stage1_54_of_54/issue_000135/BUILD7C_POSTCOMMIT_STATE.json',
    'moves':'stage1_54_of_54/issue_000135/BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv',
    'mess':'stage1_54_of_54/issue_000135/BUILD7B_FULL54_MESS_PLAN.csv',
}
for issue in range(116,136):
    required[f'decomp{issue}']=f'stage1_54_of_54/issue_{issue:06d}/ConversationA_R25M_B6_EXACT_DECOMPOSITION_AUDIT.json'
    required[f'transition{issue}']=f'stage1_54_of_54/issue_{issue:06d}/BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json'
    required[f'exact{issue}']=f'stage1_54_of_54/issue_{issue:06d}/exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json'
with tarfile.open(parent_archive,'r:gz') as tf:
    for key,member_name in required.items():
        member=tf.getmember(member_name);stream=tf.extractfile(member)
        if stream is None:raise RuntimeError('R25R parent member unreadable '+member_name)
        (RESUME/key).write_bytes(stream.read())
if sha(RESUME/'state')!=RESUME_WRAPPER_SHA:raise RuntimeError('R25R resume wrapper SHA drift')
state_wrapper=loadj(RESUME/'state')
if state_wrapper.get('sha256')!=RESUME_STATE_SHA or (state_wrapper.get('state') or {}).get('issue_step')!=136:
    raise RuntimeError('R25R issue136 PRE-state authority mismatch')
parent_summary=loadj(RESUME/'summary')
parent_records={int(x.get('issue')):x for x in parent_summary.get('issues',[]) if isinstance(x,dict)}
parent_prefix=[]
if (parent_summary.get('parent_R25P_runtime_result_sha256')!=PARENT_R25P_SHA or
    parent_summary.get('physical_state_committed_through_issue')!=135):
    raise RuntimeError('R25R parent chain/progress authority mismatch')
for issue in range(113,116):
    rec=parent_records.get(issue,{})
    try:gap=float(rec.get('global_certified_gap'))
    except Exception:gap=float('inf')
    if not (rec.get('pass') is True and gap<=0.03+1e-12 and rec.get('source_parent_sha256')==PARENT_R25P_SHA):
        raise RuntimeError(f'R25R inherited prefix issue {issue} is not authoritative')
    parent_prefix.append({'issue':issue,'pass':True,'global_certified_gap':gap,
                          'source_parent_sha256':PARENT_R25P_SHA,'chain_parent_sha256':PARENT_R25Q_SHA})
for issue in range(116,136):
    decomp=loadj(RESUME/f'decomp{issue}');transition=loadj(RESUME/f'transition{issue}');exact=loadj(RESUME/f'exact{issue}')
    try:gap=float(decomp.get('global_certified_gap'))
    except Exception:gap=float('inf')
    ok=bool(parent_records.get(issue,{}).get('pass') is True and decomp.get('certificate_pass') is True and
            decomp.get('pricing_closed') is True and gap<=0.03+1e-12 and
            transition.get('status')=='PASS' and transition.get('h0_only_committed') is True and
            exact.get('hard_constraint_pass') is True)
    if not ok:raise RuntimeError(f'R25R parent prefix issue {issue} is not authoritative')
    parent_prefix.append({'issue':issue,'pass':True,'global_certified_gap':gap,'source_parent_sha256':PARENT_R25Q_SHA})
if len(parent_prefix)!=23 or [x['issue'] for x in parent_prefix]!=list(range(113,136)):
    raise RuntimeError('R25R verified prefix must be exactly issue113..135')
(RESUME/'resume_state.json').write_bytes((RESUME/'state').read_bytes())
(RESUME/'resume_moves.csv').write_bytes((RESUME/'moves').read_bytes())
(RESUME/'resume_mess.csv').write_bytes((RESUME/'mess').read_bytes())

child=ROOT/'stage1_child.py'
child.write_text("""import importlib.util,sys\nfrom pathlib import Path\nSCI=Path(sys.argv[1]);OUT=Path(sys.argv[2]);WORK=Path(sys.argv[3]);OUT.mkdir(parents=True,exist_ok=True)\nsys.path.insert(0,str(SCI))\nspec=importlib.util.spec_from_file_location('r25p_stage1_science',SCI/'main.py');mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)\nraise SystemExit(int(mod.rolling54_main(OUT,WORK)))\n""",encoding='utf-8')

env=os.environ.copy()
for key in [
    'MOBILEESS_GUROBI_NUMERICFOCUS','MOBILEESS_GUROBI_MIPFOCUS','MOBILEESS_GUROBI_CUTS',
    'MOBILEESS_GUROBI_PREMIQCPFORM','MOBILEESS_GUROBI_PRESOLVE','MOBILEESS_GUROBI_MIRCUTS',
    'MOBILEESS_GUROBI_FLOWCOVERCUTS','MOBILEESS_GUROBI_CONCURRENTMIP','MOBILEESS_GUROBI_SYMMETRY',
    'MOBILEESS_GUROBI_NODEMETHOD','MOBILEESS_GUROBI_WORKLIMIT','MOBILEESS_GUROBI_BESTOBJSTOP',
    'MOBILEESS_GUROBI_CUTOFF','MOBILEESS_GUROBI_TIMELIMIT',
    'MOBILEESS_R25M_B6_CG_TIMELIMIT','MOBILEESS_R25M_B6_INTEGER_TIMELIMIT',
    'MOBILEESS_R25M_B6R3_BP_TIMELIMIT','MOBILEESS_R25M_B6R3_BP_NODE_LIMIT',
    'MOBILEESS_R25M_B6R3_BP_NODE_CG_TIMELIMIT','MOBILEESS_R25N_B6C5R4_POLISH_TIMELIMIT',
    'MOBILEESS_R25M_B6_MAX_CG_ITER','MOBILEESS_R25J_B3_SCREEN_ONLY',
    'MOBILEESS_R25M_B6_SCREEN_ONLY','MOBILEESS_R25M_B6_SCREEN_ISSUE',
    'MOBILEESS_R25N_B6C5R2_THREAD_SCREEN','MOBILEESS_R25N_B6C5R2_ROOT_FORENSIC_ONLY',
    'MOBILEESS_R25O_B6C5R4R1_ROOT_PRICING_ONLY','MOBILEESS_RESUME_STATE_SHA256',
    'MOBILEESS_R25Q_RESUME_STATE_PATH','MOBILEESS_R25Q_RESUME_HINT_DIR',
    'MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES','MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE',
    'MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP','MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET',
]:env.pop(key,None)

env.update({
    'MOBILEESS_OPT_HORIZON_STEPS':'54','MOBILEESS_GUROBI_THREADS':str(THREADS),
    'MOBILEESS_GUROBI_ECON_MIPGAP':'0.03','MOBILEESS_GUROBI_ROOT_METHOD':'2',
    'MOBILEESS_EXACT_PCC_LEAF_ELIM':'0','MOBILEESS_EXACT_IMPLIED_BOUNDS':'1','MOBILEESS_BR14_PRODUCTION':'1',
    'MOBILEESS_BULK_MOBILITY_VARS':'1','MOBILEESS_VECTOR_K3_PARETO':'1','MOBILEESS_DISABLE_PARETO_CACHE':'1',
    'MOBILEESS_WORKER_FOUNDATION_CACHE':'0','MOBILEESS_GUROBI_SOFTMEMLIMIT_GB':'8.0','MOBILEESS_FINAL_HEURISTICS':'0.05',
    'MOBILEESS_R24_PERMANENT_EXACT_REBASE':'1','MOBILEESS_R25A_FORWARD_BACKWARD_PRUNE':'1',
    'MOBILEESS_R25B_ROUTE_DOMINANCE_AUDIT':'1','MOBILEESS_R25D_RADIAL_GRID_PROJECTION':'1',
    'MOBILEESS_R25E_NODE_ARC_EXACT':'1','MOBILEESS_R25E_PERSISTENT_STATIC_CONTEXT':'1',
    'MOBILEESS_R25G_HYBRID_STAY_BINARY':'1','MOBILEESS_R25H_B1_CERTIFICATE_FOCUS':'1',
    'MOBILEESS_R25I_B2_NUMERICAL_RESCALING':'1','MOBILEESS_R25K_B4_ROOT_BRANCH_STRENGTHENING':'1',
    'MOBILEESS_R25M_B6_EXACT_DECOMPOSITION':'1','MOBILEESS_R25M_B6_KBEST':'64',
    'MOBILEESS_R25M_B6_PRICING_BATCH':'16','MOBILEESS_R25M_B6_RC_AUDIT_TOL':'1e-4',
    'MOBILEESS_R25M_B6_PRICING_TOL':'1e-7','MOBILEESS_R25N_B6C5R2_BARQCP_TOL':'1e-9',
    'MOBILEESS_R25M_B6R3_PRIMAL_KBEST':'96','MOBILEESS_R25N_B6C5R3_PRIMAL_HEURISTICS':'0.20',
    'MOBILEESS_R25M_B6R3_BRANCH_PRICE':'1','MOBILEESS_R25M_B6C2_CHILD_PRICING_BATCH':'16',
    'MOBILEESS_R25M_B6C3_DUAL_STABILIZATION':'0','MOBILEESS_R25M_B6C4_STRONG_BRANCHING':'0',
    'MOBILEESS_R25N_B6C5R3_MOBILITY_FIRST':'1','MOBILEESS_R25N_B6C5R3_FIXED_DUAL_MULTIWAY':'0',
    'MOBILEESS_R25N_B6C5R1_FIXED_DUAL_PREPASS':'0',
    'MOBILEESS_R25N_B6C5R4_COMPLETE_UNIT_NORMALIZATION':'1',
    'MOBILEESS_R25N_B6C5R4_FIXED_INTEGER_QCP_POLISH':'1',
    'MOBILEESS_R25N_B6C5R4_DISABLE_FIXED_DUAL_PREPASS':'1',
    'MOBILEESS_R25N_B6C5R4_POLISH_CONSTRVIO_GATE':'1e-6',
    'MOBILEESS_R25N_B6C5R4_POLISH_BOUNDVIO_GATE':'1e-7',
    'MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION':'1',
    'MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE':'1','MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP':'5e-4',
    'MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET':'2',
    'MOBILEESS_R25Q_RESUME_STATE_PATH':str(RESUME/'resume_state.json'),
    'MOBILEESS_R25Q_RESUME_HINT_DIR':str(RESUME),
    'MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME':'resume_moves.csv',
    'MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME':'resume_mess.csv',
    'MOBILEESS_R25Q_RESUME_SOURCE':f'R25Q SHA {PARENT_R25Q_SHA} issue135 POST == issue136 PRE',
    'MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES':'23','MOBILEESS_RESUME_STATE_SHA256':RESUME_STATE_SHA,
    'MOBILEESS_ROLL_START':'113','MOBILEESS_ROLL_COUNT':'54','MOBILEESS_RESUME_ISSUE':'136',
    'MOBILEESS_GUROBI_MIQCPMETHOD':'-1',
})
if VALIDATE_ROOT_ONLY:env['MOBILEESS_R25O_B6C5R4R1_ROOT_PRICING_ONLY']='1'

run=ROOT/'stage1_54_of_54';run.mkdir()
stdout=run/'R25R_STAGE1_RESUME136_STDOUT_STDERR.txt'
print('[R25R] verified issues 113..135 retained; authoritative continuation 136..166; no solver time/node limits.',flush=True)
t0=time.time()
with stdout.open('w',buffering=1,encoding='utf-8') as f:
    proc=subprocess.Popen([sys.executable,str(child),str(SCI),str(run),str(WORK)],
        env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    for line in proc.stdout:
        f.write(line);print(line,end='',flush=True)
    child_rc=proc.wait()
wall=time.time()-t0

result=loadj(run/'_RESULT.json');failure=loadj(run/'_FAILURE.json')
progress=loadj(run/'BUILD7C_ROLLING54_PROGRESS_LIVE.json')
issues=list(parent_prefix);issue_failures=[]
for issue in range(136,167):
    out=run/f'issue_{issue:06d}'
    decomp=loadj(out/'ConversationA_R25M_B6_EXACT_DECOMPOSITION_AUDIT.json')
    term=loadj(out/'BUILD7BR6_GUROBI_TERMINATION.json')
    transition=loadj(out/'BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json')
    exact=loadj(out/f'exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json')
    policy=decomp.get('b6c5r4_policy') or {}
    try:gap=float(decomp.get('global_certified_gap'))
    except Exception:gap=float('inf')
    numerical=True
    for key,gate in [('ConstrVio',1e-6),('BoundVio',1e-6),('IntVio',1e-5)]:
        try:numerical &= math.isfinite(float(term[key])) and float(term[key])<=gate
        except Exception:numerical=False
    ok=bool(
        decomp.get('revision')=='R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME' and
        decomp.get('pricing_closed') is True and decomp.get('certificate_pass') is True and gap<=0.03+1e-12 and
        policy.get('unlimited_completion') is True and
        all(policy.get(key) is None for key in [
            'root_CG_time_limit_s','restricted_integer_time_limit_s','polish_time_limit_s',
            'branch_price_time_limit_s','branch_price_node_limit','branch_price_child_CG_time_limit_s',
            'root_CG_iteration_limit']) and
        int(term.get('requested_threads',-1))==THREADS and term.get('thread_policy_verified') is True and numerical and
        transition.get('status')=='PASS' and transition.get('h0_only_committed') is True and
        exact.get('hard_constraint_pass') is True)
    rec={'issue':issue,'pass':ok,'global_certified_gap':None if not math.isfinite(gap) else gap,
         'pricing_closed':decomp.get('pricing_closed'),'certificate_pass':decomp.get('certificate_pass'),
         'transition_status':transition.get('status'),'fresh_exact_ac_pass':exact.get('hard_constraint_pass')}
    issues.append(rec)
    if not ok:issue_failures.append(rec)

if VALIDATE_ROOT_ONLY:
    validation=loadj(run/'issue_000136/ConversationA_R25O_B6C5R4R1_ROOT_PRICING_AUDIT.json')
    validation_ok=bool(validation.get('status')=='PASS_ROOT_PRICING_CLOSED' and validation.get('pricing_closed') is True and
                       validation.get('revision')=='R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME')
    validation_result={'release':'R25R_ISSUE136_ROOT_VALIDATION','status':'PASS' if validation_ok else 'FAIL',
        'parent_R25Q_sha256':PARENT_R25Q_SHA,'resume_state_sha256':RESUME_STATE_SHA,
        'verified_prefix':parent_prefix,'root_pricing_audit':validation,'child_return_code':child_rc,'wall_s':wall}
    jw(ROOT/'ConversationA_R25R_ISSUE136_ROOT_VALIDATION.json',validation_result)
    print('[R25R_ROOT_VALIDATION]',validation_result['status'],flush=True)
    raise SystemExit(0 if validation_ok else 2)

final_pass=bool(
    child_rc==0 and result.get('status')=='PASS_R25R_STAGE1_54_OF_54_FINAL' and
    result.get('authoritative_54_of_54') is True and
    result.get('all_54_global_3pct_certificates_pass') is True and
    result.get('all_continuation_optimization_completed') is True and
    progress.get('completed_issues')==31 and result.get('authoritative_verified_issue_count')==54 and not issue_failures)
status='PASS_R25R_STAGE1_54_OF_54_FINAL_FREEZE' if final_pass else 'R25R_STAGE1_54_OF_54_FIX_REQUIRED'
summary={
    'conversation':'A','release':'R25R_B6C5R4R4_STAGE1_54_OF_54_RUNTIME_RESULT',
    'status':status,'child_return_code':child_rc,'wall_s':wall,
    'authoritative_issue_axis':[113,166],'required_issue_count':54,
    'verified_parent_prefix_issue_count':23,'continuation_issue_count':31,
    'verified_issue_count':sum(1 for rec in issues if rec['pass']),
    'all_solver_time_limits_removed':True,'all_branch_price_node_limits_removed':True,
    'threads_per_process':THREADS,'parent_R25P_chain_sha256':PARENT_R25P_SHA,
    'parent_R25Q_runtime_result_sha256':PARENT_R25Q_SHA,
    'resume_state_sha256':RESUME_STATE_SHA,
    'final_result':result,'progress':progress,'issues':issues,'issue_failures':issue_failures,
    'failure':failure,'physical_state_committed_through_issue':progress.get('last_issue'),
    'next_stage':('ANNUAL_MONTHLY_48H_BURNIN_4X4' if final_pass else 'R25R_FAIL_CLOSED_REPAIR'),
}
jw(ROOT/'ConversationA_R25R_STAGE1_54_OF_54_RUNTIME_RESULT.json',summary)
if final_pass:
    jw(ROOT/'ConversationA_R25R_STAGE1_FINAL_FREEZE.json',{
        'release':'R25R_STAGE1_FINAL_FREEZE','status':'PASS_STAGE1_FINAL_FREEZE',
        'issue_axis':[113,166],'issue_count':54,'all_global_3pct_certificates_pass':True,
        'all_numerical_gates_pass':True,'all_fresh_exact_opendss_gates_pass':True,
        'all_h0_only_transitions_committed':True,'final_state_sha256':result.get('final_state_sha256'),
        'scientific_model_changed':False,'objective_changed':False,'causality_changed':False,
        'authorized_next_stage':'ANNUAL_MONTHLY_48H_BURNIN_4_PROCESSES_X_4_THREADS'})

stamp=time.strftime('%Y%m%dT%H%M%S')
bundle=ART/f'ConversationA_R25R_STAGE1_54_OF_54_RUNTIME_RESULT_{stamp}.tar.gz'
with tarfile.open(bundle,'w:gz',compresslevel=1) as tf:
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and SCI not in path.parents:
            tf.add(path,arcname=path.relative_to(ROOT).as_posix())
print('[R25R_STAGE1_STATUS]',status,flush=True)
print('[R25R_VERIFIED_ISSUES]',sum(1 for rec in issues if rec['pass']),'of 54',flush=True)
print('ONLY_HANDOFF_FILE='+str(bundle),flush=True)
raise SystemExit(0 if final_pass else 2)
