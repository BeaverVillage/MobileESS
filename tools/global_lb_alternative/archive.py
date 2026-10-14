"""Preserve measured source epochs, metadata supplements and exact root transport."""
from fractions import Fraction as F
import hashlib
from pathlib import Path

from tools.global_lb_alternative.research import ROOT,OUT,read,write,file_sha,csv_write,BASE
from tools.global_lb_alternative.math import dot
from tools.critical_grid_cg.verify import npz


def archive():
    current=(ROOT/'tools/global_lb_alternative/research.py').read_text(encoding='utf-8')
    original=current.replace("source_sha=read(Path('D:/v42_may_joint_repair_campaign_20261013/FINAL_FREEZE.json'))['source_SHA']",
                             'source_sha=signature(input_identity)')
    original=original.replace("        require(not (OUT/'LAGRANGIAN_GLOBAL_LB_CERTIFICATE.json').exists(),'COMPLETED_WEIGHT_SEARCH_NOT_RESUMABLE')\n",'')
    original=original.replace("update_oracle='NUMERICAL_PRIMAL_HEURISTIC_CANDIDATE_GENERATION_ONLY_NEVER_EXACT_SUBGRADIENT'",
        "update_oracle='EXACT_NUMERICAL_LOCAL_OPTIMUM' if all(p['status']==2 for p in local) else 'HEURISTIC_INCOMPLETE_PRIMAL_NOT_EXACT_SUBGRADIENT'")
    original=original.replace("        native_violation=dot(transported['native_terms'],npz(BASE/'LP_POINT.npz')['x'])-F(transported['native_rhs'])\n",'')
    original=original.replace("                    native_compact_root_violation_exact=str(native_violation),\n",'')
    original=original.replace("accepted=violation>F(1e-8) and native_violation>F(1e-8) and key not in signatures,",
                              "accepted=violation>F(1e-8) and key not in signatures,")
    start=original.index('    final.update(LB_K48=LB,')
    end=original.index("    write(OUT/'FINAL_GLOBAL_LB_REGISTRY.json',final)",start)
    original=original[:start]+original[end:]
    epoch2=original
    # The continuation changes only reuse/accounting of previously completed
    # calls. Reconstruction is checked against the pre-existing execution SHA.
    start=original.index('def algorithm_a(resume=False):')
    end=original.index('    rows={int(k):v',start)
    original=original[:start]+"def algorithm_a():\n    phase_latch('A');bound=load_binding();budget=NativeBudget(OUT)\n"+original[end:]
    original=original.replace('        completed_dir=OUT/\'A\'/f\'E{evaluation:02d}_{candidate["label"]}\'\n'
        "        pending=sum(not (completed_dir/u/'RESULT.json').exists() for u in UNITS)\n"
        "        if evaluation and budget.remaining('A')<pending*30+1:\n",
        "        if evaluation and budget.remaining('A')<4*30+1:\n")
    start=original.index("                if target.exists() and (target/'RESULT.json').exists():")
    end=original.index("                lower=F(result['exact_corrected_bound'])",start)
    original=original[:start]+"                result=solve(target,A,d,c,start,budget,'A',f'A_E{evaluation}_{unit}')\n"+original[end:]
    original=original.replace("choices=['audit','a','resume-a','b','finish']","choices=['audit','a','b','finish']")
    original=original.replace("dict(audit=audit,a=algorithm_a,**{'resume-a':lambda:algorithm_a(resume=True)},b=algorithm_b,finish=finish)",
                              'dict(audit=audit,a=algorithm_a,b=algorithm_b,finish=finish)')
    records=[]
    for name,text,receipt in (('initial_research.py',original,'A_STARTED.json'),('continued_research.py',epoch2,'B_STARTED.json')):
        expected=read(OUT/receipt)['source_sha'];digest=hashlib.sha256(text.encode()).hexdigest()
        if digest!=expected:raise ValueError('MEASURED_SOURCE_EPOCH_RECONSTRUCTION:'+name+':'+digest+':'+expected)
        path=OUT/'measured_source'/name;path.parent.mkdir(exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
        records.append(dict(path=str(path),sha256=digest,matched_execution_receipt=receipt))
    # Explicitly retain trial native runner BEFORE post-pilot callback/raw-bound
    # diagnostics hardening. No Native rerun was used to validate that hardening.
    native=(ROOT/'tools/global_lb_alternative/native.py').read_text(encoding='utf-8')
    native=native.replace("        require(not any(c['label']==label for c in calls),'DUPLICATE_NATIVE_SIGNATURE')\n",'')
    start=native.index('        if runtime is None or not math.isfinite(runtime) or runtime<0:')
    end=native.index("        p['calls'].append(dict(**p['inflight'], Native_Runtime=runtime, error=error))",start)
    native=native[:start]+native[end:]
    native=native.replace('        last_peer = 0.\n','').replace('            nonlocal last,last_peer','            nonlocal last')
    start=native.index('            if now-last_peer>=2:');end=native.index('            if where == gp.GRB.Callback.MESSAGE:',start)
    native=native[:start]+native[end:]
    native=native.replace("        status_valid=model.Status in (2,9,11)\n        budget.finish(runtime, '|'.join(problems) if problems else None if status_valid else 'INVALID_SOLVER_STATUS')",
                          "        budget.finish(runtime, '|'.join(problems) if problems else None)")
    native=native.replace('            raw_bound,raw_bound_c=float(model.ObjBound),float(model.ObjBoundC)\n            bound = (max if maximize else min)(raw_bound,raw_bound_c)',
                          '            bound = (max if maximize else min)(float(model.ObjBound),float(model.ObjBoundC))')
    native=native.replace('            raw_bound=raw_bound_c=None\n','').replace('                      raw_ObjBound=raw_bound,raw_ObjBoundC=raw_bound_c,\n','')
    start=native.index('            try:\n                failed_runtime=float(model.Runtime)')
    end=native.index("        write(out/'ERROR.json'",start)
    native=native[:start]+"            budget.finish(float(model.Runtime),repr(exc))\n"+native[end:]
    path=OUT/'measured_source/native.py';path.write_text(native,encoding='utf-8',newline='\n')
    records.append(dict(path=str(path),sha256=file_sha(path),reconstructed_from_recorded_patch=True,
        pre_execution_independent_runner_hash_anchor_available=False))
    math=(ROOT/'tools/global_lb_alternative/math.py').read_text(encoding='utf-8')
    math=math.replace('import re\n','')
    math=math.replace("    require(not set(w)&set(u),'EPIGRAPH_AND_COUPLING_AXIS_OVERLAP')\n",'')
    math=math.replace("    require(all(rows[int(k)]['thermal'] for k in packet['weights']) and\n            all(not rows[int(k)]['thermal'] for k in packet['mu']), 'WRONG_DUAL_ROW_FAMILY')\n",'')
    math=math.replace("isinstance(v, str) and re.fullmatch('[0-9a-f]{64}',v)","isinstance(v, str) and len(v) == 64")
    path=OUT/'measured_source/math.py';path.write_text(math,encoding='utf-8',newline='\n')
    records.append(dict(path=str(path),sha256=file_sha(path),reconstructed_from_recorded_patch=True))
    write(OUT/'SOURCE_EPOCH_HISTORY.json',dict(records=records,postpilot_Native_calls=0,
        postpilot_changes=['source field metadata correction; original digest preserved','explicit heuristic-oracle label',
            'unknown-runtime quarantine and additional row/SHA checks','callback peer monitoring and raw ObjBound fields for future calls',
            'native compact root violation gate; no actual cut adopted','final registry/report fields'],
        original_scientific_model_mutations=0,measured_performance_not_claimed_for_postpilot_hardening=True))
    history=read(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json')['evaluations'];csv=[]
    for p in history:
        r=dict(evaluation=p['evaluation'],label=p['label'],weight_sha=p['sha256'],Global_LB=p['LB'],delta_vs_K48=p['delta_vs_K48'],
               Native_Runtime=p['Native_Runtime'],replay_wall_seconds=p['wall_seconds'],cached=p['evaluation']==0)
        ram=[];commit=[]
        starts=[];ends=[]
        for local in p['local']:
            q=read(Path(local.get('cached_from',str(Path(local.get('path',''))/'RESULT.json'))))
            prefix=local['unit']+'_';r[prefix+'Bound']=local['LB'];r[prefix+'Objective']=local['Incumbent']
            r[prefix+'Status']=local['status'];r[prefix+'TimeLimit']=q.get('TimeLimit',29.)
            ram.append(q.get('peak_RSS_bytes',0));commit.append(q.get('peak_private_commit_bytes',0))
            if 'path' in local:
                folder=Path(local['path']);starts.append(read(folder/'RESOURCE_BEFORE.json')['memory']['time'])
                ends.append(read(folder/'MEMORY_TRACE.json')['samples'][-1]['time'])
        r['wall_seconds']=max(ends)-min(starts) if starts else p['wall_seconds']
        r['wall_basis']='Measured original resource timestamps; includes external gate/continuation pause' if starts else 'Cached certificate replay only'
        r['Peak_RAM_bytes']=max(ram);r['Peak_Commit_bytes']=max(commit);csv.append(r)
    csv_write(OUT/'LAGRANGIAN_WEIGHT_HISTORY.csv',csv)
    # Exact native compact fractional violation supplements the original
    # rounded-lift diagnostic. The admission result remains false for both.
    b=read(OUT/'MULTIPERIOD_HULL_CUT_CERTIFICATES.json');root=npz(BASE/'LP_POINT.npz')['x']
    for p in b['certificates']:
        cut=p['transport'];v=dot(cut['native_terms'],root)-F(cut['native_rhs'])
        p['native_compact_root_violation_exact']=str(v)
        if p['accepted'] and v<=0:raise ValueError('NO_ACTUAL_COMPACT_ROOT_VIOLATION')
    write(OUT/'MULTIPERIOD_HULL_CUT_CERTIFICATES.json',b)
    bound=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')['binding']
    path=OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json';ledger=read(path);ledger['binding']=bound;write(path,ledger)
    print('MEASURED_SOURCE_EPOCHS_RESTORED',len(records))


if __name__=='__main__':archive()
