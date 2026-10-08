"""Read-only certified materiality gate and critical grid support census."""
from common import *
from collections import Counter,defaultdict

def gate(label):
    original=read(OUT/'runs/ORIGINAL/RESULT.json');candidate=read(OUT/f'runs/{label}/RESULT.json')
    paired=None;conservative=None;passed=False
    if original['optimal_certificate_PASS'] and candidate['optimal_certificate_PASS']:
        original_exact=F(original['valid_LB_exact']);candidate_exact=F(candidate['valid_LB_exact'])
        paired=candidate_exact-original_exact
        conservative=candidate_exact-max(original_exact,F.from_float(LB))
        passed=conservative>=F(1,1000)
    r=dict(PASS=passed,label=label,required_certified_improvement=.001,paired_certified_Delta_LB=float(paired) if paired is not None else None,paired_certified_Delta_exact=str(paired) if paired is not None else None,improvement_over_best_original_or_inherited=float(conservative) if conservative is not None else None,materiality_policy='Conservative preregistered gate: candidate exact LB minus max(fresh original exact LB, inherited valid global LB) >= 1/1000. Paired delta reported separately.',candidate_native_status=candidate['status_name'],original_native_status=original['status_name'],exactness_PASS=read(OUT/f'{label}_EXACTNESS_VERIFICATION.json')['PASS'],native_objective_gain=candidate['native_LP_objective']-original['native_LP_objective'] if candidate['native_LP_objective'] is not None and original['native_LP_objective'] is not None else None,canary_authorized_by_gate=passed)
    atomic(OUT/f'{label}_MATERIALITY_GATE.json',r);print(json.dumps(r),flush=True);return r

def support():
    A,d,_=load();selection=read(OUT/'ROOT_WINDOW_SELECTION.json');meta=[info(n) for n in d['names']];names={str(n):j for j,n in enumerate(d['names'])}
    points=[('ARCHIVED_ROOT',*root_point())]
    for label in ['ORIGINAL','A','B']:
        folder=OUT/'runs'/label
        if (folder/'LP_POINT_DUAL.npz').exists():
            with np.load(folder/'LP_POINT_DUAL.npz') as z:points.append((label,z['x'][:A.shape[1]],z['Pi'][:A.shape[0]]))
        elif (folder/'UNRESOLVED_POINT.npz').exists():
            with np.load(folder/'UNRESOLVED_POINT.npz') as z:points.append((label+'_UNRESOLVED',z['x'][:A.shape[1]],None))
    physical=[];rows=[];contributions=[]
    for label,x,pi in points:
        for t in range(selection['window']['start'],selection['window']['end_exclusive']):
            for unit in selection['all_units']:
                for j,(fam,u,slot,args) in enumerate(meta):
                    if u!=unit or slot!=t or fam not in ['Pch','Pdis','Q','node_activity','charge_mode']:continue
                    activity=names.get(f'node_activity[{unit},{args[1]},{t}]') if len(args)==3 else None
                    mode=names.get(f'charge_mode[{unit},{t}]')
                    physical.append(dict(point=label,column=j,name=str(d['names'][j]),unit=unit,retained_slot=t,family=fam,value=float(x[j]),bound_fractionality=float(min(abs(x[j]),abs(1-x[j]))) if d['types'][j]=='B' else None,associated_node_activity=float(x[activity]) if activity is not None else None,associated_charge_mode=float(x[mode]) if mode is not None else None))
        for g in selection['grid_rows']:
            i=g['row'];cols=A.indices[A.indptr[i]:A.indptr[i+1]];coeffs=A.data[A.indptr[i]:A.indptr[i+1]];lhs=float((A.getrow(i)@x).item());rhs=float(d['rhs'][i]);sense=str(d['sense'][i]);slack=rhs-lhs if sense=='<' else lhs-rhs if sense=='>' else -abs(lhs-rhs)
            rows.append(dict(point=label,original_row_id=i,row_name=str(d['row_names'][i]),sense=sense,retained_variable_slot=g['slot'],physical_line_id='NOT_RETAINED_IN_C3A_GENERIC_ROW_NAMES',rhs=rhs,lhs=lhs,feasible_signed_slack=slack,Pi=float(pi[i]) if pi is not None else None,nonzeros=len(cols),source='Original C3A row unchanged; slot inferred from retained variable names, possibly affected by frozen aliases'))
            for j,a in zip(cols,coeffs):
                if abs(float(a*x[j]))<1e-10:continue
                contributions.append(dict(point=label,original_row_id=i,retained_variable_slot=g['slot'],column=int(j),variable=str(d['names'][j]),family=meta[j][0],unit=meta[j][1],coefficient=float(a),value=float(x[j]),row_contribution=float(a*x[j])))
    table(OUT/'CRITICAL_GRID_ROW_COMPARISON.csv',rows);table(OUT/'CRITICAL_WINDOW_FRACTIONAL_SUPPORT.csv',physical);table(OUT/'CRITICAL_GRID_NONZERO_CONTRIBUTIONS.csv',contributions)
    atomic(OUT/'CRITICAL_GRID_PROVENANCE.json',dict(PASS=True,selected_original_grid_rows=selection['selected_grid_rows'],window=selection['window'],actual_physical_line_labels_available=False,limitation='The frozen C3A row names omit original line identities. Retained-variable slots can be alias representatives and are not asserted to be original physical timestamps. Actual matrix row IDs/coefficient contributions and node/mode/PQ support are reported without invented identifiers.',support_not_used_as_bound_certificate=True))

if __name__=='__main__':
    if len(sys.argv)>1:gate(sys.argv[1])
    else:support()
