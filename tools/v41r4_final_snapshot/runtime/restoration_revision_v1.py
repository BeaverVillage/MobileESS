"""Versioned post-DA closure and read-only May acceptance/reuse audit."""
from pathlib import Path
import sys, json, hashlib, shutil, math, time, traceback
from dataclasses import asdict,replace
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
RUN=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4'
OLDAC=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
OUT=ROOT/'frozen_artifacts/v41r4_restoration_revision_v1'
NEWAC=ROOT/'frozen_artifacts/v41r4_selective_actual_revision_v1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def save(p,x):
    p=Path(p);assert p.resolve().is_relative_to(OUT) or p.resolve().is_relative_to(NEWAC)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def record(p):return dict(path=str(p),sha256=sha(p),bytes=Path(p).stat().st_size)
def verify(rec):assert sha(rec['path'])==rec['sha256'],('HASH_DRIFT',rec['path'])
def seal_check():
    s=read(OUT/'RULE_FREEZE.json')
    for r in s['code']:verify(r)
    return s
def deviation(a,b):return sum(((r['p_kw']-s['p_kw'])/300)**2+((r['q_kvar']-s['q_kvar'])/400)**2 for r,s in zip(a,b))
def identities(d):
    from dayahead.v40a.invariants import MOBILITY_FIELDS
    rows=d['MESS_trajectory']
    return dict(AIDC=digest(d['AIDC_decision']),route=digest([{k:r.get(k) for k in MOBILITY_FIELDS} for r in rows]),
                PQ=digest([{k:r[k] for k in ('mess_id','slot','p_kw','q_kvar')} for r in rows]),trajectory=digest(rows),
                physical_inputs=digest({k:v for k,v in d.items() if k not in ('MESS_trajectory','optimizer_scalar_sha256')}))

def freeze():
    assert not (OUT/'RULE_FREEZE.json').exists()
    OUT.mkdir(parents=True,exist_ok=True)
    helpers=[ROOT/'restoration_revision_v1.py',ROOT/'selective_actual_revision_v1.py',ROOT/'mission_ac_cut_restore.py',ROOT/'dayahead/v40h/recourse.py',ROOT/'dayahead/v37r3/restoration.py',ROOT/'dayahead/v34/integrated_mess.py',ROOT/'dayahead/mess_physics.py']
    specification=dict(version='V41R4_POST_DA_LOCAL_THEN_FULL_PQ_V1',frozen_at=time.time(),
        primary='Unchanged Primary Fresh. Hash-valid primary PASS is no-op; accepted final commands remain byte-identical.',
        local='Existing local fixed-discrete restoration first. Existing successful local result may be reused only with matching original decision, local helper/margin hashes and a clean exact replay. Otherwise invoke original helper unchanged. Fallback only on solver INFEASIBLE (status 3). Other failures remain failures.',
        fallback='Full physical P/Q domain, frozen AIDC and all mobility fields, eta .95, 300kW,400kVA,16 faces, energy 440..1080kWh, E0=ET=760kWh. No local P/Q radius and no primary-objective improvement lock.',
        deviation='sum over all vehicle-slots of ((P-P_original)/300)^2+((Q-Q_original)/400)^2',
        search='Generate seed 1 by full-physical minimum normalized P/Q squared effort; seed 2 by minimum deviation to original under frozen affine grid rows. Each solve deterministic Threads=1 Seed=20260909 WorkLimit=20 MIPGap=1e-6, no wall-time stop. Validate both with clean 96-slot exact AC. For each passing seed, 16 deterministic bisection steps toward original, projecting each interpolated target onto full physical domain by squared deviation; exact validate every candidate. Select minimum original-deviation among all exact passing candidates, digest tie-break. No seed reads forensic witness. Candidate-set minimum only, no global AC optimum claim.',
        acceptance='Clean sequential 96-slot exact OpenDSS, convergence96, V .95..1.05 and line/transformer current/kVA <=1, inherited tolerance1e-9, physical battery audit. Repeat accepted fallback using independent clean replay.',
        actual='Exact dependency/hash reuse only; changed final PQ/dependencies rerun sealed current causal Q-only Actual V2, eta .95. New restored prior-invalid unit gets NEW Actual. This closure never calls DA optimizer/route search.',
        DA_execution_scope='EXISTING_DA_REUSE=123. NEW_REQUIRED_DA_EXECUTION=2025-05-31 B3 only, current frozen B3 M1/A1(1800s)/MF method. Explicit user correction authorizes first execution; existing May31 B0/B1/B2 unchanged.',
        code=[record(p) for p in helpers],local_margin=record(RUN/'audit/mission/AC_CUT_MARGIN_AUTHORITY.json'),
        actual_method=record(OLDAC/'METHOD_FREEZE.json'),actual_implementation=record(OLDAC/'EXECUTION_BINDING.json'))
    save(OUT/'RULE_FREEZE.json',specification)
    # Preserve original FAIL and diagnostic evidence separately; never modify old namespace.
    failed=RUN/'audit/mission/CUT_REPAIR/2025-05-31/B2'
    shutil.copytree(failed,OUT/'historical/MAY31_B2_LOCAL_FAILURE')
    for p in (OLDAC/'logs/2025-05-31').glob('B2_DA*.log'):shutil.copy2(p,OUT/'historical'/p.name)
    save(OUT/'historical/PRIMARY_FAILURE.json',read(RUN/'2025-05-31/B2/dayahead/FRESH_RESULT.json')['summary'])
    print('RULE_FROZEN',flush=True)

