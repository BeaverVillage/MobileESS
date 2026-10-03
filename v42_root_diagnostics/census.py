"""Full scientific matrix census, conservative helper bounds, source traces."""
import math,re
from collections import Counter
from .common import *
from v42_exact_start.reconstruct import binding_rules

THRESHOLDS=[1e-14,1e-13,1e-12,1e-10,1e-8]
def stats(values,prefix=''):
    v=np.asarray(values);v=v[np.isfinite(v)]
    if not len(v):return {prefix+k:None for k in ['min','max','p01','p05','p50','p95','p99']}
    return {prefix+k:float(x) for k,x in zip(['min','max','p01','p05','p50','p95','p99'],[v.min(),v.max(),*np.percentile(v,[1,5,50,95,99])])}
def axis_stats(A):
    mx=np.asarray(abs(A).max(axis=1).toarray()).ravel();counts=np.diff(A.indptr)
    mn=np.minimum.reduceat(np.r_[abs(A.data),np.inf],A.indptr[:-1]);mn[counts==0]=np.inf
    return dict(L1=np.asarray(abs(A).sum(axis=1)).ravel(),L2=np.sqrt(np.asarray(A.multiply(A).sum(axis=1)).ravel()),
        Linf=mx,ratio=np.divide(mx,mn,out=np.zeros_like(mx),where=counts>0))
def axis_census(kind,A,labels,rhs=None,lower=None,upper=None):
    groups,codes=np.unique(labels,return_inverse=True);entry_codes=np.repeat(codes,np.diff(A.indptr));norm=axis_stats(A);results=[]
    for code,label in enumerate(groups):
        selected=codes==code;vals=abs(A.data[entry_codes==code]);n=len(vals)
        item=dict(formulation=kind,family=str(label),axis_elements=int(selected.sum()),nnz=n,min_nonzero_abs_a=float(vals.min()) if n else None,
            max_abs_a=float(vals.max()) if n else None,dynamic_range=float(vals.max()/vals.min()) if n else None,median_abs_a=float(np.median(vals)) if n else None)
        item.update(stats(vals,'coefficient_'))
        for t in THRESHOLDS:item['count_abs_a_lt_'+str(t)]=int((vals<t).sum())
        item['count_abs_a_gt_100']=int((vals>100).sum())
        for key,value in norm.items():item.update(stats(value[selected],key+'_'))
        for t in [1e6,1e8,1e10,1e12]:item['coefficient_ratio_gt_'+str(t)]=int((norm['ratio'][selected]>t).sum())
        if rhs is not None:item.update(RHS_min=float(rhs[selected].min()),RHS_max=float(rhs[selected].max()))
        if lower is not None:item.update(declared_LB_min=float(lower[selected].min()),declared_UB_max=float(upper[selected].max()))
        results.append(item)
    return results,norm

def conservative_bounds(m,names,rows):
    rules,A,rhs,_=binding_rules(m,names,rows)
    lo=np.array(m.getAttr('LB'));hi=np.array(m.getAttr('UB'));lo[lo<=-gp.GRB.INFINITY]=-np.inf;hi[hi>=gp.GRB.INFINITY]=np.inf
    for j,i in rules:
        l=[float(rhs[i])];u=[float(rhs[i])]
        for k,a in zip(A[i].indices,A[i].data):
            if k==j:continue
            w=-float(a);l.append(math.nextafter(w*(lo[k] if w>=0 else hi[k]),-math.inf));u.append(math.nextafter(w*(hi[k] if w>=0 else lo[k]),math.inf))
        lo[j]=math.nextafter(math.fsum(l),-math.inf);hi[j]=math.nextafter(math.fsum(u),math.inf)
    return np.maximum(abs(lo),abs(hi))

def source_context(fam):
    if fam.startswith('compact_'):return 'v42_monolithic/formulation.py','Compact.__init__','Mapped route/connected state expression','dimensionless route state'
    if GRID(fam):return 'v42_m1_sparse/grid.py','add_compressed / compressed_grid / response','Frozen Planning grid affine response or 16-face grid limit','row-specific: pu^2, dimensionless line loading, kW/kvar/kVA'
    return 'v42_native/mess.py','solve / pcs_rows','Native route, PCS, mode or battery energy balance','row-specific: dimensionless route/mode, kW/kvar/kVA or kWh'

def replay(row,col,a,fam,names,rows,coeff,initial_units):
    name=str(names[col]);vf=family(name);terms={};reason='Original source-defined coefficient; magnitude follows stated units and frozen source formula.'
    slot=None;expected=None;formula=None
    if fam=='PCS16':
        # Kept PCS rows occur as sixteen consecutive polygon faces.
        face=int(np.searchsorted(np.flatnonzero(rows=='PCS16'),row))%16
        if vf=='Pch':expected=-math.cos(2*math.pi*face/16);formula='-cos(2*pi*face/16)'
        elif vf=='Pdis':expected=math.cos(2*math.pi*face/16);formula='cos(2*pi*face/16)'
        elif vf=='Q':expected=math.sin(2*math.pi*face/16);formula='sin(2*pi*face/16)'
        reason='Polygon direction cosine/sine (source floating evaluation) or fixed PCS rating multiplier. No coefficient is deleted.'
    if fam.startswith('response_') and fam.endswith('_binding'):
        targetfam=fam[:-8];targets=[str(names[j]) for j in row[1]] if isinstance(row,tuple) else []
    return expected,formula,reason

