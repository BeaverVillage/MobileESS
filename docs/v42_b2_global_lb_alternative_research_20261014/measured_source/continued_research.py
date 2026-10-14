"""B2 May01 audit, independent A/B pilots, and stage-bound evidence delivery.

Usage: python -m tools.global_lb_alternative.research audit|a|b|finish
Each phase has a durable no-repeat latch. Existing sources are read only.
"""
from collections import defaultdict, Counter
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
import argparse
import csv
import gc
import hashlib
import json
import subprocess
import time

import numpy as np
from scipy import sparse

from tools.global_lb_alternative.math import (require, directed, signature, normalize, weight_packet,
    objective, stabilized_step, dot, exact_dual, transport_cut, binding, combine)
from tools.global_lb_alternative.native import solve, NativeBudget
from tools.physical_global_lb_pilot import read, write, file_sha, owner, UNITS, exact_helpers, project
from tools.critical_grid_cg.verify import npz, canonical_data, CompactMap, Geometry, axis
from tools.verify_physical_global_lb import support_partition, compare_sparse
from tools.joint_critical_grid_lb.pilot import memory, admission
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'docs/v42_b2_global_lb_alternative_research_20261014'
CURRENT = Path('D:/v42_may_joint_repair_campaign_20261013/dates/B2/2025-05-01/attempts/attempt_01/output')
PREFIX = CURRENT.parent/'NATIVE_RUNTIME_LEDGER.json'
PHYS = ROOT/'docs/v42_physical_global_lb_pilot'
BASE = ROOT/'docs/v42_b2_root_lp_tightening/base'
K48 = ROOT/'docs/v42_critical_grid_cg/iteration02'
LB = .46498486997548166


def csv_write(path, rows, fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields or list(rows[0]),extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def phase_latch(name):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/(name+'_STARTED.json')).open('x',encoding='utf-8') as stream:
        json.dump(dict(phase=name,UTC=time.time(),source_sha=file_sha(Path(__file__))),stream)


def load_unit(unit):
    A=sparse.load_npz(PHYS/f'UNIT_{unit}_A.npz').tocsr()
    d=canonical_data(npz(PHYS/f'UNIT_{unit}_DATA.npz'))
    axes=npz(PHYS/f'UNIT_{unit}_AXES.npz')
    # canonical_data includes original synonym keys, remove those for saved native packets.
    d={k:d[k] for k in ('names','c','lb','ub','vtypes','rhs','senses','row_names','constant')}
    return A,d,axes


def load_binding():
    p=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json')
    require(p['PASS'],'IDENTITY_GATE')
    for q in p['protected_files']:
        require(file_sha(Path(q['path']))==q['sha256'],'PROTECTED_INPUT_DRIFT')
    return p['binding']


