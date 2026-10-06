"""Recover completed ORIGINAL evidence; execute REDUCED once, never replay A."""
import csv,re,json,time,subprocess,ast
import numpy as np
import gurobipy as gp
from benchmark_m1_redundancy import Resource,arm,parameters,gap,resource_gate,NATIVE_SECONDS,ARM_WALL_SECONDS
from v42_degen.identity import inputs
from v42_degen.common import POLICY
from v42_one_tree_bc.audit import Validator
from v42_redundancy.common import *
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def recover():
 assert read('M1_BENCHMARK_EXECUTION_ERROR.json')['traceback'].endswith('ValueError: Out of range float values are not JSON compliant: inf\n')
 oldcommit=read('M1_BENCHMARK_ONCE.json')['source_commit'];oldsource=subprocess.check_output(['git','show',oldcommit+':benchmark_m1_redundancy.py'],cwd=ROOT)
 archive=OUT/'EXECUTED_SOURCE';archive.mkdir(exist_ok=True);(archive/'benchmark_m1_redundancy_ORIGINAL.py').write_bytes(oldsource)
 # Only the metadata parameters helper changes; the original native arm and
 # callbacks/models/settings/budget code must remain byte-equivalent in AST.
 def scientific_ast(source):
  tree=ast.parse(source);tree.body=[n for n in tree.body if not (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='parameters')];return ast.dump(tree,include_attributes=False)
 assert scientific_ast(oldsource.decode())==scientific_ast((ROOT/'benchmark_m1_redundancy.py').read_text(encoding='utf-8'))
 log=(OUT/'M1_REDUNDANCY_ORIGINAL.log').read_text();assert 'Time limit reached' in log and 'Root relaxation: time limit' in log and 'Solution count 1:' in log
 explored=re.search(r'Explored (\d+) nodes \((\d+) simplex iterations\) in ([\d.]+) seconds \(([\d.]+) work units\)',log);end=re.search(r'Best objective ([\deE+.-]+), best bound ([\deE+.-]+), gap ([\d.]+)%',log);pre=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log);bar=re.search(r'Barrier solved model in (\d+) iterations',log)
 assert explored and end and pre and bar
 A,d,B,e,identity,_=inputs();validator=Validator(A,d)
 with np.load(OUT/'M1_REDUNDANCY_ORIGINAL_RAW_POINT.npz') as z:raw=validator(z['point'])
 with np.load(OUT/'M1_REDUNDANCY_ORIGINAL_VALID_POINT.npz') as z:point=z['point'].copy()
 valid=validator(point);assert raw['PASS'] and valid['PASS']
 freeze=read('M1_BENCHMARK_EXECUTION_FREEZE.json');lb=freeze['initial_LB'];ub=valid['objective'];assert float(end[2])<lb and abs(float(end[1])-ub)<1e-12
 with (OUT/'M1_REDUNDANCY_RESOURCE_LEDGER.csv').open(encoding='utf-8') as f:resources=list(csv.DictReader(f))
 memory=OUT/'M1_REDUNDANCY_RESOURCE_LEDGER_ORIGINAL_RECOVERED.csv';memory.write_bytes((OUT/'M1_REDUNDANCY_RESOURCE_LEDGER.csv').read_bytes())
 rows=[r for r in resources if r['arm']=='ORIGINAL'];wall_upper=float(rows[-1]['wall'])+.5;assert wall_upper<300
 env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.Model(env=env)
 for k,v in dict(POLICY,TimeLimit=NATIVE_SECONDS,PreCrush=1,LazyConstraints=0).items():m.setParam(k,v)
 m.Params.OutputFlag=1;m.Params.LogToConsole=0
 # Do not optimize, or emit additional solver messages into the finished log.
 pp=parameters(m);pp['LogFile']=str(OUT/'M1_REDUNDANCY_ORIGINAL.log');m.dispose();env.dispose()
 r=dict(arm='ORIGINAL',executed=True,optimize_calls=1,source_commit=oldcommit,settings=dict(POLICY,TimeLimit=NATIVE_SECONDS,PreCrush=1,LazyConstraints=0),all_native_parameters=pp,
  rows=B.shape[0],columns=B.shape[1],binaries=int(np.sum(e['types']=='B')),continuous=int(np.sum(e['types']=='C')),nnz=B.nnz,build_wall=None,presolved=dict(rows=int(pre[1]),columns=int(pre[2]),nnz=int(pre[3])),root_completed=False,root_time=None,root_objective_rounded=None,root_iterations=int(explored[2]),root_interrupted_native_log_seconds=238.00,
  raw_native_BestBd=float(end[2]),raw_native_BestBd_scope='Native verbatim printed decimal, rounded to log precision; full double lost in JSON metadata serialization failure.',valid_global_LB=lb,valid_UB=ub,valid_global_gap=gap(ub,lb),initial_valid_UB=freeze['start_full_original_validation']['objective'],initial_valid_LB=lb,first_native_incumbent=None,first_independently_valid_incumbent=None,initial_independently_valid_start_time=0.,node_count=int(explored[1]),LP_iterations=int(explored[2]),barrier_iterations=int(bar[1]),Gurobi_Work=float(explored[4]),native_runtime=float(explored[3]),optimize_wall=None,total_arm_wall=wall_upper,
  peak_RSS=max(int(r['RSS']) for r in rows),peak_process_commit=max(int(r['process_commit']) for r in rows),minimum_free_RAM=min(int(r['free_RAM']) for r in rows),peak_system_commit_percent=max(float(r['commit_percent']) for r in rows),native_status=9,native_SolCount=1,raw_native_UB=float(end[1]),valid_final_full_original_audit=valid,terminal_native_point_audit=raw,progress=[],errors=[],PASS=True,benchmark_native_cap=NATIVE_SECONDS,benchmark_arm_wall_cap=ARM_WALL_SECONDS,
  recovery=dict(reason='JSON serialization rejected an infinite default solver parameter after ORIGINAL optimize and all final point audits had completed.',optimizer_reexecuted=False,scientific_arm_AST_unchanged=True,raw_source_archive_SHA=sha(archive/'benchmark_m1_redundancy_ORIGINAL.py'),native_metrics_source='Verbatim completed original Gurobi log.',work_and_native_runtime_precision='Rounded native printed values; no full-double claim.',wall_scope='Conservative telemetry elapsed upper bound, including failure/finalization; exact arm wall unavailable.',unavailable_metrics=['exact build wall','first native incumbent wall','first independently native-valid incumbent wall','full-double Gurobi Work','exact optimize wall'],parameter_payload_scope='Reconstructed same installed Gurobi defaults + exact original POLICY, without optimize; only metadata encoding changed.',original_native_start_audited=True,full_native_row_transport_scope='Original source transport_audit passed before native call; scientific AST unchanged.'))
 write('M1_REDUNDANCY_BASELINE_RESULT.json',r);return r,A,d,B,e,validator,point,lb,resources
