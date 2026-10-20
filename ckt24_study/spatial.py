"""Offline PCC drawing-order witness. It cannot certify port infrastructure."""
from .preflight import *
from .traffic import readcsv
from .order import sign,verify

def select():
    # Require complete fresh AC survey before scoring any final witness.
    receipt=json.loads((DOC/'SENSITIVITY_RAW_RECEIPT.json').read_text())
    s=readcsv(DOC/'MESS_PQ_CONTROLLABILITY.csv')
    if len(s)!=receipt['candidate_count']*4:raise ValueError('INCOMPLETE_SENSITIVITY')
    scores={}
    for r in s:scores[r['bus']]=max(scores.get(r['bus'],0),-float(r['delta_rho']))
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text())
    cand=[b for b in inv['buses'] if b['bus'] in scores]
    service=readcsv(DOC/'ORIGINAL_TRAFFIC_SERVICES.csv')
    import gurobipy as gp
    from gurobipy import GRB
    outcome=[]
    # Attempt all 24 first. A time limit does not prove infeasibility.
    for active,label in [(service,'ALL24'),([s for s in service if s['type']=='IDC'],'AIDC12')]:
        n=len(active);m=len(cand)
        with gp.Env(empty=True) as env:
            env.setParam('OutputFlag',0);env.start()
            with gp.Model('OFFLINE_PCC_ORDER_SCREENING_'+label,env=env) as model:
                model.Params.Threads=1;model.Params.TimeLimit=45;model.Params.MIPGap=.01;model.Params.Seed=20261020
                model.Params.FeasibilityTol=1e-9;model.Params.IntFeasTol=1e-9
                x=model.addVars(n,m,vtype=GRB.BINARY)
                ex=np.asarray([b['x'] for b in cand]);ey=np.asarray([b['y'] for b in cand])
                ex=(ex-ex.min())/np.ptp(ex);ey=(ey-ey.min())/np.ptp(ey)
                tx=np.asarray([float(s['x']) for s in active]);ty=np.asarray([float(s['y']) for s in active])
                tx=(tx-tx.min())/np.ptp(tx);ty=(ty-ty.min())/np.ptp(ty)
                for i in range(n):model.addConstr(x.sum(i,'*')==1)
                for j in range(m):model.addConstr(x.sum('*',j)<=1)
                for axis,values,source in [('x',ex,tx),('y',ey,ty)]:
                    order=sorted(range(n),key=lambda i:source[i])
                    for a,b in zip(order,order[1:]):
                        if source[b]-source[a]>1e-10:
                            eps=.010001/(np.ptp([c[axis] for c in cand]))
                            model.addConstr(gp.quicksum(values[j]*(x[b,j]-x[a,j]) for j in range(m))>=eps)
                # Geography cost gives broad coverage without changing axes/IDs.
                # Electrical response enters only after the independent survey.
                scale=max(scores.values()) or 1
                model.setObjective(gp.quicksum(((ex[j]-tx[i])**2+(ey[j]-ty[i])**2-.1*scores[cand[j]['bus']]/scale)*x[i,j]
                                               for i in range(n) for j in range(m)),GRB.MINIMIZE)
                model.optimize()
                result=dict(scope=label,status=int(model.Status),solutions=model.SolCount,wall=model.Runtime,
                    source='OFFLINE_MAPPING_ONLY_NOT_A1_M1_A2_M2',spatial_metric='Original axes; no rotation/reflection/axis exchange',
                    electrical_branch_dispersion_certified=False)
                outcome.append(result)
                if model.SolCount:
                    rows=[]
                    for i,sr in enumerate(active):
                        j=max(range(m),key=lambda j:x[i,j].X);b=cand[j]
                        rows.append(dict(**sr,ckt24_bus=b['bus'],electrical_phase='1.2.3',voltage_base_ll_kv=b['kv_ll'],
                            e_x=b['x'],e_y=b['y'],pcc_rating_kva='',pcc_port_count='',
                            screening_response_pu=scores[b['bus']],
                            status='PROVISIONAL_DRAWING_ORDER_WITNESS_NOT_PHYSICAL_PCC_FREEZE'))
                    proof=verify(rows)
                    if any(not r['PASS'] for r in proof):
                        result['postcheck']='REJECTED_NUMERICAL_ORDER_VIOLATION';continue
                    csvout('SPATIAL_RELATIVE_ORDER_VERIFICATION.csv',proof)
                    csvout('CKT24_AIDC_PCC_MAPPING.csv',[r for r in rows if r['type']=='IDC'])
                    if n==24:csvout('CKT24_SERVICE_SITE_MAPPING.csv',rows)
                    else:
                        matched={r['service_id']:r for r in rows}
                        blank={k:'' for k in rows[0]}
                        complete=[matched.get(s['service_id'],dict(blank,**s,status='UNMAPPED_NO_VERIFIED_PCC')) for s in service]
                        csvout('CKT24_SERVICE_SITE_MAPPING.csv',complete)
                    result['postcheck']='DRAWING_ORDER_PASS_GEOGRAPHIC_AUTHORITY_AND_PHYSICAL_PCC_PENDING'
                    save('SPATIAL_SCREENING_STATUS.json',dict(attempts=outcome,rows=n,relations=len(proof),
                        inversions=sum(not r['PASS'] for r in proof),frozen=False,
                        selection_limit='No port/transformer/interface engineering or branch-diversity certificate; no final deployment claim'))
                    return
    save('SPATIAL_SCREENING_STATUS.json',dict(attempts=outcome,frozen=False,
        status='NO_VERIFIED_WITNESS; time-limit outcomes do not prove infeasibility'))
    blank_fields=dict(ckt24_bus='',electrical_phase='',voltage_base_ll_kv='',e_x='',e_y='',pcc_rating_kva='',pcc_port_count='',
                      screening_response_pu='',status='UNMAPPED_NO_VERIFIED_PCC')
    rows=[dict(**s,**blank_fields) for s in service]
    csvout('CKT24_SERVICE_SITE_MAPPING.csv',rows)
    csvout('CKT24_AIDC_PCC_MAPPING.csv',[r for r in rows if r['type']=='IDC'])
    pending=[]
    from itertools import combinations
    for a,b in combinations(service,2):
        for axis in ['x','y']:
            pending.append(dict(service_i=a['service_id'],service_j=b['service_id'],axis=axis,
                traffic_delta=float(a[axis])-float(b[axis]),electrical_delta='',traffic_sign=sign(float(a[axis])-float(b[axis]),.01),
                electrical_sign='',applicable='',PASS='',both_AIDC=a['type']==b['type']=='IDC',authority='NOT_VERIFIED'))
    csvout('SPATIAL_RELATIVE_ORDER_VERIFICATION.csv',pending)

if __name__=='__main__':select()
