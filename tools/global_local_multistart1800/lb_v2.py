"""One K32 selective-integrality relaxation, with independent inclusion/readback."""
import argparse,gc,math,time,traceback
from collections import defaultdict
from scipy import sparse
from tools.global_local_multistart1800.adapter_v2 import *
from tools.u4_primal_alns.pilot import PARAMS,finite_attr

PARENT=ROOT/'docs/v42_critical_grid_cg/iteration01'
LP=ROOT/'docs/v42_b2_root_lp_tightening/base'
def data(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}

def inclusion(A,d,types,selected):
    parent=read(PARENT/'INDEPENDENT_CERTIFICATE.json')
    assert parent['PASS'] and parent['FULL_projection_subset_native_Joint'] and parent['Global_LB']==.46497617639758426
    assert parent['source18r']==v.SOURCE_SHA and parent['case_sha']==v.CASE_SHA
    for name,digest in read(PARENT/'INDEPENDENT_NATIVE0.json')['file_sha256'].items():assert v.file_sha(PARENT/name)==digest
    original=data(PARENT/'JOINT_DATA.npz');origA=sparse.load_npz(PARENT/'JOINT_A.npz').tocsr()
    assert v.matrix_sha(A)==v.matrix_sha(origA)
    assert set(d)==set(original) and all(np.array_equal(d[k],original[k]) for k in d)
    binary=set(map(int,np.flatnonzero(d['vtypes']=='B')));chosen=set(map(int,selected))
    assert len(binary)==9322 and 100<=len(chosen)<=300 and chosen<=binary
    expected=np.full(len(types),'C',dtype=types.dtype);expected[list(chosen)]='B';assert np.array_equal(types,expected)
    assert all(d['lb'][j]==0 and d['ub'][j]==1 for j in binary)
    return dict(PASS=True,FULL_integer_projection_subset_selective_K32=True,
        reasoning='Inherited exact/outward K32 projection accepts every FULL integer feasible projection. All rows/RHS/senses/bounds/objective are unchanged. Selected original binary types remain B; other original binaries become C on their unchanged [0,1] bounds, a domain superset. No route fixing/Hamming/objective cutoff.',
        source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,
        parent_certificate=record(PARENT/'INDEPENDENT_CERTIFICATE.json'),parent_matrix_SHA=v.matrix_sha(origA),
        exact_parent_rows_preserved=True,new_row_rounding='NO_NEW_ROWS; inherited conservative outward projection unchanged',
        selected_binary=len(chosen),relaxed_binary=9322-len(chosen),new_Optimize_calls=0)