def model_candidate(initial, target, ctx, affine=False):
    import numpy as np,gurobipy as gp
    from gurobipy import GRB
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v40h.recourse import validate_physics
    from dayahead.v40a.grid import add_grid
    a=MessElectricalAuthority.from_repository();assert a.charge_efficiency==a.discharge_efficiency==.95
    rows={(r.mess_id,r.slot):r for r in initial.slots};tar={(r.mess_id,r.slot):r for r in target.slots}
    ids=sorted({r.mess_id for r in initial.slots});H=96
    m=gp.Model('POST_DA_FULL_PHYSICAL_PQ_ONLY');m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=20260909
    m.Params.WorkLimit=20;m.Params.MIPGap=1e-6;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9;m.Params.OptimalityTol=1e-9
    p={};q={};e={};objective=gp.QuadExpr()
    names=ctx.coefficients[0].control_names
    controls=[[float(v) for v in row] for row in np.c_[ctx.revision_pcc,np.zeros((H,len(names)-12))]]
    try:
        for mid in ids:
            for t in range(H+1):e[mid,t]=m.addVar(lb=a.energy_min_kwh,ub=a.energy_max_kwh,name=f'E[{mid},{t}]')
            m.addConstr(e[mid,0]==a.initial_energy_kwh);m.addConstr(e[mid,H]==a.terminal_energy_kwh)
            for t in range(H):
                r=rows[mid,t];s=tar[mid,t];c=int(r.mode=='CONNECTED')
                z=m.addVar(vtype=GRB.BINARY,ub=c);pd=m.addVar(lb=0,ub=a.active_power_limit_kw*c);pc=m.addVar(lb=0,ub=a.active_power_limit_kw*c)
                p[mid,t]=pd-pc;q[mid,t]=m.addVar(lb=-a.pcs_kva*c,ub=a.pcs_kva*c)
                m.addConstr(pd<=a.active_power_limit_kw*z);m.addConstr(pc<=a.active_power_limit_kw*(1-z))
                z.Start=int(s.p_kw>0);pd.Start=max(s.p_kw,0);pc.Start=max(-s.p_kw,0);q[mid,t].Start=s.q_kvar
                for f in range(a.pcs_polygon_faces):
                    ang=2*math.pi*f/a.pcs_polygon_faces
                    m.addConstr(math.cos(ang)*p[mid,t]+math.sin(ang)*q[mid,t]<=a.pcs_kva*math.cos(math.pi/a.pcs_polygon_faces)*c)
                travel=r.energy_safe_kwh if r.departure_slot==t and r.mode=='TRANSIT' else 0.
                m.addConstr(e[mid,t]>=a.energy_min_kwh+travel)
                m.addConstr(e[mid,t+1]==e[mid,t]+a.charge_efficiency*a.interval_hours*pc-a.interval_hours*pd/a.discharge_efficiency-travel)
                objective+=((p[mid,t]-s.p_kw)/300)**2+((q[mid,t]-s.q_kvar)/400)**2
                if c:
                    controls[t][names.index(f'mess_p_kw[{r.service_id}]')]+=p[mid,t]
                    controls[t][names.index(f'mess_q_kvar[{r.service_id}]')]+=q[mid,t]
        if affine:add_grid(m,ctx.coefficients,controls,1.0)
        m.setObjective(objective,GRB.MINIMIZE);m.optimize()
        info=dict(status=int(m.Status),solutions=int(m.SolCount),work=float(m.Work),runtime=float(m.Runtime),objective=float(m.ObjVal) if m.SolCount else None,affine=affine)
        if not m.SolCount:return None,info
        result=MessTrajectory(tuple(replace(r,p_kw=float(p[r.mess_id,r.slot].getValue()),q_kvar=float(q[r.mess_id,r.slot].X),battery_energy_kwh=float(e[r.mess_id,r.slot].X),soc_fraction=float(e[r.mess_id,r.slot].X)/a.capacity_kwh) for r in initial.slots))
        info['physics']=validate_physics(result,tolerance=1e-6);assert info['physics']['status']=='PASS',info
        return result,info
    finally:m.dispose()

