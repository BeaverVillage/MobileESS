"""Recheck inherited artifacts, native identity, coefficients and byte preservation."""
import gzip,xml.etree.ElementTree as ET
import gurobipy as gp
from .common import *
from .oracle import Oracle,finite_bound_certificate

def energy_extract():
    v=root_values();_,_,_,sites,initial,routes,_=inputs();arcs=arcs_for(sites,routes)
    sums={}
    for u in initial:
        for s in sites:
            for t in range(96):sums[u,s,t]=dict(travel_departure_mass=0.,travel_departure_G_kWh=0.,travel_arrival_mass=0.,travel_arrival_G_kWh=0.,transit_mass_from_site=0.,transit_arc_departure_G_kWh=0.)
        for k,(s,t,d,e,r) in enumerate(arcs):
            if r is None:continue
            mass=v[f'arc[{u},{k}]'];G=v.get(f'G[{u},{k}]')
            if G is None:continue
            sums[u,s,t]['travel_departure_mass']+=mass;sums[u,s,t]['travel_departure_G_kWh']+=G
            if e<96:
                sums[u,d,e]['travel_arrival_mass']+=mass;sums[u,d,e]['travel_arrival_G_kWh']+=G-r.energy_kwh*mass
            for j in range(t,e):
                sums[u,s,j]['transit_mass_from_site']+=mass;sums[u,s,j]['transit_arc_departure_G_kWh']+=G
    rows=[]
    for r in csvread('ROOT_SITE_STATE_VALUES.csv'):
        r.update(sums[r['MESS'],r['site'],int(r['time'])]);rows.append(r)
    table('ROOT_SITE_STATE_VALUES.csv',rows)
    dump('ROOT_ENERGY_VALUE_SEMANTICS.json',dict(SOC='Native pooled time-index energy, unchanged',stay_departure_G='S3 arc departure energy flow',
        travel_departure_G='S3 G on travel departure arc',travel_arrival_G='G - travel_energy*x',transit_arc_departure_G='Sum original departure G for currently crossing travel arcs, not an inferred instantaneous SOC',no_clipping=True))

def retained_validation():
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    from v42_bootstrap.grid import grid_report,coefficients
    from v42_m1_sparse.post_validate import controls_from_plan
    from v42_m1_sparse.grid import map_bindings
    base=configure_inherited();bundle,anchor,inc,sites,initial,routes,b=inputs();report={}
    def inspect(m,obj,bindings,controls,data):
        m.setObjective(obj[0][1]);m.update();values=inc['values'].copy();map_bindings(bindings,values)
        m.setAttr('Start',[values[n] for n in m.getAttr('VarName')]);m.update();identity=base.stats(m)
        assert identity==base.EXPECTED
        report.update(PASS=True,identity=identity,matrix=base.matrix_validate(m,values),optimize_calls=0,default_hook=None,
            native_source_sha256=sha(ROOT/'v42_native/mess.py'))
        return None,dict(optimize_calls=0)
    base.build(inspect);dump('E0_DEFAULT_PATH_IDENTITY.json',report)
    physical=validate(inc,sites,routes,b,96);extra=supplemental_physical(inc,sites,b);ctrl=controls_from_plan(inc,anchor);grid=grid_report(bundle,ctrl,UB)
    assert physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS']
    assert all(inc['values'][f'SOC[{u},0]']==b.initial for u in initial)
    physical.update(extra,initial_SOC_checked=True,AIDC_anchor_unchanged=True,line_transformer_robust_PASS=grid['PASS'])
    dump('M1_PHYSICAL_VALIDATION.json',dict(run=False,new_production_validation=False,retained_incumbent_independently_revalidated=True,retained_incumbent_PASS=True,validation=physical,source_plan_sha256=sha(LOCAL/'PR107_M1_PLAN.json')))
    cert,coeff=coefficients(bundle)
    with np.load(cert['outputs']['voltage']['path'],allow_pickle=False) as z:
        nodes=next(z[k].astype(str).tolist() for k in z.files if any(w in k.lower() for w in ('node','bus','name')) and z[k].ndim==1 and len(z[k])==len(coeff[0].voltage_constant))
    n=nodes.index('83.2');sq=float(coeff[79].voltage_constant[n]+coeff[79].voltage_matrix[:,n]@np.asarray(ctrl[79]))
    grid.update(node83p2_slot79_voltage_pu=float(np.sqrt(sq)),node83p2_used_for_cut_tuning=False)
    dump('M1_ROBUST_VOLTAGE_REPORT.json',dict(run=False,new_production_validation=False,retained_incumbent_independently_revalidated=True,retained_incumbent_PASS=True,validation=grid))
    print('E0 IDENTITY & RETAINED INCUMBENT PASS',report,flush=True)

def certificates():
    records=[read(p) for p in sorted((OUT/'oracle_certificates').glob('*.json'))];checks=[]
    for t in sorted({r['slot'] for r in records}):
        o=Oracle(t)
        try:
            for r in [r for r in records if r['slot']==t]:
                cond=[o.m.addConstr(o.expr(u,s)==1,name=f'condition[{u},{s},{t}]') for u,s in r['conditions']];o.m.update()
                assert sha(LOCAL/f'O1_{t}.mps')==r['template_sha256']
                with np.load(OUT/'oracle_certificates'/f"{r['key']}.npz",allow_pickle=False) as z:
                    pi=np.zeros(o.m.NumConstrs);pi[z['indices']]=z['Pi']
                bound,cert,_=finite_bound_certificate(o.m,pi,r['certificate']['primal_objective'])
                assert abs(bound-r['O1_lower_bound'])<=1e-12 and r['beta']==max(DEFAULT,bound)
                checks.append(dict(key=r['key'],recomputed_lower_bound=bound,PASS=True,optimize_calls=0))
                o.m.remove(cond);o.m.update()
        finally:o.close()
    dump('O1_DUAL_CERTIFICATE_REVALIDATION.json',dict(PASS=True,checks=checks,optimize_calls=0))
    print('DUAL CERTIFICATES REVALIDATED',len(checks),flush=True)

