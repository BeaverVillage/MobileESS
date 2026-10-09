"""Exact customer pairing, device/source identity and predeclared comparison rules."""
import re
from .common import *
from .engine import OriginalCase, customer_records


def snapshot(label):
    from ieee8500_v42_aemo import source_audit
    source_audit.REPORT=REPORT
    source_audit.snapshot(label)


def pair_customers(balanced, unbalanced):
    b={r['name'].lower():r for r in balanced}; u={}
    assert len(b)==1177 and len(unbalanced)==2354
    for r in unbalanced:
        name=r['name'].lower(); assert name[-1] in 'ab'
        u.setdefault(name[:-1],{})[name[-1]]=r
    assert set(b)==set(u), 'EXACT_CUSTOMER_ID_ROSTER_MISMATCH'
    output=[]
    for name,r in b.items():
        assert set(u[name])=={'a','b'}
        a,c=u[name]['a'],u[name]['b']
        for leg,node in ((a,1),(c,2)):
            assert leg['buses'][0].lower()==r['buses'][0].split('.')[0].lower()+'.'+str(node)
            for key in ('status','pf','model','delta','vminpu_load_characteristic','vmaxpu_load_characteristic',
                        'primary_phase','daily','yearly','duty','enabled'):
                assert r[key]==leg[key], (name,key)
        p=a['kw']+c['kw']; q=a['kvar']+c['kvar']
        assert abs(r['kw']-p)<1e-10 and abs(r['kvar']-q)<1e-10, ('CUSTOMER_POWER_NONCONSERVATION',name)
        output.append(dict(customer_id=name,bus=r['buses'][0],primary_phase=r['primary_phase'],status=r['status'],
            unbal_load_a=a['name'],unbal_load_b=c['name'],unbal_P_a_kw=a['kw'],unbal_P_b_kw=c['kw'],
            unbal_Q_a_kvar=a['kvar'],unbal_Q_b_kvar=c['kvar'],unbal_P_sum_kw=p,unbal_Q_sum_kvar=q,
            balanced_P_kw=r['kw'],balanced_Q_kvar=r['kvar'],P_difference_kw=r['kw']-p,Q_difference_kvar=r['kvar']-q,
            balanced_nominal_each_leg_P_kw=r['kw']/2,balanced_nominal_each_leg_Q_kvar=r['kvar']/2,
            customer_PF=r['pf'],model=r['model'],Vminpu=r['vminpu_load_characteristic'],Vmaxpu=r['vmaxpu_load_characteristic'],
            balanced_phases=r['phases'],balanced_kV=r['kv'],balanced_connection='wye',PASS=True))
    return output