def run():
    freeze_check();matrices=[];columns=[];hist=[];traces=[];impact={};structures={};identities={}
    from v42_forensic.common import inputs
    from v42_bootstrap.grid import coefficients
    bundle,anchor,*_=inputs();_,coeff=coefficients(bundle)
    with gp.Env(params={'OutputFlag':0}) as env:
        for kind in ['original','compact']:
            m=make(kind,env);names=np.array(m.getAttr('VarName'));rows=row_families(kind);A=m.getA().tocsr();A.sort_indices()
            rhs=np.array(m.getAttr('RHS'));labels=np.array([family(n) for n in names]);C=A.tocsc().T.tocsr()
            row_records,norm=axis_census(kind,A,rows,rhs);col_records,colnorm=axis_census(kind,C,labels,lower=np.array(m.getAttr('LB')),upper=np.array(m.getAttr('UB')))
            matrices+=row_records;columns+=col_records
            groups,codes=np.unique(rows,return_inverse=True);entry_rows=np.repeat(np.arange(A.shape[0]),np.diff(A.indptr));entry_codes=codes[entry_rows]
            bound=conservative_bounds(m,names,rows);absA=abs(A.data);histogram=np.histogram(np.log10(absA),bins=np.r_[-np.inf,np.arange(-20,5),np.inf])[0]
            edges=np.r_[-np.inf,np.arange(-20,5),np.inf]
            hist+=[dict(formulation=kind,log10_lower=str(edges[i]),log10_upper=str(edges[i+1]),count=int(n)) for i,n in enumerate(histogram)]
            family_impact={}
            for t in THRESHOLDS:
                selected=absA<t;rr=entry_rows[selected];bb=bound[A.indices[selected]];finite=np.isfinite(bb)
                weights=np.nextafter(absA[selected][finite]*bb[finite],np.inf)
                sums=np.bincount(rr[finite],weights=weights,minlength=A.shape[0]);counts=np.bincount(rr[finite],minlength=A.shape[0])
                gamma=counts*np.finfo(float).eps/(1-counts*np.finfo(float).eps);sums=np.nextafter(sums*(1+gamma),np.inf)
                sums[counts==0]=0
                unbounded=np.bincount(rr[~finite],minlength=A.shape[0])>0
                for code,label in enumerate(groups):
                    mask=codes==code;infcount=int(unbounded[mask].sum());valid=sums[mask&~unbounded]
                    family_impact.setdefault(str(label),{})[str(t)]=dict(maximum_possible_row_contribution=None if infcount else float(valid.max(initial=0)),
                        finite_row_maximum=float(valid.max(initial=0)),unbounded_rows=infcount,below_threshold_nnz=int((selected&(entry_codes==code)).sum()))
            impact[kind]=dict(families=family_impact,declared_or_equality_derived_finite_bound_columns=int(np.isfinite(bound).sum()),
                bounds_proof='All helper bounds are propagated through source triangular equations from global primary bounds. Directed nextafter products and fsum endpoints enclose exact real interval bounds. Nonnegative row sums use gamma_n forward-error enlargement. Correlations ignored conservatively.',removal_authorized=False)
            for code,fam in enumerate(groups):
                idx=np.flatnonzero((entry_codes==code)&((absA<=1e-12)|(absA>=100)))
                if not len(idx):continue
                chosen=sorted(set([*idx[:2],*idx[np.argsort(absA[idx])[:2]],*idx[np.argsort(-absA[idx])[:2]]]))
                for p in chosen:
                    i=int(entry_rows[p]);j=int(A.indices[p]);a=float(A.data[p]);vf=family(names[j]);file,fun,meaning,units=source_context(str(fam));formula='source row formula / frozen native affine coefficient';expected=None
                    if str(fam).startswith('response_') and str(fam).endswith('_binding') and vf in ['injection_P','injection_Q']:
                        targetfam=str(fam)[:-8];target=[str(names[k]) for k in A[i].indices if family(names[k])==targetfam][0]
                        t,k=map(int,re.findall(r'\d+',target));c=coeff[t];site=str(names[j]).split('[',1)[1].rsplit(',',1)[0]
                        control=('mess_p_kw' if vf=='injection_P' else 'mess_q_kvar')+'['+site+']';q=list(c.control_names).index(control)
                        if targetfam.endswith('_P'):w=c.flow_p_matrix[k];formula='-flow_p_matrix[branch,control]'
                        elif targetfam.endswith('_Q'):w=c.flow_q_matrix[k];formula='-flow_q_matrix[branch,control]'
                        else:
                            angles=2*np.pi*np.arange(16)/16;cos=np.cos(angles);sin=np.sin(angles);ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
                            pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor;raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
                            grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None];w=(c.current_matrix.T-grad)[k]
                            formula='-(current_matrix.T - active_face_affine_gradient)[branch,control]'
                        expected=-float(w[q]);meaning='Frozen affine line/transformer Jacobian response; correction uses the source current-versus-active-polygon gradient difference.'
                    elif str(fam) in ['voltage_lower','voltage_upper'] and vf in ['injection_P','injection_Q']:
                        ordinal=int(np.searchsorted(np.flatnonzero(rows==fam),i));t,k=divmod(ordinal,len(coeff[0].voltage_constant));c=coeff[t]
                        site=str(names[j]).split('[',1)[1].rsplit(',',1)[0];control=('mess_p_kw' if vf=='injection_P' else 'mess_q_kvar')+'['+site+']';q=list(c.control_names).index(control)
                        expected=float(c.voltage_matrix[q,k]);formula='voltage_matrix[control,node]';meaning='Frozen Planning voltage sensitivity to P/Q injection';units='pu^2 per kW/kvar'
                    elif str(fam)=='PCS16' and abs(a)>=100:
                        # Native PCS rating multiplied by cos(pi/16); Compact keeps exact +/- copies through route substitution.
                        battery=inputs()[-1];expected=float(battery.pcs_kva*math.cos(math.pi/16));formula='+/- pcs_kva*cos(pi/16)';units='kVA per unit route/connected indicator'
                        if a<0:expected=-expected
                    elif str(fam).startswith(('connected_','no_simultaneous_')) and abs(a)>=100:
                        battery=inputs()[-1];limit=battery.pcs_kva if 'Q' in str(fam) else battery.p_limit;expected=float(limit if a>0 else -limit);formula='+/- PCS or active-power limit';units='kW/kvar per unit binary/route indicator'
                    traces.append(dict(formulation=kind,row=i,column=j,row_family=str(fam),variable_name=str(names[j]),variable_family=vf,coefficient=a,coefficient_hex=a.hex(),
                        source_file=file,source_function=fun,physical_meaning=meaning,physical_units=units,source_formula=formula,
                        source_recomputed_coefficient=expected,source_replay_absolute_difference=None if expected is None else abs(a-expected),
                        why_small_or_large='Source affine derivative / cancellation of explicitly reconstructed gradients' if abs(a)<=1e-12 else 'Source physical rating or power limit multiplier',
                        compact_mapping_source='v42_monolithic.formulation.Compact exact +/- stay substitution' if kind=='compact' else 'native source builder'))
            structures[kind]=dict(matrix_coefficient_min=float(absA.min()),matrix_coefficient_max=float(absA.max()),dynamic_range=float(absA.max()/absA.min()),
                row_norms={k:stats(v) for k,v in norm.items()},column_norms={k:stats(v) for k,v in colnorm.items()},
                grid_rows=int(sum(x['axis_elements'] for x in row_records if GRID(x['family']))),grid_nnz=int(sum(x['nnz'] for x in row_records if GRID(x['family']))),rows=m.NumConstrs,nnz=m.NumNZs,
                extreme_nnz=int(((absA<=1e-12)|(absA>=100)).sum()),grid_extreme_nnz=int(sum(int((((absA<=1e-12)|(absA>=100))&(entry_codes==code)).sum()) for code,f in enumerate(groups) if GRID(str(f)))))
            identities[kind]=dict(fingerprint=int(m.Fingerprint),fingerprint_hex=hex(int(m.Fingerprint)),matrix_signature=signature(m),signature_without_types=signature(m,False),rows=m.NumConstrs,columns=m.NumVars,nnz=m.NumNZs)
            m.dispose()
    def uniform(records):
        fields=list(dict.fromkeys(k for r in records for k in r));return [{k:r.get(k) for k in fields} for r in records],fields
    for file,records in [('MATRIX_FAMILY_CENSUS.csv',matrices),('COLUMN_FAMILY_CENSUS.csv',columns)]:rr,ff=uniform(records);table(file,rr,ff)
    table('COEFFICIENT_MAGNITUDE_HISTOGRAM.csv',hist);table('EXTREME_COEFFICIENT_SOURCE_TRACE.csv',traces)
    dump('TINY_COEFFICIENT_PHYSICAL_IMPACT_BOUNDS.json',dict(formulations=impact,removal_authorization=False))
    dump('MATRIX_STRUCTURAL_AUDIT.json',structures);dump('SOURCE_MATRIX_IDENTITY.json',dict(PASS=True,formulations=identities,Start_unchanged_SHA={k:sha(OLD/(k.upper()+'_RECONSTRUCTED_START.npz')) for k in ['original','compact']},absent_source_row_family='response_voltage_binding: absent in F3 level3'))
    print('FULL_CENSUS_COMPLETE',structures,flush=True)

if __name__=='__main__':run()