def exact(day,policy,d,power,candidate,ctx,folder):
    from mission_ac_cut_restore import make_frozen
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    frozen=make_frozen(day,policy,d['AIDC_decision'],power,candidate)
    with corrected_mapping():return run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=ctx.electrical,voltage=ctx.electrical.voltage,trajectory=frozen,output=folder)

def fallback(day,policy,d,power,initial,ctx,folder):
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v40a.invariants import route_sha
    original=[asdict(r) for r in initial.slots];candidates=[];ledger=[];seed_candidates=[]
    def consider(c,info,label):
        if c is None:ledger.append(dict(label=label,solver=info,feasible=False));return False
        assert route_sha(c.slots)==route_sha(initial.slots)
        result=exact(day,policy,d,power,c,ctx,folder/label/'fresh')
        dev=deviation([asdict(r) for r in c.slots],original)
        passed=result.summary['convergence_count']==96 and not result.summary['physical_violation']
        entry=dict(label=label,solver=info,feasible=passed,deviation=dev,Fresh=result.summary)
        ledger.append(entry);save(folder/'SEARCH_LEDGER.json',ledger)
        print('FALLBACK_CANDIDATE',label,passed,dev,flush=True)
        if passed:candidates.append((dev,digest([asdict(r) for r in c.slots]),c,result.summary,label))
        return passed
    zero=MessTrajectory(tuple(replace(r,p_kw=0.,q_kvar=0.) for r in initial.slots))
    for label,target,affine in [('minimum_effort',zero,False),('affine_minimum_deviation',initial,True)]:
        c,info=model_candidate(initial,target,ctx,affine)
        if consider(c,info,label):seed_candidates.append((label,c))
    for label,seed in seed_candidates:
        lo=0.;hi=1.
        for k in range(16):
            weight=(lo+hi)/2
            target=MessTrajectory(tuple(replace(r,p_kw=(1-weight)*s.p_kw+weight*r.p_kw,q_kvar=(1-weight)*s.q_kvar+weight*r.q_kvar) for r,s in zip(initial.slots,seed.slots)))
            c,info=model_candidate(initial,target,ctx,False);info['weight_toward_original']=weight
            if consider(c,info,f'{label}_refine_{k:02}'):lo=weight
            else:hi=weight
    assert candidates,'FULL_PQ_SEARCH_UNRESOLVED_NOT_PROOF_OF_INFEASIBILITY'
    selected=min(candidates,key=lambda x:(x[0],x[1]));candidate=selected[2]
    repeat=exact(day,policy,d,power,candidate,ctx,folder/'FINAL_CLEAN_REPLAY')
    assert not repeat.summary['physical_violation'] and repeat.summary['convergence_count']==96
    save(folder/'SELECTION.json',dict(status='PASS',selected=selected[4],deviation=selected[0],feasible_candidates=len(candidates),candidate_count=len(ledger),
        global_minimum_claim=False,selection='minimum normalized squared original-PQ deviation among all validated candidates',final_slots=[asdict(r) for r in candidate.slots],Fresh=repeat.summary))
    return candidate,repeat.summary

