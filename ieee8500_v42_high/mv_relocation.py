"""Exact rational common-rotation domain audit for fixed12 AIDC and606 MV hosts.

For cos(theta) nonzero use t=tan(theta) and its sign c in {+1,-1}.
Every required direction is a strict linear inequality in t with coefficients
from original decimal coordinates. This covers the full proper-rotation circle,
including a separate check of the two cos(theta)=0 orientations. No AC outcomes
are used. Source coordinates remain layout coordinates with unverified CRS.
"""
from __future__ import annotations

import itertools
import json
import math
from fractions import Fraction

from ieee8500_v42.geometry import pair_sign, traffic_xy
from ieee8500_v42.joint_geometry import audit_mapping, bitset_csp
from .mv_design import (ROOT, OLD, SELECTION, REPORT, read, csv_rows, write_json,
                        write_csv, sha, load_candidates, transform, FEEDER)


def rational_text(value):
    return '' if value is None else f'{value.numerator}/{value.denominator}'


def interval_constraints(constraints, lower=None, upper=None):
    """Return the exact open interval for a*t+b>0, with binding row IDs."""
    lower_id=''; upper_id=''
    for a,b,name in constraints:
        if a==0:
            if b<=0: return None, None, name, name, False
            continue
        root=-b/a
        if a>0 and (lower is None or root>lower): lower=root; lower_id=name
        if a<0 and (upper is None or root<upper): upper=root; upper_id=name
        if lower is not None and upper is not None and lower>=upper:
            return lower,upper,lower_id,upper_id,False
    return lower,upper,lower_id,upper_id,True


def directions(dx,dy,expected_x,expected_y,c,identifier):
    result=[]
    if expected_x: result.append((-c*expected_x*dy,c*expected_x*dx,identifier+':x'))
    if expected_y: result.append((c*expected_y*dx,c*expected_y*dy,identifier+':y'))
    return result


