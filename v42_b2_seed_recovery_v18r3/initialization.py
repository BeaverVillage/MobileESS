"""Fresh original continuous dispatch guides candidate modes; never admits relaxation."""
import numpy as np
from scipy import sparse
from v42_may_campaign_native90 import m_stage as original
from v42_b2_seed_recovery_v18.initialization import values_for,candidate_lp,admit,initialize as fallback
from .common import atomic

def mode_patterns(case,point):
    """Candidate binary decisions, not a repair to an admitted physical point."""
    totals={}
    for name,value in zip(map(str,case.d['names']),point):
        if name.startswith(('Pch[','Pdis[')):
            family,axis=name[:-1].split('[');unit,site,slot=axis.split(',')
            pair=totals.setdefault((unit,int(slot)),dict(Pch=0.,Pdis=0.))
            pair[family]+=float(value)
    direction={axis:float(v['Pch']>=v['Pdis']) for axis,v in totals.items()}
    fractional={}
    for name,value in zip(map(str,case.d['names']),point):
        if name.startswith('charge_mode['):
            unit,t=name[12:-1].split(',');fractional[unit,int(t)]=float(value>=.5)
            direction.setdefault((unit,int(t)),0.)
    return [('ORIGINAL_LP_PCH_PDIS_DIRECTION',direction),('ORIGINAL_LP_MODE_THRESHOLD',fractional)]

def initialize(case,budget,progress):
    sites,initial,arcs,_,_=case.graph
    stays={(a[0],a[1]):k for k,a in enumerate(arcs) if a[-1] is None}
    paths={u:[stays[s,t] for t in range(96)] for u,s in initial.items()}
    ids,values=values_for(case,paths,lambda u,t:False)
    route_only=np.asarray([not str(case.d['names'][j]).startswith('charge_mode[') for j in ids])
    ids,values=ids[route_only],values[route_only]
    model,identity=original._model(case,continuous=True)
    guide=None
    try:
        fix=sparse.csr_matrix((np.ones(len(ids)),(np.arange(len(ids)),ids)),shape=(len(ids),case.A.shape[1]))
        model.addMConstr(fix,model.getVars(),'=',values,name='INITIALIZATION_ONLY_ORIGINAL_STATIONARY_ROUTE')
        model.Params.Method=1;model.update()
        atomic(case.output/'MODE_GUIDE_MODEL.json',dict(model_identity=identity,route_integer_columns_fixed=len(ids),
            charge_mode_relaxed_for_candidate_generation_only=True,original_rows_and_objective_unchanged=True,
            no_UB_or_integer_feasibility_claim=True,Adaptive_domain_changed=False))
        budget.native_optimize(model,component='FEASIBILITY_LP',track='M_MODE_GUIDE',
            label='CURRENT_DAY_ORIGINAL_ROUTE_LP_MODE_GUIDE',requested_seconds=120.)
        if model.SolCount:
            guide=np.asarray(model.getAttr('X'),dtype=float)
            np.savez_compressed(case.output/'UNADMITTED_MODE_GUIDE_POINT.npz',point=guide)
        atomic(case.output/'MODE_GUIDE_RESULT.json',dict(Native_status=int(model.Status),SolCount=int(model.SolCount),
            certified_UB=None,FULL_validated_integer_point=False,point_used_only_for_candidate_modes=guide is not None))
    finally:model.dispose()
    if guide is not None:
        seen=set()
        for i,(kind,modes) in enumerate(mode_patterns(case,guide)):
            key=tuple(sorted(modes.items()))
            if key in seen:continue
            seen.add(key)
            ids,values=values_for(case,paths,lambda u,t,m=modes:bool(m[u,t]))
            found=candidate_lp(case,budget,ids,values,f'GUIDED_{i:02d}',dict(kind=kind,
                source='UNADMITTED_CURRENT_DAY_ORIGINAL_CONTINUOUS_LP',paths=paths,
                candidate_generation_only=True,rounding_or_repair_of_returned_LP_point=False),progress)
            if found is not None:
                point,receipt,path=found
                accepted=admit(case,point,receipt,path,budget,kind)
                from .common import read
                receipt_path=case.output/'SEED_BYPASS_CERTIFIED_DISPATCH.json'
                row=read(receipt_path)
                row.update(LP_initialization_Native_Runtime=sum(c['Native_Runtime'] for c in budget.calls
                    if c['track'] in ('M_MODE_GUIDE','M_CANDIDATE','M_START')),
                    relaxed_guide_never_admitted_as_integer_point=True)
                atomic(receipt_path,row)
                return accepted
    return fallback(case,budget,progress)
