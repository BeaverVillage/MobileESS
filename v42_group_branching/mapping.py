"""Full original binary census, CSR physics ranking, and scalar coverage."""
from .common import *
from collections import defaultdict,Counter
import re

WEIGHTS=dict(fractionality=.15,critical_grid=.25,injection_sensitivity=.10,SOC=.10,
    route=.10,PCS=.08,matrix_coupling=.07,propagation=.07,complexity=.05,numerical=.03)

def parse(name):
    match=re.fullmatch(r'([^\[]+)\[([^\]]+)\]',str(name))
    return (match[1],match[2].split(',')) if match else (str(name),[])

def primary_group(row):return f"{'B_MODE' if row['family']=='charge_mode' else 'A_LOCATION'}:{row['MESS']}:{row['slot']:02d}"

def grid_closure(A,d):
    families=[str(n).split('[')[0] for n in d['names']];definitions={};cache={};active=set()
    for i,n in enumerate(d['row_names']):
        family=str(n).split('[')[0]
        if not family.endswith('_binding'):continue
        js=A.indices[A.indptr[i]:A.indptr[i+1]]
        own=[int(j) for j in js if families[j]==family[:-8]]
        assert len(own)==1 and d['sense'][i]=='=' and own[0] not in definitions
        definitions[own[0]]=i
    def expand(j):
        if j in cache:return cache[j]
        assert j not in active,'CYCLIC_BINDING';active.add(j)
        if families[j] in ('Pch','Pdis','Q'):result={j:1.}
        elif d['lower'][j]==d['upper'][j]:result={}
        else:
            i=definitions[j];row=A.getrow(i);own=float(row[0,j]);assert own!=0
            result=defaultdict(float)
            for k,a in zip(row.indices,row.data):
                if k==j:continue
                for p,v in expand(int(k)).items():result[p]-=float(a)*v/own
            result={p:v for p,v in result.items() if v}
        active.remove(j);cache[j]=result;return result
    return expand,definitions