def audit_day(day):
    seal_check()
    import numpy as np
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    ctx=None
    try:
        for policy in ('B0','B1','B2','B3'):
            dest=OUT/day/policy;unit=dest/'ACCEPTANCE.json'
            if unit.exists():continue
            da=RUN/day/policy/'dayahead';joint=da/'FROZEN_JOINT_DECISION.json'
            if not joint.exists():
                print('WAITING_NEW_REQUIRED_DA',day,policy,flush=True);continue
            saved=read(joint);d=saved['decision'];oldids=identities(d)
            source_snapshot={str(p):sha(p) for p in da.rglob('*') if p.is_file()}
            save(dest/'UPSTREAM_SNAPSHOT.json',source_snapshot)
            original_d=d;oldfresh=read(da/'FRESH_RESULT.json')['summary'];rest=da/'AC_RESTORATION_RECEIPT.json'
            restored=rest.exists();local='NOT_CALLED';fallback_used=False
            if restored:
                rr=read(rest);verify(rr['original_optimizer_decision']);verify(rr['report'])
                original_d=read(rr['original_optimizer_decision']['path'])['decision'];report=read(rr['report']['path'])
                assert report['status']=='PASS' and report['discrete_unchanged']
                verify(report['margin_authority'])
                assert report['final_slots']==d['MESS_trajectory']
                oldfresh=read(Path(rr['original_optimizer_decision']['path']).parent/'FRESH_RESULT.json')['summary']
                local='PASS_REUSED_BY_HASH'
            initial=MessTrajectory(tuple(_restore_slots(original_d['MESS_trajectory'])))
            final=MessTrajectory(tuple(_restore_slots(d['MESS_trajectory'])))
            originalids=identities(original_d)
            assert oldids['AIDC']==originalids['AIDC'] and oldids['route']==originalids['route']
            primary='FAIL' if oldfresh['physical_violation'] else 'PASS'
            summary=read(da/'FRESH_RESULT.json')['summary']
            assert summary['convergence_count']==96
            if primary=='FAIL':
                if ctx is None:
                    from v41r4_electrical import configure
                    ctx=configure(day).load(day)
                with np.load(da/'FROZEN_AIDC_POWER.npz') as z:power={k:z[k].copy() for k in z.files}
                ctx.revision_pcc=power['pcc']
                if not restored:
                    from mission_ac_cut_restore import restore
                    try:
                        final,r=restore(day,policy,original_d['AIDC_decision'],power,initial,ctx,dest/'local')
                        local='PASS';summary=r['Fresh']
                    except AssertionError as error:
                        info=error.args[0] if error.args else None
                        if not (isinstance(info,tuple) and info[0]=='CUT_RECOURSE_FAILURE' and info[1].get('status_code')==3):raise
                        local='INFEASIBLE';fallback_used=True
                        save(dest/'LOCAL_INFEASIBLE.json',dict(status='INFEASIBLE',error=repr(error),solver=info[1]))
                        final,summary=fallback(day,policy,original_d,power,initial,ctx,dest/'full_pq')
                result=exact(day,policy,original_d,power,final,ctx,dest/'accepted_fresh')
                summary=result.summary;assert not summary['physical_violation'] and summary['convergence_count']==96
            newd={**d,'MESS_trajectory':[asdict(r) for r in final.slots]} if primary=='FAIL' and not restored else d
            newids=identities(newd)
            assert newids['AIDC']==oldids['AIDC'] and newids['route']==oldids['route'] and newids['physical_inputs']==oldids['physical_inputs']
            changed=newids!=oldids
            oldactual=OLDAC/'replays'/day/policy/'COMPLETE.json'
            prior=oldactual.exists() and read(oldactual).get('status')=='PASS'
            disposition='NEW_ACTUAL_REQUIRED' if not prior else ('RERUN_ACTUAL_REQUIRED' if changed else 'REUSE_ACTUAL')
            if not changed:
                # Existing clean-Fresh hashes are verified by unit/DA manifests and recomputed extrema in final audit.
                newjoint=record(joint)
            else:
                od=dest/'dayahead';od.mkdir(exist_ok=True)
                from dayahead.v40a.invariants import digest as decision_digest
                save(od/'FROZEN_JOINT_DECISION.json',dict(decision=newd,decision_SHA=decision_digest(newd),frozen_at=time.time()))
                save(od/'FROZEN_MESS_COMMANDS.json',dict(MESS_trajectory=newd['MESS_trajectory']))
                for name in ('PLANNING_RESULT.json','FROZEN_AIDC_POWER.npz'):shutil.copy2(da/name,od/name)
                save(od/'RESTORATION_PARENT.json',dict(original=record(joint),rule=record(OUT/'RULE_FREEZE.json'),scientific_objectives_unchanged=True))
                newjoint=record(od/'FROZEN_JOINT_DECISION.json')
            assert all(sha(p)==h for p,h in source_snapshot.items())
            save(unit,dict(day=day,policy=policy,status='PASS',old_primary_fresh=primary,new_primary_fresh=primary,local_restoration=local,
                full_PQ_fallback=fallback_used,final=summary,old_identity=oldids,new_identity=newids,changed=changed,
                new_joint=newjoint,previous_Actual=record(oldactual) if prior else None,actual_disposition=disposition,
                no_DA_optimization=True,no_route_search=True,source_snapshot=record(dest/'UPSTREAM_SNAPSHOT.json'),
                reason='Primary Fresh PASS: no-op' if primary=='PASS' else ('Full physical PQ correction after local INFEASIBLE' if fallback_used else 'Existing local PASS preserved and independently replayed')))
            print('ACCEPTED',day,policy,disposition,flush=True)
    finally:
        if ctx is not None:ctx.electrical.voltage.close();ctx.electrical.current.close()

