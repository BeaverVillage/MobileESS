"""Stored coefficient contribution and substitution census, no solves."""
from common import *
from collections import defaultdict
from fractions import Fraction as F
from common_mode_separator import supports
import re

def grid_closure(A,d):
    families=[str(n).split('[')[0] for n in d['names']];defs={};cache={}
    for i,n in enumerate(d['row_names']):
        family=str(n).split('[')[0]
        if family.endswith('_binding'):
            js=A.indices[A.indptr[i]:A.indptr[i+1]];own=[int(j) for j in js if families[j]==family[:-8]]
            assert len(own)==1;defs[own[0]]=i
    def expand(j):
        if j in cache:return cache[j]
        if families[j] in ('Pch','Pdis','Q'):result=({j:1.},0.)
        elif d['lower'][j]==d['upper'][j]:result=({},float(d['lower'][j]))
        else:
            i=defs[j];js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]];own=float(ws[list(js).index(j)]);terms=defaultdict(float);constant=float(d['rhs'][i])/own
            for k,w in zip(js,ws):
                if k==j:continue
                part,offset=expand(int(k));constant-=w*offset/own
                for p,v in part.items():terms[p]-=w*v/own
            result=dict(terms),constant
        cache[j]=result;return result
    return expand,defs

def main():
    A,d,reference=load();a=Authority()
    with np.load(HISTORY/'PURE_LP_POINT.npz') as z:baseline=z['x']
    with np.load(OUT/'SINGLE_WINDOW_STRENGTHENED_LP_PRIMAL.npz') as z:new=z['x'][:A.shape[1]]
    with np.load(OUT/'UB_LOCAL_NEIGHBORHOOD_POINT.npz') as z:ubnew=z['x']
    points={'PR167_PROXY':baseline,'SINGLE_WINDOW':new,'UB_REFERENCE':reference,'UB_NEIGHBORHOOD':ubnew}
    rho=int(np.flatnonzero(d['names']=='rho_max')[0]);expand,defs=grid_closure(A,d)
    indices=np.array([i for i,n in enumerate(d['row_names']) if str(n)=='line_thermal_face'])
    oldres=np.asarray(A@baseline-d['rhs']);newres=np.asarray(A@new-d['rhs'])
    active=indices[(abs(oldres[indices])<=1e-7)|(abs(newres[indices])<=1e-7)]
    with np.load(PARENT/'C3_RETAINED_AXES.npz') as z:c3rows=z['rows']
    with np.load(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz') as z:c2rows=z['rows'];c1orig=z['C1_original_rows']
    with np.load(history_authority.SOURCE/'REDUCTION_AXES.npz') as z:original_keep=z['keep']
    full=a.load_matrix();branch_authority=read(HISTORY/'CRITICAL_BRANCH_AUTHORITY.json')
    with np.load(branch_authority['branch_axis_source']) as z:branch_names=z['branch_names']
    assert sha(branch_authority['branch_axis_source'])==branch_authority['planning_SHA256']
    census=[];rowdescriptors=[]
    for i in active:
        js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]];rhow=float(ws[list(js).index(rho)]);terms=defaultdict(float);constant=0.
        for j,w in zip(js,ws):
            if j==rho:continue
            part,offset=expand(int(j));constant+=w*offset
            for k,v in part.items():terms[k]+=w*v
        originalrow=int(original_keep[int(c1orig[c2rows[c3rows[i]]])]);native_names=[str(a.full['names'][j]) for j in full.indices[full.indptr[originalrow]:full.indptr[originalrow+1]]]
        axes=[re.fullmatch(r'response_line_(?:P|Q|correction)\[(\d+),(\d+)\]',n) for n in native_names];axes=[(int(m[1]),int(m[2])) for m in axes if m];assert len(set(axes))==1
        t,line=axes[0];const=(constant-float(d['rhs'][i]))/-rhow
        rowdescriptors.append(dict(row=int(i),slot=t,line_index=line,branch_name=str(branch_names[line]),baseline_rho_constant=const,coefficients={str(j):w/-rhow for j,w in terms.items()}))
        for name,x in points.items():
            grouped=defaultdict(lambda:defaultdict(float))
            for j,w in terms.items():
                family=d['names'][j].split('[',1)[0];unit,site,_=str(d['names'][j]).split('[',1)[1][:-1].split(',');grouped[unit][family]+=w*x[j]/-rhow
            required=const+sum(sum(v.values()) for v in grouped.values())
            for unit,g in grouped.items():census.append(dict(row=int(i),slot=t,branch_name=str(branch_names[line]),point=name,MESS=unit,Pch_rho_contribution=g['Pch'],Pdis_rho_contribution=g['Pdis'],Q_rho_contribution=g['Q'],total_MESS_rho_contribution=sum(g.values()),required_rho_all_units=required,actual_rho=float(x[rho]),diagnostic_active=abs(required-x[rho])<=1e-7,coefficient_source='Original retained C3A bindings, target line recovered from exact saved row axes; float affine contribution, not lower-bound certificate'))
    table('CRITICAL_GRID_COUPLING_AUDIT.csv',census);write('CRITICAL_GRID_ROW_DESCRIPTORS.json',dict(rows=rowdescriptors,grid_binding_definitions={str(j):i for j,i in defs.items()},source_C3A_matrix_SHA256=sha(PARENT/'C3A_A.npz'),branch_authority_SHA256=branch_authority['planning_SHA256']))
    target=[r for r in census if r['slot']==72 and r['branch_name'] in ('line.sw1::A','line.l10::A')]
    write('MESS04_GRID_EFFECT.json',dict(rows=target,scope='Affine contribution contrasts at the same stored thermal faces; not causal share of integrality gap or independent LB gain',MESS04_details=[r for r in census if r['MESS']=='MESS04' and 69<=r['slot']<=72]))
    substitutions=[]
    for desc in rowdescriptors:
        if not 69<=desc['slot']<=72:continue
        rows=[r for r in census if r['row']==desc['row']]
        by={(r['point'],r['MESS']):r for r in rows}
        delta={u:by['SINGLE_WINDOW',u]['total_MESS_rho_contribution']-by['PR167_PROXY',u]['total_MESS_rho_contribution'] for u in a.initial}
        if delta['MESS04']>1e-6 and sum(v for u,v in delta.items() if u!='MESS04')<-.5*delta['MESS04']:substitutions.append(dict(**{k:desc[k] for k in ('row','slot','branch_name')},contribution_changes=delta,other_units_compensated=True))
    fractional=[];time_rows=[]
    for name,x in (('PR167_PROXY',baseline),('SINGLE_WINDOW',new)):
        for unit in sorted(a.initial):
            ids=np.array([j for j,n in enumerate(d['names']) if d['types'][j]=='B' and n.startswith(('node_activity['+unit+',','charge_mode['+unit+','))])
            fractional.append(dict(point=name,MESS=unit,fractional_count=int(((x[ids]>1e-8)&(x[ids]<1-1e-8)).sum()),mass=float(np.minimum(x[ids],1-x[ids]).sum())))
            for t in range(96):time_rows.append(dict(point=name,MESS=unit,slot=t,C=sum(float(a.value(f'Pch[{unit},{s},{t}]',x)) for s in a.sites),D=sum(float(a.value(f'Pdis[{unit},{s},{t}]',x)) for s in a.sites),Q=sum(float(a.value(f'Q[{unit},{s},{t}]',x)) for s in a.sites),mode=float(a.value(f'charge_mode[{unit},{t}]',x)),SOC=float(a.value(f'SOC[{unit},{t}]',x))))
    table('SUBSTITUTION_TIME_CENSUS.csv',time_rows)
    candidates=[]
    for unit in sorted(a.initial):
        for t in range(69,73):
            required=F(0)
            for sid,site in enumerate(a.sites):
                if f'Q[{unit},{site},{t}]' not in a.names:continue
                values={k:a.value(n,new) for k,n in {'y':f'arc[{unit},{sid*96+t}]','C':f'Pch[{unit},{site},{t}]','D':f'Pdis[{unit},{site},{t}]','Q':f'Q[{unit},{site},{t}]'}.items()}
                _,supports_list=supports(a,unit,site,t)
                required+=max(sum(terms.get(k,F(0))*v for k,v in values.items()) for _,terms in supports_list)
            violation=required+a.value(f'charge_mode[{unit},{t}]',new)-1
            candidates.append(dict(MESS=unit,slot=t,mode_location_PQ_defect=float(violation),exact_defect=str(violation)))
    table('NEW_POINT_EXACT_MODE_LOCATION_DEFECTS.csv',candidates)
    summary=dict(substitution_observed=bool(substitutions),same_line_time_compensations=substitutions,fractionality_census=fractional,approximate_primal_change=float(new[rho]-baseline[rho]),valid_LB_change=read(OUT/'SINGLE_WINDOW_VALID_LB_CERTIFICATE.json')['delta_LB'],new_point_mode_location_defects=candidates,materiality_is_valid_LB_only=True,windows_outside69_72_census_saved=True,other_lines_and_times_in_grid_audit=True)
    write('SUBSTITUTION_EFFECT_AUDIT.json',summary);print('SUBSTITUTION_AUDIT',len(substitutions),'max_other_defect',max(r['mode_location_PQ_defect'] for r in candidates if r['MESS']!='MESS04'),flush=True)

if __name__=='__main__':main()
