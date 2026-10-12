"""Two bounded attribution tests: candidate four-slot and one eight-slot reach."""
from common import *

def main():
    assert read(OUT/'SINGLE_WINDOW_STRENGTHENED_LP.json')['material'] is False
    assert (OUT/'CROSS_MESS_COUPLING_AUDIT.json').exists()
    import gurobipy as gp
    from v42_redundancy.model import build
    A,d,reference=load();start=reference
    if read(OUT/'UB_LOCAL_NEIGHBORHOOD_RESULT.json')['new_valid_UB']<UB:
        with np.load(OUT/'UB_LOCAL_NEIGHBORHOOD_POINT.npz') as z:start=z['x'].copy()
    results=[]
    for end in (72,76):
        label=f'SELECTIVE_MESS04_69_{end}';chosen=[]
        for j,name in enumerate(d['names']):
            if d['types'][j]=='B' and str(name).startswith(('node_activity[MESS04,','charge_mode[MESS04,')):
                t=int(str(name).rsplit(',',1)[-1][:-1])
                if 69<=t<=end:chosen.append(j)
        f=dict(d,types=np.full(len(start),'C'));f['types'][chosen]='B'
        definition=dict(UTC=stamp(),MESS='MESS04',start=69,end=end,selected_original_binary_count=len(chosen),selected_names=d['names'][chosen].tolist(),other_original_binaries_relaxed=True,all_original_C3A_rows_bounds_P1_unchanged=True,reason='Exact common-mode/location/PQ separation at71 identifies this unit; extend69..72 to69..76 once to test SOC/mobility carryover into the next active late thermal slots. No global96-slot hull.',not_a_production_solution=True)
        write(label+'_DEFINITION.json',definition);m=build(A,f);m.setAttr('Start',m.getVars(),start.tolist())
        settings=dict(Threads=1,TimeLimit=300,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0)
        for k,v in settings.items():m.setParam(k,v)
        m.Params.LogFile=str(OUT/(label+'.log'));m.Params.OutputFlag=1;m.Params.LogToConsole=0
        once(label,settings,definition);snapshot(label+'_CONCURRENCY.json');print(label+'_START',len(chosen),flush=True);m.optimize()
        point=np.asarray(m.getAttr('X')) if m.SolCount else None
        if point is not None:np.savez_compressed(OUT/(label+'_POINT.npz'),x=point)
        bound=float(m.ObjBound);safe=float(np.nextafter(bound-1e-8,-np.inf)) if math.isfinite(bound) else None
        valid=max(LB,safe) if safe is not None else LB
        raw=replay(A,f,point,True) if point is not None else None
        record=dict(case=label,Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),NodeCount=float(m.NodeCount),SolCount=int(m.SolCount),ObjVal=float(m.ObjVal) if m.SolCount else None,native_ObjBound=bound,conservative_native_bound=safe,valid_global_LB=valid,delta_LB=valid-LB,percent_required_LB_recovered=100*(valid-LB)/REQUIRED,settings=settings,definition=definition,raw_selected_integrality_replay=raw,start_supplied=True,start_accepted='Loaded user MIP start' in (OUT/(label+'.log')).read_text(),partial_MILP_point_not_promoted_to_production_UB=True,all_values_saved_before_validation=True)
        write(label+'.json',record);results.append(record);m.dispose();print(label+'_DONE',valid,record['Runtime'],flush=True)
    cross=read(OUT/'CROSS_MASTER_INTEGER.json')
    table('SELECTIVE_INTEGRALITY_RESULTS.csv',[dict(case=r['case'],selected_original_binary_count=r['definition']['selected_original_binary_count'],Status=r['Status'],Runtime=r['Runtime'],TimeLimit=300,Threads=1,valid_global_LB=r['valid_global_LB'],delta_LB=r['delta_LB'],production_UB=False) for r in results]+[dict(case='CROSS_MASTER_INTEGER',selected_original_binary_count=192,Status=cross['Status'],Runtime=cross['Runtime'],TimeLimit=300,Threads=1,valid_global_LB=max(LB,cross['conservative_global_LB']),delta_LB=max(0,cross['conservative_global_LB']-LB),production_UB=False)])
    write('LONGER_HORIZON_DIAGNOSTIC.json',dict(executed=True,only_one_eight_slot_extension=True,horizon=8,baseline_four_slot=results[0],eight_slot=results[1],exact_original_global_physics_preserved=True,not_a_full_eight_slot_convex_hull=True,scope='Selective-integrality reachability/SOC attribution, original rest relaxed; no production solution',material_bound_gain=results[1]['delta_LB']>=.001,total_selective_tests_including_coupling_master=3))

if __name__=='__main__':main()