def complete_orientation_audit():
    candidates,authority=load_candidates(ROOT)
    candidates=[c for c in candidates if c['mode']=='MV_MODELED_PORT']
    raw={r['dss_bus']:r for r in csv_rows(OLD/'MV_AIDC_CANDIDATES.csv')}
    coord={c['bus']:(Fraction(raw[c['bus']]['x']),Fraction(raw[c['bus']]['y'])) for c in candidates}
    anchors=read(ROOT/'ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json')
    fixed=[a for a in anchors if a['role']=='AIDC']; mobile=[a for a in anchors if a['role']=='STA']
    mapping={r['location_id']:r for r in csv_rows(SELECTION/'JOINT_SERVICE_MAPPING.csv')}
    fixed_bus={a['location_id']:mapping[a['location_id']]['candidate_bus'] for a in fixed}
    occupied=set(fixed_bus.values())
    originalfit=read(REPORT/'MV_RELOCATION_PREREGISTRATION.json')['proper_common_transform']
    policy={'schema':'MV_RELOCATION_FULL_PROPER_ROTATION_AUDIT_V1',
        'scope':'separate MV relocation; original12 AIDC physical buses fixed; full common proper rotation circle',
        'all_source_guarded_MV_candidates':606,'candidate_source_sha256':authority,
        'AIDC_fixed_bus_mapping':fixed_bus,'original_fit':originalfit,
        'positive_uniform_scale_frozen':originalfit['uniform_scale'],
        'common_translation_policy':'hold original source centroid and common target centroid fixed for each global rotation',
        'traffic_axis_zero_tolerance_km':.001,'traffic_pair_distance_tolerance_km':.001,
        'source_axis_inequality':'strict >0, exactly as prior joint pair audit; no invented source spacing',
        'rotation_certificate':'decimal source XY converted to exact rational coefficients; t=tan(theta), cos sign ±1; strict linear intervals',
        'circle_coverage':['cos positive semicircle','cos negative semicircle','theta90deg','theta270deg'],
        'relocation_branch_priority':'squared common-frame distance to original STA primary proxy then lexical bus',
        'AC_or_B1_B2_B3_or_bottleneck_ranking_used':False,'Native_calls':0,
        'if_joint_assignment_search_needed':'all606 CSP on preregistered increasing slope-cell midpoints; percell45sec/200000nodes',
        'geography_access_and_physical_ETA':'UNVERIFIED engineering proxy only',
        'preserve_prior_frozen_orientation_failure':True,'Production_final_mapping_frozen':False}
    prereg=REPORT/'MV_RELOCATION_ORIENTATION_PREREGISTRATION.json'
    write_json(prereg,policy,immutable=True)
    results=[]; candidate_rows=[]; circle_cells=[]; aa_rows=[]; winner=None
    for c in (1,-1):
        constraints=[]
        for a,b in itertools.combinations(fixed,2):
            pa,pb=coord[fixed_bus[a['location_id']]],coord[fixed_bus[b['location_id']]]
            dx,dy=pb[0]-pa[0],pb[1]-pa[1]
            expected=[pair_sign(traffic_xy(a),traffic_xy(b),k) for k in (0,1)]
            constraints.extend(directions(dx,dy,*expected,c,a['location_id']+'->'+b['location_id']))
        assert len(constraints)==132
        lower,upper,lid,uid,feasible=interval_constraints(constraints)
        for a,b,name in constraints:
            aa_rows.append({'cos_sign':c,'fixed_AIDC_axis_relation':name,
                            'a_t_coefficient_exact':rational_text(a),'b_constant_exact':rational_text(b),
                            'strict_relation':'a*t+b>0','root_exact':rational_text(-b/a) if a else ''})
        info={'cos_sign':c,'AA132_orientation_feasible':feasible,
              't_lower_open_exact':rational_text(lower),'t_upper_open_exact':rational_text(upper),
              'lower_binding_AIDC_axis':lid,'upper_binding_AIDC_axis':uid}
        if not feasible:
            results.append(info); continue
        assert lower is not None and upper is not None, 'Expected bounded original AIDC rotation interval'
        offset=0 if c==1 else 180
        info.update(theta_lower_degrees=math.degrees(math.atan(float(lower)))+offset,
                    theta_upper_degrees=math.degrees(math.atan(float(upper)))+offset)
        allowed={}; endpoints={lower,upper}
        for a in mobile:
            ranges=[]
            for candidate in candidates:
                bus=candidate['bus']; cons=[]
                for f in fixed:
                    pa,pb=coord[fixed_bus[f['location_id']]],coord[bus]
                    dx,dy=pb[0]-pa[0],pb[1]-pa[1]
                    expected=[pair_sign(traffic_xy(f),traffic_xy(a),k) for k in (0,1)]
                    cons.extend(directions(dx,dy,*expected,c,f['location_id']+'->'+a['location_id']))
                lo,hi,li,ui,ok=interval_constraints(cons,lower,upper)
                ok=ok and bus not in occupied
                candidate_rows.append({'cos_sign':c,'STA':a['location_id'],'candidate_bus':bus,
                    'fixed_AIDC_compatible_at_any_allowed_rotation':ok,
                    't_lower_open_exact':rational_text(lo),'t_upper_open_exact':rational_text(hi),
                    'lower_binding_relation':li,'upper_binding_relation':ui,
                    'excluded_already_occupied_AIDC_bus':bus in occupied,
                    'all606_candidates_enumerated':True})
                if ok:
                    ranges.append((lo,hi,bus)); endpoints.add(lo); endpoints.add(hi)
            allowed[a['location_id']]=ranges
        ordered=sorted(endpoints); potential=[]
        for k,(lo,hi) in enumerate(zip(ordered,ordered[1:])):
            mid=(lo+hi)/2
            domains={s:[bus for l,u,bus in intervals if l<mid<u] for s,intervals in allowed.items()}
            empty=[s for s,domain in domains.items() if not domain]
            row={'cos_sign':c,'slope_cell':k,'lower_open_exact':rational_text(lo),
                 'upper_open_exact':rational_text(hi),'mid_exact':rational_text(mid),
                 'empty_STA_domains':';'.join(empty),'fixed_AIDC_domain_feasible':not empty,
                 'boundary_argument':'strict inequalities at root cannot create a candidate absent in both adjacent open cells',
                 **{s+'_domain_count':len(domains[s]) for s in sorted(domains)}}
            circle_cells.append(row)
            if not empty: potential.append((mid,domains))
        info.update(slope_cells=len(ordered)-1,potential_complete_STA_domain_cells=len(potential),
                    per_STA_candidate_count_any_angle={s:len(v) for s,v in allowed.items()})
        if potential:
            center_policy=read(OLD/'joint_selection_v3/geometry_first/GEOMETRY_PREREGISTRATION.json')
            sc=center_policy['common_source_center']; tc=center_policy['common_target_center']
            by_bus={candidate['bus']:j for j,candidate in enumerate(candidates)}
            for mid,domains in potential:
                angle=math.atan(float(mid))+(math.pi if c<0 else 0)
                scale=originalfit['uniform_scale']; u=scale*math.cos(angle); v=scale*math.sin(angle)
                fit={'u':u,'v':v,'translation_x':tc[0]-u*sc[0]+v*sc[1],
                     'translation_y':tc[1]-v*sc[0]-u*sc[1],'rotation_degrees':math.degrees(angle),
                     'uniform_scale':scale,'determinant':u*u+v*v}
                domainlist=[]; priority=[]
                for a in anchors:
                    r=mapping[a['location_id']]
                    domain=[by_bus[r['candidate_bus']]] if a['role']=='AIDC' else [by_bus[b] for b in domains[a['location_id']]]
                    oldpoint=transform((float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])),fit)
                    domainlist.append(domain)
                    priority.append({j:(math.dist(oldpoint,transform((candidates[j]['x'],candidates[j]['y']),fit))**2,
                                          candidates[j]['bus']) for j in domain})
                ans=bitset_csp(anchors,candidates,fit,200000,45,domainlist,priority)
                if ans['feasible']:
                    winner={'selected':ans['selected'],'fit':fit,'slope_exact':rational_text(mid),
                            'cos_sign':c,'algorithm':{k:v for k,v in ans.items() if k!='selected'}}
                    break
            info['joint_search_completeness']='MIDPOINTS_ONLY; candidate-candidate ordering roots not exhaustively partitioned'
        results.append(info)
        if winner: break
    vertical=[]
    for sine in (1,-1):
        failing=[]
        for a,b in itertools.combinations(fixed,2):
            pa,pb=coord[fixed_bus[a['location_id']]],coord[fixed_bus[b['location_id']]]
            dx,dy=pb[0]-pa[0],pb[1]-pa[1]
            expected=[pair_sign(traffic_xy(a),traffic_xy(b),k) for k in (0,1)]
            for axis,delta in enumerate((-sine*dy,sine*dx)):
                if expected[axis]*delta<=0: failing.append(a['location_id']+'->'+b['location_id']+':'+ 'xy'[axis])
        vertical.append({'theta_degrees':90 if sine==1 else 270,'AA_axis_failures':len(failing),
                         'first_failing_AA_axis':failing[0] if failing else '', 'orientation_allowed':not failing})
    write_csv(REPORT/'MV_RELOCATION_AA132_ROTATION_CONSTRAINTS.csv',aa_rows)
    if candidate_rows:write_csv(REPORT/'MV_RELOCATION_ALLANGLE_CANDIDATE_INTERVALS.csv',candidate_rows)
    if circle_cells:write_csv(REPORT/'MV_RELOCATION_ALLANGLE_DOMAIN_CELLS.csv',circle_cells)
    simple_infeasible=all(not r['AA132_orientation_feasible'] or r['potential_complete_STA_domain_cells']==0 for r in results) and not any(r['orientation_allowed'] for r in vertical)
    result={'schema':'MV_RELOCATION_ALL_PROPER_ROTATION_RESULT_V1',
        'preregistration_sha256':sha(prereg),'finite_source_guarded_domain':606,'AIDC_buses_fixed':fixed_bus,
        'semicircle_results':results,'vertical_orientations':vertical,
        'feasible':bool(winner),'complete_all_allowed_rotation_domain_infeasibility':simple_infeasible,
        'status':'FEASIBLE_GEOMETRIC_ENGINEERING_WITNESS' if winner else 'INFEASIBLE_ALL_COMMON_PROPER_ROTATIONS_FIXED_AIDC606' if simple_infeasible else 'LIMITED_ORIENTATION_JOINT_SEARCH_NO_WITNESS',
        'certificate_scope':'fixed12 AIDC and606 guarded original ABC hosts; all positive uniform scales/translations preserve direction; physical relocation/access not certified',
        'global_arbitrary_AIDC_reselection_or_new_primary_line_infeasibility_claim':False,
        'certificate_arithmetic':'exact rational decimal XY and linear strict slope inequalities; displayed degrees are approximations',
        'field_GIS_protection_ETA':'UNVERIFIED','AC_result_or_bottleneck_used_for_relocation':False,
        'all_original_source_or_mapping_files_changed':False}
    if winner:
        selected=winner['selected']; fit=winner['fit']; audit=audit_mapping(anchors,selected,fit)
        output=[]
        for a in anchors:
            site=a['location_id']; candidate=selected[site]; r=mapping[site]
            p=transform((candidate['x'],candidate['y']),fit)
            oldp=transform((float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])),fit)
            output.append({'location_id':site,'role':a['role'],'traffic_node_id':a['traffic_node'],
                'retained_L0_customer_bus':r['candidate_bus'] if a['role']=='STA' else '',
                'old_source_or_proxy_bus':r['upstream_primary_bus'],'candidate_bus':candidate['bus'],
                'source_x':candidate['x'],'source_y':candidate['y'],'common_frame_x_km':p[0],'common_frame_y_km':p[1],
                'traffic_x_km':a['x_east_km'],'traffic_y_km':a['y_north_km'],
                'relocation_layout_equivalent_distance_km_NOT_road_distance':math.dist(p,oldp),
                'root_distance_ohm':candidate['root_distance_ohm'],'source_ABC_host_eligible':True,
                'status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED','physical_ETA':'UNVERIFIED','final_production_mapping':False})
        write_csv(REPORT/'MV_RELOCATION_ALTERNATE_ORIENTATION_MAPPING.csv',output)
        write_csv(REPORT/'MV_RELOCATION_ALTERNATE_276PAIR_AUDIT.csv',audit)
        assert len(audit)==276 and all(r['pair_pass'] for r in audit)
        result.update(proper_common_transform=fit,slope_exact=winner['slope_exact'],cos_sign=winner['cos_sign'],
                      STA_bus_mapping={r['location_id']:r['candidate_bus'] for r in output if r['role']=='STA'},
                      pair_passes=276,axis_passes=552,distinct_buses=24,
                      witness_sha256=sha(REPORT/'MV_RELOCATION_ALTERNATE_ORIENTATION_MAPPING.csv'))
    write_json(REPORT/'MV_RELOCATION_ORIENTATION_RESULT.json',result)
    return result


