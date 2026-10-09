"""Geometry-only MV interface audit; never starts a V42 policy solver.

Current LV ports and a separate MV relocation engineering witness are distinct
scenarios. Existing DSS/customer/traffic files are read-only. A bus does not
become ABC by appending '.1.2.3' to its name.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import defaultdict, deque
from pathlib import Path

import opendssdirect as odd

from ieee8500_v42.geometry import pair_sign, traffic_xy, transform
from ieee8500_v42.joint_geometry import audit_mapping, bitset_csp
from ieee8500_v42.joint_geometry_v3 import load_candidates

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/ieee8500_v42_high_impact_scenario'
OLD = ROOT / 'docs/ieee8500_v42_single_case'
SELECTION = OLD / 'joint_selection_v3/score_selection'
FEEDER = ROOT / 'ieee8500_v42/data/feeder'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_json(path, value, immutable=False):
    normalized = json.loads(json.dumps(value))
    if immutable and path.exists():
        assert read(path) == normalized, 'Preregistration is immutable; do not retune.'
        return
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def write_csv(path, rows):
    assert rows
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def original_bus_audit():
    """Independent untouched official Balanced compilation; no policy/AC days."""
    source_before = {p.name: sha(p) for p in sorted(FEEDER.iterdir()) if p.is_file()}
    d = odd.NewContext()
    for method in ('AllowChangeDir', 'AllowForms', 'AllowEditor', 'AllowDOScmd'):
        getattr(d.Basic, method)(False)
    d.Text.Command(f'compile "{FEEDER/"Master.dss"}"')
    d.Text.Command('set controlmode=off')
    actual = {}
    for bus in d.Circuit.AllBusNames():
        d.Circuit.SetActiveBus(bus)
        actual[bus.lower()] = {'nodes': list(d.Bus.Nodes()), 'kv_base_ln': d.Bus.kVBase(),
                              'x': d.Bus.X(), 'y': d.Bus.Y()}
    inv = read(OLD/'ORIGINAL_FEEDER_INVENTORY.json')
    assert d.Lines.Count() == 3703 and d.Transformers.Count() == 1190 and d.Loads.Count() == 1177
    graph = defaultdict(list)
    for row in inv['lines']+inv['transformers']:
        if not row['enabled']: continue
        head = row['buses'][0].split('.')[0].lower()
        for bus in row['buses'][1:]:
            tail = bus.split('.')[0].lower()
            if head == tail: continue
            graph[head].append((tail, row['element']))
            graph[tail].append((head, row['element']))
    parents = {'_hvmv_sub_lsb': None}; queue = deque(parents)
    while queue:
        bus = queue.popleft()
        for other, element in sorted(graph[bus]):
            if other not in parents:
                parents[other] = (bus, element); queue.append(other)
    equipment = {r['location_id']:r for r in csv_rows(SELECTION/'SELECTED_STA_LV_EQUIPMENT.csv')}
    rows = []
    for r in csv_rows(SELECTION/'STA_MAPPING.csv'):
        site = r['location_id']; proxy = r['upstream_primary_bus']; node = actual[proxy]
        assert node['x'] == float(r['source_or_proxy_x']) and node['y'] == float(r['source_or_proxy_y'])
        mv_abc = sorted(node['nodes']) == [1,2,3]
        path=[]; cursor=proxy; ancestor=None
        while cursor in parents and parents[cursor] is not None:
            parent, element = parents[cursor]; path.append(element)
            if sorted(actual[parent]['nodes']) == [1,2,3]: ancestor=parent; break
            cursor=parent
        previous = equipment[site]['old_retained_MV_bus']; oldnode=actual[previous]
        rows.append({'location_id':site, 'traffic_node_id':r['traffic_node_id'],
            'retained_L0_customer_bus':r['candidate_bus'], 'retained_L0_terminal':r['customer_terminal_240v'],
            'unchanged_primary_proxy_bus':proxy, 'fresh_original_proxy_nodes':','.join(map(str,node['nodes'])),
            'nominal_proxy_kv_ll':node['kv_base_ln']*math.sqrt(3),
            'proxy_source_connected':proxy in parents, 'same_proxy_continuous_ABC':mv_abc,
            'same_proxy_M1_M2_M3_eligibility':'PASS_SOURCE_HOST_ONLY' if mv_abc else 'FAIL_MISSING_PRIMARY_PHASES',
            'missing_primary_nodes':','.join(map(str,sorted({1,2,3}-set(node['nodes'])))),
            'primary_proxy_x':node['x'], 'primary_proxy_y':node['y'],
            'first_upstream_ABC_ancestor_UNSELECTED':ancestor,
            'single_phase_path_to_ABC_ancestor':';'.join(path),
            'historical_different_MV_bus_UNSELECTED':previous,
            'historical_different_MV_nodes':','.join(map(str,oldnode['nodes'])),
            'historical_MV_coordinate_change_native_unknown_units':math.dist((node['x'],node['y']),(oldnode['x'],oldnode['y'])),
            'hypothetical_MV_output_assigned_to_LV_bus':False,
            'site_access_protection_GIS':'UNVERIFIED', 'source_scope':'independent official Master.dss compile',
            'original_DSS_mutated':False})
    assert len(rows)==12
    source_after={p.name:sha(p) for p in sorted(FEEDER.iterdir()) if p.is_file()}
    assert source_before == source_after == inv['source_sha256']
    write_json(REPORT/'MV_ORIGINAL_SOURCE_PRESERVATION.json',
        {'official_Balanced_master':'Master.dss','official_customer_file':'Loads.dss',
         'before_sha256':source_before,'after_sha256':source_after,
         'original_PR193_source_manifest_identical':True,'source_file_count':31,
         'original_lines':3703,'original_transformers':1190,'balanced_original_load_objects':1177,
         'fresh_same_proxy_MV_eligible_STA':sum(r['same_proxy_continuous_ABC'] for r in rows),
         'original_DSS_write_calls':0,'production_campaign_write_calls':0,'Native_solver_calls':0})
    write_csv(REPORT/'MV_STA_ELIGIBILITY_AUDIT.csv', rows)
    return rows, source_before


def relocate_geometry():
    """All606 domains, fixed AIDC/common fit, nearest-old-proxy branch priority.

    First feasible CSP witness; no claim of a global distance optimum. Every
    candidate is considered. Time/node exhaustion is UNKNOWN, not impossible.
    """
    candidates, authority = load_candidates(ROOT)
    candidates = [c for c in candidates if c['mode']=='MV_MODELED_PORT']
    assert len(candidates)==606
    anchors = read(ROOT/'ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json')
    mapping = {r['location_id']:r for r in csv_rows(SELECTION/'JOINT_SERVICE_MAPPING.csv')}
    fit = read(OLD/'joint_selection_v3/geometry_first/GEOMETRY_RESULT.json')['proper_common_transform']
    assert fit['determinant']>0 and len(anchors)==24
    traffic_dir = ROOT/'ieee8500_v42/data/traffic_audit'
    policy = {'schema':'MV_RELOCATION_GEOMETRY_ONLY_V1',
        'scenario':'SEPARATE_MV_RELOCATION_ENGINEERING_PROXY_CONDITIONAL',
        'AIDC12_frozen':{s:r['candidate_bus'] for s,r in mapping.items() if r['role']=='AIDC'},
        'STA12_traffic_IDs_frozen':{s:r['traffic_node_id'] for s,r in mapping.items() if r['role']=='STA'},
        'MESS_count':6, 'service_count':24, 'candidate_count':606,
        'candidate_source_sha256':authority, 'proper_common_transform':fit,
        'pair_tolerance_km':.001, 'axis_zero_tolerance_km':.001,
        'required_pairs':276, 'required_axis_signs':552,
        'hard_conditions':['same frozen fit','12 unchanged AIDC buses','606 original source-guarded continuous ABC buses',
                           '24 distinct buses','all original traffic pair signs'],
        'static_algorithm':'full-domain bitset CSP; complete pairwise arc consistency',
        'branch_order':'MRV then fixed service identity; squared common-frame distance to old primary proxy then lexical bus',
        'stopping_rule':'first complete exact-audited witness; no global nearest-distance optimum claim',
        'node_limit':200000, 'seconds_limit':45,
        'truncated_nearest_domain':False, 'AC_or_bottleneck_sensitivity_used':False,
        'B1_B2_B3_used':False, 'Native_policy_solver_calls':0,
        'original_traffic_files_sha256':{p.name:sha(p) for p in sorted(traffic_dir.iterdir()) if p.is_file()},
        'traffic_interpretation':'same abstract service IDs and ETA assumed; electrical relocation has no surveyed physical-route correction',
        'physical_geography_access_and_actual_ETA':'UNVERIFIED', 'field_installation_PASS':False,
        'current_L0_scenario_mutated':False, 'study_final_frozen':False}
    prereg = REPORT/'MV_RELOCATION_PREREGISTRATION.json'
    write_json(prereg, policy, immutable=True)
    by_bus = {c['bus']:i for i,c in enumerate(candidates)}
    domains=[]; priorities=[]
    for anchor in anchors:
        r=mapping[anchor['location_id']]
        domain = [by_bus[r['candidate_bus']]] if anchor['role']=='AIDC' else list(range(606))
        oldpoint = transform((float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])), fit)
        domains.append(domain)
        priorities.append({j:(math.dist(oldpoint, transform((candidates[j]['x'],candidates[j]['y']),fit))**2,
                               candidates[j]['bus']) for j in domain})
    answer=bitset_csp(anchors,candidates,fit,node_limit=policy['node_limit'],seconds_limit=policy['seconds_limit'],
                      allowed_domains=domains,candidate_priorities=priorities)
    result={k:v for k,v in answer.items() if k!='selected'}
    result.update(preregistration_sha256=sha(prereg), production=False, field_geography_PASS=False,
                  physical_ETA_reverified=False, B1_B2_B3_performance_used=False,
                  scenario=policy['scenario'], AIDC12_unchanged=True)
    # A direct, exhaustive certificate when an individual STA has no candidate
    # compatible with the immutable AIDC anchors. This is stronger than merely
    # citing a CSP failure, and applies only to this frozen finite candidate set.
    fixed=[a for a in anchors if a['role']=='AIDC']
    fixed_buses={mapping[a['location_id']]['candidate_bus'] for a in fixed}
    domain_audit=[]; certificate=[]; empty=[]
    for a in [a for a in anchors if a['role']=='STA']:
        constraints=[]
        for f in fixed:
            r=mapping[f['location_id']]
            p=transform((float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])),fit)
            for axis in (0,1):
                sign=pair_sign(traffic_xy(f),traffic_xy(a),axis)
                if sign: constraints.append({'fixed_AIDC':f['location_id'],'axis':axis,'sign':sign,'boundary':p[axis]})
        accepted=[]; rejected=[]
        for c in candidates:
            p=transform((c['x'],c['y']),fit)
            failed=[q for q in constraints if q['sign']*(p[q['axis']]-q['boundary'])<=0]
            if not failed and c['bus'] not in fixed_buses: accepted.append(c['bus'])
            else:
                q=failed[0] if failed else None
                rejected.append({'STA':a['location_id'],'candidate_bus':c['bus'],
                    'candidate_source_x':c['x'],'candidate_source_y':c['y'],
                    'candidate_common_x_km':p[0],'candidate_common_y_km':p[1],
                    'rejecting_fixed_AIDC':q['fixed_AIDC'] if q else 'occupied_AIDC_bus',
                    'axis':'xy'[q['axis']] if q else 'distinct_bus',
                    'required_sign_STA_minus_AIDC':q['sign'] if q else '',
                    'fixed_AIDC_boundary_common_km':q['boundary'] if q else '',
                    'candidate_delta_common_km':p[q['axis']]-q['boundary'] if q else '',
                    'strict_axis_violation_proven':bool(q),
                    'scope':'all606 frozen source-guarded ABC candidates; same fit and fixed AIDC only'})
        bounds={}
        for axis in (0,1):
            lower=max((q for q in constraints if q['axis']==axis and q['sign']>0),
                      key=lambda q:q['boundary'],default=None)
            upper=min((q for q in constraints if q['axis']==axis and q['sign']<0),
                      key=lambda q:q['boundary'],default=None)
            for label,q in [('lower',lower),('upper',upper)]:
                bounds[f'{"xy"[axis]}_{label}_strict_km']=q['boundary'] if q else ''
                bounds[f'{"xy"[axis]}_{label}_fixed_AIDC']=q['fixed_AIDC'] if q else ''
        domain_audit.append({'STA':a['location_id'],'all_original_ABC_candidates':606,
                            'compatible_fixed_AIDC_candidate_count':len(accepted),
                            'compatible_candidate_buses':';'.join(accepted),**bounds})
        if not accepted:
            empty.append(a['location_id']); certificate.extend(rejected)
            assert len(rejected)==606
    write_csv(REPORT/'MV_RELOCATION_FIXED_AIDC_DOMAINS.csv',domain_audit)
    if empty:
        write_csv(REPORT/'MV_RELOCATION_INFEASIBILITY_CERTIFICATE.csv',certificate)
        result.update(empty_STA_domains=empty,
            finite_domain_infeasibility_certificate_sha256=sha(REPORT/'MV_RELOCATION_INFEASIBILITY_CERTIFICATE.csv'),
            certificate_scope='fixed AIDC12 + frozen proper fit + all606 verified ABC hosts; no global-transform impossibility claim',
            candidate_rejections_enumerated=len(certificate))
    if answer['feasible']:
        selected=answer['selected']; audit=audit_mapping(anchors,selected,fit)
        assert len(audit)==276 and all(r['pair_pass'] for r in audit)
        assert sum(bool(r[k]) for r in audit for k in ('expected_x_sign','expected_y_sign'))==552
        assert len({c['bus'] for c in selected.values()})==24
        output=[]
        for a in anchors:
            site=a['location_id']; c=selected[site]; r=mapping[site]
            point=transform((c['x'],c['y']),fit)
            oldpoint=transform((float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])),fit)
            output.append({'location_id':site,'role':a['role'],'traffic_node_id':a['traffic_node'],
                'retained_L0_customer_bus':r['candidate_bus'] if a['role']=='STA' else '',
                'old_source_or_proxy_bus':r['upstream_primary_bus'], 'candidate_bus':c['bus'],
                'source_x':c['x'],'source_y':c['y'],'common_frame_x_km':point[0],'common_frame_y_km':point[1],
                'traffic_x_km':a['x_east_km'],'traffic_y_km':a['y_north_km'],
                'relocation_layout_equivalent_distance_km_NOT_road_distance':math.dist(point,oldpoint),
                'traffic_anchor_error_layout_equivalent_km':math.dist(point,traffic_xy(a)),
                'root_distance_ohm':c['root_distance_ohm'],'source_ABC_host_eligible':True,
                'geometry_status':'SOURCE_LAYOUT_DIRECTION_PASS_UNVERIFIED_GEOGRAPHY',
                'interface_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED',
                'ETA_policy':'retained abstract traffic service node; physical access UNVERIFIED',
                'is_final_production_mapping':False})
        write_csv(REPORT/'MV_RELOCATION_JOINT_MAPPING.csv',output)
        write_csv(REPORT/'MV_RELOCATION_MAPPING.csv',[r for r in output if r['role']=='STA'])
        write_csv(REPORT/'MV_RELOCATION_276PAIR_AUDIT.csv',audit)
        axes=[]
        for r in audit:
            for axis in ('x','y'):
                axes.append({'location_a':r['location_a'],'location_b':r['location_b'],
                    'axis':axis,'expected_sign':r[f'expected_{axis}_sign'],
                    'actual_sign':r[f'actual_{axis}_sign'],'axis_pass':r[f'{axis}_pass'],
                    'field_geography_certified':False})
        write_csv(REPORT/'MV_RELOCATION_552AXIS_AUDIT.csv',axes)
        result.update(pairs=276,axes=552,pair_failures=0,axis_failures=0,distinct_buses=24,
            witness_sha256=sha(REPORT/'MV_RELOCATION_MAPPING.csv'),
            STA_bus_mapping={r['location_id']:r['candidate_bus'] for r in output if r['role']=='STA'})
    write_json(REPORT/'MV_RELOCATION_RESULT.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


def transformer_overlay_commands(site, primary_bus, original_nodes):
    """Unselected template: callers must separately pass source host audit gates."""
    if sorted(original_nodes)!=[1,2,3]:
        raise ValueError('Original primary bus lacks ABC; fictitious phases are forbidden')
    if not site.startswith('STA') or not primary_bus:
        raise ValueError('Explicit audited site and original bus required')
    lv=f'mess_mv_{site.lower()}_480'
    x=math.sqrt(5.75**2-1.0**2)
    # 5.75% |Z| is catalog-backed. 1% total R, losses and X/R split are research assumptions.
    return [f'new Transformer.MESS_MV_{site} phases=3 windings=2 '
        f'buses=[{primary_bus}.1.2.3 {lv}.1.2.3.0] conns=[delta wye] '
        f'kvs=[12.47 0.480] kvas=[750 750] %Rs=[0.5 0.5] XHL={x:.17g} '
        '%noloadloss=0.2 %imag=0.5 normhkva=750 emerghkva=750 '
        'wdg=1 tap=1 mintap=1 maxtap=1 wdg=2 rneut=0 xneut=0 tap=1 mintap=1 maxtap=1',
        f'new Load.MESS_MV_PORT_{site} phases=3 bus1={lv}.1.2.3.0 conn=wye kv=0.480 '
        'kw=0 kvar=0 model=1 status=fixed vminpu=0.95 vmaxpu=1.05']


def hardware_design(eligibility, relocation):
    joint=read(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_RESULT.json') if (REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_RESULT.json').exists() else {}
    vehicle={'count':6,'Pmax_kw':450,'Smax_kva':600,'Emax_kwh':1800,
             'source':'unchanged user-approved V42 research vehicle rating; no manufacturer identity certified'}
    z=5.75; total_r=1.0; x=math.sqrt(z*z-total_r*total_r)
    sources=[
        {'id':'IEEE1547','url':'https://standards.ieee.org/ieee/1547/5915/',
         'supports':'interconnection/interoperability, reactive voltage control, abnormal conditions, power quality, islanding, tests'},
        {'id':'NREL_ISLANDING_2022','url':'https://www.nrel.gov/docs/fy22osti/77782.pdf',
         'supports':'islanding requirements need coordinated protection and validation, not only steady-state AC'},
        {'id':'EATON_CA202003EN','url':'https://www.eaton.com/content/dam/eaton/products/utility-and-grid-solutions/transformer/pad-mounted-transformer/Eaton-Pad-mounted-Transformer-Brochure-EN-US.pdf',
         'supports':'catalog 750kVA and 5.75% impedance; delta-wye grounded neutral option; ±7.5% impedance tolerance'},
        {'id':'ELSCO_TX750','url':'https://elscotransformers.com/transformers/dry-type-transformers/750-kva-12470-delta-to-480y-277/',
         'supports':'commercial 750kVA 12470V delta to 480Y/277 transformer voltage/topology feasibility only'},
        {'id':'DYNAPOWER_MPS125','url':'https://dynapower.com/wp-content/uploads/2021/12/MPS-125_Datasheet_Dec2021.pdf',
         'supports':'commercial 480V three-phase 125kVA/125kW module, 150A RMS; not a certified exact mobile600kVA product'},
        {'id':'DYNAPOWER_PARALLELING','url':'https://dynapower.com/products/energy-storage/mps-125-energy-storage-inverter/',
         'supports':'manufacturer allows multiple125kW modules to be paralleled; five modules625kVA conceptual basis for600kVA limit'},
        {'id':'EPRI_NEUTRAL','url':'https://opendss.epri.com/OpenDSSNeutralRules.html',
         'supports':'explicit neutral node and grounding impedance must agree; grounded node0 is an ideal grounding assumption'},
        {'id':'EPRI_TX_PROPERTIES','url':'https://opendss.epri.com/Properties16.html',
         'supports':'3phase winding kV is line-line; XHL is reactance not impedance magnitude; losses/resistances explicit'}]
    design={'schema':'ENGINEERING_MV_DESIGN_V1','status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED',
        'vehicle':vehicle,'same_proxy_MV_eligible_STA':sum(r['same_proxy_continuous_ABC'] for r in eligibility),
        'same_proxy_MV_design':'FAIL_ALL12_SINGLE_PHASE; current L0 never receives MV output',
        'relocation_scenario_status':relocation.get('status','NOT_RUN'),
        'relocation_STA_mapping':relocation.get('STA_bus_mapping',{}),
        'relocation_geography_access_ETA':'UNVERIFIED', 'final_production_configuration_frozen':False,
        'all_proper_rotation_audit':read(REPORT/'MV_RELOCATION_ORIENTATION_RESULT.json') if (REPORT/'MV_RELOCATION_ORIENTATION_RESULT.json').exists() else 'NOT_RUN',
        'joint_AIDC_STA_reselection_diagnostic':joint,
        'joint_reselection_STA_mapping':joint.get('STA_bus_mapping',{}),
        'joint_reselection_hardware_availability':'SOURCE_GEOMETRY_CANDIDATE_ONLY_REQUIRES_NEW_AC_AND_EQUIPMENT_AUDIT' if joint.get('geometric_feasible') else 'NO_WITNESS',
        'transformer':{'kva':750,'HV_kv_LL':12.47,'LV_kv_LL':.480,'conns':['delta','grounded_wye'],
            'catalog_Z_pct':z,'R_total_pct_assumed':total_r,'winding_R_pct_assumed':[.5,.5],
            'XHL_pct_calculated_from_Z_and_assumed_R':x,'noloadloss_pct_assumed':.2,'imag_pct_assumed':.5,
            'neutral':'explicit LV .1.2.3.0, Rneut=0; ideal solid earth, electrode/protection UNVERIFIED',
            'tap':1,'automatic_taps':False,'normal_and_emergency_kva':750,
            'HV_rated_line_A':750/(math.sqrt(3)*12.47),'LV_rated_line_A':750/(math.sqrt(3)*.480)},
        'port':{'voltage_kv_LL':.480,'phases':3,'stationary_interface_Smax_kva_assumed':600,
            'commercial_topology_evidence':'five parallel125kVA480V modules625kVA demonstrate scale; exact mobile compatibility unverified',
            'actual_vehicle_PCS_manufacturer_DC_interface_temperature_derating':'UNVERIFIED',
            'current_limit_A_at_nominal_voltage':600/(math.sqrt(3)*.480),'simultaneous_vehicles_per_STA':1,
            'P_Q_coupling':'P^2+Q^2<=600^2 and mode P limit, transformer/current/voltage limits can tighten further',
            'all450kW_to_B_phase':False,'per_phase_balanced_PQ':'command total P/3,Q/3; actual AC currents/voltage may differ'},
        'safety_gates':{'powerflow_voltage_and_thermal':'requires all96realAC including new transformer and480Vnodes',
            'short_circuit':'UNVERIFIED; inverter dynamic current and relay/fuse duty/coordination data absent',
            'grounding_step_touch_and_zero_sequence':'UNVERIFIED; delta_HV isolates LV zero-sequence from HV, not certification',
            'IEEE1547_2018_type_and_commissioning_tests':'UNVERIFIED',
            'reverse_export_utility_permission_and_regulator_policy':'UNVERIFIED; default field-authorized export=0',
            'PCS_transient_inrush_harmonics_and_anti_islanding':'UNVERIFIED',
            'traffic_ETA_SOC_energy_efficiency_connection_delay':'retained V42 research inputs; physical MV relocation ETA UNVERIFIED'},
        'short_circuit_screening_only':{'LV_ideal_infinite_primary_tx_limited_3phase_A':750/(math.sqrt(3)*.480)/(.0575),
            'interpretation':'calculated nominal transformer-only screen; not actual fault result, breaking duty, or PASS'},
        'original_lines_transformers_mutated':False,'new_dedicated_transformer_count_current_L0':0,
        'new_dedicated_transformer_count_relocation_candidate':12 if relocation.get('feasible') else 0,
        'new_dedicated_transformer_count_joint_reselection_candidate':12 if joint.get('geometric_feasible') else 0,
        'sources':sources}
    rows=[]
    for mode,pmax in [('L0',5),('M1',150),('M2',300),('M3',450)]:
        mv=mode!='L0'; s=600 if mv else 6; q=math.sqrt(s*s-pmax*pmax) if mv else 3
        rows.append({'interface':mode,'vehicle_Pmax_kw':450,'vehicle_Smax_kva':600,'vehicle_Emax_kwh':1800,
            'port_P_import_export_limit_kw':pmax,'port_S_limit_kva':s,
            'abs_Q_at_Pmax_kvar':q,'independent_Q_limit_kvar':600 if mv else 3,
            'P_Q_circle_required':True,'voltage_LL_kv':.480 if mv else .240,'phase_connection':'ABC480V' if mv else 'split_phase120_240V',
            'dedicated_transformer_kva':750 if mv else 0,'original_service_transformer_changed':False,
            'dedicated_transformer_HV_kv':12.47 if mv else '', 'dedicated_transformer_Z_pct':z if mv else '',
            'dedicated_transformer_XHL_pct':x if mv else '',
            'port_current_A_at_Smax_nominal':s/(math.sqrt(3)*.480) if mv else 27,
            'full_P_per_phase_kw':pmax/3 if mv else '', 'simultaneous_MESS_per_STA':1,
            'same_proxy_eligible_ports':0 if mv else 12,
            'separate_relocation_candidate_ports':12 if mv and relocation.get('feasible') else 0,
            'separate_joint_AIDC_STA_geometry_candidate_ports':12 if mv and joint.get('geometric_feasible') else 0,
            'physical_export_permission':'UNVERIFIED_FIELD_EXPORT0', 'field_protection_GIS_certified':False,
            'status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED' if mv else 'EXISTING_RESEARCH_L0_INTERFACE'})
    write_csv(REPORT/'MESS_PORT_TRANSFORMER_RATINGS.csv',rows)
    write_json(REPORT/'ENGINEERING_MV_DESIGN.json',design)
    return design


def source_evidence(design):
    """Retain exact consulted public-primary pages/PDFs and byte checksums."""
    import concurrent.futures
    import urllib.request
    folder=REPORT/'mv_sources'; folder.mkdir(exist_ok=True)
    def fetch(source):
        result={'id':source['id'],'url':source['url'],'supports':source['supports']}
        try:
            request=urllib.request.Request(source['url'],headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(request,timeout=20) as response:
                data=response.read(); final_url=response.geturl()
            assert len(data)>500
            suffix='.pdf' if data.startswith(b'%PDF') else '.html'
            path=folder/(source['id']+suffix); path.write_bytes(data)
            result.update(status='RETAINED',final_url=final_url,bytes=len(data),
                          relative_path=path.relative_to(ROOT).as_posix(),sha256=sha(path))
        except Exception as error:
            result.update(status='FETCH_UNVERIFIED',error_type=type(error).__name__)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(fetch,design['sources']))
    write_json(REPORT/'MV_SOURCE_EVIDENCE.json',{'sources':records,'retrieval_date_KST':'2026-10-10',
        'source_type':'manufacturer/EPRI/IEEE/NREL public-primary; no field hardware certification'})
    return records


def retain_web_source_facts():
    """Retain reviewed primary-web facts when direct byte download is blocked.

    These are extraction/checksum receipts, not hashes of unavailable originals.
    The source URLs were separately opened/read using the primary web tool.
    """
    facts=[
        {'source_id':'IEEE1547','source_url':'https://standards.ieee.org/ieee/1547/5915/',
         'reviewed_fact':'IEEE1547-2018 covers DER connection/interoperability, reactive voltage control, abnormal conditions, power quality, islanding and test requirements.'},
        {'source_id':'NREL_ISLANDING_2022','source_url':'https://research-hub.nlr.gov/en/publications/a-primer-on-the-unintentional-islanding-protection-requirement-in/',
         'reviewed_fact':'Narang/Gonzalez/Ingram2022, NREL/TP-5D00-77782, explains unintentional islanding requirements of IEEE1547; not site-specific certification.'},
        {'source_id':'EATON_CA202003EN','source_url':'https://www.eaton.com/content/dam/eaton/products/utility-and-grid-solutions/transformer/pad-mounted-transformer/Eaton-Pad-mounted-Transformer-Brochure-EN-US.pdf',
         'reviewed_fact':'Table2 includes750kVA. Table3 specifies5.75% impedance for750–2500kVA and standard±7.5% tolerance. Delta-wye LV neutral has removable ground strap.'},
        {'source_id':'ELSCO_TX750','source_url':'https://elscotransformers.com/transformers/dry-type-transformers/750-kva-12470-delta-to-480y-277/',
         'reviewed_fact':'Manufacturer product lists750kVA,12470V delta primary,480Y/277V secondary. No this-study purchased unit or test report established.'},
        {'source_id':'DYNAPOWER_MPS125','source_url':'https://dynapower.com/wp-content/uploads/2021/12/MPS-125_Datasheet_Dec2021.pdf',
         'reviewed_fact':'Manufacturer datasheet lists480VAC three-phase,125kVA,125kW,150A RMS,60Hz and power factor leading/lagging0–1. Exact vehicle600kVA manufacturer unspecified.'},
        {'source_id':'DYNAPOWER_PARALLELING','source_url':'https://dynapower.com/products/energy-storage/mps-125-energy-storage-inverter/',
         'reviewed_fact':'Manufacturer describes125kW modular inverter and allows parallel units. Five-unit625kVA600kVA-limit concept is an engineering inference, not an installed assembly.'},
        {'source_id':'EPRI_NEUTRAL','source_url':'https://opendss.epri.com/OpenDSSNeutralRules.html',
         'reviewed_fact':'OpenDSS neutral rules distinguish explicit node0 grounds and implicit neutral impedance. This design models ideal solid LV grounding without field electrode tests.'},
        {'source_id':'EPRI_TX_PROPERTIES','source_url':'https://opendss.epri.com/Properties16.html',
         'reviewed_fact':'Three-phase transformer kV uses line-line values. XHL specifies reactance, so magnitude5.75% requires assumedR split and calculatedXHL.'}]
    write_json(REPORT/'MV_PRIMARY_WEB_FACTS.json',{'source_review_date_KST':'2026-10-10','facts':facts,
        'sha_scope':'saved reviewed extraction only; direct raw byte fetch status and original byte SHA are separate in MV_SOURCE_EVIDENCE.json',
        'field_certification':False})
    proof=read(REPORT/'MV_SOURCE_EVIDENCE.json') if (REPORT/'MV_SOURCE_EVIDENCE.json').exists() else {'sources':[]}
    proof['primary_web_fact_extraction']={'relative_path':(REPORT/'MV_PRIMARY_WEB_FACTS.json').relative_to(ROOT).as_posix(),
        'sha256':sha(REPORT/'MV_PRIMARY_WEB_FACTS.json'),'scope':'reviewed extraction, NOT original full source byte SHA'}
    write_json(REPORT/'MV_SOURCE_EVIDENCE.json',proof)


def component_regression():
    """Tiny isolated component test, not an IEEE8500 MV siting/eligibility test."""
    import numpy as np
    rejected=False
    try: transformer_overlay_commands('STA01','single_phase_proxy',[2])
    except ValueError: rejected=True
    assert rejected
    d=odd.NewContext()
    for method in ('AllowChangeDir','AllowForms','AllowEditor','AllowDOScmd'):
        getattr(d.Basic,method)(False)
    d.Text.Command('new Circuit.MV_COMPONENT_ONLY bus1=unit_primary.1.2.3 basekv=12.47 pu=1 '
                   'frequency=60 r1=0 x1=0.001 r0=0 x0=0.001')
    commands=transformer_overlay_commands('STA_TEST','unit_primary',[1,2,3])
    for command in commands:d.Text.Command(command)
    d.Text.Command('set voltagebases=[12.47 0.480]')
    d.Text.Command('calcvoltagebases')
    d.Text.Command('set controlmode=off maxiterations=100 tolerance=1e-10')
    # The component curve is inspected at import/export and both Q signs.
    cases=[]
    for mode,pmax in [('M1',150.),('M2',300.),('M3',450.)]:
        qmax=math.sqrt(600**2-pmax**2)
        for p,q in [(pmax,0.),(-pmax,0.),(pmax,qmax),(-pmax,-qmax)]:
            d.Loads.Name('MESS_MV_PORT_STA_TEST'); d.Loads.kW(p);d.Loads.kvar(q)
            d.Solution.Solve(); assert d.Solution.Converged()
            actual=np.asarray(d.CktElement.Powers()).reshape(-1,2)
            currents=np.asarray(d.CktElement.CurrentsMagAng()).reshape(-1,2)[:3,0]
            assert np.max(np.abs(actual[:3]-np.array([p,q])/3))<1e-5
            d.Transformers.Name('MESS_MV_STA_TEST')
            txp=np.asarray(d.CktElement.Powers()).reshape(2,4,2)
            loss=txp.sum((0,1))
            assert loss[0]>0
            assert abs(math.hypot(p,q))<=600+1e-10
            assert float(d.Properties.Value('%noloadloss'))==.2
            assert float(d.Properties.Value('%imag'))==.5
            assert float(d.Properties.Value('normhkva'))==750
            cases.append({'mode':mode,'P_consumption_positive_kw':p,'Q_consumption_positive_kvar':q,
                'apparent_kva':math.hypot(p,q),'three_phase_total_readback_error':float(np.max(np.abs(actual.sum(0)-np.array([p,q])))),
                'maximum_actual_LV_line_A':float(currents.max()),'transformer_real_loss_kw':float(loss[0]),
                'port_line_current_limit_A':600/(math.sqrt(3)*.480),
                'all_port_phase_current_limits_pass':bool(currents.max()<=600/(math.sqrt(3)*.480)+1e-7),
                'all_actual_per_phase_PQ_match_one_third_command':True})
    receipt={'schema':'ISOLATED_MV_COMPONENT_REGRESSION','single_phase_fake_ABC_rejected':True,
        'cases':cases,'case_count':len(cases),'PASS':True,
        'PASS_definition':'equivalent circuit parameter/readback regression only; no field or host physical PASS',
        'all_unit_endpoints_port_current_PASS':all(r['all_port_phase_current_limits_pass'] for r in cases),
        'scope':'one isolated stiff-source unit component, no eligible current IEEE8500 STA MV host and no selected relocation',
        'IEEE8500_case_MV_eligibility_PASS':False,'short_circuit_protection_field_PASS':False}
    write_json(REPORT/'MV_COMPONENT_REGRESSION.json',receipt)
    return receipt


def write_design_document(design):
    full=design.get('all_proper_rotation_audit',{})
    if isinstance(full,dict) and full.get('complete_all_allowed_rotation_domain_infeasibility'):
        angular='고정 AIDC 12곳의 132개 축 조건을 만족하는 전체 공통 회전은 191.3192150747514°–191.82333172004934°의 열린 구간뿐이다. '
        angular+='이 구간 전체에서도 STA01·STA02·STA05·STA06·STA07·STA10의 적격 MV 후보 수는 각각 0이다. '
        angular+='원본 십진 좌표를 유리수로 계산한 전 각도 후보 구간 증명으로, 현재 AIDC 고정과 606개 후보 집합에서 공동 MV 재배치는 불가능하다. '
        angular+='AIDC 재선정이나 새로운 Primary 배선을 포함한 다른 문제의 불가능성을 주장하지 않는다.'
    else:angular='공통 회전 전역 감사 상태는 별도 MV_RELOCATION_ORIENTATION_RESULT.json을 참조한다.'
    text=f'''# MESS 중압 연계 설계와 실제 후보 적격성

현재 STA 12곳의 고객 측 120/240 V 포트는 보존한다. 같은 위치 Proxy의 상위 Primary 버스는 모두 단상이다. **동일 Proxy에 M1/M2/M3를 설치할 수 있는 적격 3상 호스트는 0곳**이다. `.1.2.3`를 붙여 누락된 상을 만들거나 450 kW를 기존 Triplex에 주입하지 않았다.

별도 위치 변경 시나리오를 사전등록해, AIDC 12곳을 고정하고 source proximity guard를 통과한 원본 606개 12.47 kV ABC 버스를 검토했다. 선정 순서는 기존 Proxy와의 형상 거리이며 AC 민감도·병목선로·정책 성능을 사용하지 않았다. 기존 프레임에서는 STA01·02·05·06·07·10의 후보가 없고 3,636개 거절 증거를 출력했다. {angular}

따라서 아래 M1–M3는 **UNAVAILABLE_AT_CURRENT_STA_AND_FIXED_AIDC_GEOMETRY**인 기술 설계 후보다. 현재 IEEE8500에 새 변압기를 설치한 적격 시나리오라고 표현하지 않는다. 실제 추가 변압기는 0개다. L0만 기존 연구 포트에서 실행할 수 있다.

| 인터페이스 | 차량당 P 한도 | 차량/설계 포트 S 한도 | P 한도에서 Q 원 상한 | 연결 |
|---|---:|---:|---:|---|
| L0 | ±5 kW | 포트 6 kVA | 별도 ±3 kvar | 기존 120/240 V, hot 전류 27 A |
| M1 | ±150 kW | 600 kVA | 580.947502 kvar | 적격 ABC Primary → 전용 변압기 → 480 V 3상 |
| M2 | ±300 kW | 600 kVA | 519.615242 kvar | 같은 구조 |
| M3 | ±450 kW | 600 kVA | 396.862697 kvar | 같은 구조 |

차량은 6대·450 kW·600 kVA·1,800 kWh를 유지한다. P²+Q²≤S²를 항상 적용하고, 현장 포트/변압기/도체/전압/SOC/ETA 제약은 추가로 출력을 줄일 수 있다. Q를 원 한계까지 쓸 수 있다는 표는 기술적 산술 상한이며 계통 허용 판정이 아니다. 각 STA 동시 접속은 1대로 가정한다. 3상 명령 P/Q는 총량의 1/3씩이며, 실제 전류는 불평형 전압과 변압기 손실을 포함한 AC로 읽어야 한다. 450 kW 전부를 B상에 넣지 않는다.

가정한 전용 변압기는 750 kVA, 12.47 kV delta / 480Y/277 V이며 tap=1 고정이다. [ELSCO의 750 kVA 상품](https://elscotransformers.com/transformers/dry-type-transformers/750-kva-12470-delta-to-480y-277/)은 이 전압과 결선 조합의 상용 가능성을 뒷받침한다. 이는 실제 특정 STA의 승인 또는 납품 자료가 아니다. [Eaton CA202003EN](https://www.eaton.com/content/dam/eaton/products/utility-and-grid-solutions/transformer/pad-mounted-transformer/Eaton-Pad-mounted-Transformer-Brochure-EN-US.pdf)은 750 kVA 및 5.75% 임피던스와 delta–wye 중성점 접지 구성을 명시한다. 이 두 상품의 사양을 단일 구매품 인증으로 합치지 않았다.

연구 모델의 |Z|=5.75%는 위 카탈로그 범위로 정하고, 총 R=1.0%를 두 권선 0.5%씩 나누는 것은 **미실측 설계 가정**이다. 따라서 XHL=√(5.75²−1²)={design['transformer']['XHL_pct_calculated_from_Z_and_assumed_R']:.12f}%로 계산한다. XHL에 |Z|를 그대로 대입하지 않는다. 무부하손실 0.2%·여자전류 0.5%도 가정이며 구매품 시험성적서가 없다. 두 권선 정격 및 Normal/Emergency kVA는 750으로 동일하다. 750 kVA 정격 전류는 HV {design['transformer']['HV_rated_line_A']:.6f} A, LV {design['transformer']['LV_rated_line_A']:.6f} A이다. [EPRI Transformer Properties](https://opendss.epri.com/Properties16.html)의 3상 LL 전압·권선 R·XHL 정의를 적용했다.

480 V 600 kVA 포트의 명목 전류는 {design['port']['current_limit_A_at_nominal_voltage']:.6f} A이다. [Dynapower MPS-125 자료](https://dynapower.com/wp-content/uploads/2021/12/MPS-125_Datasheet_Dec2021.pdf)는 480 V 3상 125 kVA/125 kW 모듈을 제시하며 [제조사 제품 설명](https://dynapower.com/products/energy-storage/mps-125-energy-storage-inverter/)은 병렬 구성을 허용한다. 5개 모듈 625 kVA에서 600 kVA로 제한하는 구성은 규모의 근거가 될 수 있지만, 차량에 이 PCS가 설치됐다는 주장이나 정확한 600 kVA 이동형 제품 인증이 아니다. 차량 DC 전압·커넥터·온도 디레이팅·배터리 호환성은 UNVERIFIED다. 최고효율을 96슬롯 충방전 효율로 대신하지 않고 기존 V42 효율을 보존한다.

모델은 LV `.1.2.3.0`, Rneut=0인 이상적 고정 접지를 사용한다. HV delta는 LV 영영상 전류를 HV 선로로 전달하지 않는 결선 선택이며 현장 접지 인증이 아니다. [EPRI Neutral Rules](https://opendss.epri.com/OpenDSSNeutralRules.html)에 따라 중성점과 접지 임피던스를 명시했다. 접지전극, 접촉/보폭전압, 단선 및 지락 동작은 검증되지 않았다.

[IEEE 1547-2018](https://standards.ieee.org/ieee/1547/5915/)의 전압/무효전력, 비정상 전압·주파수, 전력품질, 단독운전, 상호운용과 시험 요구를 검토 대상으로 둔다. [NREL의 단독운전 보호 해설](https://www.nrel.gov/docs/fy22osti/77782.pdf)에 근거해 정적 AC 통과를 anti-islanding/보호 적격성으로 승격하지 않는다. 현장 릴레이·퓨즈·recloser 협조, 변압기 여자돌입, 고장시 PCS 전류와 지속시간, 차단용량, 원격 차단, utility export 승인 및 IEEE 1547.1 시험 자료가 없다. 모두 **UNVERIFIED**, 설계 상태는 **ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED**다. 현장 승인된 역송전 한도는 입증된 값이 없어 0으로 둔다. 연구 반사실의 양방향 P/Q 허용 가정은 이와 구분한다.

변압기와 무한대 강도 HV 전원을 가정한 LV 3상 단락 전류 산술 화면은 {design['short_circuit_screening_only']['LV_ideal_infinite_primary_tx_limited_3phase_A']:.6f} A다. 이는 실제 계통 단락해석, PCS 기여, 차단 duty 또는 PASS 증거가 아니다. 현재 3상 호스트 자체가 없으므로 이 숫자로 사이트 적격성을 판정하지 않는다.

교통 노드 24개, MESS 6대, 기존 도로·ETA·거리·연결 지연 파일의 SHA를 MV_RELOCATION_PREREGISTRATION.json에 봉인했다. 새로운 MV 위치의 형상 거리로 도로 거리를 환산하지 않았다. 위치 변경 시 실제 ETA·이동에너지·현장 접근성 재검증은 UNVERIFIED이며, 기존 서비스 노드 ETA를 쓰는 것은 추상 연구 Proxy 가정에 한정한다.

재현: `python -B -m ieee8500_v42_high.mv_design --relocate` 다음 `python -B -m ieee8500_v42_high.mv_relocation`. 단상 거절·P/Q 원 한도·전용 변압기·3상 전력 readback은 MV_COMPONENT_REGRESSION.json의 별도 작은 구성요소 회귀로 검증한다. 이것은 실제 IEEE8500 MV 접속 입지 또는 96슬롯 운전 적격성 증거가 아니다. 기존 원본 선로 3,703개·Triplex 1,177개·변압기 1,190개와 DSS 31개는 변경하지 않았다.

구성요소 AC에서 P=150 kW/Q=580.947502 kvar인 600 kVA 충전 명령의 실제 LV 전류는 약 758.47 A였다. 480 V/600 kVA의 명목 전류 한도 721.687836 A를 초과하므로 이 끝점은 포트 전류 FAIL이다. S 원 제약만으로 저전압에서의 전류 제한이 보장되지 않으며, 향후 MV 포트 구현에서는 상별 실제 전압·전류에 따른 추가 디레이팅이 필요하다. MV_COMPONENT_REGRESSION의 PASS는 파라미터와 상별 전력 readback 검사만을 뜻하고 모든 끝점의 물리적 PASS가 아니다.

출처 원문 바이트를 보존한 자료는 mv_sources와 MV_SOURCE_EVIDENCE.json에 SHA를 기록했다. 서버 오류로 원문 바이트를 내려받지 못한 자료는 FETCH_UNVERIFIED로 표시했으며, 별도 Primary 웹 도구로 읽은 근거 추출은 MV_PRIMARY_WEB_FACTS.json에 보존했다. 이 추출 SHA를 내려받지 못한 원문 전체의 SHA라고 주장하지 않는다.
'''
    (REPORT/'MESS_MV_INTERFACE_DESIGN.md').write_text(text,encoding='utf-8')
    joint=design.get('joint_AIDC_STA_reselection_diagnostic',{})
    if joint.get('geometric_feasible'):
        with (REPORT/'MESS_MV_INTERFACE_DESIGN.md').open('a',encoding='utf-8') as handle:
            handle.write('''
## 별도 AIDC–STA 공동 재선정 진단의 추가 결과

위 불가능 판정과 M1–M3 UNAVAILABLE은 **기존 AIDC 12개 버스를 고정한 문제**에 한정한다. 이후 사용자 지시에 따른 별도 공동 형상 진단에서는 AIDC 고정을 해제하되 v3 전기 적격성·source guard·원본 606개 ABC 후보·24개 서비스 ID·276쌍 방향을 유지했다. 사전등록한 135° 공통 회전에서 24개 모두 MV인 witness를 확보했으며 276쌍/552축이 모두 PASS다. AIDC 10곳이 변경됐다. 기존 저압 및 기존 P5 결과는 별도 보존된다.

JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv의 STA 12곳은 전용 변압기 연구 설계를 검토할 수 있는 **별도 원본 MV 호스트 후보**다. Master.dss Fresh compile의 ABC/12.47kV/원본 좌표와 source guard는 JOINT_MV_HOST_SOURCE_AUDIT.csv에서 확인했다. 이것을 M1–M3 설비 또는 96슬롯 운전 적격성 PASS로 승격하지 않았다. 향후 새 연구 overlay에 전용 변압기 12개를 설치하는 경우 원본 1,190개와 명확히 구분해 각 신규 권선·480V 노드·PCS 상전류·전력 손실을 다시 AC로 검증해야 한다.

공동 진단은 AC 효과를 읽지 않은 형상 우선 결과다. 실제 GIS·접근성·물리 ETA·단락/보호·현장 접속 승인과 exact600kVA 차량 하드웨어 호환성은 계속 UNVERIFIED다. 최종 Production 또는 단일 운전 시나리오를 동결하지 않았다.
''')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--relocate',action='store_true')
    parser.add_argument('--sources',action='store_true'); parser.add_argument('--component-test',action='store_true'); args=parser.parse_args()
    REPORT.mkdir(parents=True,exist_ok=True)
    eligibility, source = original_bus_audit()
    relocation=relocate_geometry() if args.relocate else read(REPORT/'MV_RELOCATION_RESULT.json') if (REPORT/'MV_RELOCATION_RESULT.json').exists() else {}
    design=hardware_design(eligibility,relocation)
    write_design_document(design)
    if args.sources:source_evidence(design)
    retain_web_source_facts()
    if args.component_test:component_regression()
    print(json.dumps({'same_proxy_MV_eligible':sum(r['same_proxy_continuous_ABC'] for r in eligibility),
                      'source_preserved':True,'original_DSS_count':len(source)}),flush=True)


if __name__=='__main__': main()