def run():
 original,A,d,B,e,validator,seed,lb,oldresources=recover();resource_gate('REDUCED_RECOVERY_PREFLIGHT')
 freeze=read('M1_BENCHMARK_EXECUTION_FREEZE.json')
 with np.load(ROOT/freeze['start_file']) as z:seed=z['point'].copy()
 assert validator(seed)['PASS'] and float(e['objective']@seed+float(e['constant']))==original['initial_valid_UB']
 with (OUT/'M1_REDUCED_ONCE_AFTER_METADATA_RECOVERY.json').open('x',encoding='utf-8') as f:json.dump(dict(original_native_calls=1,reduced_native_calls_allowed=1,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),no_original_rerun=True),f)
 with np.load(OUT/'M1_REDUCTION_AXES.npz') as z:keep=z['keep']
 memory=Resource();memory.start()
 try:reduced=arm('REDUCED',B,e,keep,validator,seed,lb,memory)
 finally:memory.close()
 newresources=list(memory.rows)
 for r in newresources:r['wall']+=float(oldresources[-1]['wall'])
 # Preserve gap between arms separately: rows are elapsed active-arm ledger
 # positions; UTC timestamps remain authoritative for total elapsed downtime.
 table('M1_REDUNDANCY_RESOURCE_LEDGER.csv',oldresources+newresources,list(newresources[0]))
 pa={k:v for k,v in original['all_native_parameters'].items() if k!='LogFile'};pb={k:v for k,v in reduced['all_native_parameters'].items() if k!='LogFile'};assert pa==pb
 root=False;bound=reduced['valid_global_LB']>original['valid_global_LB']+.001 and reduced['valid_global_gap']<original['valid_global_gap']-.001 and reduced['native_runtime']<=original['native_runtime']+2
 transition=bool(not original['root_completed'] and reduced['root_completed'] and reduced['node_count']>1)
 selected=bool(reduced['PASS'] and (bound or transition));state='EXACT_REDUNDANCY_REDUCTION_SELECTED' if selected else 'EXACT_REDUNDANCY_PROVEN_BUT_NO_SPEEDUP'
 write('M1_REDUNDANCY_COMPARISON.json',dict(PASS=reduced['PASS'],final_state=state,EXACT_REDUNDANCY_REDUCTION_SELECTED=selected,identical_all_solver_parameters_except_LogFile=True,compared_parameter_count=len(pa),sequential=True,concurrent_heavy_solves=False,original_calls=1,reduced_calls=1,metadata_recovery_without_original_rerun=True,scientific_arm_AST_unchanged=True,original_parameter_payload_reconstructed_from_exact_same_defaults_and_POLICY=True,root_time_gate=root,valid_LB_gap_gate=bound,beyond_root_transition_gate=transition,memory_only_selection=False,unmatched_unfinished_root_Work_used_for_selection=False,original_root_completed=False,reduced_root_completed=reduced['root_completed'],original_root_time=None,reduced_root_time=reduced['root_time'],original_UB=original['valid_UB'],reduced_UB=reduced['valid_UB'],original_LB=original['valid_global_LB'],reduced_LB=reduced['valid_global_LB'],original_gap=original['valid_global_gap'],reduced_gap=reduced['valid_global_gap'],original_peak_RSS=original['peak_RSS'],reduced_peak_RSS=reduced['peak_RSS'],original_Work=original['Gurobi_Work'],reduced_Work=reduced['Gurobi_Work'],original_native_runtime=original['native_runtime'],reduced_native_runtime=reduced['native_runtime'],combined_arm_wall_upper=original['total_arm_wall']+reduced['total_arm_wall'],optional_second_benchmark=False,production=False,STOP=True))
 print('RECOVERED_COMPARISON_COMPLETE',state,flush=True)
if __name__=='__main__':run()
