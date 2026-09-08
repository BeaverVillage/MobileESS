"""Finite forced, existence, coupled and ablation probes; never production."""
from collections import Counter
import time
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from dayahead.v40a.grid import controls_from_trajectory
from .flex_diagnostic import OUT,WORK,A0
from .flex_model import Data,ProbeModel
from .migration import state_at_d00,pending_in_day
from .feasible_seed import row_audit


def force(p,choices,label):
    certificate,x=p.certify(choices,label+'_ORIGINAL_MODEL_WITNESS')
    assert certificate['status']=='PASS',certificate['original_model_row_audit']
    d=p.d;groups={d.uidgroup[u] for u in choices};p.reset(groups)
    for g in groups:
        for i in p.groups[g]:
            if x[i]>0:p.temporary.append(p.m.addConstr(p.vs[i]==x[i],name='DIAGNOSTIC_FORCE_'+str(i)))
    p.m.setObjective(0,GRB.MINIMIZE);p.m.setAttr('Start',p.vs,x.tolist())
    p.m.Params.TimeLimit=30;p.m.Params.LogFile=str(OUT/(label+'.log'))
    started=time.perf_counter();p.m.optimize()
    assert p.m.SolCount
    raw=np.array(p.m.getAttr('X',p.vs));selected=p.decode(raw)
    assert selected==choices
    with np.load(certificate['power']['path']) as z:power={k:z[k] for k in z.files}
    changes={k:dict(changed_cells=int(np.count_nonzero(power[k]!=d.base_power[k])),
        max_abs_delta=float(np.max(np.abs(power[k]-d.base_power[k])))) for k in power}
    controls=controls_from_trajectory(d.ctx.coefficients,power['pcc'],())
    before=controls_from_trajectory(d.ctx.coefficients,d.base_power['pcc'],())
    rows=d.rows(choices)
    detail=[]
    for u,k in choices.items():
        old=d.byuid[u];new=next(r for r in rows if r['job_uid']==u);opt=d.option(u,k)
        detail.append(dict(job=u,old_site=old['AIDC_site'],new_site=new['AIDC_site'],
            old_segments=[dict(site=old['AIDC_site'],start=old['start_slot'],end=old['end_slot'])],
            new_segments=[dict(site=s,start=a,end=b) for s,a,b in opt.segments(old)],
            old_rack=old['Rack_label'],new_rack=new['Rack_label'],migration=opt.migrated,
            variables=[dict(name=p.names[i],type=p.vs[i].VType,LB=float(p.vs[i].LB),UB=float(p.vs[i].UB),
                Start=float(p.vs[i].Start),X=float(raw[i])) for i in p.groups[d.uidgroup[u]] if x[i]>0]))
    # Compare the entire Planning response, not only the maximum, which can
    # remain at an unaffected bottleneck after a correct linkage response.
    voltage_delta=[];line_p_delta=[];line_q_delta=[];loading_delta=[]
    from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading
    for t,c in enumerate(d.ctx.coefficients):
        dx=controls[t]-before[t]
        voltage_delta.append(float(np.max(abs(c.voltage_matrix.T@dx))))
        line_p_delta.append(float(np.max(abs(c.flow_p_matrix@dx))))
        line_q_delta.append(float(np.max(abs(c.flow_q_matrix@dx))))
        loading_delta.append(float(np.max(abs(anchored_polygon_loading(c,controls[t])-anchored_polygon_loading(c,before[t])))))
    result=dict(status='PASS',forced_changes=detail,solver_status=int(p.m.Status),seconds=time.perf_counter()-started,
        actual_model_row_audit=row_audit(p.m,raw),original_model_witness=record(OUT/(label+'_ORIGINAL_MODEL_WITNESS.json')),
        power_changes=changes,injection_changed_cells=int(np.count_nonzero(controls!=before)),
        max_voltage_squared_response=max(voltage_delta),max_line_P_response=max(line_p_delta),max_line_Q_response=max(line_q_delta),
        max_line_loading_response=max(loading_delta),vector=certificate['vector'],delta=certificate['delta'],
        forced_condition_removed_for_original_validation=True,Actual_reads=0,production_modified=False)
    assert changes['pcc']['changed_cells'] and max(loading_delta)>0 and max(voltage_delta)>0
    write_json(OUT/(label+'.json'),result)
    p.reset()
    print('FORCED_LINKAGE_PASS',label,certificate['vector'],flush=True)
    return result,x


def pairs(d):
    single=read(WORK/'FEASIBLE_SINGLE_MOVES.json')
    first=[r for r in single if 'MIGRATION' in r['kind'] and r['initial']==d.byuid[r['uid']]['AIDC_site']]
    first.sort(key=lambda r:(-d.byuid[r['uid']]['r1_first_valid_checkpoint'],r['uid'],r['destination']))
    first=first[:24]
    sensitivity={r['IDC']:r['critical_fixed_PF_load_sensitivity'] for r in read(OUT/'ELECTRICAL_RESPONSIVENESS.json')['table']}
    second=[r for r in d.refs if state_at_d00(r)=='RUNNING' and r['start_slot']<=96<r['end_slot']]
    second.sort(key=lambda r:(-sensitivity[r['AIDC_site']]*r['requested_GPU'],r['job_uid']))
    second=second[:24]
    tested=0;feasible=[];reject=Counter();best=None
    for a in first:
        ao=d.option(a['uid'],a['option_index'])
        for r in second:
            u=r['job_uid']
            if a['uid']>=u:continue
            ar=d.opts[u];ks=np.flatnonzero((ar[:,3]>=0)&(ar[:,4]==max(ao.transfer_end,int(r['r1_first_valid_checkpoint']))))
            for k in ks:
                choice={a['uid']:a['option_index'],u:int(k)};tested+=1
                q,why=d.quick(choice);reject[why]+=1
                if q is None:continue
                item=dict(choices=choice,vector=q['vector'],delta_P1=q['vector'][0]-d.base[0],
                    first_move=a,second_job=u,second_alone_reason=d.quick({u:int(k)})[1])
                feasible.append(item)
                if best is None or tuple(item['vector'])<tuple(best['vector']):best=item
    result=dict(status='PASS',tested=tested,feasible=len(feasible),reasons=dict(reject),best=best,
        selection='24_LATEST_FEASIBLE_PENDING_CHECKPOINT_MOVES_X_24_HIGHEST_CRITICAL_RUNNING_GPU_CONTRIBUTORS; COMPLETE_MATCHING_DESTINATIONS',
        triple_required=best is None or best['delta_P1']>=-1e-10,Actual_reads=0)
    write_json(OUT/'CAPACITY_RELEASE_PAIR_PROBES.json',result)
    print('PAIR_SCAN_FINISHED',tested,len(feasible),best,flush=True)
    return result


