"""Conservative fixed-AIDC grid outer support, with no route/row deletion.

Input-only boxes use all reachable MESS controls.  They are diagnostics until
the original stored FULL rows have been checked.  The row bridge uses exact
binary rationals and cached affine intervals, never Forecast evaluation at a
nominal MESS point.  A violated minimum proves whole-model infeasibility; a
nonviolated outer box is not a feasibility certificate.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
import hashlib
from time import perf_counter

import numpy as np

from .contracts import digest, require
from .mess_domain import BATTERY_FIELDS
from .mess_domain_verify import verify_domain
from v42_m1_hybrid.blocks import matrix_sha

GRID_FAMILIES=('voltage_lower','voltage_upper','line_thermal_face',
               'transformer_kVA','NormalAmps','transformer_current')
SOURCES=('v42_native/grid_prescreen.py','v42_native/mess_domain.py',
         'v42_native/mess_domain_verify.py')


@lru_cache(maxsize=16384)
def _binary(value):
    return F(value)


def _domain_sha(data):
    h=hashlib.sha256()
    for key in sorted(data):
        value=np.asarray(data[key]);h.update(key.encode());h.update(value.dtype.str.encode())
        h.update(np.asarray(value.shape,dtype='<i8').tobytes());h.update(value.tobytes())
    return h.hexdigest()


def _boxes(physical):
    battery=dict(zip(BATTERY_FIELDS,physical.battery));p=F(battery['p_limit']);q=F(battery['pcs_kva'])
    members=defaultdict(list)
    for unit in physical.units:
        for k in unit.retained:
            site,t,dest,end,route=physical.arcs[k]
            if route is None:members[site,t].append(unit.mess)
    return tuple((site,t,tuple(sorted(members[site,t])),
        -len(members[site,t])*p,len(members[site,t])*p,
        -len(members[site,t])*q,len(members[site,t])*q)
        for t in range(physical.horizon) for site in physical.sites)


@dataclass(frozen=True)
class GridPrescreen:
    physical:object
    inputs:tuple
    boxes:tuple
    state_sha:str

    def scientific_state(self):
        return dict(schema='V42_EXACT_GRID_OUTER_PRESCREEN_V1',
            physical_state_sha=self.physical.state_sha,
            current_coefficients_and_fixed_controls=self.inputs,
            aggregate_PQ_outer_boxes=[dict(site=s,slot=t,eligible_MESS=list(u),
                P_lower_exact=str(pl),P_upper_exact=str(ph),
                Q_lower_exact=str(ql),Q_upper_exact=str(qh)) for s,t,u,pl,ph,ql,qh in self.boxes],
            arithmetic='EXACT_STORED_IEEE_BINARY_RATIONAL',
            box_policy='ALL_REACHABLE_MESS_RECTANGLE_NOT_SOC_OR_PCS_TIGHTENING',
            gridinfeasibility_stage='ORIGINAL_MATRIX_OUTER_BOX_AFTER_BUILD_NO_ROUTE_REMOVALS',
            Forecast_MESS_point_used=False,route_or_column_or_row_deletions=0,
            Native_optimize_calls=0,pre_model_grid_inequality_adoption=0)

    def receipt(self):
        _verify_input(self)
        return dict(self.scientific_state(),PASS=True,state_sha=self.state_sha,
            actual_original_row_bridge_required=True,
            pre_model_entire_model_infeasibility_certified=False)


def build_grid_prescreen(physical,coefficients,fixed_controls):
    verify_domain(physical)
    require(len(coefficients)==len(fixed_controls)==physical.horizon,'GRID_OUTER_CURRENT_SLOT_AXIS')
    inputs=[];control_axis=None
    for t,(coefficient,controls) in enumerate(zip(coefficients,fixed_controls)):
        names=tuple(map(str,coefficient.control_names));values=tuple(map(float,controls))
        require(coefficient.slot==t and len(names)==len(values) and len(set(names))==len(names),
            'GRID_OUTER_CURRENT_CONTROL_AXIS')
        require(len(coefficient.coefficient_sha256)==64 and np.isfinite(values).all(),
            'GRID_OUTER_CURRENT_COEFFICIENT_OR_FIXED_INPUT')
        if control_axis is None:control_axis=names
        require(names==control_axis,'GRID_OUTER_CURRENT_CONTROL_AXIS_DRIFT')
        for name,value in zip(names,values):
            if name.startswith(('mess_p_kw[','mess_q_kvar[')):
                require(name.split('[',1)[1][:-1] in physical.sites and value==0,
                    'GRID_OUTER_MESS_PLACEHOLDER_IS_NOT_AN_OPTIMIZATION_POINT')
            else:require(name.startswith('aidc_load_kw['),'GRID_OUTER_UNKNOWN_FIXED_CONTROL')
        inputs.append((t,coefficient.coefficient_sha256,names,values))
    result=GridPrescreen(physical,tuple(inputs),_boxes(physical),'')
    return GridPrescreen(physical,result.inputs,result.boxes,digest(result.scientific_state()))


def _verify_input(result):
    verify_domain(result.physical)
    require(result.boxes==_boxes(result.physical),'GRID_OUTER_REACHABLE_BOX_DRIFT')
    require(digest(result.scientific_state())==result.state_sha,'GRID_OUTER_INPUT_STATE_DRIFT')


def verify_grid_original_rows(result,A,d,progress=None):
    """Actual stored FULL bridge; intervals cover LP and integer domains.

    Each independent response box overapproximates its defining equality.
    Ignoring correlation enlarges the domain and therefore cannot produce a
    false infeasibility witness.  No bound is installed in the actual model.
    """
    began=perf_counter();_verify_input(result);A=A.tocsr(copy=False)
    names=list(map(str,d['names']));lookup={name:j for j,name in enumerate(names)}
    require(A.has_canonical_format and np.isfinite(A.data).all() and np.all(A.data!=0),
        'GRID_OUTER_ORIGINAL_CSR_AUTHORITY')
    require(len(lookup)==A.shape[1]==len(names),'GRID_OUTER_ORIGINAL_COLUMN_AXIS')
    require(all(len(d[key])==A.shape[1] for key in ('types','lower','upper','objective'))
        and all(len(d[key])==A.shape[0] for key in ('rhs','sense','row_names')),
        'GRID_OUTER_ORIGINAL_METADATA_AXIS')
    families=[name.split('[',1)[0] for name in names]
    raw=set();injections={};battery=dict(zip(BATTERY_FIELDS,result.physical.battery))
    p=F(battery['p_limit']);q=F(battery['pcs_kva']);bounds={}
    for site,t,units,pl,ph,ql,qh in result.boxes:
        for unit in units:
            for family,lo,hi in (('Pch',F(0),p),('Pdis',F(0),p),('Q',-q,q)):
                name=f'{family}[{unit},{site},{t}]';raw.add(name)
                require(name in lookup,'GRID_OUTER_ORIGINAL_RAW_PQ_MISSING')
                j=lookup[name]
                require(d['types'][j]=='C' and np.isfinite(d['lower'][j]) and np.isfinite(d['upper'][j])
                    and F(float(d['lower'][j]))==lo and F(float(d['upper'][j]))==hi,
                    'GRID_OUTER_ORIGINAL_RAW_PQ_BOX_DRIFT')
                bounds[j]=(lo,hi)
        for family,box in (('injection_P',(pl,ph)),('injection_Q',(ql,qh))):
            name=f'{family}[{site},{t}]';require(name in lookup,'GRID_OUTER_ORIGINAL_INJECTION_MISSING')
            injections[lookup[name]]=(family,site,t,units,box)
    require({n for n,f in zip(names,families) if f in ('Pch','Pdis','Q')}==raw,
        'GRID_OUTER_ORIGINAL_RAW_PQ_COVER_DRIFT')
    require({j for j,f in enumerate(families) if f in ('injection_P','injection_Q')}==set(injections),
        'GRID_OUTER_ORIGINAL_INJECTION_COVER_DRIFT')
    rho=lookup.get('rho_max');require(rho is not None and d['types'][rho]=='C'
        and d['lower'][rho]==0 and d['upper'][rho]==1,'GRID_OUTER_ORIGINAL_RHO_01_REQUIRED')
    bounds[rho]=(F(0),F(1));definitions={};unsupported_definitions=Counter()
    for i,label in enumerate(d['row_names']):
        family=str(label).split('[',1)[0]
        if not family.endswith('_binding'):continue
        a,z=A.indptr[i:i+2];matches=[int(j) for j in A.indices[a:z] if families[j]==family[:-8]]
        if len(matches)!=1 or d['sense'][i]!='=' or not np.isfinite(d['rhs'][i]):
            unsupported_definitions[family]+=1;continue
        j=matches[0]
        require(j not in definitions,'GRID_OUTER_ORIGINAL_DUPLICATE_AFFINE_DEFINITION')
        pivot=np.searchsorted(A.indices[a:z],j)
        if A.data[a+pivot]!=1:
            unsupported_definitions[family]+=1;continue
        definitions[j]=i
    for j,(family,site,t,units,box) in injections.items():
        require(j in definitions,'GRID_OUTER_ORIGINAL_INJECTION_DEFINITION_MISSING')
        i=definitions[j];a,z=A.indptr[i:i+2]
        terms={int(k):F(float(w)) for k,w in zip(A.indices[a:z],A.data[a:z])}
        expected={j:F(1)}
        for unit in units:
            for raw_family,weight in ([('Q',-1)] if family=='injection_Q' else [('Pch',1),('Pdis',-1)]):
                expected[lookup[f'{raw_family}[{unit},{site},{t}]']]=F(weight)
        require(terms==expected and d['rhs'][i]==0,'GRID_OUTER_ORIGINAL_INJECTION_EQUALITY_DRIFT')
        bounds[j]=box
    unknown={};active=set();affine_count=0
    def interval(j):
        nonlocal affine_count
        j=int(j)
        if j in bounds:return bounds[j]
        if j in unknown:return None
        if j in active:
            unknown[j]='CYCLIC_AFFINE_DEPENDENCY';return None
        i=definitions.get(j)
        if i is None:
            if families[j].startswith(('response_','injection_')):
                unknown[j]='MISSING_OR_UNSUPPORTED_AFFINE_DEFINITION';return None
            lo,hi=float(d['lower'][j]),float(d['upper'][j])
            if np.isfinite(lo) and np.isfinite(hi) and lo<=hi:
                bounds[j]=(F(lo),F(hi));return bounds[j]
            unknown[j]='NONFINITE_ORIGINAL_VARIABLE_BOX';return None
        active.add(j);lo=hi=F(float(d['rhs'][i]));a,z=A.indptr[i:i+2]
        for k,w in zip(A.indices[a:z],A.data[a:z]):
            if k==j:continue
            child=interval(k)
            if child is None:
                active.remove(j);unknown[j]='UNMEASURED_AFFINE_DEPENDENCY';return None
            weight=-_binary(float(w));left,right=child if weight>0 else child[::-1]
            lo+=weight*left;hi+=weight*right
        active.remove(j);bounds[j]=(lo,hi);affine_count+=1;return bounds[j]
    counts={f:Counter() for f in GRID_FAMILIES};witnesses=[];hash_bounds=hashlib.sha256()
    for i,label in enumerate(d['row_names']):
        family=str(label).split('[',1)[0]
        if family not in counts:continue
        record=counts[family];record['rows']+=1
        if d['sense'][i] not in ('<','>') or not np.isfinite(d['rhs'][i]):
            record['not_measured_unsupported_sense_or_rhs']+=1;continue
        sign=-1 if d['sense'][i]=='>' else 1
        lo=hi=F(0);a,z=A.indptr[i:i+2];measured=True
        for j,w in zip(A.indices[a:z],A.data[a:z]):
            box=interval(j)
            if box is None:measured=False;break
            weight=sign*_binary(float(w));left,right=box if weight>0 else box[::-1]
            lo+=weight*left;hi+=weight*right
        if not measured:
            record['not_measured_unknown_expression']+=1
            hash_bounds.update(f'{i}|UNKNOWN\n'.encode());continue
        rhs=sign*F(float(d['rhs'][i]));record['rows_exactly_measured']+=1
        hash_bounds.update(f'{i}|{lo}|{hi}|{rhs}\n'.encode())
        if lo>rhs:
            record['whole_model_infeasibility_witnesses']+=1
            witnesses.append(dict(row=i,name=str(label),normalized_minimum_exact=str(lo),
                normalized_maximum_exact=str(hi),normalized_rhs_exact=str(rhs),
                strict_positive_margin_exact=str(lo-rhs)))
        elif hi<=rhs:record['outer_box_entirely_satisfies_row']+=1
        else:record['outer_box_overlaps_row_boundary']+=1
        if progress and i%50000==0:
            progress(dict(phase='M_EXACT_GRID_OUTER_ORIGINAL_ROW_BRIDGE',rows_scanned=i,
                rows_total=A.shape[0],whole_model_witnesses=len(witnesses)))
    state=digest(dict(input_state_sha=result.state_sha,original_matrix_sha=matrix_sha(A),
        original_domain_sha=_domain_sha(d),exact_row_bounds_digest=hash_bounds.hexdigest()))
    return dict(PASS=True,grid_prescreen_state_sha=result.state_sha,bridge_state_sha=state,
        original_matrix_sha=matrix_sha(A),original_domain_sha=_domain_sha(d),
        exact_row_bounds_sha256=hash_bounds.hexdigest(),entire_model_infeasible=bool(witnesses),
        infeasibility_witnesses=witnesses,per_family={f:dict(c) for f,c in counts.items()},
        original_raw_PQ_boxes_checked=len(raw),original_injection_equalities_checked=len(injections),
        stored_affine_equalities_cached=affine_count,
        unsupported_definition_families=dict(unsupported_definitions),
        unmeasured_variable_reasons=dict(Counter(unknown.values())),
        outer_boxes_cover_original_integer_and_fractional_LP=True,
        no_infeasibility_witness_is_not_a_feasibility_certificate=True,
        actual_stored_RHS_and_equalities_used=True,coefficient_zeroing_thresholds_used=0,
        Forecast_MESS_point_used=False,route_or_column_or_row_deletions=0,
        Native_optimize_calls=0,independent_original_row_bridge_wall_seconds=perf_counter()-began)