def audit():
    phase_latch('AUDIT')
    began=time.perf_counter()
    # Latest heads and original reports are retrieved before any optimization.
    prs=[]
    for n in (187,202,203,209,210,211,214,215,220,221,222):
        p=json.loads(subprocess.check_output(['gh','pr','view',str(n),'--repo','BeaverVillage/MobileESS',
            '--json','number,title,headRefOid,headRefName,baseRefName,state,url,body'],text=True,encoding='utf-8'))
        prs.append(p)
    write(OUT/'PR_LATEST_HEADS.json',prs)
    expected={209:'9383a99f1bdcabbd49c79b3ad9f9ee36d523868a',211:'d12315a3757aec187c8da0685c28ef901466386a',
              214:'40ab888b884255e76fd6c89fd01933570b60c242',222:'12594e281bb89611331950f11f775a2612d3cb48'}
    require(all(p['headRefOid']==expected[p['number']] for p in prs if p['number'] in expected),'PR_HEAD_DRIFT')
    full=sparse.load_npz(CURRENT/'FULL_A.npz').tocsr()
    d=npz(CURRENT/'FULL_DATA.npz')
    ident=read(CURRENT/'SCIENTIFIC_CASE_IDENTITY.json')
    prior=read(PHYS/'NATIVE0.json')
    require(matrix_sha(full)==ident['original_matrix_sha']==prior['original_matrix_sha'],'CURRENT_FULL_MATRIX_DRIFT')
    require(_domain_sha(d)==ident['original_domain_sha']==prior['original_domain_sha'],'CURRENT_FULL_DOMAIN_DRIFT')
    rho=list(d['names']).index('rho_max')
    require(d['objective'][rho]==1 and np.count_nonzero(d['objective'])==1 and float(d['constant'])==0,
            'OBJECTIVE_DRIFT')
    require(d['lower'][rho]==0 and d['upper'][rho]==1,'RHO_FINITE_BOUND_DRIFT')
    input_identity=read(CURRENT/'INPUT_AND_SOURCE_IDENTITY.json')
    source_sha=signature(input_identity)
    obj_sha=signature(dict(objective=d['objective'].tolist(),constant=float(d['constant'])))
    bound=binding('B2',source_sha,ident['case_sha'],ident['original_matrix_sha'],ident['original_domain_sha'],
                  obj_sha,ident['anchor_sha'])
    owners,row_low,row_high,_,empty_physical=support_partition(full,d)
    unit_checks=[]
    root_d=npz(BASE/'LP_DATA.npz');root_A=sparse.load_npz(BASE/'LP_A.npz').tocsr()
    raw=npz(BASE/'LP_POINT.npz');root_x=raw['x'];pi=raw['pi'].copy()
    root_cert=read(BASE/'INDEPENDENT_CERTIFICATE.json')
    require(root_cert['PASS'] and root_cert['solver_status']==2,'ROOT_CERTIFICATE_GATE')
    for name in ('LP_A.npz','LP_DATA.npz','LP_POINT.npz'):
        require(file_sha(BASE/name)==root_cert['file_sha256'][name],'ROOT_BYTES_DRIFT')
    bad=np.flatnonzero((root_d['senses']=='<')&(pi>0)|(root_d['senses']=='>')&(pi<0))
    # Raw Pi is rejected. An explicitly separate sign-cone vector is rechecked
    # from scratch against every finite variable bound, including nonzero RC.
    repaired=pi.copy();repaired[bad]=0
    exact,repair_detail=exact_dual(root_A,root_d['c'],root_d['rhs'],root_d['senses'],root_d['lb'],root_d['ub'],repaired,
                                   root_d['constant'])
    require(str(exact)==root_cert['LP_lower_bound_exact'],'INDEPENDENT_ROOT_DUAL_RECALCULATION')
    np.savez_compressed(OUT/'CERTIFIED_ROOT_DUAL.npz',raw_pi=pi,certified_pi=repaired,raw_rc=raw['rc'])
    write(OUT/'NUMERICAL_DUAL_REPAIR_AUDIT.json',dict(PASS=True,binding=bound,raw_candidate_rejected=bool(len(bad)),
          wrong_sign_rows=bad.tolist(),separate_sign_cone_candidate=True,exact_LB=str(exact),detail=repair_detail,
          unbounded_helper_policy='No artificial finite envelope; helpers eliminated by original equalities.',
          equality_multiplier_repair='Elimination of response/injection helpers makes their stationarity exact symbolically; no old M1 dual transfer.',
          PR187_PR202='Historical injection support-loss/sign failure motivates exact elimination; their numeric LB is foreign-case.'))
    mapping=CompactMap(CURRENT,npz(BASE/'LP_AXES.npz')['columns'],root_d['names'])
    physical_root=np.zeros(full.shape[1])
    for unit in UNITS:
        A,u,axes=load_unit(unit)
        spec=prior['models'][unit]
        for suffix,key in (('A','matrix_sha'),('DATA','data_sha'),('AXES','axes_sha')):
            require(file_sha(PHYS/f'UNIT_{unit}_{suffix}.npz')==spec[key],'ORIGINAL_UNIT_SHA_DRIFT')
        columns,rows=axes['columns'],axes['rows']
        compare_sparse(full[rows][:,columns].tocsr(),A)
        for native,original in (('lb','lower'),('ub','upper'),('vtypes','types'),('names','names')):
            require(np.array_equal(u[native],d[original][columns]),'UNIT_DOMAIN_DRIFT')
        require(np.array_equal(u['rhs'],d['rhs'][rows]) and np.array_equal(u['senses'],d['sense'][rows]),'UNIT_ROW_DRIFT')
        # Recompute literal ownership row/column sets, not just inclusion.
        code=UNITS.index(unit)+1
        require(np.array_equal(columns,np.flatnonzero(owners==code)),'UNIT_COLUMN_CENSUS')
        require(np.array_equal(rows,np.flatnonzero((row_low==code)&(row_high==code))),'UNIT_ROW_CENSUS')
        for j in columns:
            offset,terms=mapping.expand(int(j))
            physical_root[j]=float(offset)+sum(float(a)*root_x[k] for k,a in terms.items())
        unit_checks.append(dict(unit=unit,rows=len(rows),columns=len(columns),binaries=int(sum(u['vtypes']=='B')),
                                complete_literal_physical_rows_bounds_types=True))
    physical_root[rho]=root_x[-1]
    # Physical coordinates are restored exactly through the alias proof. Helper
    # values are not needed for either support objective; avoid expanding the
    # entire dense response graph. All selected rows are independently expanded.
    geom=Geometry(full,canonical_data(d))
    np.savez_compressed(OUT/'ORIGINAL_ROOT_POINT.npz',point=physical_root,
                        mapped_columns=np.r_[np.flatnonzero(owners),rho])
    # Fresh current Original FULL validator replay of every PR222 registered incumbent.
    from v42_bootstrap.m1 import native_inputs
    from v42_m1_research.check_ub import validate_candidate
    from v42_m1_research.check_joint import check_exact_integer_replay
    campaign=CURRENT.parents[5]
    bundle=read(Path('D:/v42_may_joint_repair_campaign_20261013/inputs/B2/2025-05-01/NATIVE_INPUT.json'))
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
           [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    selected_A=sparse.load_npz(CURRENT/'DENSE_RESPONSE_A.npz').tocsr();selected_d=npz(CURRENT/'DENSE_RESPONSE_DATA.npz')
    require(matrix_sha(selected_A)==ident['selected_matrix_sha'] and _domain_sha(selected_d)==ident['selected_domain_sha'],
            'CURRENT_SELECTED_DOMAIN_DRIFT')
    c2=npz(CURRENT/'CURRENT_C2_AXES.npz')['columns'];aliases=read(CURRENT/'CURRENT_C2_ALIASES.json')
    def lift(point):
        size=max(full.shape[1],int(max(c2))+1,max(p['column'] for p in aliases)+1)
        x=np.zeros(size);x[c2]=point[:len(c2)]
        for p in reversed(aliases):
            x[p['column']]=p['constant']+sum(float(a)*x[int(k)] for k,a in p['terms'].items())
        return x[:full.shape[1]].copy()
    case=SimpleNamespace(A=selected_A,d=selected_d,original_A=full,original_d=d,graph=graph,
                         case_sha=ident['case_sha'],identity=ident,lift=lift,aliases=aliases,selected_columns=c2)
    incumbents=[]
    registry=read(ROOT/'docs/v42_b2_stationary_repair_20261013/VALIDATED_CASE_INCUMBENTS.json')
    for record in registry:
        path=Path(record['raw']['path'])
        require(file_sha(path)==record['raw']['sha256'],'PROTECTED_MOVING_RAW_DRIFT')
        point=npz(path)['point'];replay=validate_candidate(case,point)
        require(replay['PASS'] and check_exact_integer_replay(replay),'CURRENT_ORIGINAL_FULL_UB_REPLAY_FAIL')
        original=lift(point)
        ub_exact=F(float(d['constant']))+dot({j:F(float(d['objective'][j])) for j in np.flatnonzero(d['objective'])},original)
        original_path=OUT/f'INCUMBENT_{len(incumbents):03d}_ORIGINAL.npz'
        np.savez_compressed(original_path,point=original)
        incumbents.append(dict(PASS=True,raw_path=str(path),raw_sha=file_sha(path),original_path=str(original_path),
                               exact_UB=str(ub_exact),UB=directed(ub_exact,True),replay=replay))
    require(incumbents,'MISSING_PROTECTED_MOVING_INCUMBENT')
    write(OUT/'CURRENT_FULL_INCUMBENT_REPLAY.json',dict(PASS=True,binding=bound,incumbents=incumbents,Native_calls=0))
    # Reconstruct all K48 row formulas from ORIGINAL FULL, independently of old term exports.
    records=read(PHYS/'WEIGHTS.json')['rows'][:]
    for it in ('iteration01','iteration02'):
        records+=read(ROOT/f'docs/v42_critical_grid_cg/{it}/CUTS_EXACT.json')['rows']
    original_ids=[int(p.get('original_row',p.get('row'))) for p in records]
    require(len(original_ids)==48 and len(set(original_ids))==48,'K48_ROW_CENSUS')
    catalog={}
    helper_defs,expand=exact_helpers(full,d)
    for j,i in enumerate(original_ids):
        name=str(d['row_names'][i]);thermal=name.startswith('line_thermal_face[')
        if thermal:
            const,terms=project(full,d,i,expand,rho)
            rr,_,tt=geom.security(i)
            require(tt.pop(rho)==-1 and rr==-const and tt==terms,'INDEPENDENT_HELPER_ELIMINATION_DRIFT')
        else:
            rr,_,terms=geom.security(i);const=-rr
            require(rho not in terms,'UNEXPECTED_COUPLING_RHO')
        require(name==str(root_d['row_names'][-48+j]),'K48_FULL_ROW_AXIS_DRIFT')
        # Verify exact Full -> K48 mapping against stored native CSR, including its outer RHS.
        r,_,compact=mapping.row(-const,F(0),terms)
        if thermal:
            compact[len(root_x)-1]=F(-1)
        native=root_A.getrow(root_A.shape[0]-48+j)
        require(set(compact)==set(map(int,native.indices)),'K48_TERM_AXIS_DRIFT')
        err=sum((max((F(float(v))-compact[int(k)])*F(float(root_d['lb'][k])),
                     (F(float(v))-compact[int(k)])*F(float(root_d['ub'][k])))
                 for k,v in zip(native.indices,native.data)),F(0))
        require(F(float(root_d['rhs'][-48+j]))>=r+err,'K48_OUTWARD_RHS_FAIL')
        catalog[i]=dict(original_row=i,name=name,thermal=thermal,constant=str(const),
                         terms={str(k):str(v) for k,v in terms.items()},root_pi=float(repaired[-48+j]),
                         slot=int(axis(name)[1][0]))
    # Add sparse neighboring original thermal faces for multi-period signed responses.
    dominant=max((p for p in catalog.values() if p['thermal']),key=lambda p:-p['root_pi'])
    center=dominant['slot'];_,coord=axis(dominant['name']);branch,facet=coord[1:]
    lookup={str(n):i for i,n in enumerate(d['row_names']) if str(n).startswith('line_thermal_face[')}
    for t in range(max(0,center-4),min(96,center+4)):
        i=lookup[f'line_thermal_face[{t},{branch},{facet}]']
        if i not in catalog:
            const,terms=project(full,d,i,expand,rho)
            rr,_,tt=geom.security(i);require(tt.pop(rho)==-1 and rr==-const and tt==terms,'WINDOW_HELPER_PROOF_FAIL')
            catalog[i]=dict(original_row=i,name=str(d['row_names'][i]),thermal=True,constant=str(const),
                           terms={str(k):str(v) for k,v in terms.items()},root_pi=0.,slot=t)
    write(OUT/'ORIGINAL_AFFINE_ROW_CATALOG.json',dict(binding=bound,rows={str(k):v for k,v in catalog.items()},
          proof='Two independently implemented exact original equality eliminators agree; no grid row added to K48.'))
    # Seed A0 reuses certified numerical local bounds only under exact new identity/row proof.
    a0=normalize({int(p['row']):F(p['weight']) for p in read(PHYS/'WEIGHTS.json')['rows']})
    a1=normalize({i:F(-p['root_pi']) for i,p in catalog.items() if p['thermal'] and p['root_pi']<0})
    # Sparse neighboring responses cover a genuinely multi-period objective.
    a2=normalize({i:F(1) for i,p in catalog.items() if p['thermal'] and center-2<=p['slot']<center+2
                  and axis(p['name'])[1][1:]==[branch,facet]})
    mu={i:F(-p['root_pi']) for i,p in catalog.items() if not p['thermal'] and p['root_pi']<0}
    seeds=[dict(label='A0_CACHED_PR209',**weight_packet(a0,{})),dict(label='A1_CERTIFIED_ROOT_DUAL',**weight_packet(a1,{})),
           dict(label='A2_SPARSE_SIGNED_MULTIPERIOD',**weight_packet(a2,{})),
           dict(label='A3_SHARED_VOLTAGE_TRANSFORMER',**weight_packet(a1,mu))]
    write(OUT/'REGISTERED_WEIGHT_SEEDS.json',seeds)
    # Raw original coordinates, full route occupancy/travel energy and signed grid contributions.
    diagnostics=[]
    for unit in UNITS:
        _,u,axes=load_unit(unit);columns=axes['columns'];x=physical_root[columns]
        bytime=defaultdict(lambda:dict(Pch=0.,Pdis=0.,Q=0.,fractional_arcs=0,active_stays=0.,travel_energy=0.,mode=None,SOC=None))
        for k,name in enumerate(u['names']):
            fam,coords=axis(name);val=float(x[k])
            if fam in ('Pch','Pdis','Q','SOC','charge_mode'):
                t=int(coords[-1]);r=bytime[t]
                if fam in ('Pch','Pdis','Q'):r[fam]+=val
                else:r['SOC' if fam=='SOC' else 'mode']=val
            elif fam=='arc' and val>1e-9:
                arc=ident['physical_prescreen_authority']['proof']['arcs'][int(coords[1])]
                r=bytime[int(arc[1])];r['fractional_arcs']+=int(abs(val-round(val))>1e-8)
                if arc[4] is None:r['active_stays']+=val
        A,_,_=load_unit(unit)
        for k,name in enumerate(u['row_names']):
            if not str(name).startswith('energy_balance'):continue
            rr=A.getrow(k);soccols=[(j,a) for j,a in zip(rr.indices,rr.data) if str(u['names'][j]).startswith('SOC[')]
            t=min(int(axis(u['names'][j])[1][-1]) for j,_ in soccols)
            bytime[t]['travel_energy']=sum(float(a*x[j]) for j,a in zip(rr.indices,rr.data) if str(u['names'][j]).startswith('arc['))
        for t in range(96):
            r=bytime[t]
            candidates=[p for p in catalog.values() if p['thermal'] and p['slot']==t]
            contributions=[sum(float(F(a))*physical_root[int(j)] for j,a in p['terms'].items() if owner(d['names'][int(j)])==UNITS.index(unit)+1)
                           for p in candidates]
            diagnostics.append(dict(unit=unit,slot=t,**r,simultaneous_charge_discharge=r['Pch']>1e-8 and r['Pdis']>1e-8,
                                    signed_grid_contribution=min(contributions) if contributions else None,
                                    SOC_near_bound=r['SOC'] is not None and min(r['SOC']-440,1080-r['SOC'])<1e-6,
                                    original_coordinates=True))
    csv_write(OUT/'FRACTIONAL_ROUTE_SOC_DIAGNOSIS.csv',diagnostics)
    # Two window sets, chosen by actual active Grid dual and fractional contribution.
    candidates=[]
    for size in (4,8):
        start=max(0,min(96-size,center-size//2));window=list(range(start,start+size))
        responses=[p for p in catalog.values() if p['thermal'] and p['slot'] in window and axis(p['name'])[1][1:]==[branch,facet]]
        require(len(responses)==size,'WINDOW_RESPONSE_COVERAGE')
        for unit in UNITS:
            cols=set(map(int,npz(PHYS/f'UNIT_{unit}_AXES.npz')['columns']))
            terms=defaultdict(F)
            for p in responses:
                for j,a in p['terms'].items():
                    if int(j) in cols:terms[int(j)]-=F(a)/size
            terms={j:a for j,a in terms.items() if a}
            value=dot(terms,physical_root)
            mix=sum(r['fractional_arcs']+(r['mode'] is not None and 1e-8<r['mode']<1-1e-8) for r in diagnostics if r['unit']==unit and r['slot'] in window)
            candidates.append(dict(unit=unit,start=start,size=size,window=window,terms={str(j):str(a) for j,a in terms.items()},
                                   root_support_exact=str(value),root_support=float(value),mix_score=int(mix),
                                   rank_score=float(value)+.001*mix))
    selected=[max((p for p in candidates if p['size']==size),key=lambda p:p['rank_score']) for size in (4,8)]
    write(OUT/'REGISTERED_HULL_CANDIDATES.json',dict(binding=bound,selected=selected,all_candidates=candidates,
        allowed_sizes=[2,4,8,12,16],evaluated_sizes=[4,8],reason='Active original thermal dual at slot31, signed benefit and fractional integer physics; two window sets only.'))
    csv_write(OUT/'MULTIPERIOD_HULL_CANDIDATES.csv',[dict(unit=p['unit'],start=p['start'],size=p['size'],root_support=p['root_support'],
                  mix_score=p['mix_score'],selected=p in selected) for p in candidates])
    # Conservation of measured historical Native budget; no source/version reset.
    ledger=read(PREFIX);total=sum(F(float(c['Native_Runtime'])) for c in ledger['calls'] if c.get('entered_native'))
    require(float(total)==ledger['measured_Native_Runtime'] and ledger.get('inflight') is None,'ACTIVE_LEDGER_NOT_PROVEN')
    require(ledger['Native_ceiling_seconds']==1800 and float(total)==1003.5010001659393,'ACTIVE_PREFIX_CHANGED')
    prefix_records=[dict(path=str(PREFIX),sha256=file_sha(PREFIX))]
    old=ROOT/'docs/v42_b2_adaptive_perf_v3/ALL_SESSION_NATIVE_RUNTIME_LEDGER.json';history=read(old)
    prefix_records.append(dict(path=str(old),sha256=file_sha(old)))
    write(OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json',dict(budget_proven=True,original_ceiling=1800.,prefix_Native_Runtime=float(total),
        pilot_A_cap=360.,pilot_B_cap=240.,pilot_total_cap=600.,admitted_remaining=min(600,1800-float(total)),
        historical_PR221_fresh_used=history['same_fresh_used'],historical_PR221_fresh_remaining=history['remaining'],
        separation_basis='PR221 explicitly closed an independently user-authorized fresh1800 research session. This request explicitly targets PR222 current campaign case and requires charging its1003.501s prefix. PR221 is preserved, not reopened or reset. New calls debit a linked extension of the CURRENT ledger; neither original ledger is written.',
        prefix_records=prefix_records,calls=[],inflight=None,research_Native_Runtime=0.,effective_cumulative_Native_Runtime=float(total),
        workers=1,Threads=1,STOP=False))
    protected=[]
    for path in [CURRENT/n for n in ('FULL_A.npz','FULL_DATA.npz','DENSE_RESPONSE_A.npz','DENSE_RESPONSE_DATA.npz',
                  'SCIENTIFIC_CASE_IDENTITY.json','FIXED_AIDC_ANCHOR.json','INPUT_AND_SOURCE_IDENTITY.json','CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json')]+[PREFIX]:
        protected.append(dict(path=str(path),sha256=file_sha(path)))
    for p in incumbents:protected.append(dict(path=p['raw_path'],sha256=p['raw_sha']))
    write(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json',dict(PASS=True,binding=bound,baseline_git=expected[222],
        physical_source_git=prior['base_commit'],old_case_sha=prior['case_sha'],current_case_sha=ident['case_sha'],
        metadata_case_sha_equal=False,mathematical_model_identical=True,equality_basis='Entire named FULL CSR/domain, Dense CSR/domain, routes and current FULL replay.',
        route_table_sha=ident['route_table_sha'],objective='min rho_max',rho_bounds=[0,1],units=unit_checks,
        protected_files=protected,Native_calls=0,wall_seconds=time.perf_counter()-began))
    ub=min(incumbents,key=lambda p:F(p['exact_UB']))
    write(OUT/'B2_CURRENT_UB_LB_REGISTRY.json',dict(binding=bound,LB_K48=LB,LB_K48_exact=str(F(LB)),
        FULL_UB=ub['UB'],exact_UB=ub['exact_UB'],gap_percent=100*(ub['UB']-LB)/ub['UB'],
        FULL_replayed=True,LB_LAGRANGIAN=None,LB_ROUTE_SOC=None))
    write(OUT/'PREREGISTRATION.json',dict(binding=bound,seed=0,max_weight_evaluations=6,max_local_native_calls=24,
        A_seconds=360,B_seconds=240,local_TimeLimit=29,workers=1,threads=1,materiality=[.001,.005],target_gap_percent=3,
        candidate_window_sets=2,B_strengthened_native_calls=1,stall_updates=2,
        exact_validity_and_numerical_solver_contract_separate=True,campaign_HOLD=True,
        M1_M2_Heavy_allowed=False,automatic_restart=False))
    write(OUT/'RESOURCE_MEMORY_AUDIT.json',dict(Native0=memory(),memory_gate=admission(memory()),Native_calls=0))
    print('AUDIT_PASS',ub['UB'],'ROOT_DUAL',float(exact),'PARTITION',unit_checks,flush=True)


def algorithm_a(resume=False):
    if not resume:
        phase_latch('A')
    else:
        require((OUT/'A_STARTED.json').exists(),'A_CONTINUATION_WITHOUT_LATCH')
        require(read(OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json')['inflight'] is None,'A_INFLIGHT_QUARANTINE')
        # Continued evaluations reuse completed identical unit bounds. Never
        # repeat any consumed optimize, reset the prefix, or remove old gates.
        write(OUT/'A_CONTINUATION_NATIVE0.json',dict(Native_calls=0,ledger_sha=file_sha(OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json'),
              reason='External Known/Unknown pytest exited; complete previously unstarted unit calls under same weight and cumulative ledger.',
              completed_calls_repeated=0,failed_prelaunch_receipt_preserved=True))
    bound=load_binding();budget=NativeBudget(OUT)
    rows={int(k):v for k,v in read(OUT/'ORIGINAL_AFFINE_ROW_CATALOG.json')['rows'].items()}
    seeds=read(OUT/'REGISTERED_WEIGHT_SEEDS.json');history=[];certs=[];seen=set()
    cached=read(PHYS/'INDEPENDENT_CERTIFICATE.json')
    require(cached['PASS'],'A0_CERTIFIED_REUSE_GATE')
    best=None;best_point=None;stalls=0
    queue=seeds[:]
    for evaluation in range(6):
        if not queue:break
        candidate=queue.pop(0);w={int(k):F(v) for k,v in candidate['weights'].items()};mu={int(k):F(v) for k,v in candidate['mu'].items()}
        packet=weight_packet(w,mu)
        if packet['sha256'] in seen:break
        seen.add(packet['sha256']);constant,terms=objective(rows,w,mu);local=[];point={};wall=time.perf_counter()
        completed_dir=OUT/'A'/f'E{evaluation:02d}_{candidate["label"]}'
        pending=sum(not (completed_dir/u/'RESULT.json').exists() for u in UNITS)
        if evaluation and budget.remaining('A')<pending*30+1:
            write(OUT/'A_EARLY_STOP.json',dict(reason='COMPLETE_FOUR_UNIT_EVALUATION_RESERVE',remaining=budget.remaining('A')));break
        for unit in UNITS:
            A,d,axes=load_unit(unit);cols=axes['columns'];lookup={int(j):k for k,j in enumerate(cols)}
            c={lookup[j]:v for j,v in terms.items() if j in lookup}
            if evaluation==0:
                result=read(PHYS/unit/'RESULT.json')
                old_exact={int(j):F(a) for j,a in read(PHYS/'WEIGHTS.json')['exact_objective'].items()}
                require(terms==old_exact,'CACHED_OBJECTIVE_DRIFT')
                lower=F(result['certified_LB_exact']);native=0.;status=result['status'];inc=result['incumbent']
                x=npz(PHYS/unit/'INCUMBENT.npz')['point'];receipt=dict(cached_from=str(PHYS/unit/'RESULT.json'),cached_sha=file_sha(PHYS/unit/'RESULT.json'))
            else:
                raw=npz(OUT/'INCUMBENT_000_ORIGINAL.npz')['point'];start=raw[cols]
                target=OUT/'A'/f'E{evaluation:02d}_{candidate["label"]}'/unit
                if target.exists() and (target/'RESULT.json').exists():
                    require(resume,'CONSUMED_CALL_REUSE_REQUIRES_CONTINUATION')
                    result=read(target/'RESULT.json')
                    native_d=npz(target/'DATA.npz');exact_saved=read(target/'EXACT_OBJECTIVE.json')
                    require(exact_saved['terms']=={str(j):str(v) for j,v in c.items()},'CONTINUATION_OBJECTIVE_DRIFT')
                    compare_sparse(A,sparse.load_npz(target/'A.npz').tocsr())
                    require(np.array_equal(native_d['lb'],d['lb']) and np.array_equal(native_d['ub'],d['ub']) and
                            np.array_equal(native_d['vtypes'],d['vtypes']),'CONTINUATION_DOMAIN_DRIFT')
                    matching=[q for q in read(budget.path)['calls'] if q['label']==f'A_E{evaluation}_{unit}']
                    require(len(matching)==1 and matching[0]['Native_Runtime']==result['Native_Runtime'],'CONTINUATION_LEDGER_DRIFT')
                else:
                    if target.exists():
                        require(resume and not (target/'STARTED.json').exists(),'CONSUMED_CALL_NO_RETRY')
                        target=target.with_name(unit+'_CONTINUED_PRELAUNCH')
                    result=solve(target,A,d,c,start,budget,'A',f'A_E{evaluation}_{unit}')
                lower=F(result['exact_corrected_bound']);native=result['Native_Runtime'];status=result['status'];inc=result['Incumbent']
                x=npz(target/'POINT.npz')['point'] if result['SolCount'] else None
                receipt=dict(path=str(target),result_sha=file_sha(target/'RESULT.json'))
            if x is not None:
                point.update({int(j):float(v) for j,v in zip(cols,x)})
            local.append(dict(unit=unit,exact_LB=str(lower),LB=directed(lower),Native_Runtime=native,status=status,
                               Incumbent=inc,certificate_scope='numerical Global Solver Bound + exact original finite-box transport',**receipt))
        lower=constant+sum((F(p['exact_LB']) for p in local),F(0));display=directed(lower)
        require(lower<=F(read(OUT/'B2_CURRENT_UB_LB_REGISTRY.json')['exact_UB']),'A_LB_ABOVE_CURRENT_UB')
        record=dict(evaluation=evaluation,label=candidate['label'],**packet,binding=bound,constant=str(constant),local=local,
                    exact_LB=str(lower),LB=display,delta_vs_K48=display-LB,Native_Runtime=sum(p['Native_Runtime'] for p in local),
                    wall_seconds=time.perf_counter()-wall,proof_level='EXACT_INCLUSION_AND_TRANSPORT_PLUS_NUMERICAL_NATIVE_BOUND',
                    update_oracle='EXACT_NUMERICAL_LOCAL_OPTIMUM' if all(p['status']==2 for p in local) else 'HEURISTIC_INCOMPLETE_PRIMAL_NOT_EXACT_SUBGRADIENT')
        certs.append(record);history.append(dict(evaluation=evaluation,label=candidate['label'],weight_sha=packet['sha256'],
             Global_LB=display,delta_vs_K48=display-LB,Native_Runtime=record['Native_Runtime'],wall_seconds=record['wall_seconds'],
             **{unit+'_Bound':local[k]['LB'] for k,unit in enumerate(UNITS)},**{unit+'_Status':local[k]['status'] for k,unit in enumerate(UNITS)}))
        write(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json',dict(binding=bound,evaluations=certs))
        csv_write(OUT/'LAGRANGIAN_WEIGHT_HISTORY.csv',history)
        print('A_EVALUATION',evaluation,candidate['label'],'LB',display,'DELTA',display-LB,'NATIVE',record['Native_Runtime'],flush=True)
        if best is None or lower>F(best['exact_LB']):
            best=record;best_point=point;stalls=0
        elif evaluation>=4:stalls+=1
        if stalls>=2:break
        # Independent initial seeds are compared before any update.
        if evaluation>=3 and best_point and len(best_point)==sum(len(npz(PHYS/f'UNIT_{u}_AXES.npz')['columns']) for u in UNITS):
            w0={int(k):F(v) for k,v in best['weights'].items()};m0={int(k):F(v) for k,v in best['mu'].items()}
            g={i:float(F(p['constant']))+sum(float(F(a))*best_point[int(j)] for j,a in p['terms'].items()) for i,p in rows.items() if p['thermal']}
            mg={i:float(F(p['constant']))+sum(float(F(a))*best_point[int(j)] for j,a in p['terms'].items()) for i,p in rows.items() if not p['thermal']}
            wn,mn=stabilized_step(w0,g,m0,mg,evaluation-3)
            queue.append(dict(label=f'STABILIZED_{evaluation-2}',**weight_packet(wn,mn)))
    require(best is not None,'NO_A_CERTIFICATE')
    write(OUT/'LAGRANGIAN_GLOBAL_LB_CERTIFICATE.json',dict(PASS=True,algorithm='Stabilized Lagrangian',binding=bound,
          exact_LB=best['exact_LB'],LB=best['LB'],best_evaluation=best['evaluation'],weight_sha=best['sha256'],
          evaluations=len(certs),Native_Runtime=sum(p['Native_Runtime'] for p in certs),
          verdict='ACCEPT' if best['LB']-LB>=.001 else 'REJECT_NONMATERIAL',exact_BB_trace=False,
          proof='Every FULL projection belongs to each literal96-slot physical X_m; exact nonnegative grid multipliers and epigraph simplex; certified minima are bounds, never incumbents.'))


def algorithm_b():
    phase_latch('B');bound=load_binding();budget=NativeBudget(OUT)
    selected=read(OUT/'REGISTERED_HULL_CANDIDATES.json')['selected'];root=npz(OUT/'ORIGINAL_ROOT_POINT.npz')['point']
    d=npz(BASE/'LP_DATA.npz');mapping=CompactMap(CURRENT,npz(BASE/'LP_AXES.npz')['columns'],d['names'])
    certs=[];cuts=[];signatures=set()
    for ordinal,p in enumerate(selected):
        unit=p['unit'];A,u,axes=load_unit(unit);lookup={int(j):k for k,j in enumerate(axes['columns'])}
        original={int(j):F(a) for j,a in p['terms'].items()};c={lookup[j]:a for j,a in original.items()}
        raw=npz(OUT/'INCUMBENT_000_ORIGINAL.npz')['point']
        result=solve(OUT/'B'/f'SUPPORT_{ordinal}_{unit}',A,u,c,raw[axes['columns']],budget,'B',f'SUPPORT_{ordinal}_{unit}',maximize=True)
        upper=F(result['exact_corrected_bound']);violation=dot(original,root)-upper
        replay=[]
        for inc in read(OUT/'CURRENT_FULL_INCUMBENT_REPLAY.json')['incumbents']:
            value=dot(original,npz(Path(inc['original_path']))['point'])
            require(value<=upper,'PROTECTED_FULL_INCUMBENT_CUT_VIOLATION')
            replay.append(dict(raw_sha=inc['raw_sha'],exact_slack=str(upper-value)))
        transported=transport_cut(original,upper,mapping,d['lb'],d['ub'])
        key=signature(dict(terms=transported['compact_terms'],rhs=transported['compact_rhs']))
        record=dict(**p,binding=bound,Global_Upper_Bound=str(upper),root_violation_exact=str(violation),
                    root_violation=float(violation),support_native=result,incumbent_replay=replay,transport=transported,
                    accepted=violation>F(1e-8) and key not in signatures,
                    inclusion='FULL integer projection subset X_m; global maximization bound upper-bounds the support over X_m.',
                    exact_BB_proof=False)
        certs.append(record)
        if record['accepted']:
            cuts.append(transported);signatures.add(key)
        write(OUT/'MULTIPERIOD_HULL_CUT_CERTIFICATES.json',dict(binding=bound,certificates=certs,cuts=cuts))
        print('B_SUPPORT',ordinal,unit,p['window'],'VIOLATION',float(violation),'ACCEPTED',record['accepted'],flush=True)
    if not cuts:
        write(OUT/'CUT_BASED_GLOBAL_LB_CERTIFICATE.json',dict(PASS=False,algorithm='Multi-period Route-SOC',binding=bound,
              exact_LB=None,LB=None,verdict='REJECT_NO_CERTIFIED_ROOT_VIOLATION',strengthened_native_calls=0,
              support_Native_Runtime=sum(p['support_native']['Native_Runtime'] for p in certs)))
        return
    A=sparse.load_npz(BASE/'LP_A.npz').tocsr();rr=[];cc=[];vv=[]
    for k,cut in enumerate(cuts):
        for j,a in cut['native_terms'].items():rr.append(k);cc.append(int(j));vv.append(a)
    B=sparse.csr_matrix((vv,(rr,cc)),shape=(len(cuts),A.shape[1]))
    strengthened=sparse.vstack((A,B),format='csr')
    sd=dict(d,rhs=np.r_[d['rhs'],[p['native_rhs'] for p in cuts]],senses=np.r_[d['senses'],['<']*len(cuts)],
            row_names=np.r_[d['row_names'],[f'MULTIPERIOD_SUPPORT_{k}' for k in range(len(cuts))]])
    require(matrix_sha(strengthened[:A.shape[0]].tocsr())==matrix_sha(A),'K48_PREFIX_MODIFIED')
    write(OUT/'B_STRENGTHENED_INCLUSION.json',dict(PASS=True,binding=bound,rows=len(sd['rhs']),columns=len(d['c']),
        cut_count=len(cuts),same_K48_prefix=True,
        theorem='Original FULL integer projection subset strengthened relaxation subset original K48 LP relaxation',
        new_original_Grid_rows=0,only_new_rows_are_certified_multiperiod_integer_supports=True))
    limit=min(178.,budget.remaining('B')-2)
    require(limit>0,'B_NO_REMAINING_NATIVE')
    result=solve(OUT/'B/STRENGTHENED_LP',strengthened,sd,{int(j):F(float(d['c'][j])) for j in np.flatnonzero(d['c'])},
                 None,budget,'B','STRENGTHENED_LP',limit=limit,lp=True)
    if result['status']!=2:
        write(OUT/'CUT_BASED_GLOBAL_LB_CERTIFICATE.json',dict(PASS=False,algorithm='Multi-period Route-SOC',binding=bound,
             exact_LB=None,LB=None,verdict='INCONCLUSIVE_ROOT_INTERRUPTED',native_result=result))
        return
    pi=npz(OUT/'B/STRENGTHENED_LP/DUAL.npz')['pi'];bad=np.flatnonzero((sd['senses']=='<')&(pi>0)|(sd['senses']=='>')&(pi<0))
    candidate=pi.copy();candidate[bad]=0
    lower,detail=exact_dual(strengthened,d['c'],sd['rhs'],sd['senses'],d['lb'],d['ub'],candidate,d['constant'])
    np.savez_compressed(OUT/'B/STRENGTHENED_LP/CERTIFIED_DUAL.npz',pi=candidate)
    write(OUT/'CUT_BASED_GLOBAL_LB_CERTIFICATE.json',dict(PASS=True,algorithm='Multi-period Route-SOC',binding=bound,
         exact_LB=str(lower),LB=directed(lower),LP_ObjVal=result['Incumbent'],wrong_raw_sign_rows=bad.tolist(),
         raw_dual_rejected=bool(len(bad)),separate_exact_sign_cone_certificate=detail,
         verdict='ACCEPT' if directed(lower)-LB>=.001 else 'REJECT_NONMATERIAL',native_result=result,
         exact_LP_optimum_claim=False,exact_BB_trace=False))


def finish():
    bound=load_binding();ub=read(OUT/'B2_CURRENT_UB_LB_REGISTRY.json')
    records=[dict(PASS=True,algorithm='K48 Baseline',binding=bound,exact_LB=str(F(LB)),LB=LB)]
    for name in ('LAGRANGIAN_GLOBAL_LB_CERTIFICATE.json','CUT_BASED_GLOBAL_LB_CERTIFICATE.json'):
        records.append(read(OUT/name))
    final=combine(records,bound,dict(PASS=True,binding=bound,exact_UB=ub['exact_UB']))
    final.update(FULL_UB=ub['FULL_UB'],Native=read(OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json'),
                 M1_M2_accepted=final['LB']-LB>=.001,campaign_HOLD=True)
    write(OUT/'FINAL_GLOBAL_LB_REGISTRY.json',final)
    print('FINAL_REGISTRY',final['best'],final['LB'],final['gap_percent'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['audit','a','resume-a','b','finish'])
    args=parser.parse_args()
    dict(audit=audit,a=algorithm_a,**{'resume-a':lambda:algorithm_a(resume=True)},b=algorithm_b,finish=finish)[args.phase]()