def prepare():
    d=data(PARENT/'JOINT_DATA.npz');A=sparse.load_npz(PARENT/'JOINT_A.npz').tocsr()
    rootcert=read(LP/'INDEPENDENT_CERTIFICATE.json');assert rootcert['PASS'] and rootcert['LP_completed_numerical_OPTIMAL']
    lp=data(LP/'LP_POINT.npz')['x'];lpdata=data(LP/'LP_DATA.npz');assert np.array_equal(d['names'],lpdata['names'])
    slots=defaultdict(list)
    for j,name in enumerate(map(str,d['names'])):
        if d['vtypes'][j]!='B':continue
        axis=name.split('[',1)[1][:-1].split(',');t=int(axis[-1])
        fraction=min(abs(lp[j]),abs(1-lp[j]));slots[t].append((j,fraction))
    ranking=sorted([(sum(f for j,f in parts),t,sum(f>1e-7 for j,f in parts)) for t,parts in slots.items() if t<95],reverse=True)
    anchors=[max((a for a in ranking if lo<=a[1]<hi),key=lambda a:(a[0],-min(abs(a[1]-t) for t in (19,42,75,82,94))))[1] for lo,hi in ((0,32),(32,64),(64,95))]
    selected=[]
    for t in sorted({t for a in anchors for t in (a,a+1)}):
        for u in ('MESS01','MESS02','MESS03','MESS04'):
            nodes=[j for j,f in slots[t] if str(d['names'][j]).startswith('node_activity['+u+',')]
            nodes.sort(key=lambda j:(-min(abs(lp[j]),abs(1-lp[j])),str(d['names'][j])))
            selected.extend(nodes[:11]);selected.extend(j for j,f in slots[t] if str(d['names'][j])==f'charge_mode[{u},{t}]')
    selected=sorted(set(selected));types=np.full(len(d['vtypes']),'C',dtype=d['vtypes'].dtype);types[selected]='B'
    proof=inclusion(A,d,types,selected)
    packet=dict(choice='A_SELECTIVE_INTEGRALITY_K32',PASS=True,selected=selected,selected_names=d['names'][selected].tolist(),
        anchors=anchors,connected_slot_pairs=[[a,a+1] for a in anchors],fractional_slot_ranking=ranking[:24],
        selected_fractional_count=sum(min(abs(lp[j]),abs(1-lp[j]))>1e-7 for j in selected),
        selection='Highest sum of original fractional binary mixing in each of three horizon bands; adjacent pair; 11 most mixed Nodes plus Mode per unit/slot. Current critical slots break ties, not slot42-only selection.',
        LP_authority=record(LP/'INDEPENDENT_CERTIFICATE.json'),LP_point=record(LP/'LP_POINT.npz'),
        source_parent=record(PARENT/'INDEPENDENT_NATIVE0.json'),proof=proof,
        max_Native_seconds=180,requested_seconds=175,one_Optimize_only=True,
        K32_reduced_integer_witness_UB=.4812227124583283,K32_unchanged_feasible_set_cannot_certify_3pct=True,
        comparison=dict(A='New original-binary subset; PR215 design had no Native. Fractional Node/Mode overlap is observed and adjacent pairs preserve connected intervals.',
            B='K48 plus prior fractional16 failed in PR218; a different F1/F2 row-selection/projection would require new independent row analysis. Not executed in this canary.',
            chosen_reason='A offers a new directly verifiable relaxation and observed fractional variables, avoiding repeated Grid16 and large root-incomplete models.',
            hypothesis_not_guaranteed='Fractional coupling contribution is not a causal decomposition; K32 grid omission remains and integer witness caps formulation LB.'))
    write(DOCS/'LB_CANDIDATE_COMPARISON.json',packet);write(DOCS/'FAST_LB_NATIVE0.json',proof)
    return packet