def audit_firewall():
    import numpy as np
    from dayahead.v37r3.restoration import load_fresh_result
    rows=[];hash_cache={}
    def checked(p,h):
        key=str(p)
        if key not in hash_cache:hash_cache[key]=sha(p)
        assert hash_cache[key]==h,('REUSE_DEPENDENCY_DRIFT',key)
    for unit in sorted(OUT.glob('2025-*/B*/ACCEPTANCE.json')):
        u=read(unit);day=u['day'];pol=u['policy']
        if u['status']!='PASS':rows.append(u);continue
        for p,h in read(u['source_snapshot']['path']).items():checked(p,h)
        verify(u['new_joint'])
        if u['actual_disposition']=='REUSE_ACTUAL':
            old=OLDAC/'replays'/day/pol;receipt=read(old/'CANDIDATE_RECEIPT.json')
            for name,h in receipt['files'].items():checked(old/name,h)
            for p,h in read(OLDAC/'common_inputs'/day/pol/'DA_FRESH_INPUT_SNAPSHOT.json').items():checked(p,h)
            done=read(old/'COMPLETE.json');common_dir=OLDAC/'common_inputs'/day/pol
            assert done['binding']['AIDC_schedule_SHA']==u['new_identity']['AIDC']
            checked(common_dir/'ACTUAL_AIDC_POWER.npz',done['binding']['Actual_AIDC_power_file_SHA'])
            checked(OLDAC/'BATTERY_EFFICIENCY_AUTHORITY.json',done['binding']['eta_authority_SHA'])
            assert u['old_identity']==u['new_identity']
            # Recompute physical outputs from existing arrays without another Actual solve.
            stage='CONTROL_COMMON_BINDING' if pol in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
            s=done['summary'] if pol in ('B0','B1') else done['ETA95_QSAFE_ACTUAL']
            a=np.load(old/stage/'OPENDSS_PHASE_ARRAYS.npz',allow_pickle=False)
            assert a['convergence'].all() and np.isfinite(a['voltage_pu']).all()
            assert abs(float(a['voltage_pu'].min())-s['Vmin_pu'])<1e-12 and abs(float(a['voltage_pu'].max())-s['Vmax_pu'])<1e-12
            u['Actual_disposition']='REUSED';u['reuse_firewall']='PASS';u['Actual_receipt']=record(old/'CANDIDATE_RECEIPT.json')
            save(unit.parent/'ACTUAL_REUSE.json',u)
        rows.append(u)
    save(OUT/'MAY_AUDIT.json',dict(rows=rows,hashes_verified=len(hash_cache),DA_optimization_calls=0,route_search_calls=0))
    print('FIREWALL_PASS',len(rows),len(hash_cache),flush=True)

if __name__=='__main__':
    if sys.argv[1]=='freeze':freeze()
    elif sys.argv[1]=='day':audit_day(sys.argv[2])
    elif sys.argv[1]=='firewall':audit_firewall()
