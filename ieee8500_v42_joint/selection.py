"""Source-only electrical regions and dispersed joint PCC geometry selection.

No Native policy solver, source DSS mutation, or policy-outcome ranking. MV host
eligibility is distinct from engineered interface and field-installation gates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

from ieee8500_v42.geometry import pair_sign, traffic_xy, transform
from ieee8500_v42.joint_geometry import audit_mapping
from ieee8500_v42.joint_geometry_v3 import load_candidates
from ieee8500_v42.mv_candidates import build_candidates, complete_abc_corridors

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'docs/ieee8500_v42_joint_pcc_reselection'
OLD=ROOT/'docs/ieee8500_v42_single_case'
HIGH=ROOT/'docs/ieee8500_v42_high_impact_scenario'
PRIOR=OLD/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_json(path,data,immutable=False):
    normalized=json.loads(json.dumps(data))
    if immutable and path.exists():
        assert read(path)==normalized,'Preregistered rule changed; preserve old revision'
        return
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def write_csv(path,data):
    if not data:return
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)


def source_primary_tree():
    """Original MV graph including single-phase laterals, original phase banks."""
    inv=read(OLD/'ORIGINAL_FEEDER_INVENTORY.json')
    buses={r['bus']:r for r in inv['buses']}
    primary={b for b,r in buses.items() if abs(r['kv_base_ln']*math.sqrt(3)-12.47)<.01247}
    original={('line.'+r['name']).lower():r for r in read(ROOT/'ieee8500_v42/data/mv_candidates/HISTORICAL_LINES.json')}
    reg={('transformer.'+r['transformer']).lower() for r in inv['regcontrols']}
    graph=defaultdict(dict)
    for r in inv['lines']+inv['transformers']:
        element=r['element'].lower()
        if not r['enabled'] or r['nterm']!=2:continue
        if element.startswith('line.') and original[element]['any_open']:continue
        if element.startswith('transformer.') and element not in reg:continue
        a,b=[v.split('.')[0].lower() for v in r['buses']]
        if a not in primary or b not in primary or a==b:continue
        weight=0.
        if element.startswith('line.'):
            line=original[element]; n=line['phases']
            weight=sum(math.hypot(line['r_matrix'][k*n+k],line['x_matrix'][k*n+k]) for k in range(n))/n*line['length']
        if b not in graph[a]:graph[a][b]={'weight_ohm':weight,'elements':[]}
        graph[a][b]['elements'].append(element);graph[b][a]=graph[a][b]
    parent={'_hvmv_sub_lsb':None};depth={'_hvmv_sub_lsb':0.};edge={};queue=deque(parent)
    while queue:
        a=queue.popleft()
        for b,meta in sorted(graph[a].items()):
            if b in parent:continue
            parent[b]=a;depth[b]=depth[a]+meta['weight_ohm'];edge[b]=meta;queue.append(b)
    return inv,parent,depth,edge


def partition_tree_regions(parent,host_weights,region_count=8):
    """Bisect largest eligible-host-weight connected ABC component by tree edge.

    Every cut is an existing source tree corridor. No current, voltage, AC score
    or bottleneck value enters the partition or its labels.
    """
    adjacency=defaultdict(set)
    for b,a in parent.items():
        if a is not None:adjacency[a].add(b);adjacency[b].add(a)
    components=[set(parent)];cuts=[]
    while len(components)<region_count:
        component=max(components,key=lambda s:(sum(host_weights.get(b,0) for b in s),len(s),tuple(sorted(s))))
        total=sum(host_weights.get(b,0) for b in component)
        options=[]
        for child,a in parent.items():
            if a is None or child not in component or a not in component:continue
            side={child};q=deque([child])
            while q:
                b=q.popleft()
                for other in adjacency[b]&component:
                    if {b,other}=={child,a} or other in side:continue
                    side.add(other);q.append(other)
            left=sum(host_weights.get(b,0) for b in side);right=total-left
            if left and right:options.append((abs(left-right),abs(len(side)-(len(component)-len(side))),child,a,side,left,right))
        if not options:raise ValueError('Cannot derive requested connected nonempty eligible-host regions')
        _,_,child,a,side,left,right=min(options,key=lambda v:v[:4])
        components.remove(component);components.extend([side,component-side])
        cuts.append({'split':len(cuts)+1,'cut_parent':a,'cut_child':child,
                     'original_component_host_weight':total,'child_side_host_weight':left,'other_side_host_weight':right})
    components.sort(key=lambda s:min(s))
    membership={b:f'R{k+1:02d}' for k,s in enumerate(components) for b in s}
    return membership,cuts


def prepare_candidates_and_regions():
    REPORT.mkdir(parents=True,exist_ok=True)
    mv=build_candidates(ROOT); candidates,authority=load_candidates(ROOT)
    inv,primary_parent,primary_depth,primary_edges=source_primary_tree()
    # Every LV customer is attached to its nearest original continuous ABC
    # ancestor. The single-phase lateral remains audited, not removed.
    proxy_ancestor={}
    for c in candidates:
        proxy=c['upstream_primary_bus'];cursor=proxy
        while cursor not in mv.parent:
            assert cursor in primary_parent and primary_parent[cursor] is not None
            cursor=primary_parent[cursor]
        proxy_ancestor[proxy]=cursor
    weights=Counter(proxy_ancestor[c['upstream_primary_bus']] for c in candidates)
    membership,cuts=partition_tree_regions(mv.parent,weights,8)
    raw_mv={r['dss_bus']:r for r in rows(OLD/'MV_AIDC_CANDIDATES.csv')}
    raw_lv={r['candidate_bus']:r for r in rows(OLD/'LV_STA_CANDIDATES.csv')}
    catalog=[]
    for c in candidates:
        bus=c['bus'];is_mv=c['mode']=='MV_MODELED_PORT';proxy=c['upstream_primary_bus'];ancestor=proxy_ancestor[proxy]
        r=raw_mv[bus] if is_mv else raw_lv[bus]
        catalog.append({'candidate_id':c['candidate_id'],'candidate_bus':bus,'connection_mode':'MV_3PH' if is_mv else 'LV_SPLIT_240',
            'AIDC_role_eligible':is_mv,'STA_role_eligible':True,'phase_nodes':c['phase_nodes'],
            'source_or_proxy_x':c['x'],'source_or_proxy_y':c['y'],'coordinate_authority':c['coordinate_authority'],
            'upstream_primary_bus':proxy,'ABC_region_anchor_bus':ancestor,'electrical_region':membership[ancestor],
            'primary_proxy_path_weight_ohm':primary_depth[proxy],
            'continuous_ABC_path':True if is_mv else 'NOT_REQUIRED_FOR_SPLIT_PHASE',
            'source_proximity_guard_PASS':True if is_mv else 'SOURCE_CUSTOMER_SERVICE_PATH',
            'nominal_connection_kv_LL':12.47 if is_mv else .240,
            'original_lateral_group':r['lateral_group'] if is_mv else 'PRIMARY_PHASE_'+r['upstream_primary_phase'],
            'original_service_primary_phase':'' if is_mv else r['upstream_primary_phase'],
            'customer_terminal_240v':'' if is_mv else r['injection_terminal_240v'],
            'original_service_transformer':'' if is_mv else r['upstream_transformer'],
            'original_transformer_kva':0 if is_mv else float(r['transformer_primary_kva']),
            'support_triplex_lines':'' if is_mv else r['direct_support_lines'],
            'original_triplex_normal_amps':0 if is_mv else float(r['triplex_min_normal_amps']),
            'engineered_port_Pmax_kw':450 if is_mv else 5,'engineered_port_Qmax_at_Pmax_kvar':math.sqrt(600**2-450**2) if is_mv else 3,
            'engineered_port_Smax_kva':600 if is_mv else 6,'engineered_port_current_limit_A':600/(math.sqrt(3)*.480) if is_mv else 27,
            'new_dedicated_MV_transformer_kva':750 if is_mv else 0,'simultaneous_vehicles_per_port':1,
            'field_GIS_protection_access':'UNVERIFIED','host_eligibility_does_not_certify_installation':True,
            'interface_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED','selected_ac_voltage_thermal_and_PQ_gate':'PENDING'})
    write_csv(REPORT/'AIDC_MV_CANDIDATES.csv',[r for r in catalog if r['AIDC_role_eligible']])
    write_csv(REPORT/'STA_MV_LV_CANDIDATES.csv',catalog)
    regions=[]
    for region in sorted(set(membership.values())):
        subset=[r for r in catalog if r['electrical_region']==region]
        regions.append({'electrical_region':region,'ABC_tree_bus_count':sum(v==region for v in membership.values()),
            'eligible_AIDC_MV_host_count':sum(r['connection_mode']=='MV_3PH' for r in subset),
            'eligible_STA_MV_host_count':sum(r['connection_mode']=='MV_3PH' for r in subset),
            'eligible_STA_LV_host_count':sum(r['connection_mode']=='LV_SPLIT_240' for r in subset),
            'eligible_total_distinct_host_count':len(subset),
            'topology_before_AC_scores':True,'AIDC_max_per_region':4,'STA_max_per_region':4,
            'combined_max_per_region':6,'AIDC_min_regions':4,'STA_min_regions':4,'combined_min_regions':6})
    write_csv(REPORT/'ELECTRICAL_REGION_HOST_CAPACITY.csv',regions)
    source={'original_source_sha256':inv['source_sha256'],'candidate_source_sha256':authority,
            'primary_tree_parent':primary_parent,'primary_proxy_root_weight_ohm':primary_depth,
            'primary_edge_metadata':primary_edges,'ABC_tree_parent':mv.parent,
            'ABC_region_membership':membership,'LV_primary_proxy_ABC_ancestor':proxy_ancestor,
            'region_cut_receipts':cuts,'region_count':8,'rooted_region_connected':True,
            'partition':'bisect largest weighted connected ABC-tree component on original edge closest balanced host counts',
            'host_weight':'one each606MV+1177LV host; LV projected nearest original continuousABC ancestor',
            'AC_score_used_to_construct_regions':False,'single_phase_laterals_deleted':False}
    write_json(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json',source,immutable=True)
    oldfit=read(OLD/'joint_selection_v3/geometry_first/GEOMETRY_RESULT.json')['proper_common_transform']
    schedule=[oldfit['rotation_degrees'],135.,0.,90.,180.,270.]+[float(a) for a in range(0,360,15) if a not in (0,90,135,180,270)]
    policy={'schema':'DISPERSED_JOINT_PLACEMENT_V1','service_count':24,'AIDC_count':12,'STA_count':12,'MESS_count':6,
        'original_traffic_service_IDs_fixed':True,'AIDC_physical_buses_fixed':False,'old_mappings_mutated':False,
        'domain_counts':{'AIDC_MV':606,'STA_MV':606,'STA_LV':1177},
        'source_tree_region_sha256':sha(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json'),
        'candidate_csv_sha256':{p:sha(REPORT/p) for p in ['AIDC_MV_CANDIDATES.csv','STA_MV_LV_CANDIDATES.csv']},
        'topology_regions_frozen_before_current_AC_scores':True,'region_count':8,
        'dispersion_hard_constraints':{'role_max_per_region':4,'combined_max_per_region':6,
                                      'each_role_min_regions':4,'combined_min_regions':6},
        'C0':'old PR197 mapping,12LV STA retained as reference; new dispersion not retrospectively imposed',
        'C1':{'STA_even_IDs':'MV_3PH','STA_odd_IDs':'LV_SPLIT_240','MV_count':6,'LV_count':6,
              'allocation_rule':'frozen service parity, independent of AC or final policy outcomes'},
        'C2':{'STA_all':'MV_3PH','MV_count':12,'LV_count':0,'fallback':'report no witness; do not silently change counts'},
        'C3':'unverified future dedicated primary line design only; no new primary conductors instantiated',
        'required_direction_pairs':276,'required_direction_axes':552,'traffic_pair_axis_tolerance_km':.001,
        'common_transform':{'proper_rotation_schedule_degrees':schedule,'positive_uniform_scale':oldfit['uniform_scale'],
                            'shared_centroid_translation':True,'reflection':False,'per_site_rotation':False},
        'algorithm':'full-domain bitset CSP, exact pair arc consistency and hard global regional cardinality/coverage propagation',
        'geometry_only_seed_priority':'old-position common-scale squared distance then lexical bus',
        'score_priority_rule':'site score descending from preregistered multi-line/time capacity-bounded AC sensitivities, then geometry distance and lexical bus',
        'each_angle_search_node_limit':200000,'each_angle_search_seconds_limit':45,
        'stopping_rule':'first complete exact-audited dispersed witness; no global placement optimality claim',
        'no_witness_claim':'UNKNOWN broader proper-transform feasibility if bounded search exhausted',
        'scores_must_be_saved_before_scored_selection':True,'B1_B2_B3_outcomes_used':False,'Native_policy_calls':0,
        'field_GIS_access_protection_and_physical_ETA':'UNVERIFIED engineering proxy; physical/AC gates remain required',
        'final_dispatch_or_single_scenario_frozen':False}
    write_json(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json',policy,immutable=True)
    print(json.dumps({'MV':606,'LV':1177,'regions':regions,'prereg_sha256':sha(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json')},ensure_ascii=False),flush=True)
    return catalog,source,policy


def scope_report_and_existing_distribution():
    """Preserve historical certificates and audit C0/old diagnostic separately."""
    catalog=rows(REPORT/'STA_MV_LV_CANDIDATES.csv');by_bus={r['candidate_bus']:r for r in catalog}
    records=[]
    old=rows(PRIOR); prior_mv=rows(HIGH/'JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv')
    for tag,mapping in [('C0_PR197_REFERENCE',old),('PRIOR135_GEOMETRY_DIAGNOSTIC_NOT_FINAL',prior_mv)]:
        for region in sorted({r['electrical_region'] for r in catalog}):
            subset=[r for r in mapping if by_bus[r['candidate_bus']]['electrical_region']==region]
            A=sum(r['role']=='AIDC' for r in subset);S=sum(r['role']=='STA' for r in subset)
            records.append({'configuration':tag,'electrical_region':region,'AIDC_count':A,'STA_count':S,'combined_count':A+S,
                            'new_role_cap_4_for_comparison_only':A<=4 and S<=4,
                            'new_combined_cap_6_for_comparison_only':A+S<=6,
                            'historical_case_rejected_or_changed_by_new_rule':False})
    write_csv(REPORT/'PRIOR_REGION_DISTRIBUTION_AUDIT.csv',records)
    tree=read(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json');source_buses={r['bus']:r for r in read(OLD/'ORIGINAL_FEEDER_INVENTORY.json')['buses']}
    membership=[]
    for bus,parent in sorted(tree['primary_tree_parent'].items()):
        cursor=bus
        while cursor not in tree['ABC_region_membership']:cursor=tree['primary_tree_parent'][cursor]
        meta=source_buses[bus]
        membership.append({'original_primary_bus':bus,'parent_primary_bus':parent,
            'nearest_continuous_ABC_ancestor':cursor,'electrical_region':tree['ABC_region_membership'][cursor],
            'source_nodes':','.join(map(str,meta['nodes'])),'source_x':meta['x'],'source_y':meta['y'],
            'primary_proxy_path_weight_ohm':tree['primary_proxy_root_weight_ohm'][bus],
            'region_is_original_lateral_identity':False,'CRS_and_physical_GIS_verified':False})
    write_csv(REPORT/'ELECTRICAL_REGION_BUS_MEMBERSHIP.csv',membership)
    document='''# 과거 MV STA 불가능성 증명의 적용 범위

기존 저압 STA 12곳의 Primary Proxy는 모두 단상이다. 같은 버스에 `.1.2.3`를 붙여 중압 출력이나 3상 결선을 추가하는 것은 실제 존재하는 접속 모델이 아니다. 기존 L0는 5 kW/3 kvar/6 kVA/27 A 연구 포트 목적에 따라 선정한 것으로, 이번 고출력 요구 때문에 그 과거 선정 자체가 잘못됐다고 판단하지 않는다.

과거 전 각도 불가능성 증명은 **기존 AIDC 12개 물리 버스 고정 + 원본 source guard를 통과한 MV606 후보 + 공통 proper rotation + 276쌍 방향**의 동시 조건에 한정한다. 132개 AIDC–AIDC 축 조건에서 공통 회전이 191.319215°–191.823332° 열린 구간으로 제한되며 이 전체 구간에서 STA01·STA02·STA05·STA06·STA07·STA10의 적격 MV 후보는 0이다. 원본 십진 좌표를 유리수로 처리한 후보 구간 전수 감사와 그 증명 SHA는 high_impact_scenario의 MV_RELOCATION_ORIENTATION_RESULT.json 및 관련 CSV에 그대로 보존됐다.

그 증명은 Job/QoS·변압기·PCS·보호 정격 문제의 불가능성도, AIDC까지 공동 재선정한 문제의 불가능성도 아니다. 후보가 모두 소진되는 조건은 고정 AIDC가 정하는 좁은 상대 형상 영역이다. 606개 중압 적격 버스가 존재하며 그 개수 자체가 12개보다 적어서 생긴 문제가 아니다.

이후 별도 AIDC+STA 공동 형상 진단에서는 AIDC 고정을 해제하고 606개 MV 후보 전체를 사용했다. 공통 135° proper similarity에서 24개 서로 다른 원본 MV 버스와 276쌍/552축 PASS witness를 확보했다. 따라서 새 공동 후보 공간에 과거 불가능성을 확대할 수 없다. 이 과거135° witness는 진단 자료이며 이번 최종 배치로 자동 채택하지 않는다.

이번 재선정은 MV606 및 원본 고객 LV1177 후보, 기존 traffic24 IDs와 MESS6대를 보존한다. 원본 ABC 연결 트리를 기반으로 AC 점수를 읽기 전에 8개 연결 권역을 분할했다. 원본 간선을 자르며 eligible606MV+1177LV 수의 균형을 기준으로 가장 큰 권역부터 반복 분할한다. LV 고객은 가장 가까운 상위 ABC 조상으로 권역을 분류하고 그 단상 Primary 경로·기존 서비스 변압기·Triplex는 보존한다.

새 C1/C2에는 권역별 AIDC≤4, STA≤4, 합계≤6 및 AIDC/STA 각각≥4권역, 합계≥6권역을 실제 공동 CSP 제약으로 적용한다. C1의 MV6/LV6 서비스 배정은 AC 점수 전에 짝수 STA=MV·홀수 STA=LV로 사전등록했고 C2는 MV12를 검토한다. 탐색 시간 또는 노드 예산 소진은 UNKNOWN이며 정격·방향 또는 분산 제약을 조용히 완화하지 않는다.

8개 권역은 투명한 topology 기반 연구 분할이다. 이것을 8개의 독립 feeder lateral 또는 8개 별도 지리 지역으로 인증하지 않는다. 원본 lateral 그룹, Primary proxy 전기적 거리, 공통 상류 경로 비율과 실제 AC 기여의 중복은 별도 감사한다. 계통 좌표의 GIS/CRS·현장 접근성·재배치 후 실제 도로 ETA는 여전히 UNVERIFIED다. 중압 ABC 호스트 적격성이 IEEE1547·보호·변압기·PCS 설치 적격성을 자동 인증하지 않는다.
'''
    (REPORT/'PRIOR_MV_STA_INFEASIBILITY_SCOPE_AUDIT.md').write_text(document,encoding='utf-8')


def dispersion_audit(anchors,selected,catalog):
    by_bus={r['candidate_bus']:r for r in catalog};counts={role:Counter() for role in ('AIDC','STA','ALL')}
    for a in anchors:
        region=by_bus[selected[a['location_id']]['bus']]['electrical_region']
        counts[a['role']][region]+=1;counts['ALL'][region]+=1
    hard=read(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json')['dispersion_hard_constraints']
    output=[]
    for region in sorted({r['electrical_region'] for r in catalog}):
        A=counts['AIDC'][region];S=counts['STA'][region]
        output.append({'electrical_region':region,'AIDC_count':A,'STA_count':S,'combined_count':A+S,
            'role_max_per_region':hard['role_max_per_region'],'combined_max_per_region':hard['combined_max_per_region'],
            'region_cap_PASS':A<=hard['role_max_per_region'] and S<=hard['role_max_per_region'] and A+S<=hard['combined_max_per_region'],
            'AIDC_covered_regions':len(counts['AIDC']),'STA_covered_regions':len(counts['STA']),
            'combined_covered_regions':len(counts['ALL']),
            'coverage_PASS':len(counts['AIDC'])>=hard['each_role_min_regions'] and len(counts['STA'])>=hard['each_role_min_regions'] and len(counts['ALL'])>=hard['combined_min_regions']})
    return output


def regional_propagation(domains,roles,region_masks,hard):
    """Hard global upper-cardinality and minimum-coverage propagation.

    A site's region is forced even if several buses remain in that one region.
    This enforces caps during search; final coverage is independently rechecked.
    """
    domains=domains[:];changed=True
    groups=[(list(range(len(roles))),hard['combined_max_per_region'],hard['combined_min_regions'])]
    groups.extend(([i for i,r in enumerate(roles) if r==role],hard['role_max_per_region'],hard['each_role_min_regions']) for role in ('AIDC','STA'))
    while changed:
        changed=False
        for sites,cap,min_regions in groups:
            possible={i:{r for r,mask in region_masks.items() if domains[i]&mask} for i in sites}
            if any(not s for s in possible.values()):return None
            union=set().union(*possible.values())
            if len(union)<min_regions:return None
            forced=Counter(next(iter(s)) for s in possible.values() if len(s)==1)
            if any(n>cap for n in forced.values()):return None
            for region,n in forced.items():
                if n!=cap:continue
                mask=region_masks[region]
                for i in sites:
                    if len(possible[i])==1:continue
                    updated=domains[i]&~mask
                    if not updated:return None
                    if updated!=domains[i]:domains[i]=updated;changed=True
            # If exactly the minimum number remain possible, every such region
            # must be represented. A sole supporting site is thereby forced.
            if len(union)==min_regions:
                for region in union:
                    if forced[region]:continue
                    supporting=[i for i in sites if region in possible[i]]
                    if len(supporting)==1:
                        i=supporting[0];updated=domains[i]&region_masks[region]
                        if updated!=domains[i]:domains[i]=updated;changed=True
    return domains


def dispersed_csp(anchors,candidates,fit,allowed,priority,catalog,hard,node_limit=200000,seconds_limit=45):
    """Complete-domain hard geometry + regional cardinality CSP, bounded runtime."""
    start=time.monotonic();points=[transform((c['x'],c['y']),fit) for c in candidates]
    n=len(candidates);full=(1<<n)-1;target=[traffic_xy(a) for a in anchors]
    less=[];greater=[]
    for axis in (0,1):
        grouped={}
        for j,p in enumerate(points):grouped[p[axis]]=grouped.get(p[axis],0)|(1<<j)
        lower={};upper={};prefix=0
        for value in sorted(grouped):
            lower[value]=prefix;upper[value]=full^(prefix|grouped[value]);prefix|=grouped[value]
        less.append([lower[p[axis]] for p in points]);greater.append([upper[p[axis]] for p in points])
    signs={};compat={}
    for a,b in itertools.permutations(range(len(anchors)),2):
        sx,sy=pair_sign(target[a],target[b],0),pair_sign(target[a],target[b],1)
        signs[(a,b)]=(sx,sy)
        if (sx,sy) not in compat:
            x=greater[0] if sx>0 else less[0] if sx<0 else [full]*n
            y=greater[1] if sy>0 else less[1] if sy<0 else [full]*n
            compat[(sx,sy)]=[(x[j]&y[j])&~(1<<j) for j in range(n)]
    by_bus={r['candidate_bus']:r for r in catalog};region_masks=defaultdict(int)
    for j,c in enumerate(candidates):region_masks[by_bus[c['bus']]['electrical_region']]|=1<<j
    roles=[a['role'] for a in anchors]
    preferences=[sorted(domain,key=lambda j:priority[a][j]) for a,domain in enumerate(allowed)]
    search_nodes=0;arc_revisions=0;regional_revisions=0;bounded=False;answer=None
    def budget():
        nonlocal bounded
        if search_nodes>=node_limit or time.monotonic()-start>seconds_limit:bounded=True;raise TimeoutError
    def consistent(domains,changed=None):
        nonlocal arc_revisions,regional_revisions
        pending_queue=deque(signs if changed is None else [(a,changed) for a in range(len(anchors)) if a!=changed])
        pending=set(pending_queue)
        while True:
            while pending_queue:
                budget();a,b=pending_queue.popleft();pending.remove((a,b));support=compat[signs[(a,b)]]
                revised=0;bits=domains[a]
                while bits:
                    bit=bits&-bits;j=bit.bit_length()-1;bits^=bit
                    if support[j]&domains[b]:revised|=bit
                if revised!=domains[a]:
                    arc_revisions+=1;domains[a]=revised
                    if not revised:return None
                    for c in range(len(anchors)):
                        edge=(c,a)
                        if c!=a and c!=b and edge not in pending:pending_queue.append(edge);pending.add(edge)
            propagated=regional_propagation(domains,roles,region_masks,hard)
            if propagated is None:return None
            changed_sites=[i for i,(before,after) in enumerate(zip(domains,propagated)) if before!=after]
            if not changed_sites:return domains
            regional_revisions+=len(changed_sites);domains=propagated
            for i in changed_sites:
                for other in range(len(anchors)):
                    edge=(other,i)
                    if other!=i and edge not in pending:pending_queue.append(edge);pending.add(edge)
    def search(domains):
        nonlocal search_nodes,answer
        budget();search_nodes+=1
        unresolved=[i for i,d in enumerate(domains) if d.bit_count()>1]
        if not unresolved:
            picks=[d.bit_length()-1 for d in domains]
            selected={a['location_id']:candidates[picks[i]] for i,a in enumerate(anchors)}
            report=dispersion_audit(anchors,selected,catalog)
            if all(r['region_cap_PASS'] and r['coverage_PASS'] for r in report):answer=picks;return True
            return False
        site=min(unresolved,key=lambda i:(domains[i].bit_count(),i))
        for j in preferences[site]:
            if not domains[site]&(1<<j):continue
            child=domains[:];child[site]=1<<j;child=consistent(child,site)
            if child is not None and search(child):return True
        return False
    try:
        domains=consistent([sum(1<<j for j in domain) for domain in allowed])
        if domains is not None:search(domains)
    except TimeoutError:pass
    selected={anchors[i]['location_id']:candidates[j] for i,j in enumerate(answer)} if answer is not None else {}
    audit=audit_mapping(anchors,selected,fit) if selected else []
    dispersion=dispersion_audit(anchors,selected,catalog) if selected else []
    feasible=bool(selected) and all(r['pair_pass'] for r in audit) and all(r['region_cap_PASS'] and r['coverage_PASS'] for r in dispersion)
    return {'selected':selected,'feasible':feasible,'status':'FEASIBLE_HARD_DISPERSION_AND_GEOMETRY' if feasible else 'UNKNOWN_BOUNDED_SEARCH' if bounded else 'INFEASIBLE_THIS_DISCRETE_ORIENTATION_DOMAIN',
            'search_nodes':search_nodes,'arc_revisions':arc_revisions,'regional_revisions':regional_revisions,
            'budget_exhausted':bounded,'elapsed_seconds':time.monotonic()-start,'global_infeasibility_claim':False,
            'hard_region_caps_and_coverage_certified':feasible,'global_optimality_claim':False}


def score_table(paths):
    scores={}
    for path in paths:
        for row in rows(path):
            key=(row['location_id'],row['candidate_id']);value=float(row['score'])
            assert math.isfinite(value) and key not in scores,'Unique finite site/candidate score required'
            scores[key]=value
    return scores


def write_additional_geometry_audits(folder):
    """Read-only derived evidence; never select or rewrite a saved witness."""
    placement=rows(folder/'JOINT_LOCATION_SELECTION.csv')
    audit=rows(folder/'RELATIVE_POSITION_276PAIR_AUDIT.csv')
    axes=[]
    for r in audit:
        for axis in ('x','y'):
            axes.append({'location_a':r['location_a'],'location_b':r['location_b'],
                'role_pair':r['role_pair'],'axis':axis,
                'traffic_node_a':r['traffic_node_a'],'traffic_node_b':r['traffic_node_b'],
                'candidate_bus_a':r['candidate_bus_a'],'candidate_bus_b':r['candidate_bus_b'],
                'traffic_delta_km':r['traffic_d'+axis+'_km'],
                'traffic_axis_zero_tolerance_km':.001,
                'expected_sign':r['expected_'+axis+'_sign'],
                'common_frame_delta_km':r['common_frame_d'+axis+'_km'],
                'actual_sign':r['actual_'+axis+'_sign'],'axis_PASS':r[axis+'_pass'],
                'common_frame_is_physical_GIS_certified':False})
    assert len(axes)==552 and all(r['axis_PASS']=='True' for r in axes)
    write_csv(folder/'RELATIVE_POSITION_552AXIS_AUDIT.csv',axes)
    features={r['bus']:r for r in read(ROOT/'ieee8500_v42/data/mv_candidates/ORIGINAL_STATIC_FEATURES.json')}
    laterals=[]
    for r in placement:
        anchor=r['ABC_region_anchor_bus'];feature=features.get(anchor)
        laterals.append({'case':r['case'],'location_id':r['location_id'],'role':r['role'],
            'candidate_bus':r['candidate_bus'],'primary_proxy':r['upstream_primary_bus'],
            'electrical_region':r['electrical_region'],'original_ABC_anchor_bus':anchor,
            'original_lateral_group':feature['lateral_group'] if feature else 'UPSTREAM_SOURCE_ZONE_NO_FEATURE',
            'original_lateral_authority':'pinned original638 static features at nearestABC ancestor',
            'electrical_region_is_independent_feeder_lateral':False})
    write_csv(folder/'ORIGINAL_PRIMARY_LATERAL_AUDIT.csv',laterals)
    tree=read(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json')
    inv=read(OLD/'ORIGINAL_FEEDER_INVENTORY.json')
    elements={r['element'].lower():r for r in inv['lines']+inv['transformers']}
    catalog={r['candidate_id']:r for r in rows(REPORT/'STA_MV_LV_CANDIDATES.csv')}
    paths=[]
    for site in placement:
        meta=catalog[site['candidate_id']];bus=site['upstream_primary_bus']
        requested={1,2,3} if site['connection_mode']=='MV_3PH' else {int(meta['original_service_primary_phase'])}
        chain=[];cursor=bus
        while tree['primary_tree_parent'][cursor] is not None:
            child=cursor;cursor=tree['primary_tree_parent'][cursor];chain.append((cursor,child))
        for index,(parent,child) in enumerate(reversed(chain)):
            edge=tree['primary_edge_metadata'][child];coverage=set();enabled=True
            for element in edge['elements']:
                device=elements[element];enabled=enabled and device['enabled'];n=device['ncond']
                first=set(device['node_order'][:n])-{0};second=set(device['node_order'][n:2*n])-{0}
                coverage|=first&second
            paths.append({'case':site['case'],'location_id':site['location_id'],'role':site['role'],
                'candidate_bus':site['candidate_bus'],'connection_mode':site['connection_mode'],
                'primary_proxy':bus,'path_root':'_hvmv_sub_lsb','root_to_proxy_edge_order':index+1,
                'original_parent_bus':parent,'original_child_bus':child,
                'original_element_or_parallel_phase_bank':','.join(edge['elements']),
                'original_available_primary_phase_nodes':','.join(map(str,sorted(coverage))),
                'requested_primary_phase_nodes':','.join(map(str,sorted(requested))),
                'source_edge_enabled':enabled,'required_phase_path_PASS':enabled and requested<=coverage,
                'edge_placement_weight_ohm':edge['weight_ohm'],
                'new_primary_conductor_added':False,
                'original_service_transformer':meta['original_service_transformer'],
                'original_customer_terminal_240v':meta['customer_terminal_240v'],
                'original_support_triplex_lines':meta['support_triplex_lines'],
                'source_path_is_field_installation_approval':False})
    assert paths and all(r['required_phase_path_PASS'] for r in paths)
    write_csv(folder/'ORIGINAL_PRIMARY_CONNECTION_PATH_AUDIT.csv',paths)
    return {'direction_axes':len(axes),'source_primary_path_edges':len(paths),
            'selected_mapping_sha256':sha(folder/'JOINT_LOCATION_SELECTION.csv'),
            'direction_axes_PASS':True,'required_primary_phases_PASS':True,
            'physical_GIS_installation_access_protection':'UNVERIFIED'}


def write_prior_mapping_comparison():
    """Document physical PCC identity changes; retain original logical services."""
    prior={r['location_id']:r for r in rows(PRIOR)}
    catalog={r['candidate_id']:r for r in rows(REPORT/'STA_MV_LV_CANDIDATES.csv')}
    tree=read(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json');parents=tree['primary_tree_parent'];depth=tree['primary_proxy_root_weight_ohm']
    combined=[];scope=[]
    for case in ('C1','C2'):
        folder=REPORT/(case+'_SCORED');placement=rows(folder/'JOINT_LOCATION_SELECTION.csv');comparison=[]
        for new in placement:
            old=prior[new['location_id']];cm=catalog[new['candidate_id']];om=catalog[old['candidate_id']]
            pa,pb=old['upstream_primary_bus'],new['upstream_primary_bus'];ancestors=set();cursor=pa
            while cursor is not None:ancestors.add(cursor);cursor=parents[cursor]
            cursor=pb
            while cursor not in ancestors:cursor=parents[cursor]
            denominator=depth[pa]+depth[pb]-depth[cursor]
            is_sta=new['role']=='STA'
            record={'case':case,'P0_reference':'C0 PR197 retained mapping, original12LV STA',
                'location_id':new['location_id'],'role':new['role'],
                'original_traffic_node_id':old['traffic_node_id'],'new_traffic_node_id':new['traffic_node_id'],
                'traffic_node_ID_preserved':old['traffic_node_id']==new['traffic_node_id'],
                'original_candidate_id':old['candidate_id'],'original_PCC_bus':old['candidate_bus'],
                'new_candidate_id':new['candidate_id'],'new_PCC_bus':new['candidate_bus'],
                'PCC_bus_changed':old['candidate_bus']!=new['candidate_bus'],
                'original_connection_mode':om['connection_mode'],'new_connection_mode':cm['connection_mode'],
                'original_topology_region':om['electrical_region'],'new_topology_region':cm['electrical_region'],
                'original_primary_proxy':pa,'new_primary_proxy':pb,
                'original_source_or_proxy_x':old['source_or_proxy_x'],'original_source_or_proxy_y':old['source_or_proxy_y'],
                'new_source_or_proxy_x':new['source_or_proxy_x'],'new_source_or_proxy_y':new['source_or_proxy_y'],
                'source_or_proxy_displacement_unknown_native_units':math.dist((float(old['source_or_proxy_x']),float(old['source_or_proxy_y'])),
                                                                               (float(new['source_or_proxy_x']),float(new['source_or_proxy_y']))),
                'primary_proxy_tree_distance_ohm':depth[pa]+depth[pb]-2*depth[cursor],
                'shared_original_upstream_path_weight_ratio':depth[cursor]/denominator if denominator else 1.,
                'old_STA_port_P_ceiling_kw':5 if is_sta else '',
                'new_STA_port_P_ceiling_kw':cm['engineered_port_Pmax_kw'] if is_sta else '',
                'new_STA_nominal_design_transformer_kva':cm['new_dedicated_MV_transformer_kva'] if is_sta else '',
                'logical_AIDC_site_and_original_jobs_racks_GPU_changed':False,
                'original_road_ETA_data_changed':False,'reassigned_PCC_physical_ETA_access':'UNVERIFIED',
                'common_frame_or_source_distance_is_measured_geography':False,
                'final_nonlinear_AC_eligibility_at_selection':'PENDING',
                'field_installation_PASS':False}
            assert record['traffic_node_ID_preserved']
            comparison.append(record);combined.append(record)
        write_csv(folder/'P0_PCC_MAPPING_COMPARISON.csv',comparison)
        result=read(folder/'SELECTION_RESULT.json')
        dispersion=rows(folder/'ELECTRICAL_REGION_DISPERSION_AUDIT.csv')
        laterals=rows(folder/'ORIGINAL_PRIMARY_LATERAL_AUDIT.csv')
        lateral_counts=[]
        for group in sorted({r['original_lateral_group'] for r in laterals}):
            subset=[r for r in laterals if r['original_lateral_group']==group]
            lateral_counts.append({'case':case,'original_ABC_anchor_lateral_group':group,
                'AIDC_count':sum(r['role']=='AIDC' for r in subset),
                'STA_count':sum(r['role']=='STA' for r in subset),'combined_count':len(subset),
                'authority':'original638 features at nearestABC ancestor; not arbitrary eight region labels',
                'field_geographical_or_protection_independence_certified':False})
        write_csv(folder/'ORIGINAL_PRIMARY_LATERAL_DISTRIBUTION.csv',lateral_counts)
        scope.append({'case':case,'AIDC_count':12,'STA_count':12,'MESS_count':6,
            'AIDC_MV_3phase_count':12,'STA_MV_count':result['STA_MV_count'],'STA_LV_count':result['STA_LV_count'],
            'combined_topology_regions':sum(int(r['combined_count'])>0 for r in dispersion),
            'AIDC_topology_regions':sum(int(r['AIDC_count'])>0 for r in dispersion),
            'STA_topology_regions':sum(int(r['STA_count'])>0 for r in dispersion),
            'distinct_original_ABC_anchor_lateral_groups':len({r['original_lateral_group'] for r in laterals}),
            'all_276pairs_552axes_PASS':result['all_directions_PASS'],
            'all_preregistered_region_caps_and_coverage_PASS':result['all_region_caps_coverage_PASS'],
            'source_guard_and_requested_primary_phases_PASS':True,
            'selected_mapping_sha256':result['witness_sha256'],
            'selection_method':'first complete score-prioritized jointly direction/dispersal constrained witness; overlap audited not optimized',
            'global_optimality_claim':False,'B1_B2_B3_outcomes_used':False,'field_GIS_installation_access_protection':'UNVERIFIED'})
    write_csv(REPORT/'P0_PCC_MAPPING_COMPARISON.csv',combined)
    write_csv(REPORT/'JOINT_PLACEMENT_SCOPE_COMPARISON.csv',scope)
    return scope


def finish_geometry_technical_report():
    """Selection-time Korean conditions and proof scope; no policy results."""
    policy=read(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json')
    comparison=rows(REPORT/'JOINT_PLACEMENT_SCOPE_COMPARISON.csv')
    table=['| 구분 | AIDC MV | STA MV/LV | 권역 전체/AIDC/STA | 원본 ABC 조상 lateral 그룹 | 방향/분산 |',
           '|---|---:|---:|---|---:|---|']
    for row in comparison:
        table.append(f"| {row['case']} | 12 | {row['STA_MV_count']}/{row['STA_LV_count']} | {row['combined_topology_regions']}/{row['AIDC_topology_regions']}/{row['STA_topology_regions']} | {row['distinct_original_ABC_anchor_lateral_groups']} | 276쌍·552축 및 사전 제약 PASS |")
    message='''## 새 공동 문제의 선정 시점 감사

기존 AIDC 고정이 해제된 새 문제에서 C1과 C2의 공동 배치 witness를 확보했다. 이는 과거 고정 AIDC 조건의 불가능성 증명이 새 전체 공동 문제에는 적용되지 않음을 직접 보여준다. 후보가 많다는 추측이나 최적화 실패 여부가 아니라, 원본 버스 24곳의 실제 좌표·상 연결·552개 축 결과가 저장된 구성적 증거다.

최종 점수는 사전등록한 Planning B0·BG0.85·GPU780에서 606개 MV 및 1,177개 LV 후보의 대칭 ±1 kW/±1 kvar AC 교란으로 계산했다. 원래 6개 시간대(0,9,48,68,72,75)에 기준 B0의 전역 피크 74를 투명하게 추가한 별도 사전등록을 적용했으며, 원래 여섯 시간 결과도 보존했다. 이는 Actual 또는 B1/B2/B3 결과를 사용한 재선정이 아니다. FINAL_CANDIDATE_SCORE_FREEZE.json의 점수와 두 원본 민감도 archive SHA를 확인한 뒤 탐색했다.

AIDC와 STA 24개가 동시에 들어가는 bitset CSP에 모든 방향 조건, 버스 고유성, MV/LV 역할, 권역별 cardinality와 coverage를 넣었다. C1은 점수 전에 짝수 STA=MV·홀수 STA=LV를 결정한 6/6 구성이고 C2는 STA12 모두 MV이다. 권역별 AIDC≤4·STA≤4·합계≤6, AIDC와 STA 각각 최소4권역·합계 최소6권역 제약은 실제 탐색과 독립 감사에 적용했다. 권역은 원본 ABC 트리647개 버스를 원본 간선으로 나누어 eligible-host 수가 균형을 이루도록 만든 8개 연결 영역이며, AC 효과 점수 전에 동결했다.

'''+'\n'.join(table)+'''

7개 연결 권역을 7개의 독립 feeder lateral로 해석하지 않는다. 두 배치가 차지하는 원본 static638 features의 ABC 조상 lateral 분류 라벨은 각각4개이며 ORIGINAL_PRIMARY_LATERAL_DISTRIBUTION.csv에 그 원본 그룹별 설치 수를 기록했다. 정확히는 MAJOR:l2820531·MAJOR:l3081380·MAJOR:m1047526의 세 named major 그룹과 TRUNK_OR_MINOR_LATERAL 집계 bucket이므로 이것을 물리적으로 독립된 lateral4개로 인증하지 않는다. C1의 이 네 라벨 설치 수는 각각3·5·6·10개, C2는2·9·5·8개다. LV의 그룹은 가장 가까운 상위 ABC 조상의 원본 분류이므로 개별 단상 서비스가 독립 feeder라는 뜻도 아니다. 전기적 거리와 공통 상류 경로 비율은 ELECTRICAL_PAIR_DISTANCE_SHARED_PATH.csv, 모든 요구 상의 원본 경로는 ORIGINAL_PRIMARY_CONNECTION_PATH_AUDIT.csv에서 확인한다.

공통 변환은 양의 uniform scale 0.0011642948290067979와 하나의 proper rotation135°·공통 centroid translation이다. 모든 24개 위치에 동일한 변환을 적용했고 반사·개별 회전·임의 좌표·방향 뒤집기는 없다. 교통 축 차이가 ±0.001 km 범위이면 기존 동결 공차에 따른 무방향 조건이며 그 밖에는 부호를 엄격하게 보존한다. 원본 IEEE8500 도식 좌표의 CRS·방향·거리 단위는 실제 GIS로 인증되지 않았다. 특히 LV 고객 좌표는 원본 서비스 Primary의 위치 proxy이며 surveyed 고객 좌표가 아니다. 방향 PASS는 이 공통 도식 frame의 결과로서 물리적 지리·접근성을 인증하지 않는다.

원래 공통 각도 −168.244235°의 45초 탐색은 두 경우 모두 UNKNOWN_BOUNDED_SEARCH였고 다음 사전등록 각도135°에서 feasible witness를 얻었다. 시간 제한으로 종료된 각도를 수학적 불가능으로 판정하지 않는다. 점수 우선순위·원래 위치 거리·bus lexical tie-break를 사용한 첫 complete witness이며 전역 최적·최대효과·local optimum을 주장하지 않는다. 제어 효과의 중복과 상호보완성은 JOINT_CONTROL_OVERLAP_AUDIT.csv로 감사했으나 별도 overlap 목적함수나 교환 최적화로 개선한 배치가 아니다.

AIDC 점수에는 원본 Job mask의 알려진 감축 가능량 relaxation과 PF0.95 결합 Q만 반영했다. 실제 QoS를 만족하는 비영 96슬롯 감축 dispatch가 인증된 것은 아니므로 certified AIDC flexible P=0이다. MESS의 450 kW/300 kvar MV 및 5 kW/3 kvar LV 민감도 벡터는 정격·원본 ETA로 제한한 screening 응답이며 여섯 차량의 동시 feasible schedule이나 nonlinear 전압·상전류 PASS를 뜻하지 않는다. 따라서 실제 AIDC–MESS 공동 보완성은 UNPROVEN이다. AIDC 전체 부하 영향과 유연 Job 효과, MESS 응답은 구분했다.

권역 분산만으로 전기적 효과의 독립성을 입증할 수 없다. 동결 critical-corridor·7시간 screening 응답에서 C2의 STA–STA66쌍 모두 P-response cosine≥0.95이고 중앙값0.998440·positive-support Jaccard1.0이다. C1은66쌍 중19쌍이0.95 이상이고 중앙값0.508915다. AIDC–AIDC는 두 배치 모두66쌍 중45쌍이0.95 이상이다. 이는 여러 PCC가 같은 주요 선로 집합에 유사하게 작용하는 제한을 보여준다. 동결 후 이 결과를 근거로 입지를 다시 선택하지 않았고, JOINT_CONTROL_OVERLAP_SUMMARY.csv에 중복을 그대로 남겼다. 이 수치는 정책 개선율·독립 제어 자원 개수·실제 공동 추가 이득을 뜻하지 않는다.

MV의 원본 ABC 호스트 적격성과 새로운 750 kVA·12.47/0.480 kV 전용 변압기·PCS·보호 인터페이스의 engineering 설계 적격성은 서로 다른 gate다. 기존 Triplex·서비스 변압기·원본 선로 정격을 바꾸지 않았고 새 Primary 도체를 추가하지 않았다. LV 포트는 5 kW/3 kvar/6 kVA/27 A를 유지한다. MV 차량은 P450 kW·S600 kVA·E1800 kWh와 실제 상전류 제한721.687836 A를 함께 적용해야 하며 nonlinear AC에서 허용 출력이 줄 수 있다. 양방향 보호·접지·short-circuit·GIS·현장 도로 접근·재배치 PCC 실제 ETA는 ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED/UNVERIFIED다.

P0_PCC_MAPPING_COMPARISON.csv는 C0 PR197 원본 매핑 대비 C1/C2 48개 행을 기록한다. 기존 24개 traffic ID, 원본 ETA, Job/Rack/GPU 권위와 MESS6대는 보존하고 PCC만 변경했다. 양 배치의 SHA는 B0 전체 AC 또는 B1/B2/B3 결과를 확인하기 전에 기록했으며 이후 제어 효과로 bus를 바꾸지 않는다. 현재 문서의 방향·상 경로·분산 PASS는 최종 96슬롯 전압·선로·변압기·탭·커패시터 적격성이나 field 설치 PASS를 대신하지 않는다. 단일 연구 시나리오 결정·최종 Production 승격은 별도 원본 제약 검사와 공정한 사전 결정 규칙에 달려 있다. 기존 캠페인과 원본 DSS·과거 불가능성 증명·geometry-only seed는 보존하고 B1/B2/B3 Solver를 호출하지 않았다.

선정 파일:

- C1_SCORED/JOINT_LOCATION_SELECTION.csv — SHA `4688dc77d7252348792464e7264f6ca6a45184fd5a312a633c2a7d913703629e`
- C2_SCORED/JOINT_LOCATION_SELECTION.csv — SHA `900dec7fd8f16da4356bb109f2b629fa781c34de3ec94932d00264622fa5dd5a`
'''
    path=REPORT/'PRIOR_MV_STA_INFEASIBILITY_SCOPE_AUDIT.md'
    base=path.read_text(encoding='utf-8').split('## 새 공동 문제의 선정 시점 감사')[0].rstrip()
    path.write_text(base+'\n\n'+message,encoding='utf-8')
    (REPORT/'JOINT_GEOMETRY_AND_DISPERSION_TECHNICAL_KO.md').write_text('# 공동 배치의 형상·원본 상 경로·분산 조건 감사\n\n'+message,encoding='utf-8')
    assert policy['domain_counts']=={'AIDC_MV':606,'STA_MV':606,'STA_LV':1177}


def select_case(case,scores_paths=(),geometry_only=False):
    assert case in ('C1','C2')
    scores_paths=[Path(p).resolve() for p in scores_paths]
    catalog=rows(REPORT/'STA_MV_LV_CANDIDATES.csv');source=read(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json')
    policy=read(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json')
    scores=score_table(scores_paths)
    assert geometry_only or scores,'Scored selection requires frozen score table, no silent geometry fallback'
    candidates,_=load_candidates(ROOT)
    anchors=read(ROOT/'ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json')
    old={r['location_id']:r for r in rows(PRIOR)};role_catalog={r['candidate_id']:r for r in catalog}
    oldcenter=read(OLD/'joint_selection_v3/geometry_first/GEOMETRY_PREREGISTRATION.json')
    sc=oldcenter['common_source_center'];tc=oldcenter['common_target_center']
    folder=REPORT/(case+'_GEOMETRY_ONLY' if geometry_only else case+'_SCORED');folder.mkdir(exist_ok=True)
    receipt={'case':case,'geometry_only':geometry_only,'score_source_sha256':{str(Path(p).relative_to(ROOT)):sha(p) for p in scores_paths},
        'placement_preregistration_sha256':sha(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json'),
        'scores_read_before_any_current_policy_outcome':True,'B1_B2_B3_outcomes_used':False}
    write_json(folder/'SEARCH_INPUT_FREEZE.json',receipt,immutable=True)
    attempts=[];winner=None;fit=None
    for angle in policy['common_transform']['proper_rotation_schedule_degrees']:
        theta=math.radians(angle);scale=policy['common_transform']['positive_uniform_scale'];u=scale*math.cos(theta);v=scale*math.sin(theta)
        fit={'u':u,'v':v,'translation_x':tc[0]-u*sc[0]+v*sc[1],'translation_y':tc[1]-v*sc[0]-u*sc[1],
             'rotation_degrees':angle,'uniform_scale':scale,'determinant':u*u+v*v}
        allowed=[];priority=[]
        for a in anchors:
            site=a['location_id'];mv=a['role']=='AIDC' or case=='C2' or int(site[3:])%2==0
            domain=[j for j,c in enumerate(candidates) if (c['mode']=='MV_MODELED_PORT')==mv]
            point=(float(old[site]['source_or_proxy_x']),float(old[site]['source_or_proxy_y']))
            prefs={}
            for j in domain:
                c=candidates[j];dist=scale**2*math.dist(point,(c['x'],c['y']))**2
                if not geometry_only:assert (site,c['candidate_id']) in scores,'Missing allowed site/candidate score'
                prefs[j]=(-scores[(site,c['candidate_id'])] if not geometry_only else 0.,dist,c['bus'])
            allowed.append(domain);priority.append(prefs)
        answer=dispersed_csp(anchors,candidates,fit,allowed,priority,catalog,policy['dispersion_hard_constraints'],
                             policy['each_angle_search_node_limit'],policy['each_angle_search_seconds_limit'])
        record={k:v for k,v in answer.items() if k!='selected'};record['angle_degrees']=angle;attempts.append(record)
        write_json(folder/'SEARCH_PROGRESS.json',attempts);print(json.dumps({'case':case,**record}),flush=True)
        if answer['feasible']:winner=answer;break
    result={'case':case,'geometry_only':geometry_only,'feasible':bool(winner),'attempts':attempts,
        'status':'GEOMETRY_DISPERSION_PASS_PENDING_AC_FIELD_GATES' if winner else 'UNKNOWN_BOUNDED_ORIENTATION_FAMILY',
        'proper_common_transform':fit if winner else None,'policy_outcomes_used':False,
        'source_tree_regions_and_caps_changed_after_scores':False,'global_infeasibility_claim':False,
        'global_placement_optimality_claim':False,'Production_installation_PASS':False,'final_frozen':False}
    if winner:
        selected=winner['selected'];audit=audit_mapping(anchors,selected,fit);placement=[]
        for a in anchors:
            site=a['location_id'];c=selected[site];meta=role_catalog[c['candidate_id']];p=transform((c['x'],c['y']),fit)
            placement.append({'case':case,'location_id':site,'role':a['role'],'traffic_node_id':a['traffic_node'],
                'candidate_id':c['candidate_id'],'candidate_bus':c['bus'],'connection_mode':meta['connection_mode'],
                'electrical_region':meta['electrical_region'],'upstream_primary_bus':meta['upstream_primary_bus'],
                'ABC_region_anchor_bus':meta['ABC_region_anchor_bus'],'source_or_proxy_x':c['x'],'source_or_proxy_y':c['y'],
                'common_frame_x_km':p[0],'common_frame_y_km':p[1],'traffic_x_km':a['x_east_km'],'traffic_y_km':a['y_north_km'],
                'geometry_error_layout_equivalent_km':math.dist(p,traffic_xy(a)),
                'source_host_guard_PASS':True,'source_sensitivity_score':scores[(site,c['candidate_id'])] if not geometry_only else '',
                'field_GIS_protection_actual_ETA':'UNVERIFIED','final_AC_eligibility':'PENDING','final_Production_frozen':False})
        write_csv(folder/'JOINT_LOCATION_SELECTION.csv',placement)
        write_csv(folder/'RELATIVE_POSITION_276PAIR_AUDIT.csv',audit)
        disp=dispersion_audit(anchors,selected,catalog);write_csv(folder/'ELECTRICAL_REGION_DISPERSION_AUDIT.csv',disp)
        pair_metrics=[]
        for a,b in itertools.combinations(placement,2):
            pa,pb=a['upstream_primary_bus'],b['upstream_primary_bus'];ancestors=set();cursor=pa
            while cursor is not None:ancestors.add(cursor);cursor=source['primary_tree_parent'][cursor]
            cursor=pb
            while cursor not in ancestors:cursor=source['primary_tree_parent'][cursor]
            depth=source['primary_proxy_root_weight_ohm'];shared=depth[cursor];den=depth[pa]+depth[pb]-shared
            pair_metrics.append({'case':case,'location_a':a['location_id'],'location_b':b['location_id'],
                'role_pair':'-'.join(sorted([a['role'],b['role']])), 'primary_proxy_a':pa,'primary_proxy_b':pb,
                'common_upstream_primary_bus':cursor,'primary_proxy_tree_distance_ohm':depth[pa]+depth[pb]-2*shared,
                'shared_upstream_path_weight_ratio':shared/den if den else 1.,
                'region_a':a['electrical_region'],'region_b':b['electrical_region'],
                'source_or_proxy_distance_unknown_native_units':math.dist((a['source_or_proxy_x'],a['source_or_proxy_y']),(b['source_or_proxy_x'],b['source_or_proxy_y'])),
                'coordinate_distance_is_physical_GIS_certified':False})
        write_csv(folder/'ELECTRICAL_PAIR_DISTANCE_SHARED_PATH.csv',pair_metrics)
        write_additional_geometry_audits(folder)
        result.update(pair_count=276,axis_count=552,all_directions_PASS=all(r['pair_pass'] for r in audit),
            distinct_buses=len({r['candidate_bus'] for r in placement}),all_region_caps_coverage_PASS=all(r['region_cap_PASS'] and r['coverage_PASS'] for r in disp),
            STA_MV_count=sum(r['role']=='STA' and r['connection_mode']=='MV_3PH' for r in placement),
            STA_LV_count=sum(r['role']=='STA' and r['connection_mode']=='LV_SPLIT_240' for r in placement),
            witness_sha256=sha(folder/'JOINT_LOCATION_SELECTION.csv'))
    write_json(folder/'SELECTION_RESULT.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--case',choices=['C1','C2']);parser.add_argument('--geometry-only',action='store_true')
    parser.add_argument('--scores',nargs='*',default=[]);args=parser.parse_args()
    if args.case: print(json.dumps(select_case(args.case,[Path(p) for p in args.scores],args.geometry_only),ensure_ascii=False),flush=True)
    else:
        prepare_candidates_and_regions();scope_report_and_existing_distribution()
