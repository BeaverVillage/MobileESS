"""Fresh-context exact B0 scale search; all non-background inputs remain frozen."""
import os,sys,json,hashlib,subprocess,difflib,time
from pathlib import Path
from decimal import Decimal
import numpy as np
sys.dont_write_bytecode=True
H=Path(__file__).absolute().parent;ROOT=H.parent.parent
REF=ROOT/'independent_screening/IEEE8500_B0_POLICY_SCALE058_20260915'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def label(a):return f'{a:.6f}'.rstrip('0').rstrip('.')

def build_adapter():
    source=(REF/'run_b0_policy.py').read_text(encoding='utf-8')
    old="H=Path(__file__).absolute().parent;ROOT=H.parent.parent"
    new="WORK=Path(__file__).absolute().parent;ROOT=WORK.parent.parent\nH=Path(sys.argv[2]).absolute();ALPHA=float(sys.argv[1]);H.mkdir(parents=True,exist_ok=True)"
    assert source.count(old)==1
    changed=source.replace(old,new)
    # Replace scalar expressions only; the original alpha_0.58 audit paths stay immutable.
    for old,new,count in [('background_scale=.58','background_scale=ALPHA',1),('ap,aq,.58,md','ap,aq,ALPHA,md',1),('float(.58*md[t]','float(ALPHA*md[t]',2),("rule['source_pu'],.58,","rule['source_pu'],ALPHA,",2)]:
        assert changed.count(old)==count,(old,changed.count(old))
        changed=changed.replace(old,new)
    changed=changed.replace("print(f'B0 policy .58 AIDC", "print(f'B0 policy {ALPHA:.6f} AIDC")
    (H/'evaluate_b0.py').write_text(changed,encoding='utf-8')
    (H/'ADAPTER_DIFF.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),fromfile=str(REF/'run_b0_policy.py'),tofile='evaluate_b0.py')),encoding='utf-8')

def summarize(folder,a,kind):
    summary=read(folder/'B0_SUMMARY.json')
    with np.load(folder/'B0_ALL_PHASE_ARRAYS.npz') as z:
        arrays=[z[k] for k in ['voltage_pu','line_current_loading_pu','transformer_current_loading_pu','transformer_winding_kva_loading_pu']]
        assert all(x.shape[0]==96 and np.isfinite(x).all() for x in arrays)
        v,line,tx,kva=arrays
        slot,j=np.unravel_index(line.argmax(),line.shape)
        name,term,bus,node=str(z['line_phase_axes'][j]).split('|')
        vslot,vj=np.unravel_index(v.argmin(),v.shape)
        strict=summary['converged_slots']==96 and summary['control_complete_slots']==96 and summary['solver_error_slots']==0 and v.min()>=.95 and v.max()<=1.05 and max(line.max(),tx.max(),kva.max())<=1
        result=dict(scale=float(a),Vmin=float(v.min()),Vmax=float(v.max()),max_line_loading=float(line.max()),transformer_current=float(tx.max()),transformer_kVA=float(kva.max()),status='PASS' if strict else 'FAIL',Vmin_node=str(z['node_names'][vj]),Vmin_slot=int(vslot),critical_line=name,critical_terminal=int(term[1:]),critical_phase=int(node[4:]),critical_slot=int(slot),converged_slots=summary['converged_slots'],control_settled_slots=summary['control_complete_slots'],production_margin_ok=bool(strict and v.min()>=.9505),evaluation_kind=kind,folder=str(folder),raw_sha256=sha(folder/'B0_ALL_PHASE_ARRAYS.npz'))
    assert result['status']==summary['status']
    return result

def main():
    assert not (H/'SEARCH_RESULT.json').exists(),'Search already complete'
    build_adapter()
    freeze=read(REF/'PRE_EXECUTION_FREEZE.json')
    for r in freeze['files']:assert sha(r['path'])==r['sha256'],r['path']
    reference_files=[REF/n for n in ['B0_SUMMARY.json','B0_ALL_PHASE_ARRAYS.npz','B0_CONTROL_STATES_96.json','GEOMETRY.json','FINAL_MANIFEST.json','render_results.py']]
    files=[dict(path=r['path'],sha256=r['sha256']) for r in freeze['files']]+[dict(path=str(p),sha256=sha(p)) for p in reference_files+[Path(__file__),H/'evaluate_b0.py']]
    rule=dict(first_stage=[.570,.572,.574,.576,.578,.579,.580],reference_reuse_scale=.58,refinement='midpoint between largest feasible and smallest infeasible above it; stop width <= 0.0005',resolution=.0005,hard_Vmin=.95,production_Vmin_recommendation=.9505,production_choice='highest exact max line loading among tested hard-feasible candidates with Vmin >= .9505; tie higher scale',outside_first_stage_fallback='if no hard-feasible candidate, continue downward in 0.002 steps to obtain bracket; if no production-margin candidate continue downward by .002 until first robust candidate',non_background_inputs='identical to frozen actual B0 policy .58',B1_B2_B3_runs=0,files=files)
    save(H/'SEARCH_FREEZE.json',rule)
    results=[];trace=[]
    def persist():save(H/'SCREEN_TABLE.json',sorted(results,key=lambda r:r['scale']));save(H/'SEARCH_TRACE.json',trace)
    def evaluate(a,kind):
        a=float(a);found=[r for r in results if r['scale']==a]
        if found:return found[0]
        folder=H/('scale_'+label(a));folder.mkdir(exist_ok=False)
        print(f'START scale={a:.6f} {kind}',flush=True)
        with (folder/'run.log').open('w',encoding='utf-8') as log:
            completed=subprocess.run([sys.executable,'-B',str(H/'evaluate_b0.py'),str(a),str(folder)],stdout=log,stderr=subprocess.STDOUT)
        if completed.returncode:raise RuntimeError(f'Candidate failed execution: {folder}/run.log')
        r=summarize(folder,a,kind);results.append(r);persist();print(json.dumps(r),flush=True);return r
    results.append(summarize(REF,.58,'REUSED_FROZEN_CONTROL'))
    for a in [.570,.572,.574,.576,.578,.579]:evaluate(a,'FIRST_STAGE')
    while not any(r['status']=='PASS' for r in results):evaluate(round(min(r['scale'] for r in results)-.002,6),'LOWER_BRACKET_EXTENSION')
    feasible=max(r['scale'] for r in results if r['status']=='PASS')
    infeasible=min(r['scale'] for r in results if r['status']=='FAIL' and r['scale']>feasible)
    while Decimal(str(infeasible))-Decimal(str(feasible))>Decimal('0.0005'):
        mid=float((Decimal(str(feasible))+Decimal(str(infeasible)))/2)
        r=evaluate(mid,'BOUNDARY_MIDPOINT')
        trace.append(dict(lower_before=feasible,upper_before=infeasible,midpoint=mid,status=r['status']))
        if r['status']=='PASS':feasible=mid
        else:infeasible=mid
        persist()
    while not any(r['production_margin_ok'] for r in results):evaluate(round(min(r['scale'] for r in results)-.002,6),'PRODUCTION_MARGIN_EXTENSION')
    selected=max((r for r in results if r['production_margin_ok']),key=lambda r:(r['max_line_loading'],r['scale']))
    # Report all observed reversals; discrete automatic controls need not be monotone.
    order=sorted(results,key=lambda r:r['scale'])
    reversals=[dict(lower=x['scale'],upper=y['scale']) for x,y in zip(order,order[1:]) if x['status']=='FAIL' and y['status']=='PASS']
    assert all(sha(r['path'])==r['sha256'] for r in files)
    save(H/'SEARCH_RESULT.json',dict(status='COMPLETE',MAX_FEASIBLE_TESTED_SCALE=max(r['scale'] for r in results if r['status']=='PASS'),FIRST_INFEASIBLE_TESTED_SCALE=min(r['scale'] for r in results if r['status']=='FAIL'),boundary_lower=feasible,boundary_upper=infeasible,boundary_width=float(Decimal(str(infeasible))-Decimal(str(feasible))),RECOMMENDED_PRODUCTION_SCALE=selected['scale'],RECOMMENDED_B0_PEAK_LOADING=selected['max_line_loading'],RECOMMENDED_VMIN_MARGIN=selected['Vmin']-.95,selected=selected,continuous_maximum_claim=False,observed_feasibility_reversals=reversals,production_recommendation_only=True,authority_modified=False,B1_B2_B3_runs=0,optimization_calls=0,new_fresh_contexts=len(results)-1,new_exact_snapshots=(len(results)-1)*96,reused_reference_snapshots=96,source_conservation='PASS'))
    persist();print('SEARCH_COMPLETE',flush=True)

if __name__=='__main__':main()
