"""Small exact t72 injection-set coupling master for actual binding branches.

At t72 every unit can stay at any of the 24 reachable sites throughout69..72,
with zero earlier P/Q and free SOC69=760. Any one-slot half-PCS point extends
to that legal four-slot trajectory. Thus the one-time injection projection
is exactly the union of the 48 location/mode half-polygons; no 96-slot hull.
"""
from common import *
from window_analysis import grid_closure
from fractions import Fraction as F
from collections import defaultdict

def main():
    assert not read(OUT/'SINGLE_WINDOW_VALID_LB_CERTIFICATE.json')['delta_LB']>=.001
    import gurobipy as gp
    A,d,start=load();a=Authority();expand,definitions=grid_closure(A,d);rho=int(np.flatnonzero(d['names']=='rho_max')[0])
    with (HISTORY/'CRITICAL_LINE_TIME_AUDIT.csv').open(encoding='utf-8') as f:historic=list(csv.DictReader(f))
    targets=[r for r in historic if int(r['slot'])==72]
    target_branches=sorted({r['branch_name'] for r in targets})
    assert set(target_branches)=={'line.sw1::A','line.l3::A'}
    full=a.load_matrix()
    with np.load(PARENT/'C3_RETAINED_AXES.npz') as z:c3rows=z['rows']
    with np.load(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz') as z:c2rows=z['rows'];c1orig=z['C1_original_rows']
    with np.load(history_authority.SOURCE/'REDUCTION_AXES.npz') as z:original_keep=z['keep']
    compact_original_ids=c1orig[c2rows[c3rows]]
    original_ids=np.full(len(compact_original_ids),-1,dtype=np.int64)
    represented=compact_original_ids<len(original_keep)
    original_ids[represented]=original_keep[compact_original_ids[represented]]
    wanted=set()
    for r in targets:
        orig=int(r['original_native_row']);line=int(r['line_index'])
        for i in range(max(0,orig-16),min(full.shape[0],orig+17)):
            if str(a.full['row_names'][i])!='line_thermal_face':continue
            names=[str(a.full['names'][j]) for j in full.indices[full.indptr[i]:full.indptr[i+1]]]
            if f'response_line_P[72,{line}]' in names:wanted.add(i)
    critical=set(int(i) for i in np.flatnonzero(np.isin(original_ids,list(wanted))))
    chosen=set(critical);visiting=list(critical)
    while visiting:
        i=visiting.pop()
        for j in A.indices[A.indptr[i]:A.indptr[i+1]]:
            if j==rho or str(d['names'][j]).startswith(('Pch[','Pdis[','Q[')) or d['lower'][j]==d['upper'][j]:continue
            assert j in definitions
            row=definitions[j]
            if row not in chosen:chosen.add(row);visiting.append(row)
    physical_names=[]
    for unit in sorted(a.initial):
        for siteid,site in enumerate(a.sites):
            assert siteid*96+69 in a.reachable[unit]
            for family in ('Pch','Pdis','Q'):physical_names.append(f'{family}[{unit},{site},72]')
        for mode in (0,1):
            coef=a.energy(unit,72)['charge' if mode else 'discharge']
            endpoint=F(760)+coef*F(300)
            assert F(440)<=endpoint<=F(1080)
    columns={rho}
    for i in chosen:columns.update(map(int,A.indices[A.indptr[i]:A.indptr[i+1]]))
    for name in physical_names:columns.update(a.expression(name)[0])
    columns=np.array(sorted(columns),int);index={int(j):k for k,j in enumerate(columns)}
    rows=[];rhs=[];senses=[];lower=d['lower'][columns].tolist();upper=d['upper'][columns].tolist();types=['C']*len(columns);objective=d['objective'][columns].tolist();state_records=[]
    def row(terms,sense='<',value=0):rows.append(dict(terms));rhs.append(float(value));senses.append(sense)
    for i in sorted(chosen):row([(index[int(j)],float(w)) for j,w in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]])],str(d['sense'][i]),d['rhs'][i])
    def col(lo,hi,typ='C'):
        j=len(lower);lower.append(lo);upper.append(hi);types.append(typ);objective.append(0);return j
    def link(name,contributions):
        terms,constant=a.expression(name);row([(index[j],float(w)) for j,w in terms.items()]+[(j,-w) for j,w in contributions],'=',-constant)
    for unit in sorted(a.initial):
        lams=[];power=defaultdict(list)
        for siteid,site in enumerate(a.sites):
            for mode in (0,1):
                lam=col(0,1,'B');p=col(0,300);q=col(-400,400);lams.append(lam)
                row([(p,1),(lam,-300)])
                for alpha,beta,cap in a.pcs(unit,site,72):row([(p,float(alpha)*(1 if mode==0 else -1)),(q,float(beta)),(lam,-float(cap))])
                power['Pch' if mode else 'Pdis',site].append((p,1));power['Q',site].append((q,1))
                state_records.append(dict(MESS=unit,site=site,mode=mode,lambda_column=lam,p_column=p,q_column=q,exact_four_slot_extension='stay(site,69),stay(site,70),stay(site,71),stay(site,72); E69=760; earlier P/Q=0; exact native SOC72->73 within[440,1080]'))
        row([(j,1) for j in lams],'=',1)
        for site in a.sites:
            for family in ('Pch','Pdis','Q'):link(f'{family}[{unit},{site},72]',power[family,site])
    ri=[];ci=[];vi=[]
    for i,terms in enumerate(rows):
        for j,w in terms.items():
            if w:ri.append(i);ci.append(j);vi.append(w)
    M=sparse.csr_matrix((vi,(ri,ci)),shape=(len(rows),len(lower)))
    e=dict(lower=np.array(lower),upper=np.array(upper),types=np.array(types),objective=np.array(objective),constant=0.,rhs=np.array(rhs),sense=np.array(senses))
    sparse.save_npz(OUT/'CROSS_MASTER_MATRIX.npz',M);np.savez_compressed(OUT/'CROSS_MASTER_DATA.npz',**e,original_columns=columns)
    authority=dict(UTC=stamp(),slot=72,branches=target_branches,all_retained_faces=len(critical),grid_binding_rows=len(chosen)-len(critical),units=4,sites=24,states=state_records,local_feasible_injection_projection_exact=True,individual_LP_hulls_exact=True,original_grid_coefficients_preserved_bit_exact=True,local_SOC_extension_proved_for_all_half_polygon_points=True,global96_slot_extendability_not_claimed=True,master_is_relaxation_of_every_original_global_integer_schedule=True,scope='Small simultaneous-face one-time master; measures local cross-unit/grid integrality without asserting global gap attribution. l10A is active at71/79, not72; actual simultaneous line at72 is l3A.',matrix_SHA256=sha(OUT/'CROSS_MASTER_MATRIX.npz'),data_SHA256=sha(OUT/'CROSS_MASTER_DATA.npz'))
    write('CROSS_MESS_MASTER_AUTHORITY.json',authority)
    results=[]
    for integral in (False,True):
        stage='CROSS_MASTER_INTEGER' if integral else 'CROSS_MASTER_CONVEX'
        m=gp.Model(stage);m.Params.OutputFlag=0
        v=m.addMVar(M.shape[1],lb=e['lower'],ub=e['upper'],obj=e['objective'],vtype=e['types'] if integral else 'C');m.addMConstr(M,v,e['sense'],e['rhs'])
        settings=dict(Threads=1,TimeLimit=300,Method=2,Crossover=2 if integral else 0,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=.005,Seed=20260929)
        for k,val in settings.items():m.setParam(k,val)
        m.Params.LogFile=str(OUT/(stage+'.log'));m.Params.LogToConsole=0;m.Params.OutputFlag=1;m.update()
        once(stage,settings,authority);print(stage+'_START',M.shape,flush=True);m.optimize()
        x=np.asarray(m.getAttr('X')) if m.SolCount else None
        if x is not None:np.savez_compressed(OUT/(stage+'_POINT.npz'),x=x)
        result=dict(stage=stage,Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),ObjVal=float(m.ObjVal) if m.SolCount else None,native_ObjBound=float(m.ObjBound),NodeCount=float(m.NodeCount) if integral else None,raw=replay(M,dict(e,types=e['types'] if integral else np.full(len(lower),'C')),x,integral) if x is not None else None,settings=settings,new_production_UB=False)
        if integral:result['conservative_global_LB']=float(np.nextafter(float(m.ObjBound)-1e-8,-np.inf))
        elif m.SolCount:
            pi=np.asarray(m.getAttr('Pi'));np.savez_compressed(OUT/(stage+'_DUAL.npz'),dual=pi);result['exact_dual_certificate']=exact_bounded_lagrangian(M,e,pi)[0]
        write(stage+'.json',result);results.append(result);m.dispose();print(stage+'_DONE',result['ObjVal'],result['native_ObjBound'],flush=True)
    write('CROSS_MESS_COUPLING_AUDIT.json',dict(authority=authority,results=results,local_convex_to_integer_objective_difference=(results[1]['ObjVal']-results[0]['ObjVal']) if all(r['ObjVal'] is not None for r in results) else None,new_valid_global_LB=max(LB,results[1]['conservative_global_LB']),delta_global_LB=max(0,results[1]['conservative_global_LB']-LB),local_master_effect_not_relabelled_global_gap_share=True,selective_integrality_test_counted_as_one=True))

if __name__=='__main__':main()