def audit():
    REPORT.mkdir(parents=True,exist_ok=True)
    for manifest in (PR193/'ARTIFACT_SHA256_MANIFEST.json',OLD/'ARTIFACT_SHA256_MANIFEST.json'):
        for name,r in read(manifest)['files'].items(): assert sha(ROOT/name)==r['sha256'],name
    write(REPORT/'PREREGISTRATION.json',dict(parent_P5_commit=P5_COMMIT,day=DAY,
        official_model='customer hot-leg balanced only, not globally three-phase balanced',
        source=1.04,all_12_Vreg=123.5,CAPBank3_states=[0],CapControl_props='all original',
        policy_tuning_allowed=False,background_scale=BG_SCALE,installed_GPU=780,MESS_units=6,
        LV_P_kw=5,LV_Q_kvar=3,LV_S_kva=6,LV_hot_A=27,B0_MESS_PQ=0,
        PV_rule='same2354 existing per-hot Generator capacities/locations, not rebalanced',
        all_lines_objective='canonical source-rooted parent terminal; both-terminal security audit also',
        line_target_rule='Balanced Planning top20 max96 plus top5 Primary and old binding Triplex; stable name tie-break',
        probe_slots=[0,9,48,75],additional_probe_slots='Balanced Planning global peak and Primary peak',
        flexible_bound='same PR193 eligible-known GPU union; fixed PF .95; no independent AIDC Q actuator',
        finite_STA_corners=[[-5,-3],[-5,3],[5,-3],[5,3]],
        time_slots_selected_from_B0_baseline_only=True,siting_or_scale_retuning=False,
        independent_evaluation_day=False,balanced_added_after_observing_unbalanced=True,
        final_main_case_selection=False,final_Production_freeze=False,B1_B2_B3_Native_calls=0))
    u=OriginalCase('AUDIT_UNBALANCED',False); b=OriginalCase('AUDIT_BALANCED',True)
    ur=customer_records(u); br=customer_records(b)
    write(REPORT/'UNBALANCED_CUSTOMER_RECORDS.json',ur); write(REPORT/'BALANCED_CUSTOMER_RECORDS.json',br)
    conserved=pair_customers(br,ur); table(REPORT/'CUSTOMER_POWER_CONSERVATION.csv',conserved)
    assert abs(sum(r['kw'] for r in br)-10773.17)<1e-8
    assert sum(r['status']=='fixed' for r in br)==24 and sum(r['status']=='fixed' for r in ur)==48
    table(REPORT/'FIXED_VARIABLE_LOAD_AUDIT.csv',[dict(customer_id=r['customer_id'],status=r['status'],
        original_P_kw=r['balanced_P_kw'],original_Q_kvar=r['balanced_Q_kvar'],PF=r['customer_PF'],model=r['model'],
        BG_SCALE=BG_SCALE,temporal_factor=r['status']=='variable',Fixed_static_once=r['status']=='fixed',
        unbal_same_customer_status=True,unbal_leg_count=2,balanced_object_count=1) for r in conserved])
    checks={}
    for key in ('lines','transformers','regcontrols','capcontrols','capacitors','buses'):
        left=b.inventory[key];right=u.inventory[key]
        if key=='capacitors':
            # CMatrix is undefined for the original kvar/kV-defined type. DSS-CAPI
            # 0.14.5 exposes uninitialized numeric text through this unused getter.
            # Verify every active property, plus exact unchanged DSS bytes, instead.
            assert not re.search(r'(?im)^\s*[^!\n]*\bcmatrix\s*=',(SOURCE/'Capacitors.dss').read_text())
            left=[dict(r,properties={k:v for k,v in r['properties'].items() if k!='CMatrix'}) for r in left]
            right=[dict(r,properties={k:v for k,v in r['properties'].items() if k!='CMatrix'}) for r in right]
        checks[key]=left==right
        assert checks[key], ('ORIGINAL_NETWORK_OR_CONTROLLER_DRIFT',key)
    assert b.line_axes==u.line_axes and b.node_axes==u.node_axes and b.transformer_axes==u.transformer_axes
    source_rows=[]
    for path in sorted(SOURCE.iterdir()):
        if not path.is_file():continue
        prior=git('show',f'{P5_COMMIT}:ieee8500_v42/data/feeder/{path.name}')
        assert hashlib.sha256(prior).hexdigest()==sha(path)
        source_rows.append(dict(file=path.name,sha256=sha(path),bytes=path.stat().st_size,unchanged_from_P5=True,
            case_role='Balanced Master' if path.name=='Master.dss' else 'Balanced loads' if path.name=='Loads.dss'
            else 'Unbalanced Master' if path.name=='Master-unbal.dss' else 'Unbalanced loads' if path.name=='UnbalancedLoads.DSS' else 'common source'))
    table(REPORT/'BALANCED_UNBALANCED_SOURCE_AUDIT.csv',source_rows)
    redirects={name:re.findall(r'(?im)^\s*Redirect\s+(\S+)',(SOURCE/name).read_text()) for name in ('Master.dss','Master-unbal.dss')}
    assert 'Loads.dss' in redirects['Master.dss'] and any(n.lower()=='unbalancedloads.dss' for n in redirects['Master-unbal.dss'])
    inputs={str(p.relative_to(ROOT)).replace('\\','/'):receipt(p) for p in sorted(DATA.rglob('*')) if p.is_file()}
    mapping=[]
    for r in rows(MAPPING):
        bus=r['candidate_bus']; b.d.Circuit.SetActiveBus(bus)
        assert b.d.Bus.Name().lower()==bus.lower()
        nodes=b.d.Bus.Nodes()
        assert set((1,2,3) if r['role']=='AIDC' else (1,2))<=set(nodes)
        mapping.append(dict(site=r['location_id'],bus=bus,role=r['role'],nodes=str(nodes),
            original_STA_split_phase_nodes='1.2' if r['role']=='STA' else '',same_mapping=True,
            coordinate_authority=r['coordinate_authority'],field_geography='UNVERIFIED'))
    table(REPORT/'PCC_MAPPING_INTEGRITY.csv',mapping)
    geometry=read(PR193/'joint_selection_v3/score_selection/GEOMETRY_VERIFICATION.json')
    write(REPORT/'SOURCE_AUTHORITY.json',dict(parent_P5_commit=P5_COMMIT,parent_PR=196,PR193=PR193_SHA,PR62=PR62_SHA,
        latest_V42_authority=LATEST_SHA,engine_version=b.d.Basic.Version(),masters=redirects,
        native_customer_kw=sum(r['kw'] for r in br),native_customer_kvar=sum(r['kvar'] for r in br),
        customers=1177,unbal_load_objects=2354,balanced_load_objects=1177,Fixed_customers=24,
        max_customer_P_error=max(abs(r['P_difference_kw']) for r in conserved),max_customer_Q_error=max(abs(r['Q_difference_kvar']) for r in conserved),
        original_network_comparison=checks,original_counts=b.inventory['counts'],source_files=source_rows,
        same_input_authorities=inputs,mapping_sha256=sha(MAPPING),inherited_geometry=geometry,
        geography_certified=False,existing_campaign_mutations=0,Native_calls=0,
        unused_getter_exclusion='Capacitor.CMatrix unused for original kvar/kV type; uninitialized getter text, not physical matrix change'))
    print('source/customer audit PASS:',b.inventory['counts'],'P',sum(r['kw'] for r in br),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['audit','before','after']); a=p.parse_args()
    audit() if a.action=='audit' else snapshot(a.action)
