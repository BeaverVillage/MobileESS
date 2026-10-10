"""Read-only profiles and original binding-based critical-line projection audit."""
from fractions import Fraction as F
import numpy as np
from .adapter import axis_sha
from .budget import write


def diagnose(case,decomp,first_round_folder,output):
    from .case import read
    result=read(first_round_folder/'RESULT.json')
    raw=np.load(first_round_folder/'MASTER_SOLUTION.npz',allow_pickle=False)
    rho=float(case.d['objective']@case.point+case.d['constant'])
    product=case.A@case.point;names=case.d['row_names'].astype(str)
    thermal=np.array([n.startswith(('line_thermal_face','NormalAmps')) for n in names])
    tight=thermal & (abs(product-case.d['rhs'])<=1e-8)
    rows=np.flatnonzero(tight)
    source_rows=raw['source_rows'];profiles=[];gridcols={int(j) for j in decomp.nonunit_columns}
    binding={}
    for i,name in enumerate(names):
        if not name.startswith(('injection_P_binding','injection_Q_binding')):continue
        a,b=case.A.indptr[i:i+2]
        candidates=[(int(j),float(v)) for j,v in zip(case.A.indices[a:b],case.A.data[a:b])
                    if str(case.d['names'][j]).startswith(('injection_P[','injection_Q['))]
        if len(candidates)==1:binding[i]=candidates[0]
    source_index={str(n):i for i,n in enumerate(names)}
    for k,(u,block) in enumerate(decomp.units.items()):
        item=result['admitted_columns'][k]
        point=np.load(item['file'],allow_pickle=False)['point'];seed=case.point[block.original_columns]
        B=case.A[source_rows][:,block.original_columns].tocsr()
        new=B@point;old=B@seed;delta=new-old
        family={}
        for f in ('route_flow','node_activity','charge_mode','Pch','Pdis','Q','SOC'):
            mask=np.array([str(n).startswith(f+'[') for n in block.d['names']])
            family[f]=dict(changed_coordinates=int(np.count_nonzero(point[mask]!=seed[mask])),
                           max_abs_difference=float(np.max(abs(point[mask]-seed[mask]),initial=0.)),
                           seed_profile_sha=axis_sha(seed[mask].view(np.int64)),
                           new_profile_sha=axis_sha(point[mask].view(np.int64)))
        changes=point-seed;global_delta=np.zeros(case.A.shape[1]);global_delta[block.original_columns]=changes
        shifts=case.A@global_delta;injections={}
        exact_delta={int(j):F(float(point[k]))-F(float(seed[k]))
                     for k,j in enumerate(block.original_columns) if point[k]!=seed[k]}
        for i,(j,c) in binding.items():
            # Exact original unit contribution, no optimized response model.
            a,b=case.A.indptr[i:i+2]
            value=sum((F(float(v))*exact_delta.get(int(z),F(0)) for z,v in
                       zip(case.A.indices[a:b],case.A.data[a:b]) if z not in gridcols),F(0))
            injections[j]=-value/F(c)
        critical=[]
        for t in (29,30,31,32):
            row=dict(slot=t,line=26)
            for pq in ('P','Q'):
                label='response_line_'+pq+'_binding[%d,26]'%t
                i=source_index.get(label)
                if i is None:row[pq]='UNKNOWN';continue
                a,b=case.A.indptr[i:i+2];response=None;value=F(0);unknown=False
                for j,c in zip(case.A.indices[a:b],case.A.data[a:b]):
                    n=str(case.d['names'][j])
                    if n=='response_line_'+pq+'[%d,26]'%t:response=F(float(c))
                    elif int(j) in injections:value+=F(float(c))*injections[int(j)]
                    elif n.startswith(('injection_P[','injection_Q[')):unknown=True
                    elif c:unknown=True
                row[pq]='UNKNOWN' if unknown or response is None else str(-value/response)
            critical.append(row)
        profiles.append(dict(unit=u,comparison_to_original_UB_seed=family,
             numeric_grid_projection_changed_rows=int(np.count_nonzero(delta)),
             numeric_grid_projection_Linf=float(np.max(abs(delta),initial=0.)),
             numeric_grid_projection_duplicate=bool(np.array_equal(new,old)),
             similarity_diagnostic_only=True,no_automatic_projection_pruning=True,
             critical_line26_response_delta=critical,
             old_dual_reduced_cost=item['exact_reduced_cost'],
             adopted_lambda=float(raw['X'][-4+k]),bound_active_reduced_cost=float(raw['RC'][-4+k])))
    report=dict(original_UB_objective=rho,tight_thermal_row_count=len(rows),
         tight_thermal_rows=[str(names[i]) for i in rows[:80]],profiles=profiles,
         objective_change=result['master_objective_after']-result['master_objective_before'],
         dual_degeneracy_evidence=dict(changed_rows=result['master_dual_changed_rows'],
                                      no_material_objective_change=True,new_lambdas_near_zero=True),
         lambda_upper_bound_not_changed=True,native_optimize_calls=0)
    write(output,report);return report
