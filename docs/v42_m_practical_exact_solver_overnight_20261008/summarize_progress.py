"""Receipt-only resource and architecture summary; never loads a solver."""
import json,csv,re,os
from pathlib import Path
from datetime import datetime,timezone
from fractions import Fraction
import numpy as np
OUT=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,r):
    t=p.with_suffix(p.suffix+'.tmp')
    with t.open('w',encoding='utf-8',newline='\n') as f:json.dump(r,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(t,p)
def run():
    runs=[];external=OUT/'external_production'
    for p in sorted((OUT/'runs').glob('*/RESULT.json')):
        r=read(p);t=r['times'];log=(p.parent/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
        m=re.search(r'Root relaxation:.*?, ([\d.]+) seconds \(([\d.]+) work units\)',log)
        runs.append(dict(source=p.relative_to(OUT).as_posix(),backend='native',name=r['name'],status=r['Status'],Runtime=r['Runtime'],Work=r['Work'],nodes=r['NodeCount'],nodes_per_runtime_hour=r['NodeCount']*3600/r['Runtime'],root_LP_seconds=float(m[1]) if m else None,root_processing_end=t['root_complete'],first_nonroot=t['first_nonroot'],post_root_seconds=r['Runtime']-t['root_complete'] if t['root_complete'] else None,peak_RSS=r['peak_RSS'],cuts_generated=r['cut_summary'],valid_UB=r['valid_UB'],accepted_LB=read(p.parent/'INDEPENDENT_AUDIT.json').get('accepted_global_LB',r['global_LB']),scientific_replay_and_independent_audit_PASS=read(p.parent/'INDEPENDENT_AUDIT.json')['PASS'],new_optimize_calls=r['optimize_calls']))
    paths=list((external/'failed_attempts').glob('*/*/RESULT.json'))+list((external/'external_nodes').glob('*/RESULT.json'))
    for p in sorted(paths):
        r=read(p)
        if 'LP_status' not in r:continue
        archived=r.get('archived_origin')
        relaxed=r.get('LP_primal_replay') or r.get('unresolved_relaxed_replay') or {}
        runs.append(dict(source=p.relative_to(OUT).as_posix(),backend='external',name=p.parent.as_posix().split('external_production/')[-1],node_id=r['node_id'],depth=len(r['fixings']),status=r['LP_status'],native_status=r['native_status'],Method=r.get('parameters',{}).get('Method'),Crossover=r.get('parameters',{}).get('Crossover'),BarConvTol=r.get('parameters',{}).get('BarConvTol'),LP_objective=r.get('LP_objective'),original_relaxed_replay_PASS=relaxed.get('PASS'),max_original_row_violation=relaxed.get('max_constraint_violation'),Runtime=r.get('Runtime'),Work=r.get('Work'),peak_RSS=r.get('peak_RSS'),basis_supplied=r.get('basis_supplied'),basis_accepted=r.get('basis_accepted'),fractional_binary_count=r.get('fractional_binary_count'),certified_LB=r.get('certified_LB'),partial_basis_available=bool(r.get('partial_basis')),new_optimize_calls=0 if archived else int((p.parent/'OPTIMIZE_ONCE.json').exists()),archived_OPTIMAL_proof_import=bool(archived),historical_Runtime_excluded=archived.get('archived_Runtime') if archived else None))
    children=[r for r in runs if r['backend']=='external' and r['depth']>0];times=[r['Runtime'] for r in children if r['Runtime'] is not None];optimal=[r for r in children if r['status']=='OPTIMAL']
    configurations={}
    for r in children:
        key=f"Method{r['Method']}_Crossover{r['Crossover']}_BarConvTol{r['BarConvTol']}"
        configurations.setdefault(key,[]).append(r)
    config_stats={}
    for key,rs in configurations.items():
        vals=[r['Runtime'] for r in rs];total=sum(vals);optimal_rs=[r for r in rs if r['status']=='OPTIMAL']
        losses=[r['LP_objective']-float(Fraction(r['certified_LB'])) for r in optimal_rs]
        config_stats[key]=dict(attempts=len(rs),OPTIMAL=len(optimal_rs),median_Runtime=float(np.median(vals)),p90_Runtime=float(np.percentile(vals,90)),certified_OPTIMAL_nodes_per_native_Runtime_hour=len(optimal_rs)*3600/total if total else None,raw_original_relaxed_replay_PASS=sum(r['original_relaxed_replay_PASS'] is True for r in rs),max_original_row_violation=max((r['max_original_row_violation'] or 0 for r in rs),default=None),median_native_objective_to_exact_bound_loss=float(np.median(losses)) if losses else None,peak_RSS=max(r['peak_RSS'] or 0 for r in rs))
    checkpoint=read(external/'OPEN_CHECKPOINT.json')['state'];open_nodes=[n for n in checkpoint['nodes'].values() if n['state']=='OPEN'];lb=min((Fraction(n['LB']) for n in open_nodes),default=Fraction(checkpoint['UB']));ub=Fraction(checkpoint['UB']);deadline=read(OUT/'IMMUTABLE_DEADLINE.json');now=datetime.now(timezone.utc)
    result=dict(UTC=now.isoformat(),optimize_calls_in_summary=0,receipt_runs=runs,current_bounds=dict(LB=float(lb),UB=float(ub),gap=float((ub-lb)/abs(ub)),initial_LB=.5687116003498334,initial_UB=.6306505800203936,LB_gain=float(lb)-.5687116003498334,UB_gain=.6306505800203936-float(ub)),external=dict(by_configuration=config_stats,completed_child_LP_attempts=len(children),OPTIMAL_children=len(optimal),median_child_Runtime=float(np.median(times)) if times else None,p90_child_Runtime=float(np.percentile(times,90)) if times else None,child_statuses={s:sum(r['status']==s for r in children) for s in ['OPTIMAL','INFEASIBLE','UNRESOLVED']},basis_supplied=sum(bool(r['basis_supplied']) for r in children),basis_accepted=sum(bool(r['basis_accepted']) for r in children),warmstart_speedup_demonstrated=False,OPEN_ids=[n['id'] for n in open_nodes],generated_nodes=len(checkpoint['nodes']),processed_nodes=checkpoint['processed'],prune_counts={s:sum(r['prune_reason']==s for r in checkpoint['ledger']) for s in ['EXACT_LP_INFEASIBILITY','CERTIFIED_LB_AT_LEAST_VALIDATED_UB','INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM']},unresolved_retained_OPEN=[n['id'] for n in open_nodes if n['processed']]),resources=dict(completed_receipt_native_Runtime_sum=sum(r['Runtime'] or 0 for r in runs),completed_receipt_Work_sum=sum(r['Work'] or 0 for r in runs),peak_completed_receipt_RSS=max(r.get('peak_RSS') or 0 for r in runs),new_completed_optimize_calls=sum(r['new_optimize_calls'] for r in runs),wall_elapsed_from_immutable_start=(now-datetime.fromisoformat(deadline['task_start_UTC'])).total_seconds(),seconds_until_immutable_deadline=(datetime.fromisoformat(deadline['deadline_UTC'])-now).total_seconds(),sum_Runtime_is_not_wall='Earlier M0 overlaps native runs and began before night; its incomplete native Runtime/Work excluded from this sum and reported separately.',M0_partial=read(OUT/'M0_OPERATOR_ABORTED.json')),target_met=float((ub-lb)/abs(ub))<=.005,primal_interventions=sum(r['kind']=='primal' for r in [read(p) for p in (OUT/'runs').glob('*/RESULT.json')]),P2_executed=False)
    save(OUT/'ARCHITECTURE_COMPARISON.json',result)
    columns=sorted({k for r in runs for k in r});p=OUT/'RUN_COMPARISON.csv'
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(runs)
    print(json.dumps({k:result[k] for k in ['UTC','current_bounds','external','target_met','primal_interventions','P2_executed']}))
if __name__=='__main__':run()
