"""Independent LP integrity and exact bounded-box dual lower-bound verifier.

No Gurobi, solver generation, or optimization is imported or performed.
The numerical OPTIMAL/primal checks and exact weak-duality certificate have
different scopes: the latter proves a lower bound without an exact LP optimum.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from fractions import Fraction as F
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.critical_grid_cg.verify import (canonical_data,digests,npz,read,write,sha,require,dyadic,upward,axis,
                                        CompactMap,Geometry,original_row_sha,metadata_identity,exact_native_row)

OUT=ROOT/'docs/v42_b2_root_lp_tightening'
K48=ROOT/'docs/v42_critical_grid_cg/iteration02'
SOURCE18R='497609b46faa14ea7e32a9483a333ab32fd264ef'
PR211='d12315a3757aec187c8da0685c28ef901466386a'
CASE='34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
UB=.6760534504652341
OLD_LB=.46498486997548166
SOURCE=Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
SOC_FAMILIES=('SOC_DISCHARGE_TRAVEL_AVAILABILITY','SOC_CHARGE_HEADROOM')


def soc_proof(out):
    """Independent original-row rederivation; never imports the SOC producer."""
    started=time.perf_counter();rows=read(out/'SOC_CANDIDATES_EXACT.json')
    require(rows['source']==SOURCE18R and rows['case_sha']==CASE and len(rows['rows'])==768,'SOC_CANDIDATE_SOURCE_OR_CENSUS_CHANGED')
    old=ROOT/'docs/v42_physical_global_lb_pilot';prior=read(old/'NATIVE0.json');ind=read(old/'INDEPENDENT_NATIVE0.json')
    require(prior['PASS'] and ind['PASS'] and ind['all_single_owner_physical_rows_bounds_and_integer_types_retained'] and
            ind['independently_recomputed_original_matrix_sha']=='0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec',
            'LITERAL_ORIGINAL_FULL_PHYSICAL_SLICE_CERTIFICATE_FAILED')
    for name in ('SCIENTIFIC_CASE_IDENTITY.json','CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json'):
        require(sha(SOURCE/name)==prior['source_records'][str(SOURCE/name)],'FROZEN_ORIGINAL_MAPPING_AUTHORITY_CHANGED')
    identity=read(SOURCE/'SCIENTIFIC_CASE_IDENTITY.json');domain=identity['physical_prescreen_authority']['proof']
    require(identity['case_sha']==CASE and domain['original_matrix_bridge']['PASS'] and
            domain['original_matrix_bridge']['actual_departure_energy_debit_verified'], 'ORIGINAL_ENERGY_DOMAIN_BRIDGE_FAILED')
    battery=domain['battery'];graph=domain['arcs'];kdata=npz(K48/'JOINT_DATA.npz');kaxes=npz(K48/'JOINT_AXES.npz')['columns']
    mapping=CompactMap(SOURCE,kaxes,kdata['names'])
    records={row['name']:row for row in rows['rows']};require(len(records)==768,'DUPLICATE_SOC_CANDIDATE_NAME')
    unit_receipts=[];all_checked=0
    for unit in ('MESS01','MESS02','MESS03','MESS04'):
        spec=prior['models'][unit]
        for suffix,key in (('A','matrix_sha'),('DATA','data_sha'),('AXES','axes_sha')):
            require(sha(old/f'UNIT_{unit}_{suffix}.npz')==spec[key],'ORIGINAL_UNIT_SLICE_BYTES_CHANGED')
        A=sparse.load_npz(old/f'UNIT_{unit}_A.npz').tocsr();raw=npz(old/f'UNIT_{unit}_DATA.npz');d=canonical_data(raw)
        axes_packet=npz(old/f'UNIT_{unit}_AXES.npz');original=axes_packet['columns'];names=list(map(str,d['names']));lookup={n:c for c,n in enumerate(names)}
        unit_domain=next(v for v in domain['units'] if v['mess']==unit)
        arc_cols={int(axis(n)[1][1]):c for c,n in enumerate(names) if axis(n)[0]=='arc'}
        require(set(arc_cols)==set(unit_domain['retained_arc_indices']) and
                all(d['vtypes'][c]=='B' and d['lb'][c]==0 and d['ub'][c]==1 for c in arc_cols.values()),
                'ORIGINAL_INTEGER_ROUTE_AXIS_OR_BOX_CHANGED')
        # Independent incidence-row set matching, rather than producer node inference.
        by_node=defaultdict(dict);end_arcs={};stay={}
        for k,c in arc_cols.items():
            s,t,dest,end,route=graph[k]
            require(0<=t<end<=96,'ORIGINAL_TIME_DAG_CHANGED')
            by_node[s,t][c]=1
            if end<96:by_node[dest,end][c]=-1
            if end==96:end_arcs[c]=F(1)
            if route is None:
                require(s==dest and end==t+1,'ORIGINAL_STAY_SEMANTICS_CHANGED');stay[s,t]=c
        signatures={tuple(sorted(terms.items())):F(int(node==(unit_domain['origin'],0))) for node,terms in by_node.items() if terms}
        seen_flow=set();terminal=0;mode_cover=set();connection_cover=set();energy=[]
        for row,label in enumerate(d['row_names']):
            family=axis(label)[0]
            if family not in ('flow','terminal_location','connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge','energy_balance'):
                continue
            a,b=A.indptr[row:row+2];terms={int(c):dyadic(v) for c,v in zip(A.indices[a:b],A.data[a:b])}
            if family=='flow':
                signature=tuple(sorted((c,int(v)) for c,v in terms.items()))
                require(all(v in (F(-1),F(1)) for v in terms.values()) and signature in signatures and
                        d['senses'][row]=='=' and dyadic(d['rhs'][row])==signatures[signature] and signature not in seen_flow,
                        'ORIGINAL_UNIT_INCIDENCE_FLOW_NOT_EXACT')
                seen_flow.add(signature)
            elif family=='terminal_location':
                require(terms==end_arcs and d['senses'][row]=='=' and d['rhs'][row]==1,'ORIGINAL_UNIT_TERMINAL_NOT_EXACT');terminal+=1
            elif family=='energy_balance':energy.append((row,terms))
            else:
                power_family='Pch' if family in ('connected_Pch','no_simultaneous_charge') else 'Pdis'
                power=[c for c in terms if axis(names[c])[0]==power_family];require(len(power)==1,'POWER_GATE_PIVOT_AMBIGUOUS')
                c=power[0];_,coord=axis(names[c]);site,t=coord[1],int(coord[2]);limit=dyadic(battery['p_limit'])
                require(d['lb'][c]==0 and d['ub'][c]==battery['p_limit'],'ORIGINAL_POWER_NONNEGATIVE_BOX_CHANGED')
                if family.startswith('connected_'):
                    expected={c:F(1),stay[site,t]:-limit};rhs=F(0);connection_cover.add((power_family,site,t))
                else:
                    m=lookup[f'charge_mode[{unit},{t}]'];require(d['vtypes'][m]=='B' and d['lb'][m]==0 and d['ub'][m]==1,'ORIGINAL_MODE_NOT_BINARY')
                    expected={c:F(1),m:-limit if power_family=='Pch' else limit};rhs=F(0) if power_family=='Pch' else limit;mode_cover.add((power_family,site,t))
                require(terms==expected and d['senses'][row]=='<' and dyadic(d['rhs'][row])==rhs,'ORIGINAL_POWER_GATE_ROW_CHANGED')
        power_cover={(axis(n)[0],axis(n)[1][1],int(axis(n)[1][2])) for n in names if axis(n)[0] in ('Pch','Pdis')}
        require(seen_flow==set(signatures) and terminal==1 and mode_cover==power_cover and connection_cover==power_cover,
                'ORIGINAL_ONE_PATH_OR_MODE_CONNECTION_COVER_INCOMPLETE')
        require(len(energy)==96,'ORIGINAL_SOC_RECURRENCE_COVER_NOT_96')
        slots=set()
        for row,terms in energy:
            soc=[c for c in terms if axis(names[c])[0]=='SOC'];require(len(soc)==2,'ORIGINAL_SOC_PAIR_MISSING')
            previous_soc=next(c for c in soc if terms[c]==-1);next_soc=next(c for c in soc if terms[c]==1)
            t=int(axis(names[previous_soc])[1][1]);require(int(axis(names[next_soc])[1][1])==t+1 and t not in slots,'SOC_RECURRENCE_TIME_CHANGED');slots.add(t)
            require(d['senses'][row]=='=' and d['rhs'][row]==0 and
                    d['lb'][previous_soc]==battery['minimum'] and d['ub'][previous_soc]==battery['maximum'] and
                    d['lb'][next_soc]==battery['minimum'] and d['ub'][next_soc]==battery['maximum'],'SOC_RECURRENCE_ORIGINAL_BOX_CHANGED')
            charges={c:-v for c,v in terms.items() if axis(names[c])[0]=='Pch'}
            discharges={c:v for c,v in terms.items() if axis(names[c])[0]=='Pdis'}
            require(charges and discharges and len(set(charges.values()))==len(set(discharges.values()))==1,'ENERGY_COEFFICIENT_NOT_UNIFORM')
            alpha=next(iter(charges.values()));beta=next(iter(discharges.values()))
            require(str(alpha)==domain['original_matrix_bridge']['exact_stored_charge_coefficient'] and
                    str(beta)==domain['original_matrix_bridge']['exact_stored_discharge_coefficient'],'EXACT_STORED_EFFICIENCY_CHANGED')
            travel={c:v for c,v in terms.items() if axis(names[c])[0]=='arc'}
            expected_travel={c:dyadic(graph[k][4]['energy_kwh']) for k,c in arc_cols.items() if graph[k][4] is not None and graph[k][1]==t and graph[k][4]['energy_kwh']!=0}
            require(travel==expected_travel and all(v>=0 for v in travel.values()),'TRAVEL_DEBIT_NOT_DEPARTURE_POSITIVE')
            for family in SOC_FAMILIES:
                name=f'{family}[{unit},{t}]';record=records[name]
                original_terms={int(original[previous_soc]):F(-1 if family==SOC_FAMILIES[0] else 1)}
                for c,v in (discharges if family==SOC_FAMILIES[0] else charges).items():original_terms[int(original[c])]=v
                if family==SOC_FAMILIES[0]:
                    for c,v in travel.items():original_terms[int(original[c])]=v
                rhs=-dyadic(battery['minimum']) if family==SOC_FAMILIES[0] else dyadic(battery['maximum'])
                rhs,constant,local=mapping.row(rhs,F(0),original_terms)
                require(record['family']==family and record['unit']==unit and record['slot']==t and
                        record['original_energy_row']==int(axes_packet['rows'][row]),'SOC_CANDIDATE_ROW_AXIS_CHANGED')
                require(F(record['alpha'])==alpha and F(record['beta'])==beta and
                        F(record['Emin'])==dyadic(battery['minimum']) and F(record['Emax'])==dyadic(battery['maximum']),
                        'SOC_CANDIDATE_ENERGY_CONSTANT_CHANGED')
                require({int(c):F(v) for c,v in record['original_terms'].items()}==original_terms and
                        {int(c):F(v) for c,v in record['terms'].items()}==local and
                        F(record['exact_rhs'])==rhs and F(record['eliminated_constant'])==constant and record['normalized_sense']=='<',
                        'SOC_CANDIDATE_SIGN_COEFFICIENT_ALIAS_OR_RHS_CHANGED')
                error=F(0)
                for c,v in local.items():
                    native=float(v);require(math.isfinite(native) and native!=0,'SOC_TINY_COEFFICIENT_DROPPED')
                    delta=F(native)-v;error+=max(delta*dyadic(kdata['lb'][c]),delta*dyadic(kdata['ub'][c]))
                target=rhs+error
                require(record['native_rhs']==upward(target) and F(record['error_upper_bound'])==error and
                        F(record['rhs_outward_extra'])==dyadic(record['native_rhs'])-target,'SOC_OUTWARD_ROUNDING_CHANGED')
                all_checked+=1
        require(slots==set(range(96)),'SOC_SLOT_COVER_CHANGED')
        unit_receipts.append({'unit':unit,'flow_rows_independently_matched':len(seen_flow),'energy_rows_checked':96,
                             'power_mode_gates_checked':len(mode_cover),'power_stay_gates_checked':len(connection_cover),
                             'exact_original_one_path_argument':True,'C_positive_implies_D_and_departure_T_zero':True})
        del A,raw,d;gc.collect()
    require(all_checked==768,'SOC_INDEPENDENT_CANDIDATE_CENSUS_FAILED')
    return {'PASS':True,'schema':'V42_SOC_MODE_TRAVEL_INDEPENDENT_NATIVE0_V1','candidate_count':768,
            'source18r':SOURCE18R,'case_sha':CASE,'Native_optimize_calls':0,'Gurobi_imported':False,'FULL_CSR_loaded':False,
            'literal_UNIT_CSRs_loaded_sequentially':True,'all_768_signs_coefficients_bounds_aliases_RHS_audited':True,
            'original_integer_feasible_points_preserved':True,'no_added_physical_conditions_or_binary_variables':True,
            'units':unit_receipts,'SOC_CANDIDATES_EXACT_sha256':sha(out/'SOC_CANDIDATES_EXACT.json'),
            'proof':'Original nonnegative binary unit-flow on a strict-time DAG is one source-to-slot96 path. Positive aggregate charge implies a selected stay at that slot and binary charge_mode=1; hence aggregate discharge and all departing move flows are zero. Split C=0 versus C>0. For C=0, energy recurrence and next-SOC minimum prove B1; current-SOC maximum proves B2. For C>0, B1 is current-SOC minimum and B2 is next-SOC maximum through E_next=E+alpha*C.',
            'LP_implication_scope':'Integer validity of all 768 candidates is proved. LP redundancy is not blanket classified; only robust actual fractional-point violations may be selected.',
            'wall_seconds':time.perf_counter()-started}


def cut_validity(kind,base,out):
    """Independent exact cut certificate against the verified BASE point."""
    require(kind in ('GRID','SOC'),'CUT_VALIDITY_KIND_INVALID')
    certificate=read(base/'INDEPENDENT_CERTIFICATE.json')
    require(certificate['PASS'] and certificate['solver_status']==2 and certificate['LP_completed_numerical_OPTIMAL'],
            'BASE_FRACTIONAL_POINT_NOT_OPTIMAL_CERTIFIED')
    packet=read(out/'CUTS_EXACT.json');records=packet['rows']
    require(packet['source']==SOURCE18R and packet['case_sha']==CASE and
            packet['BASE_certificate_sha256']==sha(base/'INDEPENDENT_CERTIFICATE.json'),'CUT_BASE_OR_ORIGINAL_SOURCE_SHA_CHANGED')
    require(1<=len(records)<=(16 if kind=='GRID' else 32),'CUT_NUMBER_GATE_FAILED')
    rawbase=npz(base/'LP_DATA.npz');d=canonical_data(rawbase)
    x=npz(base/'LP_POINT.npz')['x'];u4=npz(base/'LP_START.npz')['x']
    proven=[]
    if kind=='SOC':
        proof=read(base.parent/'INDEPENDENT_SOC_NATIVE0.json')
        candidates=read(base.parent/'SOC_CANDIDATES_EXACT.json')
        require(proof['PASS'] and proof['candidate_count']==768 and
                proof['SOC_CANDIDATES_EXACT_sha256']==sha(base.parent/'SOC_CANDIDATES_EXACT.json') and
                packet['SOC_candidates_sha256']==sha(base.parent/'SOC_CANDIDATES_EXACT.json') and
                packet['fractional_point_sha256']==sha(base/'LP_POINT.npz'),'SOC_PROOF_OR_BASE_POINT_IDENTITY_CHANGED')
        lookup={row['name']:row for row in candidates['rows']}
        for row in records:
            require(row['name'] in lookup,'SOC_CUT_NOT_IN_INDEPENDENT_768_VALID_CANDIDATES')
            original=lookup[row['name']]
            for key in ('name','family','unit','slot','original_energy_row','alpha','beta','Emin','Emax','original_terms',
                        'terms','normalized_sense','exact_rhs','eliminated_constant','native_rhs','error_upper_bound','rhs_outward_extra'):
                require(row[key]==original[key],'SOC_SELECTED_EXACT_CERTIFICATE_CHANGED_'+key)
    else:
        require(packet['point_kind']=='VERIFIED_FRACTIONAL_BASE_LP','GRID_POINT_IS_NOT_VERIFIED_FRACTIONAL_BASE')
        original_records=read(ROOT/'docs/v42_physical_global_lb_pilot/NATIVE0.json')['source_records']
        for name in ('FULL_A.npz','FULL_DATA.npz','SCIENTIFIC_CASE_IDENTITY.json','CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json'):
            require(sha(SOURCE/name)==original_records[str(SOURCE/name)], 'GRID_FROZEN_SOURCE_FILE_CHANGED_'+name)
        identity=read(SOURCE/'SCIENTIFIC_CASE_IDENTITY.json')
        A=sparse.load_npz(SOURCE/'FULL_A.npz').tocsr();fullraw=npz(SOURCE/'FULL_DATA.npz');full=canonical_data(fullraw)
        require(digests(A,fullraw)==('0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec',
                '9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e') and identity['case_sha']==CASE,
                'GRID_ACTUAL_ORIGINAL_FULL_AUTHORITY_CHANGED')
        geometry=Geometry(A,full);mapping=CompactMap(SOURCE,npz(base/'LP_AXES.npz')['columns'],d['names'])
        certpath=Path(r'D:\v42_svr11_may_20261011_16\models\2025-05-01\ELECTRICAL_CERTIFICATE.json')
        electrical=read(certpath);coefficient=electrical['outputs']['planning_coefficients']
        require(sha(certpath)=='70d381c607cae03f88df55acf3f1bffdc5f43d2cf3c6c2e6e147dbe0a7c33177' and
                sha(coefficient['path'])==coefficient['sha256']=='b3370e37a375d6b358ba0695feeb5bad26da4d043447669f5d2d3024ad20eba8',
                'GRID_FROZEN_PLANNING_COEFFICIENTS_CHANGED')
        with np.load(coefficient['path'],allow_pickle=False) as z:axes={k:z[k].copy() for k in ('branch_names','node_names','transformer_ratings')}
        previous_names=set(map(str,d['row_names']))
        for record in records:
            row=int(record['original_row'])
            require(0<=row<A.shape[0] and str(full['row_names'][row]) not in previous_names,'GRID_CUT_NOT_NEW_ORIGINAL_ROW')
            rhs,constant,terms=geometry.security(row);original_terms=terms.copy()
            rhs,constant,terms=mapping.row(rhs,constant,terms)
            expected={'original_row':row,'name':str(full['row_names'][row]),'original_sense':str(full['senses'][row]),
                      'original_rhs':dyadic(full['rhs'][row]),'source_row_sha256':original_row_sha(A,full,row),
                      'metadata':metadata_identity(full['row_names'][row],axes),'original_terms':original_terms,
                      'terms':terms,'exact_rhs':rhs,'eliminated_constant':constant}
            exact_native_row(record,expected,d)
            for helper in record['helper_rows']:
                r=int(helper['original_row']);require(helper['name']==str(full['row_names'][r]) and
                    helper['source_row_sha256']==original_row_sha(A,full,r),'GRID_HELPER_ROW_AUTHORITY_CHANGED')
        del A,fullraw,full,geometry,mapping,axes;gc.collect()
    seen=set()
    for record in records:
        require(record['name'] not in seen,'DUPLICATE_SELECTED_CUT');seen.add(record['name'])
        terms={int(c):F(v) for c,v in record['terms'].items()};rhs=F(record['exact_rhs'])
        exact=sum((v*dyadic(x[c]) for c,v in terms.items()),F(0))-rhs
        native=sum((dyadic(float(v))*dyadic(x[c]) for c,v in terms.items()),F(0))-dyadic(record['native_rhs'])
        require(F(record['exact_violation'])==exact and exact>0 and native>0,'CUT_DOES_NOT_EXCLUDE_UNCHANGED_BASE_FRACTIONAL_POINT')
        if kind=='SOC':require(exact>F(1,10**7) and native>F(1,10**7),'SOC_VIOLATION_NOT_ROBUST')
        u4error=sum((dyadic(float(v))*dyadic(u4[c]) for c,v in terms.items()),F(0))-dyadic(record['native_rhs'])
        require(float(u4error)<=1e-8,'CUT_ORIGINAL_U4_REPLAY_FAILED')
        proven.append({'name':record['name'],'exact_fractional_violation':str(exact),
                       'native_fractional_violation_exact':str(native),'U4_native_violation_exact':str(u4error)})
    return {'PASS':True,'schema':'V42_B2_ROOT_LP_EXACT_CUT_VALIDITY_V1','kind':kind,'source18r':SOURCE18R,
            'case_sha':CASE,'selected_count':len(records),'source_original_integer_domain_preserved':True,
            'exact_row_elimination_or_integer_SOC_derivation':True,'minimal_conservative_outward_RHS_verified':True,
            'actual_unchanged_BASE_fractional_point_excluded':True,'original_U4_replay_verified':True,
            'Native_optimize_calls':0,'Gurobi_imported':False,'FULL_CSR_loaded':kind=='GRID',
            'FULL_CSR_released_before_solver':True,'rows':proven,'CUTS_EXACT_sha256':sha(out/'CUTS_EXACT.json'),
            'BASE_certificate_sha256':sha(base/'INDEPENDENT_CERTIFICATE.json'),'BASE_fractional_point_sha256':sha(base/'LP_POINT.npz')}


def downward(value):
    result=float(value)
    require(math.isfinite(result),'NONFINITE_EXACT_BOUND_FLOAT')
    return float(np.nextafter(result,-np.inf)) if F(result)>value else result


def native0(kind,previous,out):
    require(kind in ('BASE','GRID','SOC'),'UNKNOWN_CANDIDATE_KIND')
    original_prefix='JOINT' if kind=='BASE' else 'LP'
    oldA=sparse.load_npz(previous/(original_prefix+'_A.npz')).tocsr()
    oldraw=npz(previous/(original_prefix+'_DATA.npz'));old=canonical_data(oldraw)
    A=sparse.load_npz(out/'LP_A.npz').tocsr()
    raw=npz(out/'LP_DATA.npz');d=canonical_data(raw)
    require(A.shape[1]==oldA.shape[1]==244265,'COLUMN_COUNT_CHANGED')
    require(np.all(d['vtypes']=='C'),'LP_TYPES_NOT_ALL_CONTINUOUS')
    original_binaries=int(np.count_nonzero(old['vtypes']=='B'))
    if kind=='BASE':
        require(original_binaries==9322 and A.shape==oldA.shape,'BASE_BINARY_RELAXATION_OR_ROWS_CHANGED')
        expected=old['vtypes'].copy();expected[expected=='B']='C'
        require(np.array_equal(d['vtypes'],expected),'MORE_THAN_BINARY_RELAXATION_APPLIED')
        certificate=read(previous/'INDEPENDENT_CERTIFICATE.json')
        require(certificate['PASS'] and certificate['Global_LB']==OLD_LB,'PR211_K48_CERTIFICATE_CHANGED')
        parentzero=read(previous/'INDEPENDENT_NATIVE0.json')
        require(digests(oldA,oldraw)==(parentzero['joint_actual_matrix_sha256'],parentzero['joint_actual_domain_sha256']),
                'ACTUAL_K48_MODEL_CHANGED')
        for name,digest in parentzero['file_sha256'].items():
            require(sha(previous/name)==digest,'PR211_FROZEN_ARTIFACT_CHANGED_'+name)
    else:
        require(original_binaries==0 and read(previous/'INDEPENDENT_CERTIFICATE.json')['PASS'],
                'BASE_LP_NOT_INDEPENDENTLY_CERTIFIED')
        cuts=read(out/'CUTS_EXACT.json')
        limit=16 if kind=='GRID' else 32
        require(1<=len(cuts['rows'])<=limit and A.shape[0]==oldA.shape[0]+len(cuts['rows']),
                'CANDIDATE_CUT_COUNT_OR_ROWS_INVALID')
        original_binaries=9322
        require(read(out/'CUT_VALIDITY_NATIVE0.json')['PASS'],'EXACT_CUT_VALIDATION_FAILED')
    p=oldA.shape[0]
    prefix=A[:p]
    require(all(np.array_equal(getattr(prefix,key),getattr(oldA,key)) for key in ('indptr','indices','data')),
            'BASE_OR_PREVIOUS_ROWS_NOT_BITWISE_PRESERVED')
    for key in ('names','lb','ub','c','constant'):
        require(np.array_equal(d[key],old[key]),'BASE_DOMAIN_OR_OBJECTIVE_CHANGED_'+key)
    for key in ('row_names','rhs','senses'):
        require(np.array_equal(d[key][:p],old[key]),'BASE_ROW_DATA_CHANGED_'+key)
    if kind!='BASE':
        cutproof=read(out/'CUT_VALIDITY_NATIVE0.json')
        require(cutproof['CUTS_EXACT_sha256']==sha(out/'CUTS_EXACT.json') and
                cutproof['BASE_certificate_sha256']==sha(previous/'INDEPENDENT_CERTIFICATE.json') and
                cutproof['BASE_fractional_point_sha256']==sha(previous/'LP_POINT.npz'), 'EXACT_CUT_PROOF_HASH_CHAIN_CHANGED')
        for offset,record in enumerate(cuts['rows']):
            row=p+offset;observed=A.getrow(row)
            expected={int(c):float(F(v)) for c,v in record['terms'].items()}
            require(dict(zip(map(int,observed.indices),map(float,observed.data)))==expected and
                    d['rhs'][row]==record['native_rhs'] and d['senses'][row]=='<' and d['row_names'][row]==record['name'],
                    'APPENDED_NATIVE_LP_CUT_NOT_EXACT_VALIDATED_ROW')
    require(d['names'][-1]=='rho_max' and d['lb'][-1]==0 and d['ub'][-1]==1 and d['c'][-1]==1 and
            np.count_nonzero(d['c'])==1 and float(d['constant'])==0,'ORIGINAL_RHO_OBJECTIVE_CHANGED')
    require(np.all(np.isfinite(d['lb'])) and np.all(np.isfinite(d['ub'])) and np.all(d['lb']<=d['ub']),
            'FINITE_BOX_REQUIRED_FOR_DUAL_CORRECTION')
    require(A.shape[0]<=160000 and A.nnz<=1800000,'MODEL_SIZE_GATE_FAILED')
    binary_axis=npz(out/'LP_ORIGINAL_BINARY.npz')
    require(set(binary_axis)=={'columns'},'ORIGINAL_BINARY_AXIS_PACKET_SCHEMA')
    expected_binary=np.flatnonzero(old['vtypes']=='B') if kind=='BASE' else npz(previous/'LP_ORIGINAL_BINARY.npz')['columns']
    require(np.array_equal(binary_axis['columns'],expected_binary) and len(expected_binary)==9322,
            'ORIGINAL_BINARY_AXIS_NOT_LITERAL_SOURCE_B_POSITIONS')
    oldaxes=previous/(original_prefix+'_AXES.npz');oldstart=previous/(original_prefix+'_START.npz')
    require(sha(out/'LP_AXES.npz')==sha(oldaxes) and sha(out/'LP_START.npz')==sha(oldstart),
            'ORIGINAL_AXES_OR_U4_START_CHANGED')
    x=npz(out/'LP_START.npz')['x']
    residual=A@x-d['rhs']
    violations=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
    require(float(np.max(violations))<=1e-8 and x[-1]==UB,'ORIGINAL_U4_CANDIDATE_REPLAY_FAILED')
    matrix,domain=digests(A,raw)
    files={name:sha(out/name) for name in ('LP_A.npz','LP_DATA.npz','LP_AXES.npz','LP_START.npz','LP_ORIGINAL_BINARY.npz')}
    if kind!='BASE':files.update({name:sha(out/name) for name in ('CUTS_EXACT.json','CUT_VALIDITY_NATIVE0.json')})
    return {'PASS':True,'schema':'V42_B2_ROOT_LP_INDEPENDENT_V1','phase':'Native0','kind':kind,
            'source18r':SOURCE18R,'base_PR211':PR211,'case_sha':CASE,'Native_optimize_calls':0,
            'Gurobi_imported':False,'FULL_CSR_loaded':False,'original_integer_projection_preserved':True,
            'BASE_LP_only_B_to_C':kind=='BASE','all_original_rows_RHS_Bounds_objective_preserved':True,
            'matrix_sha':matrix,'domain_sha':domain,'original_binary_count':original_binaries,
            'dimensions':{'rows':A.shape[0],'columns':A.shape[1],'binary':0,'nnz':int(A.nnz)},
            'U4_maximum_row_violation':float(max(0.,np.max(violations))),'file_sha256':files,
            'proof_scope':'Stored K48 rows/domain identical; only original B types relaxed. Valid candidates append conservative original-integer-valid rows without changing the prefix/domain.'}


def exact_box_dual(A,d,pi):
    """Any sign-valid row multipliers prove this exact finite-box bound."""
    require(pi.shape==(A.shape[0],) and np.all(np.isfinite(pi)),'INVALID_DUAL_VECTOR')
    residual={int(c):dyadic(d['c'][c]) for c in np.flatnonzero(d['c'])}
    total=dyadic(d['constant']);changed=[];used=0
    for row,value in enumerate(pi):
        sense=d['senses'][row]
        require(sense in ('<','>','='),'INVALID_ROW_SENSE')
        wrong=(sense=='<' and value>0) or (sense=='>' and value<0)
        if wrong:
            require(abs(float(value))<=1e-8,'DUAL_ROW_SIGN_VIOLATION_TOO_LARGE')
            changed.append({'row':row,'old':float(value),'corrected':0.})
            value=0.
        if value==0:continue
        used+=1;multiplier=dyadic(value);total+=multiplier*dyadic(d['rhs'][row])
        start,end=A.indptr[row:row+2]
        for col,coefficient in zip(A.indices[start:end],A.data[start:end]):
            col=int(col);residual[col]=residual.get(col,F(0))-multiplier*dyadic(coefficient)
    row_only=total;correction=F(0)
    for col,value in residual.items():
        correction+=min(value*dyadic(d['lb'][col]),value*dyadic(d['ub'][col]))
    return total+correction,{'row_multiplier_contribution_exact':str(row_only),
                            'finite_bound_stationarity_correction_exact':str(correction),
                            'nonzero_dual_rows':used,'stationarity_columns':sum(bool(v) for v in residual.values()),
                            'dual_sign_repairs':changed,'exact_stationarity_residual_max':str(max(map(abs,residual.values()),default=F(0))),
                            'reduced_cost_vector_exact':residual}


def final(kind,previous,out):
    zero=read(out/'INDEPENDENT_NATIVE0.json');build=read(out/'NATIVE0.json')
    require(zero['PASS'] and zero['kind']==kind and zero['phase']=='Native0' and build['PASS'],
            'NATIVE0_INDEPENDENT_GATE_FAILED')
    for name,digest in zero['file_sha256'].items():require(sha(out/name)==digest,'FROZEN_LP_ARTIFACT_CHANGED_'+name)
    require(build['matrix_sha']==zero['matrix_sha'] and build['domain_sha']==zero['domain_sha'],'NATIVE0_MODEL_SHA_MISMATCH')
    result=read(out/'RESULT.json')
    if result['Status']!=2 or result.get('callback_errors') or result.get('optimize_error') is not None or result.get('memory_stop') or result.get('b1_conflict_stop'):
        require(result['Native_optimize_calls']==1 and (out/'PILOT_STARTED.json').exists(),'STOP_WITHOUT_CONSUMED_NATIVE_CALL')
        latch=read(out/'PILOT_STARTED.json');ledger=read(out.parent/'NATIVE_LEDGER.json')
        require(latch['maximum_optimize_calls']==1 and latch['kind']==kind and
                latch['files']==build['file_sha256'] and
                latch['independent_native0_sha256']==sha(out/'INDEPENDENT_NATIVE0.json'), 'STOP_LATCH_OR_EXACT_GATE_DRIFT')
        matches=[call for call in ledger['calls'] if call['kind']==kind]
        require(len(matches)==1 and matches[0]['TimeLimit']==240 and matches[0]['pid']==latch['pid'] and
                len(ledger['calls'])<=3 and sum(call['TimeLimit'] for call in ledger['calls'])<=720,
                'STOP_NATIVE_CALL_BUDGET_OR_LATCH_NOT_PRESERVED')
        require(not (out/'LP_POINT.npz').exists(),'NONOPTIMAL_LP_POINT_MUST_NOT_BE_USED')
        runtime=float(result['Runtime']);require(math.isfinite(runtime) and runtime>=0,'STOP_RUNTIME_MISSING')
        return {'PASS':False,'schema':'V42_B2_ROOT_LP_INDEPENDENT_V1','phase':'Final','kind':kind,
                'classification':'LP_NOT_COMPLETED_OPTIMAL','solver_status':result['Status'],
                'LP_completed_numerical_OPTIMAL':False,'LP_lower_bound':None,'LP_lower_bound_exact':None,
                'Global_LB':None,'Native_calls_audited':1,'verifier_Native_optimize_calls':0,
                'Native_Runtime':runtime,'requested_Native_seconds':240,'retry_authorized':False,
                'source18r':SOURCE18R,'base_PR211':PR211,'case_sha':CASE,
                'exact_Native0_model_and_cut_validity_preserved':True,'original_integer_projection_preserved':True,
                'b1_conflict_stop':result.get('b1_conflict_stop',False),'memory_stop':result.get('memory_stop',False),
                'callback_errors':result.get('callback_errors'),'optimize_error':result.get('optimize_error'),
                'exact_weak_duality_LP_lower_bound_certificate':False,'exact_LP_optimum_certificate':False,
                'intermediate_or_interrupted_objective_used_as_LB':False,'actual_Heavy_Native_collision_proven':False,
                'stop_scope':'The native LP did not complete the required OPTIMAL/primal/dual gate. Its original-integer-valid formulation remains certified at Native0; no LP effect, separation point, or new Global LB is claimed. A priority-guard trigger alone does not prove an actual heavy solver collision.',
                'file_sha256':{name:sha(out/name) for name in ('INDEPENDENT_NATIVE0.json','NATIVE0.json','PILOT_STARTED.json','RESULT.json','NATIVE_READBACK.json','B1_PRIORITY_TRACE.json','MEMORY_TRACE.json','NATIVE.log')},
                'global_ledger_sha256':sha(out.parent/'NATIVE_LEDGER.json')}
    require(result['Native_optimize_calls']==1,'LP_NATIVE_CALL_COUNT_NOT_ONE')
    require(not result.get('callback_errors') and result.get('optimize_error') is None and not result.get('memory_stop'),
            'LP_UNSAFE_OR_NUMERIC_STOP')
    require(result.get('full_MILP_calls',0)==0 and result.get('campaign_calls',0)==0,'UNAUTHORIZED_NATIVE_SCOPE')
    readback=read(out/'NATIVE_READBACK.json')
    require(readback['PASS'] and all(readback['checks'].values()),'ACTUAL_NATIVE_LP_READBACK_FAILED')
    require(readback['checks']['Binary'] and readback['checks']['IsMIP'],'NATIVE_MODEL_NOT_PURE_LP')
    parameters=readback['parameters']
    expected={'Threads':1,'TimeLimit':240.,'Method':1,'FeasibilityTol':1e-8,'OptimalityTol':1e-8}
    require(all(parameters[k]==v for k,v in expected.items()),'LP_NUMERICAL_PARAMETERS_CHANGED')
    require(readback['matrix_sha']==zero['matrix_sha'],'NATIVE_LP_MATRIX_SHA_CHANGED')
    admission=read(out/'MEMORY_ADMISSION.json');peers=read(out/'PRE_OPTIMIZE_PEERS.json')
    require(admission['PASS'] and peers['PASS'] and not peers['heavy_peers'] and not peers['errors'],
            'LP_MEMORY_OR_OTHER_HEAVY_CONFLICT_GATE_FAILED')
    require(admission['RAM_reserve_bytes']==4*1024**3 and admission['commit_reserve_bytes']==6*1024**3 and
            admission['estimated_additional_bytes']==max(2*1024**3,4*admission['observed_model_build_private_growth_bytes']),
            'LP_MEMORY_GROWTH_CONTRACT_CHANGED')
    admitted=admission['sample']['system'];extra=admission['estimated_additional_bytes']
    require(admitted['RAM_available']>=4*1024**3+extra and admitted['Commit_available']>=6*1024**3+extra,
            'LP_POST_BUILD_MEMORY_RESERVES_FAILED')
    safety=read(out/'PRE_OPTIMIZE_B1_SAFETY.json');b1=read(out/'B1_PRIORITY_TRACE.json')
    require(safety['PASS'] and all(safety['checks'].values()) and not b1['conflicts'] and b1['mutations']==0 and
            result['b1_conflict_stop'] is False,'B1_PRIORITY_OR_PROTECTED_BASELINE_GATE_FAILED')
    trace=read(out/'MEMORY_TRACE.json');samples=trace['samples']
    require(len(samples)>=2 and not trace['unsafe_samples'] and
            all(s['system']['RAM_available']>=4*1024**3 and s['system']['Commit_available']>=6*1024**3 for s in samples),
            'LP_CONTINUOUS_MEMORY_MONITOR_RESERVE_FAILED')
    require(result['peak_process_RSS_bytes']==max(s['Peak_RSS_bytes'] for s in samples) and
            result['peak_private_commit_bytes']==max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples) and
            result['minimum_RAM_available']==min(s['system']['RAM_available'] for s in samples) and
            result['minimum_commit_available']==min(s['system']['Commit_available'] for s in samples),
            'LP_RESOURCE_SUMMARY_MISMATCH')
    latch=read(out/'PILOT_STARTED.json')
    require(latch['parameters']==parameters,'EXCLUSIVE_LP_NATIVE_LATCH_PARAMETERS_MISMATCH')
    if 'independent_native0_sha256' in latch:
        require(latch['independent_native0_sha256']==sha(out/'INDEPENDENT_NATIVE0.json'),'LP_EXACT_GATE_HASH_CHANGED_AFTER_NATIVE')
    require(latch['maximum_optimize_calls']==1 and latch['kind']==kind and
            latch['files']==build['file_sha256'],'LP_EXCLUSIVE_SINGLE_CALL_LATCH_FAILED')
    ledger=read(out.parent/'NATIVE_LEDGER.json');calls=ledger['calls']
    require(ledger['maximum_calls']==3 and ledger['maximum_requested_seconds']==720 and
            len(calls)<=3 and len({c['kind'] for c in calls})==len(calls) and
            sum(c['TimeLimit'] for c in calls)==240*len(calls) and calls[0]['kind']=='BASE',
            'GLOBAL_THREE_CALL_720_SECOND_LP_LEDGER_FAILED')
    matches=[c for c in calls if c['kind']==kind]
    require(len(matches)==1 and matches[0]['pid']==latch['pid'] and Path(matches[0]['out']).resolve()==out.resolve(),
            'LP_NATIVE_LEDGER_KIND_PID_PATH_MISMATCH')
    A=sparse.load_npz(out/'LP_A.npz').tocsr();d=canonical_data(npz(out/'LP_DATA.npz'))
    point=npz(out/'LP_POINT.npz');require(set(point)=={'x','pi','rc'},'LP_POINT_SCHEMA_MISMATCH')
    x,pi,rc=point['x'],point['pi'],point['rc']
    require(x.shape==(A.shape[1],) and rc.shape==x.shape and np.all(np.isfinite(x)) and np.all(np.isfinite(rc)),
            'INVALID_NATIVE_PRIMAL_OR_REDUCED_COST_VECTOR')
    residual=A@x-d['rhs']
    violation=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
    row_error=float(max(0.,np.max(violation)));box_error=float(max(0.,np.max(d['lb']-x),np.max(x-d['ub'])))
    require(row_error<=1e-8 and box_error<=1e-8,'LP_PRIMAL_OR_BOUND_RESIDUAL_TOO_LARGE')
    objective=dyadic(d['constant'])+sum((dyadic(d['c'][c])*dyadic(x[c]) for c in np.flatnonzero(d['c'])),F(0))
    require(abs(float(objective)-float(result['ObjVal']))<=1e-10,'LP_OBJECTIVE_VECTOR_MISMATCH')
    lower,details=exact_box_dual(A,d,pi)
    exact_rc=details.pop('reduced_cost_vector_exact')
    rc_error=max((abs(float(exact_rc.get(c,F(0)))-float(rc[c])) for c in range(A.shape[1])),default=0.)
    require(rc_error<=1e-7,'NATIVE_REDUCED_COST_STATIONARITY_MISMATCH')
    gap=objective-lower
    require(float(gap)>=-1e-8 and float(gap)<=1e-7,'LP_PRIMAL_EXACT_DUAL_BOUND_GAP_TOO_LARGE')
    require(lower<=dyadic(UB),'CERTIFIED_LP_BOUND_EXCEEDS_ORIGINAL_FULL_UB')
    # Complementarity is independently measured from the native primal/dual.
    row_complementarity=float(np.max(abs(pi*residual)))
    adjusted=np.array([float(exact_rc.get(c,F(0))) for c in range(A.shape[1])])
    distances=np.where(adjusted>=0,x-d['lb'],d['ub']-x)
    bound_complementarity=float(np.max(abs(adjusted*distances)))
    require(row_complementarity<=1e-7 and bound_complementarity<=1e-7,'LP_COMPLEMENTARITY_RESIDUAL_TOO_LARGE')
    fractions={family:int(np.count_nonzero((np.char.startswith(d['names'],family+'[')) &
                (abs(x-np.rint(x))>1e-8))) for family in ('node_activity','charge_mode','route_flow')}
    bound_float=downward(lower)
    answer={'PASS':True,'schema':'V42_B2_ROOT_LP_INDEPENDENT_V1','phase':'Final','kind':kind,
            'source18r':SOURCE18R,'base_PR211':PR211,'case_sha':CASE,'solver_status':2,
            'LP_completed_numerical_OPTIMAL':True,'ObjVal':float(result['ObjVal']),
            'LP_primal_objective_exact':str(objective),'LP_lower_bound_exact':str(lower),
            'LP_lower_bound':bound_float,'Global_LB':max(OLD_LB,bound_float),
            'native_source_attribute':'Primal ObjVal and Pi, independently corrected by exact weak duality',
            'Native_calls_audited':1,'verifier_Native_optimize_calls':0,'Gurobi_imported':False,
            'FULL_CSR_loaded':False,'original_integer_projection_preserved':True,
            'primal_maximum_row_violation':row_error,'primal_maximum_bound_violation':box_error,
            'reduced_cost_stationarity_maximum_error':rc_error,'row_complementarity_maximum_error':row_complementarity,
            'bound_complementarity_maximum_error':bound_complementarity,'primal_exact_dual_gap':str(gap),
            'primal_exact_dual_gap_float':float(gap),'dual_correction':details,'fractional_counts':fractions,
            'exact_weak_duality_LP_lower_bound_certificate':True,'exact_LP_optimum_certificate':False,
            'exact_BB_trace_certificate':False,'integer_or_FULL_incumbent_claim':False,
            'proof_scope':'Exact sign-valid row multipliers plus a finite-bound correction for every exact stationarity residual prove LP_lower_bound <= min(stored native LP) <= min(original integer FULL). Numerical OPTIMAL and primal/dual/complementarity checks certify completion at reported tolerances; exact equality of the LP optimum is not claimed.',
            'dimensions':zero['dimensions'],'Native_Runtime':result['Runtime'],'UB':UB,
            'Gap_percent':100*(UB-max(OLD_LB,bound_float))/UB,
            'file_sha256':{name:sha(out/name) for name in ('LP_A.npz','LP_DATA.npz','LP_POINT.npz','LP_ORIGINAL_BINARY.npz','INDEPENDENT_NATIVE0.json','NATIVE0.json','NATIVE_READBACK.json','PILOT_STARTED.json','RESULT.json','MEMORY_ADMISSION.json','PRE_OPTIMIZE_PEERS.json','PRE_OPTIMIZE_B1_SAFETY.json','B1_PRIORITY_TRACE.json','MEMORY_TRACE.json','NATIVE.log')},
            'global_ledger_sha256':sha(out.parent/'NATIVE_LEDGER.json'),'B1_heavy_conflicts':0}
    if kind!='BASE':
        base=read(previous/'INDEPENDENT_CERTIFICATE.json')
        answer.update(BASE_LP_lower_bound=base['LP_lower_bound'],Delta_LP_lower_bound=bound_float-base['LP_lower_bound'],
                      Delta_LP_objective=float(result['ObjVal'])-base['ObjVal'],
                      adoption_bound_threshold=.001,candidate_material_LP_gain=bound_float-base['LP_lower_bound']>=.001)
    return answer


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('native0','final','soc-proof','cuts'),required=True)
    parser.add_argument('--kind',choices=('BASE','GRID','SOC'),default='BASE')
    parser.add_argument('--previous',type=Path,default=K48);parser.add_argument('--out',type=Path,default=OUT/'base')
    args=parser.parse_args();started=time.perf_counter()
    output=args.out/('CUT_VALIDITY_NATIVE0.json' if args.mode=='cuts' else 'INDEPENDENT_SOC_NATIVE0.json' if args.mode=='soc-proof' else 'INDEPENDENT_NATIVE0.json' if args.mode=='native0' else 'INDEPENDENT_CERTIFICATE.json')
    try:
        value=cut_validity(args.kind,args.previous,args.out) if args.mode=='cuts' else soc_proof(args.out) if args.mode=='soc-proof' else native0(args.kind,args.previous,args.out) if args.mode=='native0' else final(args.kind,args.previous,args.out)
        value['wall_seconds']=time.perf_counter()-started;write(output,value)
        print(json.dumps({k:value.get(k) for k in ('PASS','phase','kind','LP_lower_bound','ObjVal','wall_seconds')}))
    except Exception as error:
        write(output,{'PASS':False,'phase':args.mode,'kind':args.kind,'error':str(error),'Native_optimize_calls':0,
                      'traceback':traceback.format_exc(),'wall_seconds':time.perf_counter()-started})
        raise


if __name__=='__main__':main()