def main():
    prior.forbid_optimize();started=time.perf_counter()
    assert (REPORTS/'SOURCE_IDENTITY.json').exists()
    prereg=REPORTS/'SCORING_PREREGISTRATION_KO.md'
    if not prereg.exists():prereg.write_text('''# 분기 점수 사전등록

최초 후보 계산 전 고정한다. Fractionality=2 min(x,1−x), critical_grid=실제 rho 행의 binding 등식으로 복원한 Pch/Pdis/Q sensitivity에 원래 가용 bound 폭을 곱한 합, injection sensitivity=그 sensitivity 절댓값 합, SOC=실제 outgoing movement 에너지의 최댓값과 에너지 recurrence coupling, route=실제 outgoing arc 수, PCS=해당 power 열이 연결한 원본 PCS16 행 수, matrix=직접·연결 power 열의 실제 CSR nnz, propagation=0/1 분기에서 원본 비음수·mode 행이 함의하는 zero 열 수, complexity=1/(1+연결 nnz), numerical=1/(1+log10(연결 coefficient max/min))다.

Grid active 후보는 rho_max 계수를 가진 원본 행에서 |native slack|/max(1,|rhs|,max |row coefficient|)≤1e-6으로 고정한다. Native raw 진단의 active 판정이며 exact 물리 feasible point를 주장하지 않는다. Raw Pi를 shadow price나 점수에 사용하지 않는다. All power sensitivity는 원본 CSR binding의 선형 대입이다. Capacity·에너지·nnz는 각각 rho 단위 잠재 변화, kWh, count다. 모드가 Q를 직접 금지한다고 가정하지 않는다.

양의 요소를 전수 binary의 max로 [0,1] 정규화한다. 가중치는 fractionality .15, critical_grid .25, injection .10, SOC .10, route .10, PCS .08, matrix .07, propagation .07, complexity .05, numerical .03이다. Historical 변수별 certified gain은 확인되지 않았으므로 null이며 점수에 가짜 기여를 주지 않는다. PR179의 전체 certified gain=0은 별도 비교한다. 점수는 순위이며 LB certificate가 아니다.

Primary 그룹은 모든 binary를 family/MESS/physical slot별로 정확히 한 번 분류한다. Critical-grid/time과 96-slot SOC/route는 겹침을 허용하는 분석 view다. 그룹 representative는 free binary·B2 fractionality>1e-6 중 점수 최대, 동률이면 원본 column 최소다. 그룹 순위는 representative 점수 내림차순, primary ID 오름차순, column 오름차순이다. 최상위 그룹을 첫 pivot로 선택하고, 그 뒤 다른 family의 최고 변수 하나, critical-grid 영향이 큰 나머지 변수 하나를 택한다. 동일 column과 동일 scalar 영역은 중복하지 않는다. 최대 세 변수, 모델에 추론 고정은 추가하지 않는다.
''',encoding='utf-8')
    A,d,T,augmented,full=model_inputs();C=A.tocsc();names=list(map(str,d['names']))
    vf=np.array([parse(n)[0] for n in names]);rf=np.array([str(n).split('[')[0] for n in d['row_names']])
    B=np.flatnonzero(d['types']=='B');assert Counter(vf[B])==dict(node_activity=8938,charge_mode=384)
    assert int((vf=='route_flow').sum())==207736 and np.all(d['types'][vf=='route_flow']=='C')
    with np.load(SOURCE187/'B2_ROOT_RAW.npz') as f:x=f['x'].copy();slack=f['slack'].copy()
    with np.load(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz') as f:old=f['x'].copy()
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,battery,receipt=graph_inputs();assert len(sites)==24 and len(initial)==4
    route=read(P183/'ROUTE_PROJECTION_AUDIT.json');assert route['PASS'] and route['terminal_stay_only']
    reader=hc.physical_reader();outgoing=defaultdict(lambda:defaultdict(float));offsets=defaultdict(float);arcids=defaultdict(list)
    for j in reader.arc:
        _,args=parse(reader.d['names'][j]);u,ai=args;ai=int(ai);a=arcs[ai];key=(u,a[0],a[1]);k=int(reader.target[j])
        offsets[key]+=float(reader.offset[j]);arcids[key].append(ai)
        if k>=0:outgoing[key][k]+=1.
    power=defaultdict(list)
    for j in np.flatnonzero(np.isin(vf,['Pch','Pdis','Q'])):
        family,args=parse(names[j]);u,s,t=args;power[u,s,int(t)].append(int(j))
    expand,definitions=grid_closure(A,d);rho=int(np.flatnonzero(d['objective'])[0])
    descriptor_path=ROOT/'docs/v42_m1_gap_rootcause_20261007/CRITICAL_GRID_ROW_DESCRIPTORS.json'
    desc=read(descriptor_path);assert desc['source_C3A_matrix_SHA256']==sha(hc.PARENT/'C3A_A.npz')
    labels={int(r['row']):r for r in desc['rows']};grid=[];sensitivity=defaultdict(dict);touch=defaultdict(set)
    for i in C.getcol(rho).indices:
        row=A.getrow(i);scale=max(1.,abs(float(d['rhs'][i])),float(abs(row.data).max()))
        if abs(slack[i])/scale>1e-6:continue
        terms=defaultdict(float);rhow=float(row[0,rho])
        for j,a in zip(row.indices,row.data):
            if j==rho:continue
            for k,v in expand(int(j)).items():terms[k]+=float(a)*v/-rhow
        physical_slots={int(parse(names[k])[1][-1]) for k,v in terms.items() if v}
        assert len(physical_slots)==1;slot=next(iter(physical_slots));label=labels.get(int(i))
        if label:assert label['slot']==slot
        grid.append(dict(row=int(i),family=str(rf[i]),slot=slot,line_index=label['line_index'] if label else None,
            branch_name=label['branch_name'] if label else None,label_authority='PR169 exact row descriptor' if label else 'NOT_RESOLVED',
            normalized_slack=float(slack[i]/scale),rho_coefficient=rhow,expanded_power_columns=len(terms)))
        for k,v in terms.items():
            if v:sensitivity[k][int(i)]=v;touch[k].add(int(i))
    assert grid;table(REPORTS/'CRITICAL_GRID_ROWS.csv',grid)
    table(REPORTS/'CRITICAL_POWER_SENSITIVITY.csv',[dict(column=j,variable=names[j],row=i,coefficient=a,units='rho per kW/kvar',source='Original CSR binding substitution') for j,term in sensitivity.items() for i,a in term.items()])
    link_index={str(n):i for i,n in enumerate(d['row_names']) if str(n).startswith('node_activity_link[')}
    node_counts=Counter((parse(names[j])[1][0],int(parse(names[j])[1][-1])) for j in B if vf[j]=='node_activity')
    rows=[];node_fail=[];terminal=0
    for j in B:
        family,args=parse(names[j]);u=args[0];rawt=int(args[-1]);t=95 if family=='node_activity' and rawt==96 else rawt
        assert u in initial and 0<=t<96;site=args[1] if family=='node_activity' else None
        keys=[(u,site,t)] if site else [k for k in power if k[0]==u and k[2]==t]
        pcols=[k for key in keys for k in power[key]];outcols=set();ai=[];node_status=None
        if family=='node_activity':
            key=(u,site,t);terms=dict(outgoing[key]);off=offsets[key];ai=arcids[key];outcols=set(terms)
            if terms=={int(j):1.} and off==0.:node_status='EXACT_STAY_ALIAS'
            else:
                li=link_index.get(names[j].replace('node_activity[','node_activity_link['))
                expected={k:-v for k,v in terms.items()};expected[int(j)]=expected.get(int(j),0.)+1.;expected={k:v for k,v in expected.items() if v}
                actual=dict(zip(A.getrow(li).indices,A.getrow(li).data)) if li is not None else {}
                if li is not None and actual==expected and d['sense'][li]=='=' and d['rhs'][li]==off:node_status='OUTGOING_FLOW_IDENTITY'
                else:node_fail.append(int(j));node_status='FAIL'
            terminal+=int(rawt==96)
        direct=C.getcol(j).indices;coupled=set(map(int,direct))
        for k in pcols:coupled.update(map(int,C.getcol(k).indices))
        for k in outcols:coupled.update(map(int,C.getcol(k).indices))
        coefficients=np.concatenate([A.data[A.indptr[i]:A.indptr[i+1]] for i in sorted(coupled)])
        ratio=float(abs(coefficients).max()/abs(coefficients[coefficients!=0]).min())
        gridids=set();gs=0.;inj=0.
        for k in pcols:
            if family=='charge_mode' and vf[k]=='Q':continue
            width=float(d['upper'][k]-d['lower'][k]);v=sensitivity.get(k,{})
            gs+=sum(abs(a)*width for a in v.values());inj+=sum(abs(a) for a in v.values());gridids.update(v)
        energy=[float(arcs[a][4].energy_kwh) for a in ai if arcs[a][4] is not None]
        socrows=[i for i in coupled if rf[i]=='energy_balance']
        pcsrows=[i for i in coupled if rf[i]=='PCS16']
        if family=='charge_mode':
            z0=sum(vf[k]=='Pch' and d['upper'][k]>0 for k in pcols);z1=sum(vf[k]=='Pdis' and d['upper'][k]>0 for k in pcols)
        else:z0=len(outcols);z1=node_counts[u,rawt]-1
        matrix_nnz=sum(A.indptr[i+1]-A.indptr[i] for i in coupled)
        energy_power_potential=sum(abs(float(A[i,k]))*float(d['upper'][k]-d['lower'][k]) for i in socrows for k in pcols if A[i,k]!=0)
        row=dict(column=int(j),variable_name=names[j],family=family,MESS=u,slot=t,source_time_label=rawt,
            site=site,original_lower=float(d['lower'][j]),original_upper=float(d['upper'][j]),source_type='B',
            archived_ROOT=float(old[j]),B2_ROOT=float(x[j]),
            mode_interpretation='z=1 permits charge and forbids discharge; z=0 forbids charge and permits discharge; Q is mode-independent' if family=='charge_mode' else 'DAG vertex through-flow; mid-travel has no site activity; occupancy alone does not force STAY/charging',
            route_membership=';'.join(map(str,ai)),node_identity=node_status,
            SOC_rows=';'.join(map(str,sorted(socrows))),PCS_rows=len(pcsrows),P_Q_columns=';'.join(map(str,pcols)),
            critical_grid_rows=';'.join(map(str,sorted(gridids))),
            constraint_families=';'.join(sorted(set(rf[list(coupled)]))),
            direct_constraint_families=';'.join(sorted(set(rf[direct]))),
            fractionality=float(2*min(x[j],1-x[j])),critical_grid=gs,injection_sensitivity=inj,
            SOC=max(energy,default=0.)+energy_power_potential,SOC_energy_power_potential_kWh=energy_power_potential,
            max_departure_energy_kWh=max(energy,default=0.),SOC_row_count=len(socrows),route=len(ai),PCS=len(pcsrows),matrix_coupling=matrix_nnz,
            propagation=min(z0,z1),implied_zero_columns_z0=z0,implied_zero_columns_z1=z1,
            complexity=1/(1+matrix_nnz),numerical=1/(1+math.log10(max(1.,ratio))),
            coefficient_range_ratio=ratio,historical_variable_specific_certified_gain=None,
            no_global_LB_claim_from_ranking=True)
        row['primary_group']=primary_group(row);row['critical_view']=f'C_GRID:{u}:{t:02d}' if gridids else None
        row['SOC_route_view']=f'D_96SLOT:{u}';rows.append(row)
    assert not node_fail and len(rows)==9322 and len({r['column'] for r in rows})==9322
    for field in WEIGHTS:
        maxval=max(r[field] for r in rows)
        for r in rows:r['normalized_'+field]=max(0.,r[field])/maxval if maxval>0 else 0.
    for r in rows:r['score']=sum(WEIGHTS[k]*r['normalized_'+k] for k in WEIGHTS)
    table(REPORTS/'BINARY_9322_FULL_MAPPING.csv',rows)
    groups=defaultdict(list)
    for r in rows:groups[r['primary_group']].append(r)
    candidates=[]
    for group,members in sorted(groups.items()):
        admissible=[r for r in members if r['original_lower']==0 and r['original_upper']==1 and min(r['B2_ROOT'],1-r['B2_ROOT'])>1e-6]
        rep=min(admissible,key=lambda r:(-r['score'],r['column'])) if admissible else None
        if rep:candidates.append(dict(group=group,family=rep['family'],MESS=rep['MESS'],slot=rep['slot'],size=len(members),representative_column=rep['column'],representative_variable=rep['variable_name'],score=rep['score'],critical_grid=rep['critical_grid']))
    candidates.sort(key=lambda r:(-r['score'],r['group'],r['representative_column']))
    for i,r in enumerate(candidates):r['rank']=i+1
    table(REPORTS/'CANDIDATE_GROUP_RANKING.csv',candidates[:20])
    bycol={r['column']:r for r in rows};selected=[]
    if candidates:
        selected.append(bycol[candidates[0]['representative_column']])
        other=[r for r in candidates if r['family']!=selected[0]['family']]
        if other:selected.append(bycol[other[0]['representative_column']])
        left=[bycol[r['representative_column']] for r in candidates if r['representative_column'] not in {s['column'] for s in selected}]
        if left:selected.append(min(left,key=lambda r:(-r['critical_grid'],-r['score'],r['column'])))
    assert len({r['column'] for r in selected})==len(selected)<=3
    write(REPORTS/'SELECTED_BRANCH_VARIABLES.json',dict(PASS=bool(selected),selected=selected,selection_frozen_before_child_optimize=True,
        scoring_preregistration_SHA256=sha(prereg),ranking_is_not_bound=True,group_whole_fixing=False,native_calls_at_selection=0))
    table(REPORTS/'GROUP_CRITICAL_GRID_SCORES.csv',[dict(group=g,MESS=m[0]['MESS'],slot=m[0]['slot'],columns=len(m),critical_grid_capacity_sum=sum(r['critical_grid'] for r in m),injection_sensitivity_sum=sum(r['injection_sensitivity'] for r in m),raw_Pi_used_as_shadow_price=False) for g,m in sorted(groups.items())])
    table(REPORTS/'GROUP_SOC_PCS_COUPLING.csv',[dict(group=g,columns=len(m),SOC_rows_union=len(set(i for r in m for i in r['SOC_rows'].split(';') if i)),max_departure_energy_kWh=max(r['max_departure_energy_kWh'] for r in m),max_SOC_power_potential_kWh=max(r['SOC_energy_power_potential_kWh'] for r in m),PCS_row_coupling_max=max(r['PCS'] for r in m),route_arcs_max=max(r['route'] for r in m)) for g,m in sorted(groups.items())])
    audit=dict(PASS=True,total_binary=9322,families=dict(Counter(vf[B])),duplicate_columns=0,missing_columns=0,
        domain_identity_PASS=True,MESS=sorted(initial),slots=list(range(96)),source_time_labels=sorted({r['source_time_label'] for r in rows}),
        terminal_label_96_mapped_to_physical_slot_95=terminal,terminal_alias_identity_checked=True,node_identity_failures=node_fail,
        source_t0_occupancy_inherited_unit_flow_not_missing_binary=True,
        primary_group_unique=True,primary_groups=len(groups),analytical_cross_views_may_overlap=True,
        node_activity_has_no_mid_transit_vertex=True,site_activity_exactly_one_hot_unconditionally=False,
        site_activity_at_most_one_conditional_on_unit_DAG_flow=True,
        time_cut_identity='sum(site outgoing activity at t)+sum(route arc flow with departure<t<arrival)=1',
        flow_unit_DAG_proof_reused=sha(P183/'ROUTE_PROJECTION_AUDIT.json'),
        continuous_route_flow_columns=207736,route_flow_misclassified_as_binary=0,
        critical_rho_rows=len(grid),critical_rows_with_exact_historical_labels=sum(r['branch_name'] is not None for r in grid),
        grid_descriptor_SHA256=sha(descriptor_path),group_score_formula=WEIGHTS,native_calls=0,
        all_original_binaries_in_mapping=True,controller_wall_seconds=time.perf_counter()-started)
    write(REPORTS/'BINARY_MAPPING_AUDIT.json',audit)
    (REPORTS/'PHYSICS_GROUP_DEFINITION_KO.md').write_text('''# 물리적 그룹과 시간 의미

A_LOCATION은 MESS/physical slot별 site through-flow binary 그룹, B_MODE는 MESS/slot별 charge_mode 하나다. 모든 9,322개 binary는 두 primary 종류 중 하나에 정확히 한 번 속한다. C_GRID는 실제 CSR sensitivity로 연결된 critical rho 행/time 분석 view, D_96SLOT은 해당 MESS의 전체 SOC·route 분석 view다. C/D는 primary partition과 겹치며 이를 multi-way domain split으로 사용하지 않는다.

node_activity는 STAY 전용 binary가 아니라 forward DAG vertex의 outgoing mass다. 이동 중간에는 site vertex가 없어서 site activity 합을 항상 1로 가정할 수 없다. Unit source→sink flow의 시간 cut에서 site outgoing activity와 이전에 출발하여 아직 도착하지 않은 travel arc mass의 합이 1이다. 따라서 site activity는 조건부 at-most-one이며 이동 중 all-zero가 가능하다. Charge/PCS는 실제 STAY와 연결한 별도 원본 행으로 판정한다. 원본 label96의 terminal node 96개는 travel arrival<96과 마지막 STAY로 physical slot95에 대응하며 saved inverse의 exact alias를 전수 대조했다. Slot0의 초기 위치는 unit source flow/constant로 보존되며 새 binary를 만들지 않는다.

원래 route_flow 207,736개는 continuous다. 비평행 forward DAG, 모든 through-mass binary와 원래 flow 보존을 사용한 PR183의 일반 정수 path projection 증명을 SHA로 재사용한다. 이전 불가능 배정은 그 전체 배정의 모순이며 개별 pivot을 전역 infeasible로 선언하지 않는다. 새 모델의 implied zero columns는 점수용 추론만 기록하고 Child에 실제 추가 고정하지 않는다.
''',encoding='utf-8')
    print('BINARY_MAPPING_PASS',json.dumps(clean(audit)),flush=True)
    print('SELECTED',[(r['column'],r['variable_name'],r['score']) for r in selected],flush=True)

if __name__=='__main__':main()
