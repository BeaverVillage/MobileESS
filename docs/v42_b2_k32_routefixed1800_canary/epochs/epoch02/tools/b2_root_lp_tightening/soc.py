"""768 exact integer-valid SOC/mode/travel candidates; no solver import.

Stored PR209 unit CSR blocks are certified literal FULL slices. Their bytes,
actual energy/mode/connection rows and original DAG authority are audited before
candidate generation. Only verified fractional violations may be selected.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from fractions import Fraction as F
from functools import lru_cache
import gc
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.critical_grid_cg.verify import npz,read,write,sha,require,dyadic,upward,axis
SOURCE=Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
UNITS=('MESS01','MESS02','MESS03','MESS04')
OLD=ROOT/'docs/v42_physical_global_lb_pilot'
K48=ROOT/'docs/v42_critical_grid_cg/iteration02'
OUT=ROOT/'docs/v42_b2_root_lp_tightening'
BASE=OUT/'base'
CASE='34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
SOURCE18R='497609b46faa14ea7e32a9483a333ab32fd264ef'
FAMILIES=('SOC_DISCHARGE_TRAVEL_AVAILABILITY','SOC_CHARGE_HEADROOM')


def csr_row(A,row):
    a,b=A.indptr[row:row+2]
    return {int(c):dyadic(v) for c,v in zip(A.indices[a:b],A.data[a:b])}


def prove(out):
    started=time.perf_counter()
    require(not (out/'SOC_CANDIDATES_EXACT.json').exists(),'SOC_CANDIDATES_ALREADY_SEALED')
    parentzero=read(OLD/'NATIVE0.json');independent=read(OLD/'INDEPENDENT_NATIVE0.json')
    require(parentzero['PASS'] and independent['PASS'] and independent['base_commit']==SOURCE18R and
            independent['all_single_owner_physical_rows_bounds_and_integer_types_retained'], 'LITERAL_FULL_UNIT_PROOF_FAILED')
    identity=read(SOURCE/'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha']==CASE and sha(SOURCE/'SCIENTIFIC_CASE_IDENTITY.json')==
            parentzero['source_records'][str(SOURCE/'SCIENTIFIC_CASE_IDENTITY.json')],'ORIGINAL_CASE_DOMAIN_AUTHORITY_CHANGED')
    physical=identity['physical_prescreen_authority']['proof'];arcs=physical['arcs'];battery=physical['battery']
    bridge=physical['original_matrix_bridge']
    require(physical['PASS'] and bridge['PASS'] and bridge['actual_original_energy_rows_checked']==384 and
            bridge['actual_departure_energy_debit_verified'] and physical['horizon']==96,'ORIGINAL_DAG_ENERGY_BRIDGE_FAILED')
    require(all(0<=int(a[1])<int(a[3])<=96 for a in arcs),'ORIGINAL_ARCS_NOT_STRICT_TIME_DAG')
    c2=npz(SOURCE/'CURRENT_C2_AXES.npz')['columns'];columns=npz(K48/'JOINT_AXES.npz')['columns']
    aliases=read(SOURCE/'CURRENT_C2_ALIASES.json');alias={int(p['column']):p for p in aliases}
    for name in ('CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json'):
        require(sha(SOURCE/name)==parentzero['source_records'][str(SOURCE/name)],'STATIC_ALIAS_AUTHORITY_CHANGED')
    direct={int(c2[c]):j for j,c in enumerate(columns)}
    joint=npz(K48/'JOINT_DATA.npz')
    @lru_cache(maxsize=None)
    def transport(col):
        if col in direct:return F(0),{direct[col]:F(1)}
        require(col in alias,'ORIGINAL_PHYSICAL_COORDINATE_NOT_TRANSPORTABLE')
        p=alias[col];constant=dyadic(p['constant']);pieces=defaultdict(F)
        for c,v in p['terms'].items():
            offset,leaves=transport(int(c));w=dyadic(v);constant+=w*offset
            for leaf,weight in leaves.items():pieces[leaf]+=w*weight
        return constant,{c:v for c,v in pieces.items() if v}
    rows=[];audits=[];source_records={}
    for unit in UNITS:
        spec=parentzero['models'][unit]
        for suffix,key in (('A','matrix_sha'),('DATA','data_sha'),('AXES','axes_sha')):
            p=OLD/f'UNIT_{unit}_{suffix}.npz';require(sha(p)==spec[key],'LITERAL_FULL_UNIT_BYTES_CHANGED');source_records[str(p)]=sha(p)
        A=sparse.load_npz(OLD/f'UNIT_{unit}_A.npz').tocsr();d=npz(OLD/f'UNIT_{unit}_DATA.npz')
        axes_packet=npz(OLD/f'UNIT_{unit}_AXES.npz');original_columns=axes_packet['columns']
        names=list(map(str,d['names']));lookup={name:c for c,name in enumerate(names)}
        unitspec=next(p for p in physical['units'] if p['mess']==unit)
        local_arcs={int(axis(name)[1][1]):c for c,name in enumerate(names) if axis(name)[0]=='arc'}
        require(set(local_arcs)==set(unitspec['retained_arc_indices']),'ORIGINAL_UNIT_ARC_COVER_CHANGED')
        require(all(d['types'][c]=='B' and d['lower'][c]==0 and d['upper'][c]==1 for c in local_arcs.values()),
                'ORIGINAL_ROUTE_BINARY_BOX_CHANGED')
        outgoing=defaultdict(dict);incoming=defaultdict(dict);terminal={};stay={};travel=defaultdict(dict)
        for k,col in local_arcs.items():
            s,t,dest,end,route=arcs[k]
            outgoing[s,t][col]=F(1);incoming[dest,end][col]=F(1)
            if end==96:terminal[col]=F(1)
            if route is None:
                require(s==dest and end==t+1,'INVALID_ORIGINAL_STAY_ARC');stay[s,t]=col
            else:
                require(route['depart']==t and route['connect']==end and route['energy_kwh']>=0,'TRAVEL_DEPARTURE_DEBIT_MISMATCH')
                if route['energy_kwh']:travel[t][col]=dyadic(route['energy_kwh'])
        flow_expected={}
        for site in physical['sites']:
            for t in range(96):
                pieces=defaultdict(F,outgoing[site,t])
                for c,v in incoming[site,t].items():pieces[c]-=v
                pieces={c:v for c,v in pieces.items() if v}
                if pieces:flow_expected[site,t]=pieces
        seen_flow=set();mode_seen=set();connection_seen=set();energy_seen=set();endpoint_seen=set();terminal_seen=False
        energy_by_time={}
        for row,name in enumerate(d['row_names']):
            family=axis(name)[0];terms=csr_row(A,row);rhs=dyadic(d['rhs'][row]);sense=d['sense'][row]
            if family=='flow':
                candidate=[]
                for c,v in terms.items():
                    k=int(axis(names[c])[1][1]);arc=arcs[k]
                    require(v in (F(1),F(-1)),'FLOW_NOT_SIGNED_UNIT_INCIDENCE')
                    candidate.append((arc[0],arc[1]) if v==1 else (arc[2],arc[3]))
                require(candidate and len(set(candidate))==1,'FLOW_NODE_AXIS_AMBIGUOUS')
                key=candidate[0];require(sense=='=' and terms==flow_expected[key] and
                        rhs==int(key==(unitspec['origin'],0)) and key not in seen_flow,'ORIGINAL_UNIT_FLOW_CHANGED')
                seen_flow.add(key)
            elif family=='terminal_location':
                require(sense=='=' and rhs==1 and terms==terminal and not terminal_seen,'ORIGINAL_ANY_SITE_TERMINAL_CHANGED');terminal_seen=True
            elif family in ('initial_SOC','terminal_SOC'):
                t=0 if family=='initial_SOC' else 96;c=lookup[f'SOC[{unit},{t}]']
                require(sense=='=' and terms=={c:F(1)} and rhs==dyadic(battery['initial' if t==0 else 'terminal']),
                        'ORIGINAL_SOC_ENDPOINT_CHANGED');endpoint_seen.add(t)
            elif family in ('connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge'):
                power_family='Pch' if family in ('connected_Pch','no_simultaneous_charge') else 'Pdis'
                power=[c for c in terms if axis(names[c])[0]==power_family]
                require(len(power)==1,'MODE_OR_CONNECTION_POWER_PIVOT_AMBIGUOUS')
                col=power[0];_,coord=axis(names[col]);_,site,t=coord;t=int(t);limit=dyadic(battery['p_limit'])
                if family.startswith('connected_'):
                    expected={col:F(1),stay[site,t]:-limit};expected_rhs=F(0);connection_seen.add((power_family,site,t))
                else:
                    mode=lookup[f'charge_mode[{unit},{t}]'];require(d['types'][mode]=='B' and d['lower'][mode]==0 and d['upper'][mode]==1,
                            'ORIGINAL_MODE_BINARY_BOX_CHANGED')
                    expected={col:F(1),mode:-limit if power_family=='Pch' else limit}
                    expected_rhs=F(0) if power_family=='Pch' else limit;mode_seen.add((power_family,site,t))
                require(sense=='<' and rhs==expected_rhs and terms==expected,'ORIGINAL_MODE_OR_STAY_CONNECTION_CHANGED')
            elif family=='energy_balance':
                soc=sorted([(int(axis(names[c])[1][1]),c,v) for c,v in terms.items() if axis(names[c])[0]=='SOC'])
                require(len(soc)==2 and soc[1][0]==soc[0][0]+1 and soc[0][2]==-1 and soc[1][2]==1 and rhs==0 and sense=='=',
                        'ORIGINAL_SOC_RECURRENCE_SIGN_OR_TIME_CHANGED')
                t=soc[0][0];require(t not in energy_seen,'DUPLICATE_ENERGY_SLOT');energy_seen.add(t)
                charge={c:-v for c,v in terms.items() if axis(names[c])[0]=='Pch'}
                discharge={c:v for c,v in terms.items() if axis(names[c])[0]=='Pdis'}
                require(charge and discharge and len(set(charge.values()))==1 and len(set(discharge.values()))==1,
                        'NONUNIFORM_OR_MISSING_ENERGY_COEFFICIENT')
                alpha=next(iter(charge.values()));beta=next(iter(discharge.values()))
                require(alpha>0 and beta>0 and str(alpha)==bridge['exact_stored_charge_coefficient'] and
                        str(beta)==bridge['exact_stored_discharge_coefficient'],'STORED_EFFICIENCY_COEFFICIENT_CHANGED')
                moves={c:v for c,v in terms.items() if axis(names[c])[0]=='arc'}
                require(moves==travel[t] and all(v>=0 for v in moves.values()),'TRAVEL_ENERGY_TIME_SIGN_CHANGED')
                require(set(terms)==set(charge)|set(discharge)|set(moves)|{soc[0][1],soc[1][1]},'UNKNOWN_ENERGY_VARIABLE')
                energy_by_time[t]=(row,soc[0][1],alpha,beta,charge,discharge,moves)
        require(seen_flow==set(flow_expected) and terminal_seen and endpoint_seen=={0,96} and energy_seen==set(range(96)),
                'ORIGINAL_DAG_OR_FULL_HORIZON_COVER_FAILED')
        expected_power={(family,axis(name)[1][1],int(axis(name)[1][2])) for family in ('Pch','Pdis') for name in names if axis(name)[0]==family}
        require(connection_seen==expected_power and mode_seen==expected_power,'MODE_OR_CONNECTION_COVER_FAILED')
        soccols=[c for c,name in enumerate(names) if axis(name)[0]=='SOC']
        require(len(soccols)==97 and all(d['lower'][c]==battery['minimum'] and d['upper'][c]==battery['maximum'] for c in soccols),
                'ORIGINAL_SOC_BOX_CHANGED')
        require(all(d['lower'][c]==0 and d['upper'][c]==battery['p_limit'] for c,name in enumerate(names) if axis(name)[0] in ('Pch','Pdis')),
                'POWER_NONNEGATIVITY_OR_BOUNDS_CHANGED')
        for t in range(96):
            row,soc,alpha,beta,charge,discharge,moves=energy_by_time[t]
            for family in FAMILIES:
                original={int(original_columns[soc]):F(-1 if family==FAMILIES[0] else 1)}
                power=discharge if family==FAMILIES[0] else charge
                for c,v in power.items():original[int(original_columns[c])]=v
                if family==FAMILIES[0]:
                    for c,v in moves.items():original[int(original_columns[c])]=v
                rhs=-dyadic(battery['minimum']) if family==FAMILIES[0] else dyadic(battery['maximum'])
                constant=F(0);local=defaultdict(F)
                for c,v in original.items():
                    offset,pieces=transport(c);constant+=v*offset
                    for leaf,weight in pieces.items():local[leaf]+=v*weight
                local={c:v for c,v in local.items() if v};rhs-=constant;error=F(0)
                for c,v in local.items():
                    native=float(v);require(math.isfinite(native) and native!=0,'SOC_COEFFICIENT_OVERFLOW_OR_UNDERFLOW')
                    delta=F(native)-v;error+=max(delta*dyadic(joint['lb'][c]),delta*dyadic(joint['ub'][c]))
                native_rhs=upward(rhs+error)
                rows.append({'name':f'{family}[{unit},{t}]','family':family,'unit':unit,'slot':t,
                             'original_energy_row':int(axes_packet['rows'][row]),'alpha':str(alpha),'beta':str(beta),
                             'Emin':str(dyadic(battery['minimum'])),'Emax':str(dyadic(battery['maximum'])),
                             'original_terms':{str(c):str(v) for c,v in sorted(original.items())},
                             'terms':{str(c):str(v) for c,v in sorted(local.items())},'normalized_sense':'<',
                             'exact_rhs':str(rhs),'eliminated_constant':str(constant),'native_rhs':native_rhs,
                             'error_upper_bound':str(error),'rhs_outward_extra':str(F(native_rhs)-(rhs+error)),
                             'original_integer_valid':True,'LP_implication_status':'NOT_ASSERTED; evaluate verified BASE fractional point before selecting'})
        audits.append({'unit':unit,'original_flow_rows_checked':len(seen_flow),'energy_slots':len(energy_seen),
                       'connection_rows_checked':len(connection_seen),'mode_rows_checked':len(mode_seen),
                       'SOC_points':97,'binary_route_arcs':len(local_arcs),'integer_single_path_proved':True,
                       'charge_positive_implies_discharge_and_departure_travel_zero':True})
        del A,d;gc.collect()
    require(len(rows)==768 and len({r['name'] for r in rows})==768,'SOC_CANDIDATE_CENSUS_NOT_768')
    write(out/'SOC_CANDIDATES_EXACT.json',{'schema':'V42_SOC_MODE_TRAVEL_CANDIDATES_V1','source':SOURCE18R,'case_sha':CASE,
          'rows':rows,'candidate_count':768,'source_records':source_records,'Native_optimize_calls':0,
          'integer_proof':'If C=0, B1 is original E[t+1]>=Emin after recurrence and B2 is E[t]<=Emax. If C>0, a nonnegative Pch is positive, its binary stay arc is 1. The original nonnegative unit DAG flow gives exactly one path, so all movement departures at t are 0. Binary charge_mode forces every Pdis=0. Hence D=T=0, B1 is E[t]>=Emin and B2 follows E[t+1]=E[t]+alpha*C<=Emax. No extra physical assumption is used.',
          'continuous_scope':'The integer path/mode disjunction is essential. No assertion that all 768 rows are nonredundant for the actual BASE LP is made.'})
    write(out/'SOC_INTEGER_VALIDITY_NATIVE0.json',{'PASS':True,'schema':'V42_SOC_MODE_TRAVEL_VALIDITY_V1','source18r':SOURCE18R,
          'case_sha':CASE,'candidate_count':768,'Native_optimize_calls':0,'FULL_CSR_loaded':False,
          'unit_original_CSRs_loaded_sequentially':True,'units':audits,'all_original_integer_points_preserved':True,
          'all_original_96_slots_and_97_SOC_points_verified':True,'no_new_binary_bounds_or_physical_assumptions':True,
          'stored_binary64_energy_coefficient_authority':True,'SOC_CANDIDATES_EXACT_sha256':sha(out/'SOC_CANDIDATES_EXACT.json'),
          'wall_seconds':time.perf_counter()-started,'independent_validation_required':True})
    print(json.dumps({'PASS':True,'candidate_count':768,'wall_seconds':time.perf_counter()-started}))


def select(base,out):
    certificate=read(base/'INDEPENDENT_CERTIFICATE.json')
    require(certificate['PASS'] and certificate['kind']=='BASE' and certificate['solver_status']==2 and
            certificate['LP_completed_numerical_OPTIMAL'],'BASE_LP_NOT_OPTIMAL_INDEPENDENTLY_CERTIFIED')
    allrows=read(base.parent/'SOC_CANDIDATES_EXACT.json');proof=read(base.parent/'INDEPENDENT_SOC_NATIVE0.json')
    require(proof['PASS'] and proof['candidate_count']==768,'INDEPENDENT_SOC_INTEGER_PROOF_NOT_PASS')
    x=npz(base/'LP_POINT.npz')['x'];u4=npz(base/'LP_START.npz')['x']
    candidates=[];reasons=[]
    for row in allrows['rows']:
        terms={int(c):F(v) for c,v in row['terms'].items()};rhs=F(row['exact_rhs'])
        violation=sum((v*dyadic(x[c]) for c,v in terms.items()),F(0))-rhs
        native=sum((dyadic(float(v))*dyadic(x[c]) for c,v in terms.items()),F(0))-dyadic(row['native_rhs'])
        # Well above native row tolerance: no numerical-zero-only adoption.
        positive=violation>F(1,10**7) and native>F(1,10**7)
        item=dict(row,exact_violation=str(violation),native_fractional_violation_exact=str(native),
                  raw_violation=float(violation),selected=False,
                  reason='ACTUAL_VERIFIED_BASE_FRACTIONAL_VIOLATION' if positive else 'NOT_ROBUSTLY_VIOLATED_OR_NUMERIC_ZERO')
        if positive:candidates.append(item)
        reasons.append({'name':row['name'],'exact_violation':str(violation),'native_violation_exact':str(native),
                        'robust_positive':positive,'LP_implication_scope':'A nonviolated row is not inserted. Robust violation at a validated numerical BASE optimum is observed; no blanket LP redundancy claim.'})
    chosen=sorted(candidates,key=lambda row:(-row['raw_violation'],row['unit'],row['slot'],row['family']))[:32]
    for row in chosen:
        row['selected']=True
        terms={int(c):F(v) for c,v in row['terms'].items()}
        u4_error=sum((dyadic(float(v))*dyadic(u4[c]) for c,v in terms.items()),F(0))-dyadic(row['native_rhs'])
        require(float(u4_error)<=1e-8,'SOC_ORIGINAL_U4_REPLAY_FAILED');row['U4_native_violation_exact']=str(u4_error)
    out.mkdir(parents=True,exist_ok=True)
    write(out/'CUTS_EXACT.json',{'schema':'V42_SOC_MODE_TRAVEL_SELECTED_V1','source':SOURCE18R,'case_sha':CASE,
          'BASE_certificate_sha256':sha(base/'INDEPENDENT_CERTIFICATE.json'),'fractional_point_sha256':sha(base/'LP_POINT.npz'),
          'SOC_candidates_sha256':sha(base.parent/'SOC_CANDIDATES_EXACT.json'),'rows':chosen,'selected_count':len(chosen),
          'Native_optimize_calls':0,'original_integer_points_preserved':True})
    write(out/'SOC_FRACTIONAL_SEPARATION.json',{'PASS':True,'candidate_count':768,'robustly_violated_count':len(candidates),
          'selected_count':len(chosen),'all_candidate_diagnostics':reasons,'selected_names':[r['name'] for r in chosen],
          'selection':'Maximum 32 robust exact/native positive violations of the certified BASE fractional point; raw kWh violations ranked together.',
          'Native_optimize_calls':0,'skip_native_if_zero_selected':not bool(chosen)})
    rr=[];cc=[];vv=[]
    for i,row in enumerate(chosen):
        for c,v in row['terms'].items():rr.append(i);cc.append(int(c));vv.append(float(F(v)))
    A=sparse.coo_matrix((vv,(rr,cc)),shape=(len(chosen),len(x))).tocsr();sparse.save_npz(out/'CUTS_A.npz',A)
    np.savez_compressed(out/'CUTS_DATA.npz',rhs=np.array([r['native_rhs'] for r in chosen]),
                        senses=np.full(len(chosen),'<'),row_names=np.array([r['name'] for r in chosen]))
    print(json.dumps({'PASS':True,'violated':len(candidates),'selected':len(chosen)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('prove','select'),required=True)
    parser.add_argument('--base',type=Path,default=BASE);parser.add_argument('--out',type=Path)
    args=parser.parse_args();target=args.out or (OUT if args.mode=='prove' else OUT/'soc')
    prove(target) if args.mode=='prove' else select(args.base,target)