def native(seconds):
    assert 0<seconds<=175;out=DOCS/'dual';out.mkdir(exist_ok=False);guard()
    packet=read(DOCS/'LB_CANDIDATE_COMPARISON.json');d=data(PARENT/'JOINT_DATA.npz');A=sparse.load_npz(PARENT/'JOINT_A.npz').tocsr()
    types=np.full(len(d['vtypes']),'C',dtype=d['vtypes'].dtype);types[packet['selected']]='B'
    proof=inclusion(A,d,types,packet['selected']);write(out/'INDEPENDENT_NATIVE0.json',proof)
    pre=r.audit('DUAL_PRE_BUILD');write(out/'PRE_BUILD_GATE.json',pre);assert pre['PASS'];before=r.memory()
    import gurobipy as gp
    model=gp.Model('Source18r_K32_Selective_288_Global_LB');entered=False
    params=dict(PARAMS,Method=1,MIPFocus=3,TimeLimit=seconds)
    ledger=dict(method='DUAL',stage='DUAL',entered_native=False,Native_Runtime=None,requested_seconds=seconds,Native_worker=1,Threads=1,
        resource_samples=[],callback_errors=[],captures=[],Global_LB_admissible=True,restricted_ObjBound_is_Global_LB=False,
        execution_source_seal=record(DOCS/'EXECUTED_SOURCE_HASHES.json'),ACTUAL='ACTUAL_NOT_RUN')
    cert=dict(PASS=False,Global_LB=None)
    try:
        for key,val in dict(params,LogFile=str(out/'NATIVE_GUROBI.log')).items():setattr(model.Params,key,val)
        x=model.addMVar(A.shape[1],lb=d['lb'],ub=d['ub'],vtype=types,obj=d['c']);x.VarName=d['names'].tolist();model.ObjCon=float(d['constant'])
        cons=model.addMConstr(A,x,d['senses'],d['rhs']);cons.ConstrName=d['row_names'].tolist();model.update()
        actual=model.getA().tocsr()
        checks=dict(matrix=v.matrix_sha(actual)==v.matrix_sha(A),rhs=np.array_equal(model.getAttr('RHS'),d['rhs']),sense=np.array_equal(model.getAttr('Sense'),d['senses']),
            bounds=np.array_equal(x.LB,d['lb']) and np.array_equal(x.UB,d['ub']),types=np.array_equal(x.VType,types),objective=np.array_equal(x.Obj,d['c']) and model.ObjCon==float(d['constant']),
            binaries=model.NumBinVars==len(packet['selected']),no_route_fixing_or_Hamming=model.NumConstrs==A.shape[0],minimize=model.ModelSense==1)
        del actual;assert all(checks.values());write(out/'NATIVE_READBACK.json',dict(PASS=True,checks=checks,parameters={k:getattr(model.Params,k) for k in params}))
        gate=r.admit(before,r.memory());write(out/'POST_BUILD_NATIVE_ADMISSION.json',gate);assert gate['PASS']
        ledger.update(parameter_readback={k:getattr(model.Params,k) for k in params},build_memory_before=before,build_memory_after=r.memory())
        guard();next_gate=0.
        def callback(m,where):
            nonlocal next_gate
            if where==gp.GRB.Callback.POLLING:return
            try:
                runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if runtime>=next_gate:
                    next_gate=runtime+10;guard();safety=r.callbackcheck();ledger['resource_samples'].append(dict(Native_elapsed=runtime,sample=r.memory(),safety=safety))
                    if not safety['PASS']:ledger['callback_stop_reason']='RESOURCE_OR_SOURCE_CALLBACK_GATE';m.terminate()
            except Exception as e:ledger['callback_errors'].append(repr(e));m.terminate()
        entered=True;ledger['entered_native']=True;write(out/'NATIVE_CALL.json',ledger);begin=time.perf_counter();model.optimize(callback)
        ledger['Optimize_return_wall_seconds']=time.perf_counter()-begin
        for k in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount'):ledger[k]=finite_attr(model,k)
        ledger['Native_Runtime']=finite_attr(model,'Runtime');ledger['after_native_memory']=r.memory()
        if model.SolCount:np.savez_compressed(out/'REDUCED_RAW_NOT_FULL_UB.npz',x=np.asarray(x.X))
        bound=ledger['ObjBound'];ok=ledger['Status'] in (2,9) and bound is not None and math.isfinite(bound) and 0<=bound<=INITIAL_UB and not ledger['callback_errors'] and not ledger.get('callback_stop_reason')
        cert=dict(PASS=ok,Global_LB=bound if ok else None,native_source_attribute='ObjBound',source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,
            inclusion=record(out/'INDEPENDENT_NATIVE0.json'),readback=record(out/'NATIVE_READBACK.json'),Global_LB_gain=None if not ok else max(0.,bound-GLOBAL_LB),
            Reduced_ObjVal_is_FULL_UB=False,numerical_Gurobi_BB_contract=True,exact_rational_optimality_claim=False)
    except Exception as e:
        ledger.update(error=repr(e),traceback=traceback.format_exc())
        if entered:ledger['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        model.dispose();write(out/'NATIVE_CALL.json',ledger);write(DOCS/'FAST_LB_NATIVE_RESULT.json',ledger);write(DOCS/'FAST_LB_INDEPENDENT_CERTIFICATE.json',cert)
    print(json.dumps(dict(Native=ledger['Native_Runtime'],certificate=cert)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,required=True);native(parser.parse_args().seconds)