def run():
    d=Data();p=ProbeModel(d)
    try:
        single=read(OUT/'SINGLE_MOVE_SCAN.json')
        best=single['best']['ALL'];move={best['uid']:best['option_index']}
        _,single_x=force(p,move,'FORCED_CHANGE_PROBE_SINGLE_BEST')
        placement=single['best']['PENDING_PRESTART_ONLY']
        force(p,{placement['uid']:placement['option_index']},'FORCED_CHANGE_PROBE_PRESTART')
        pair=pairs(d)
        pairchoice=pair['best']['choices'] if pair['best'] else move
        paircert,pair_x=p.certify(pairchoice,'PAIR_ORIGINAL_MODEL_WITNESS')
        assert paircert['status']=='PASS',paircert['original_model_row_audit']
        force(p,pairchoice,'FORCED_CHANGE_PROBE_RUNNING_WITH_CAPACITY_RELEASE')
        for label,p1,p2 in [('NON_B0_FEASIBLE',None,None),('NON_B0_P1_NO_WORSE',d.base[0]+1e-10,None),
                ('NON_B0_P1_P2_NO_WORSE',d.base[0]+1e-10,d.base[1]+1e-9)]:
            p.solve(label,None,seconds=30,objective='feasibility',different=True,p1=p1,p2=p2,start=single_x)
        sens=read(OUT/'ELECTRICAL_RESPONSIVENESS.json');weights={r['IDC']:r['critical_fixed_PF_load_sensitivity'] for r in sens['table']}
        ordered=sorted(weights,key=weights.get);gaps=np.diff([weights[s] for s in ordered]);cut=int(np.argmax(gaps))+1
        regions={s:'LOW_CRITICAL_EFFECT' if s in ordered[:cut] else 'HIGH_CRITICAL_EFFECT' for s in ordered}
        # Include the pair, critical contributors and receiving-site occupants;
        # use complete job domains for every opened group.
        selected=set(pairchoice)
        ranked=sorted([r for r in d.refs if r['start_slot']<=96<r['end_slot']],
            key=lambda r:(-r['requested_GPU']*weights[r['AIDC_site']],r['job_uid']))
        for region in ('HIGH_CRITICAL_EFFECT','LOW_CRITICAL_EFFECT'):
            candidates=[r for r in ranked if regions[r['AIDC_site']]==region]
            per_site=Counter()
            for row in candidates:
                if per_site[row['AIDC_site']]>=2:continue
                selected.add(row['job_uid']);per_site[row['AIDC_site']]+=1
        for item in sorted(read(WORK/'FEASIBLE_SINGLE_MOVES.json'),key=lambda x:(-d.byuid[x['uid']]['r1_first_valid_checkpoint'],x['uid']))[:8]:selected.add(item['uid'])
        groups=sorted({d.uidgroup[u] for u in selected})
        plan=dict(opened_jobs=sorted(selected),groups=groups,regions=regions,
            full_authoritative_destinations=True,seconds_per_coupled_solve=180,
            source='CURRENT_PLANNING_SENSITIVITIES_GPU_CAPACITY_AND_AUTHORIZED_CHECKPOINTS',Actual_reads=0)
        write_json(OUT/'COUPLED_NEIGHBORHOOD_PLAN.json',plan)
        coupled=p.solve('COUPLED_ESCAPE_TEST',groups,seconds=180,start=pair_x)
        if coupled.get('choices'):
            ccert,cx=p.certify(coupled['choices'],'COUPLED_FINAL_ORIGINAL_MODEL_WITNESS')
        else:cx=single_x
        if not coupled.get('best_vector') or tuple(coupled['best_vector'])>=tuple(d.base):
            p.solve('CROSS_REGION_ESCAPE_TEST',groups,seconds=180,different=True,cross=regions,start=pair_x)
        else:
            write_json(OUT/'CROSS_REGION_ESCAPE_TEST.json',dict(status='NOT_REQUIRED',
                reason='COUPLED_TEST_ALREADY_ESCAPED_B0; CONDITIONAL_EXTRA_PROBE_NOT_TRIGGERED',
                coupled=record(OUT/'COUPLED_ESCAPE_TEST.json'),delta_P1=None))
        p.solve('ABLATION_PRESTART_ONLY',groups,seconds=90,only='placement')
        p.solve('ABLATION_MIGRATION_ONLY',groups,seconds=180,only='migration',start=pair_x)
        write_json(OUT/'PROBES_COMPLETE.json',dict(status='PASS',Actual_reads=0,production_modified=False))
    finally:p.close();d.close()


if __name__=='__main__':run()