def joint_unfixed_geometry_diagnostic():
    """Separate joint24 MV diagnostic, explicitly releasing fixed AIDC buses.

    Full-domain deterministic CSP with old-position distance branch priority;
    no global displacement optimality or electrical control claim.
    """
    candidates,authority=load_candidates(ROOT)
    candidates=[c for c in candidates if c['mode']=='MV_MODELED_PORT']
    anchors=read(ROOT/'ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json')
    mapping={r['location_id']:r for r in csv_rows(SELECTION/'JOINT_SERVICE_MAPPING.csv')}
    oldfit=read(REPORT/'MV_RELOCATION_PREREGISTRATION.json')['proper_common_transform']
    angles=[oldfit['rotation_degrees'],135.,0.,90.,180.,270.]+[float(a) for a in range(0,360,15) if a not in (0,90,135,180,270)]
    policy={'schema':'JOINT_MV_GEOMETRY_DIAGNOSTIC_V1',
        'scope':'new separate geometry-only diagnostic; previous fixed-AIDC infeasibility evidence preserved',
        'AIDC12_physical_buses_fixed':False,'old_AIDC_STA_mapping_mutated':False,
        'traffic_IDs_service24_MESS6_fixed':True,'all_roles_domain':'all606 source-guarded continuousABC12.47kV original hosts',
        'candidate_source_sha256':authority,'required_pairs':276,'required_axes':552,
        'traffic_pair_and_axis_zero_tolerances_km':.001,
        'common_rotation_schedule_degrees':angles,'positive_uniform_scale':oldfit['uniform_scale'],
        'translation':'shared source/target centroid from original geometry preregistration',
        'reflection_or_per_site_rotation':False,
        'algorithm':'all606 full-domain bitset CSP with exact pairwise arc consistency',
        'branch_order':'MRV then service identity; squared common-scale displacement from old bus/proxy then lexical candidate',
        'per_angle_node_limit':200000,'per_angle_seconds_limit':45,
        'stopping_rule':'first complete exact-audited witness in angle schedule; no global distance optimum claim',
        'no_witness_claim':'UNKNOWN allowed proper transformation class if budget/angle schedule exhausted',
        'AC_or_sensitivity_or_B0_B1_B2_B3_effect_ranking_used':False,'Native_calls':0,
        'physical_GIS_access_and_ETA':'UNVERIFIED; no surveyed route correction',
        'interface_hardware_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED',
        'Production_or_single_final_scenario_frozen':False}
    prereg=REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_PREREGISTRATION.json'
    write_json(prereg,policy,immutable=True)
    centers=read(OLD/'joint_selection_v3/geometry_first/GEOMETRY_PREREGISTRATION.json')
    sc=centers['common_source_center'];tc=centers['common_target_center']
    attempts=[]; winner=None; fit=None
    for angle in angles:
        theta=math.radians(angle);scale=oldfit['uniform_scale'];u=scale*math.cos(theta);v=scale*math.sin(theta)
        fit={'u':u,'v':v,'translation_x':tc[0]-u*sc[0]+v*sc[1],
             'translation_y':tc[1]-v*sc[0]-u*sc[1],'rotation_degrees':angle,
             'uniform_scale':scale,'determinant':u*u+v*v}
        priorities=[]
        for a in anchors:
            r=mapping[a['location_id']];point=(float(r['source_or_proxy_x']),float(r['source_or_proxy_y']))
            priorities.append({j:(scale**2*math.dist(point,(c['x'],c['y']))**2,c['bus'])
                               for j,c in enumerate(candidates)})
        answer=bitset_csp(anchors,candidates,fit,200000,45,None,priorities)
        record={k:v for k,v in answer.items() if k!='selected'};record['angle_degrees']=angle
        attempts.append(record)
        write_json(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_PROGRESS.json',attempts)
        print(json.dumps(record),flush=True)
        if answer['feasible']:winner=answer;break
    result={'schema':'JOINT_MV_GEOMETRY_DIAGNOSTIC_RESULT_V1','status':'GEOMETRY_ONLY_PASS_UNVERIFIED_FIELD_AND_AC' if winner else 'UNKNOWN_BOUNDED_ANGLE_SEARCH',
        'geometric_feasible':bool(winner),'AIDC_fixed_bus_constraint_released':True,
        'preregistration_sha256':sha(prereg),'attempts':attempts,
        'all606_role_domains_considered':True,'original_old_mapping_mutated':False,
        'proper_common_transform':fit if winner else None,'physical_ETA_access_GIS':'UNVERIFIED',
        'AC_or_policy_effects_used':False,'electrical_and_equipment_dispatch_96slot_PASS':False,
        'field_hardware_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED',
        'global_infeasibility_claim':False,'global_displacement_optimality_claim':False,
        'Production_or_single_final_scenario_frozen':False}
    if winner:
        selected=winner['selected'];audit=audit_mapping(anchors,selected,fit);output=[]
        for a in anchors:
            site=a['location_id'];c=selected[site];r=mapping[site]
            p=transform((c['x'],c['y']),fit)
            oldp=transform((float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])),fit)
            output.append({'location_id':site,'role':a['role'],'traffic_node_id':a['traffic_node'],
                'old_P5_bus':r['candidate_bus'],'old_primary_proxy_bus':r['upstream_primary_bus'],
                'candidate_bus':c['bus'],'source_x':c['x'],'source_y':c['y'],
                'common_frame_x_km':p[0],'common_frame_y_km':p[1],
                'traffic_x_km':a['x_east_km'],'traffic_y_km':a['y_north_km'],
                'displacement_layout_equivalent_km_NOT_road_distance':math.dist(p,oldp),
                'traffic_fit_error_layout_equivalent_km':math.dist(p,traffic_xy(a)),
                'root_distance_ohm':c['root_distance_ohm'],'source_continuous_ABC_12p47kV_guard_PASS':True,
                'is_geometric_diagnostic_only':True,'geography_access_actual_ETA':'UNVERIFIED',
                'model_hardware_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED','final_Production_mapping':False})
        assert len(audit)==276 and all(r['pair_pass'] for r in audit)
        assert len({r['candidate_bus'] for r in output})==24
        write_csv(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv',output)
        write_csv(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_276PAIR_AUDIT.csv',audit)
        axes=[]
        for r in audit:
            for axis in ('x','y'):
                axes.append({'location_a':r['location_a'],'location_b':r['location_b'],'axis':axis,
                    'expected_sign':r[f'expected_{axis}_sign'],'actual_sign':r[f'actual_{axis}_sign'],
                    'axis_pass':r[f'{axis}_pass'],'field_geography_certified':False})
        write_csv(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_552AXIS_AUDIT.csv',axes)
        result.update(distinct_buses=24,pair_passes=276,axis_passes=552,
            AIDC_bus_mapping={r['location_id']:r['candidate_bus'] for r in output if r['role']=='AIDC'},
            STA_bus_mapping={r['location_id']:r['candidate_bus'] for r in output if r['role']=='STA'},
            AIDC_changed_count=sum(r['candidate_bus']!=r['old_P5_bus'] for r in output if r['role']=='AIDC'),
            mapping_sha256=sha(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv'))
    write_json(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_RESULT.json',result)
    return result


def audit_saved_joint_witness():
    """Fresh original source and traffic readback of saved geometry-only witness."""
    from ieee8500_v42_original.hold import require_execution_approval
    require_execution_approval('OPENDSS:audit_saved_joint_witness')
    import opendssdirect as odd
    result=read(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_RESULT.json')
    assert result['geometric_feasible']
    mapping=csv_rows(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv')
    before={p.name:sha(p) for p in sorted(FEEDER.iterdir()) if p.is_file()}
    d=odd.NewContext()
    for method in ('AllowChangeDir','AllowForms','AllowEditor','AllowDOScmd'):
        getattr(d.Basic,method)(False)
    d.Text.Command(f'compile "{FEEDER/"Master.dss"}"')
    d.Text.Command('set controlmode=off')
    candidates={r['dss_bus']:r for r in csv_rows(OLD/'MV_AIDC_CANDIDATES.csv')}
    rows=[]
    for r in mapping:
        bus=r['candidate_bus']; d.Circuit.SetActiveBus(bus); meta=candidates[bus]
        nodes=d.Bus.Nodes(); kv=d.Bus.kVBase()*math.sqrt(3)
        assert sorted(nodes)==[1,2,3] and abs(kv-12.47)<1e-10
        assert d.Bus.X()==float(r['source_x']) and d.Bus.Y()==float(r['source_y'])
        assert meta['continuous_abc_from_feeder_head'].lower()=='true'
        assert meta['source_proximity_guard_pass'].lower()=='true'
        rows.append({'location_id':r['location_id'],'role':r['role'],'original_bus':bus,
                     'fresh_original_nodes':','.join(map(str,nodes)),
                     'fresh_kv_base_LL':kv,'fresh_original_x':d.Bus.X(),'fresh_original_y':d.Bus.Y(),
                     'continuous_ABC_authority':meta['continuous_abc_from_feeder_head'],
                     'source_proximity_guard_pass':meta['source_proximity_guard_pass'],
                     'root_distance_ohm':float(meta['root_distance_ohm']),
                     'source_host_PASS':True,'field_geography_protection_ETA':'UNVERIFIED',
                     'new_stationary_transformer_added_by_this_geometry_audit':False})
    assert before=={p.name:sha(p) for p in sorted(FEEDER.iterdir()) if p.is_file()}
    assert before==read(OLD/'ORIGINAL_FEEDER_INVENTORY.json')['source_sha256']
    write_csv(REPORT/'JOINT_MV_HOST_SOURCE_AUDIT.csv',rows)
    traffic=ROOT/'ieee8500_v42/data/traffic_audit'
    hashes={p.name:sha(p) for p in sorted(traffic.iterdir()) if p.is_file()}
    oldhash=read(REPORT/'MV_RELOCATION_PREREGISTRATION.json')['original_traffic_files_sha256']
    assert hashes==oldhash
    receipt={'geometry_witness_sha256':sha(REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv'),
             'original_source31_byte_sha256':before,'source31_original_manifest_identical':True,
             'traffic_files_before_sha256':oldhash,'traffic_files_after_sha256':hashes,
             'traffic_data_all_bytes_unchanged':True,'service_IDs':24,'MESS_count':6,
             'source_host_verified_count':24,'geometric_pair_passes':276,'geometric_axis_passes':552,
             'geographic_displacement_vs_actual_traffic_route':'UNVERIFIED; original abstract road ETA preserved',
             'actual_MV_site_access_and_arrival_connection_delay':'UNVERIFIED, not measured installation data',
             'physical_installed_site_PASS':False}
    write_json(REPORT/'JOINT_MV_TRAFFIC_ETA_AUDIT.json',receipt)
    report='''# AIDC–STA 공동 MV 형상 진단 결과

기존 STA 선정은 5 kW 연구용 저압 포트와 Triplex 하류 전류 제어를 위한 선택이었다. 그 선정이 잘못됐다는 결론은 없다. 동일 위치 Proxy의 상위 Primary가 단상이어서 3상 450 kW급 설비를 그대로 연결할 수 없다는 별도 조건이 확인됐다.

고정 AIDC 12곳 조건에서는 606개 적격 MV 후보에 대한 공통 회전 전 각도의 유리수 증명이 불가능 판정을 주었다. 허용 회전은 191.319215°–191.823332° 열린 구간이며 STA01·02·05·06·07·10에 후보가 하나도 없다. 이 증명은 **AIDC 버스 고정 조건**에 한정된다. 교통 방향 조건 자체가 모순되거나 공동 재선정 전체가 불가능하다는 뜻이 아니다.

사용자가 허용한 별도 공동 재선정 진단에서는 AIDC 고정을 해제하고 기존 source proximity guard·12.47 kV·연속 ABC·교통 노드 ID 24개·MESS 6대를 유지했다. 모든 역할에 606개 전체 후보를 허용하며 공통 회전과 변환을 공유했다. 반사·개별 회전·방향 제약 완화·AC 민감도나 병목 효과 순위는 사용하지 않았다. 기존 Proxy와의 거리 우선 탐색이며 전역 최소 이동거리 최적해라고 주장하지 않는다.

기존 -168.244235° 프레임의 45초 탐색은 UNKNOWN_BOUNDED_SEARCH였고, 다음 사전등록한 135°에서 3.375초·16개 탐색 노드로 witness가 나왔다. **276쌍·552축 모두 PASS, MV 버스 24개 모두 서로 다르며 AIDC 10곳이 변경**됐다. 별도 원본 Master.dss fresh compilation으로 24곳 모두 실제 원본 ABC 노드·12.47 kV·원본 좌표를 확인했다. 기존 DSS 31개와 모든 교통 파일의 바이트 SHA도 보존됐다.

결과는 JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv 및 276PAIR/552AXIS 감사표에 보존했다. 이는 **GEOMETRY_ONLY_PASS_UNVERIFIED_FIELD_AND_AC**다. 형상상 적격 전기 호스트가 있음을 증명하며, 고출력 PCS/변압기의 96슬롯 AC·SOC/ETA 스케줄·보호·단락·현장 설치 적격성을 증명하지 않는다. 기존 저압 P5 연구 매핑을 덮어쓰거나 최종 Production으로 동결하지 않았다.

원본 전력망 좌표의 CRS/거리 단위·실제 고객 GIS·MV 접속 위치의 도로 접근성을 인증할 자료가 없다. 기존 교통 서비스 노드와 ETA는 추상 연구 Proxy로 그대로 사용하며 형상 거리를 실제 도로 이동거리로 환산하지 않는다. 물리 ETA·이동에너지·현장 연결시간은 추가 검증이 필요하다. 실제 MV 변압기 및 접속 설비는 새 연구 overlay이며 원본 IEEE8500 장치라고 주장하지 않는다.
'''
    table='\n| 위치 | 기존 P5 버스 | 별도 MV 후보 버스 |\n|---|---|---|\n'
    table+=''.join(f'| {r["location_id"]} | {r["old_P5_bus"]} | {r["candidate_bus"]} |\n' for r in mapping)
    (REPORT/'JOINT_MV_GEOMETRY_DIAGNOSTIC_KO.md').write_text(report+table,encoding='utf-8')
    return receipt


if __name__=='__main__':
    import argparse
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--joint',action='store_true')
    parser.add_argument('--audit-joint',action='store_true');args=parser.parse_args()
    answer=audit_saved_joint_witness() if args.audit_joint else joint_unfixed_geometry_diagnostic() if args.joint else complete_orientation_audit()
    print(json.dumps(answer,ensure_ascii=False),flush=True)