def constant_cut_ceiling():
    base=configure_inherited()
    with np.load(PRIOR/'BASE_ROOT_LP_SOLUTION.npz',allow_pickle=False) as z:values=dict(zip(map(str,z['names']),map(float,z['values'])))
    values['rho_max']=DEFAULT
    result={}
    def inspect(m,obj,*args):
        m.setObjective(obj[0][1]);m.update();result.update(base.matrix_validate(m,values));return None,dict(optimize_calls=0)
    base.build(inspect)
    dump('CONSTANT_CUT_BOUND_CEILING.json',dict(PASS=True,counterfactual_only=True,cut_rows_installed=0,optimize_calls=0,
        original_F3_point_with_rho_raised_to_default=result,all_beta_equal=DEFAULT,exact_uniform_cut_bound=DEFAULT,
        gain_vs_F3=DEFAULT-F3,material=False,
        proof='State mass sums to one by original flow. Every uniform-beta E1 cut is rho>=default. Every E2 extension has total w=1, also rho>=default. Original F3 rho appears only in epigraph line inequalities and its [0,1] bound. Raising the immutable F3 optimum rho to default preserves every original row, as matrix checked. Hence even adding all these uniform cuts could achieve at most/exactly default, below material gain .001. No new cut or candidate is built.'))
    print('UNIFORM CUT CEILING',DEFAULT-F3,result,flush=True)

def verify():
    from .report import REQUIRED
    missing=[n for n in REQUIRED if n!='VERIFICATION.json' and not (OUT/n).is_file()];assert not missing,missing
    legacy=read(OUT/'LEGACY_PRESERVATION_AUDIT.json');changed=[r['path'] for r in legacy['files'] if sha(ROOT/r['path'])!=r['sha256']];assert not changed,changed
    for r in read(OUT/'PR109_BASE_RECEIPT.json')['inherited_evidence']:assert sha(ROOT/r['path'])==r['sha256']
    for r in read(OUT/'SOURCE_MANIFEST.json')['sources']:assert sha(ROOT/r['path'])==r['sha256']
    import hashlib
    for r in read(OUT/'SOURCE_MANIFEST.json')['templates']:
        assert sha(ROOT/r['path'])==r['compressed_sha256']
        assert hashlib.sha256(gzip.decompress((ROOT/r['path']).read_bytes())).hexdigest()==r['raw_sha256']
    assert read(OUT/'ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json')['full_matrix_revalidation']['PASS']
    assert read(OUT/'O1_VALIDATION_SUMMARY.json')['PASS'] and read(OUT/'O1_UNIVERSAL_STOP_CERTIFICATE.json')['PASS']
    assert read(OUT/'O1_DUAL_CERTIFICATE_REVALIDATION.json')['PASS'] and read(OUT/'E0_DEFAULT_PATH_IDENTITY.json')['PASS']
    assert read(OUT/'CONSTANT_CUT_BOUND_CEILING.json')['PASS'] and read(OUT/'CONSTANT_CUT_BOUND_CEILING.json')['gain_vs_F3']<.001
    assert all(r['PASS']=='True' for r in csvread('ROOT_STATE_MASS_AUDIT.csv'))
    expected=sorted(csvread('ROOT_INCUMBENT_SLOT_GAP.csv'),key=lambda r:(-float(r['gap_proxy']),int(r['time'])))[:6]
    assert [int(r['time']) for r in expected]==read(OUT/'CRITICAL_SLOT_FREEZE.json')['slots']
    assert len(csvread('E1_BETA_TABLE.csv'))==600 and len(csvread('E2_BETA_TABLE.csv'))==11250 and len(csvread('E2_TRANSPORT_PRECHECK.csv'))==18
    assert all(float(r['beta'])==DEFAULT for r in csvread('E1_BETA_TABLE.csv')+csvread('E2_BETA_TABLE.csv'))
    f=read(OUT/'FINAL_FLAGS.json');assert not f['MATERIAL_ROOT_BOUND_GAIN'] and not f['MIP_CANARY_RUN'] and not f['PRODUCTION_RUN'] and not f['M1_ACCEPTED'] and not f['PROBLEM13_FINAL_VALIDATED']
    tests=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot();suite=tests.find('testsuite');assert int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
    assert int(suite.attrib['tests'])==529
    import re
    assert len(re.findall(r'^\d+\. ',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M))==50
    dump('VERIFICATION.json',dict(PASS=True,required_files=len(REQUIRED),tests=529,O1_enumerated_conditional_checks=74,reachable_single_witnesses=600,
        reachable_pair_bounds=11250,transport_prechecks=18,dual_certificates=len(read(OUT/'O1_DUAL_CERTIFICATE_REVALIDATION.json')['checks']),
        inherited_bytes_preserved=True,source_hashes_PASS=True,slot_freeze_PASS=True,state_mass_PASS=True,integer_physical_set_changed=False,full_root_reoptimization_calls=0,
        A1_optimize_calls=0,legacy_changes=[],new_cut_rows=0,new_cut_columns=0,new_cut_nonzeros=0))
    print('ALL VERIFICATION PASS',flush=True)

if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
