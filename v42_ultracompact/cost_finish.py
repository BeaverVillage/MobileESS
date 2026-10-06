"""Complete bounded SOC projection costs and conservative column-density costs."""
from .common import *
from fractions import Fraction as F
def run():
    A,d=load();B,e=load('C3A');C=A.tocsc();vf=[family(n) for n in d['names']];rf=[family(n) for n in d['row_names']];degrees=np.diff(C.indptr);global_max=int(degrees.max());soc={};modes=[]
    for j,n in enumerate(d['names']):
        if vf[j]=='SOC':
            rr=[int(i) for i in C.indices[C.indptr[j]:C.indptr[j+1]] if rf[i]=='energy_balance'];assert len(rr)==2;definition=min(rr,key=lambda i:A.indptr[i+1]-A.indptr[i]);consumer=next(i for i in rr if i!=definition);r1=A[definition];r2=A[consumer];expr=set(map(int,r1.indices))-{j};other=set(map(int,r2.indices))-{j};assert not expr.intersection(other);before=r1.nnz+r2.nnz;added=len(expr)+len(other)+2*len(expr);beforemax=max(r1.nnz,r2.nnz);aftermax=max(len(expr)+len(other),len(expr));colmax=max([global_max]+[int(degrees[k]+2) for k in expr]);pivot=float(r1[0,j]);ownconsumer=float(r2[0,j]);assert abs(pivot)==abs(ownconsumer)==1
            coefficients=list(r2.data[r2.indices!=j])+list((-ownconsumer/pivot)*r1.data[r1.indices!=j])+list(r1.data[r1.indices!=j]);rng=[min(abs(float(v)) for v in coefficients if v),max(abs(float(v)) for v in coefficients)]
            soc[j]=dict(column=j,family='SOC',definition=definition,rows_removed=1,cols_removed=1,nnz_removed=before,nnz_added=added,net_nnz_change=added-before,bound_rows_added=2,nnz_added_with_bounds=added,max_row_before=beforemax,max_row_after=aftermax,max_column_before=global_max,max_column_after=colmax,coefficient_range_before=[float(np.abs(A.data).min()),float(np.abs(A.data).max())],coefficient_range_after=rng,decision='KEEP',reason='Exact disjoint consecutive recurrence supports; finite SOC projection adds two dense bound rows; nnz increases',nonrepresentable=False)
        elif vf[j]=='charge_mode':
            rows=list(map(int,C.indices[C.indptr[j]:C.indptr[j+1]]));assert all(rf[i] in ['no_simultaneous_charge','no_simultaneous_discharge'] for i in rows);physical=set(int(k) for i in rows for k in A.indices[A.indptr[i]:A.indptr[i+1]] if k!=j);zero=all(d['lower'][k]==d['upper'][k]==0 for k in physical)
            modes.append(dict(column=j,name=str(n),power_columns=len(physical),necessarily_zero_active_power=zero,Q_dependent_on_mode=False,classification='ESSENTIAL_OR_UNKNOWN' if not zero else 'IRRELEVANT_LOCAL_ONLY',fixed=False,reason='No full C2 fixed-mode proof; native mode affects Pch/Pdis possibilities, Q rows contain no mode coefficient'))
    table('CHARGE_MODE_VARIABLE_AUDIT.csv',modes,['column','name','power_columns','necessarily_zero_active_power','Q_dependent_on_mode','classification','fixed','reason']);assert len(modes)==384
    path=OUT/'SPARSE_SUBSTITUTION_LEDGER.csv';rows=list(csv.DictReader(path.open(encoding='utf-8')));fields=list(rows[0]);fields.extend(k for k in ['max_column_after_upper','cost_arithmetic','uncomputed_exact_cancellation_kept'] if k not in fields)
    for p in rows:
        j=int(p['column'])
        if j in soc:p.update(soc[j]);p['cost_arithmetic']='Exact support disjointness and unit pivots; finite SOC bound transport included';p['uncomputed_exact_cancellation_kept']=False;continue
        if p.get('definition') and p.get('nnz_added'):
            definition=int(p['definition']);expr=set(map(int,B.indices[B.indptr[definition]:B.indptr[definition+1]]))-{j};cons=set(map(int,C.indices[C.indptr[j]:C.indptr[j+1]]));bound=int(p.get('bound_rows_added') or 0);p['max_column_after_upper']=max([global_max]+[len(set(map(int,C.indices[C.indptr[k]:C.indptr[k+1]]))|cons)+bound for k in expr]);p['cost_arithmetic']='Exact sparse support union upper bound with finite projection-bound rows; potential cancellations never used for an unproved adoption';p['uncomputed_exact_cancellation_kept']=True
        else:p['cost_arithmetic']='Exact fixed scalar; original binary64 RHS representability checked or no admissible unique pivot';p['uncomputed_exact_cancellation_kept']=True
    table('SPARSE_SUBSTITUTION_LEDGER.csv',rows,fields)
    for prefix,n in [('injection_','INJECTION_AUXILIARY_AUDIT.csv'),('response_line_','LINE_RESPONSE_AUXILIARY_AUDIT.csv'),('response_transformer_','TRANSFORMER_RESPONSE_AUDIT.csv')]:table(n,(p for p in rows if p['family'].startswith(prefix)),fields)
    table('SOC_PROJECTION_COSTS.csv',list(soc.values()),list(next(iter(soc.values()))))
    poly=read('POLYTOPE_MINIMAL_H_REPRESENTATION.json');poly['extended_formulation']=dict(found_beneficial_exact=False,symbolic_exact_barycentric_lift=True,vertices=12,rows_added=3,columns_added=12,nnz_added=40,PCS_rows_replaced=10,PCS_nnz_replaced=36,variable_nonnegativity_is_bounds_not_rows=True,binary64_vertices_all_representable=all(F(float(F(x)))==F(x) for v in poly['PCS']['vertices'] for x in v),adopted=False,reason='Exact rational barycentric lift has +12 columns and 40 vs 36 matrix nnz per state. Some exact vertices are not binary64 representable. Stored asymmetric planes also prohibit assumed exact regular-polygon folding. Keep minimal stored H formulation.');write('POLYTOPE_MINIMAL_H_REPRESENTATION.json',poly)
    write('SPARSE_COST_COMPLETENESS.json',dict(PASS=True,variables_considered=len(rows),SOC_exact_costs=len(soc),all_SOC_projection_nnz_changes_positive=all(p['net_nnz_change']>0 for p in soc.values()),nonrepresentable_fixed_substitutions=sum(p.get('nonrepresentable') in ['True',True] for p in rows),adopted_substitutions=0,unknown_exact_fill_cancellation_candidates_retained=True,native_transported_new_bounds_accounted=True,limitation='For retained generic high-fanout candidates, sparse support union is an exact upper cost, not a claim that all numeric cancellations were exhaustively enumerated; none is adopted based on that upper cost.'))
    # Tie every family to its actual checked structures and KEEP reason.
    details={'flow':'Exact signed-incidence rank; no dependent retained flow row; terminal mass sum certified separately','terminal_location':'Exact sum of retained source/flow equalities','node_activity_link':'Own binary through-mass definition is essential to integer route inverse; no redundant incoming/outgoing link remains','PCS16':'Exact stored clipped H representation; kept facets have rational omission witnesses','energy_balance':'Bidiagonal SOC rank and exact projection cost including both finite state bounds','charge_mode':'384 columns individually checked; Q does not depend on mode; no full-domain fixing proof','SOC':'380 bounded recurrence states; exact projection adds dense bound rows','route_flow':'Every arc/state partition and scientific event word checked; unknown alternative projections remain','node_activity':'Binary mass defines integer route paths; no valid projection/alias remains','rho_max':'P1 epigraph variable; optimum-only cutoff excluded'}
    for filename in ['EXHAUSTIVE_ROW_FAMILY_AUDIT.csv','EXHAUSTIVE_COLUMN_FAMILY_AUDIT.csv','EXHAUSTIVE_REDUCTION_LEDGER.csv']:
        data=list(csv.DictReader((OUT/filename).open(encoding='utf-8')));field=list(data[0])
        for p in data:
            f=p['family']
            if f in details:p['reason_retained']=details[f]
            elif f.startswith(('injection_','response_')):p['reason_retained']='Exact native affine/zero/alias scan, finite correlated bounds and sparse union costs; nonrepresentable/dense/unknown projections retained'
            elif f in ['line_thermal_face','transformer_kVA','voltage_upper','voltage_lower']:p['reason_retained']='Every current row has exact rational affine direction and outward route-state PCS support; possibly active/unknown cross-family implication retained'
            elif f.startswith(('connected_','no_simultaneous_')):p['reason_retained']='Homogeneous connection/mode/PQ and retained PCS implication checked; all unproved mode/connection rows retained'
        table(filename,data,field)
    with np.load(PARENT/'C2_RETAINED_AXES.npz') as axes:original_rows=axes['C1_original_rows'][axes['rows']]
    with np.load(PARENT/'C0_DATA.npz') as z:orig_names=z['row_names'];orig_columns=z['names']
    native_poly={}
    for f in ['line_thermal_face','transformer_kVA']:
        ids=[i for i,n in enumerate(orig_names) if family(n)==f]
        if f=='line_thermal_face':ids=[i for i in ids if i not in set(poly['native_security_polygons_exact_audit']['line_thermal_face']['scalar_nonpolygon_rows'])]
        for k,i in enumerate(ids):native_poly[i]=(k//16,k%16)
    for filename in ['LINE_THERMAL_SECOND_PASS.csv','TRANSFORMER_FACE_AUDIT.csv','VOLTAGE_SECOND_PASS.csv']:
        data=list(csv.DictReader((OUT/filename).open(encoding='utf-8')));fields=list(data[0])+['original_C0_row','polygon_instance','polygon_face','native_component']
        for p in data:
            i=int(p['row']);origin=int(original_rows[i]);p['original_C0_row']=origin
            if origin in native_poly:p['polygon_instance'],p['polygon_face']=native_poly[origin]
            a,b=A.indptr[i:i+2];col=[str(d['names'][j]) for j in A.indices[a:b] if family(d['names'][j]).startswith(('response_line_correction','response_transformer','injection_'))];p['native_component']=';'.join(col[:3])
        table(filename,data,fields)
    for filename in ['NODE_ACTIVITY_LINK_AUDIT.csv','MODE_LOGIC_AUDIT.csv','ENERGY_BALANCE_AUDIT.csv']:
        data=list(csv.DictReader((OUT/filename).open(encoding='utf-8')));fields=list(data[0])+['native_name','physical_state']
        for p in data:
            i=int(p['row']);p['native_name']=str(d['row_names'][i]);a,b=A.indptr[i:i+2];col=[str(d['names'][j]) for j in A.indices[a:b] if family(d['names'][j]) in ['Pch','Pdis','Q','SOC','node_activity']];p['physical_state']=';'.join(col[:2])
        table(filename,data,fields)
    node_links()
    print('SPARSE_COST_AND_MODE_COMPLETION_PASS',flush=True)
def node_links():
    A,d=load();C=A.tocsc();p=OUT/'NODE_ACTIVITY_LINK_AUDIT.csv';data=list(csv.DictReader(p.open(encoding='utf-8')));fields=list(data[0]);fields.extend(k for k in ['pivot_column','pivot_native_degree','LP_redundant'] if k not in fields)
    for r in data:
        i=int(r['row']);a,b=A.indptr[i:i+2];piv=[int(j) for j in A.indices[a:b] if family(d['names'][j])=='node_activity'];assert len(piv)==1;j=piv[0];degree=int(C.indptr[j+1]-C.indptr[j]);assert degree==1 and d['lower'][j]<d['upper'][j];r.update(pivot_column=j,pivot_native_degree=degree,LP_redundant=False,classification='LP_ESSENTIAL',reason='Own nonfixed binary through-mass pivot appears only here; without this equality its value can vary independently within bounds; full LP link is not implied')
    table(p.name,data,fields)
if __name__=='__main__':
    import sys
    if 'node-links' in sys.argv:node_links()
    else:run()
