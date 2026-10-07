"""At most two census-motivated partial-integrality tests, <=300 seconds each."""
import json,time
import numpy as np
from pure_lp import OUT,load,write,rows,replay
from analyze_point import context
from datetime import datetime,timezone
UB=.6694159238756877

def main():
    assert (OUT/'FRACTIONAL_CORE.json').exists(),'SELECTIVE_TEST_REQUIRES_FRESH_CENSUS'
    assert (OUT/'LP_STRENGTHENING_SUMMARY.json').exists(),'SELECTIVE_MILP_FORBIDDEN_DURING_LP_LOOP'
    finished_loop=json.loads((OUT/'LP_STRENGTHENING_SUMMARY.json').read_text())
    assert finished_loop['rounds']<=10 and finished_loop['MILP_calls_during_loop']==0
    c=context();A,d,start=c['A'],c['d'],c['start']
    census={r['family']:r for r in __import__('csv').DictReader((OUT/'FRACTIONALITY_CENSUS.csv').open())}
    mapping=list(__import__('csv').DictReader((OUT/'DISCRETE_VARIABLE_FAMILY_MAP.csv').open()))
    ref=json.loads((OUT/'aborted_1h_provenance/SOLVER_PARAMETERS.json').read_text())['settings']
    from v42_redundancy.model import build
    import gurobipy as gp
    results=[]
    for family in ['node_activity','charge_mode']:
        if int(census[family]['fractional_count'])==0:continue
        token=OUT/f'SELECTIVE_{family}_ONCE.json';assert not token.exists(),'SELECTIVE_RETRY_FORBIDDEN'
        model=build(A,d);v=model.getVars()
        cols=[int(r['column']) for r in mapping if r['family']==family]
        assert len(cols)==int(census[family]['binary_count']) and all(d['types'][j]!='C' for j in cols)
        types=np.full(len(v),'C');types[cols]=d['types'][cols];model.setAttr('VType',v,types.tolist())
        for k,value in ref.items():model.setParam(k,value)
        model.Params.TimeLimit=300;model.Params.Threads=1;model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.LogFile=str(OUT/f'SELECTIVE_{family}.log')
        model.setAttr('Start',v,start.tolist());model.update()
        write(token.name,dict(optimize_calls=1,family=family,TimeLimit=300,Threads=1,integer_columns=len(cols),motivation='Only two actual retained discrete families; fresh census has fractional variables in this family. Restore this entire family; all other discrete variables remain continuous.',production_acceptance=False))
        started_UTC=datetime.now(timezone.utc).isoformat()
        model.optimize()
        finished_UTC=datetime.now(timezone.utc).isoformat()
        point_check=None
        if model.SolCount:
            x=np.asarray(model.getAttr('X'));np.savez_compressed(OUT/f'SELECTIVE_{family}_POINT.npz',x=x)
            point_check=replay(A,d,x)
            point_check.update(restored_integrality_max_residual=float(np.max(abs(x[cols]-np.rint(x[cols])),initial=0.)),not_an_original_all_integer_feasible_certificate=True)
        conservative_LB=float(np.nextafter(float(model.ObjBound)-1e-8,-np.inf))
        row=dict(family=family,integer_columns=len(cols),Status=model.Status,Runtime=model.Runtime,Work=model.Work,NodeCount=model.NodeCount,SolCount=model.SolCount,UB=float(model.ObjVal) if model.SolCount else None,native_LB=float(model.ObjBound),conservative_native_LB=conservative_LB,gap_ref=(UB-conservative_LB)/UB,baseline_valid_global_LB=.5687116003498334,diagnostic_only=True,production_acceptance=False,TimeLimit=300,Threads=1,remaining_original_discrete_relaxed=9322-len(cols),point_replay_PASS=point_check['PASS'] if point_check else None,restored_integrality_max_residual=point_check['restored_integrality_max_residual'] if point_check else None)
        results.append(row);rows('SELECTIVE_INTEGRALITY_RESULTS.csv',results)
        write(f'SELECTIVE_{family}_RESULT.json',dict(**row,point_replay=point_check,partial_integrality_only=True,source_settings=ref,changed_scientific_parameters=False,started_UTC=started_UTC,finished_UTC=finished_UTC,LP_loop_completed_before_test=True))
        model.dispose();print('SELECTIVE_DONE',family,row['native_LB'],row['Status'],flush=True)
    if not results:
        rows('SELECTIVE_INTEGRALITY_RESULTS.csv',[dict(family='NOT_RUN',reason='No fresh-census fractional family justified a selective test.',diagnostic_only=True)])

if __name__=='__main__':main()
