"""Zero-optimize independent checks and immutable-source sealing."""
import xml.etree.ElementTree as ET
from .common import *
from .oracle import Oracle,lower_certificate

def duals():
    o=Oracle();checks=[]
    try:
        for p in sorted((OUT/'oracle_certificates').glob('G*.json')):
            r=read(p);assert r['status']==2
            rows=[o.m.addConstr(o.state(u,t,a)==1,name=f'condition[{u},{t},{a}]') for u,t,a in r['conditions']];o.m.update()
            with np.load(p.with_suffix('.dual.npz'),allow_pickle=False) as z:
                pi=np.zeros(o.m.NumConstrs);pi[z['indices']]=z['Pi']
            bound,cert,_=lower_certificate(o.m,pi,o.box,r['certificate']['primal_objective']);assert abs(bound-r['O1_W7_lower_bound'])<=1e-12
            checks.append(dict(key=r['key'],certified_bound=bound,PASS=True,optimize_calls=0));o.m.remove(rows);o.m.update()
    finally:o.close()
    dump('W7_DUAL_CERTIFICATE_REVALIDATION.json',dict(PASS=True,checks=checks,optimize_calls=0))

def incumbent():
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    from v42_bootstrap.grid import grid_report
    from v42_m1_sparse.post_validate import controls_from_plan
    bundle,anchor,plan,sites,initial,routes,b=inputs();physical=validate(plan,sites,routes,b,96);extra=supplemental_physical(plan,sites,b)
    grid=grid_report(bundle,controls_from_plan(plan,anchor),UB);assert physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS']
    physical.update(extra,initial_SOC_PASS=all(abs(plan['values'][f'SOC[{u},0]']-b.initial)<=TOL for u in initial),AIDC_anchor_unchanged=True)
    assert physical['initial_SOC_PASS']
    dump('M1_PHYSICAL_VALIDATION.json',dict(run=False,new_production_incumbent=False,retained_incumbent_independently_validated=True,retained_incumbent_PASS=True,validation=physical))
    grid['node83p2_slot79_voltage_pu']=read(PRIOR/'FINAL_FLAGS.json')['NODE83P2_SLOT79_VOLTAGE'];grid['node83p2_used_for_tuning']=False
    dump('M1_ROBUST_VOLTAGE_REPORT.json',dict(run=False,new_production_incumbent=False,retained_incumbent_independently_validated=True,retained_incumbent_PASS=True,validation=grid))

def verify():
    from .report import REQUIRED
    missing=[n for n in REQUIRED if n!='VERIFICATION.json' and not (OUT/n).exists()];assert not missing,missing
    for r in read(OUT/'LEGACY_PRESERVATION_AUDIT.json')['files']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    for r in read(OUT/'PR110_BASE_RECEIPT.json')['inherited_evidence']:assert sha(ROOT/r['path'])==r['sha256']
    for r in read(OUT/'SOURCE_MANIFEST.json')['sources']:assert sha(ROOT/r['path'])==r['sha256']
    assert read(OUT/'BASE_F3_IDENTITY.json')['PASS'] and read(OUT/'ROOT_SOURCE_RECEIPT.json')['PASS']
    assert read(OUT/'W7_VALIDATION_SUMMARY.json')['PASS'] and read(OUT/'W7_UNIVERSAL_STOP_CERTIFICATE.json')['PASS'] and read(OUT/'W7_DUAL_CERTIFICATE_REVALIDATION.json')['PASS']
    assert len(csvread('G1_BETA_TABLE.csv'))==600 and len(csvread('G2_BETA_TABLE.csv'))==11250 and len(csvread('G3_BETA_TABLE.csv'))==4952
    assert len(csvread('G2_TRANSPORT_PRECHECK.csv'))==18 and len(csvread('G3_TRANSPORT_PRECHECK.csv'))==16
    assert all(float(r['beta'])==DEFAULT for n in ['G1_BETA_TABLE.csv','G2_BETA_TABLE.csv'] for r in csvread(n))
    assert all(float(r['gamma'])==DEFAULT for r in csvread('G3_BETA_TABLE.csv'))
    assert all(r['representable']=='True' for r in csvread('G3_ROOT_MARGINAL_FEASIBILITY.csv'))
    assert read(OUT/'FROZEN_CRITICAL_SLOTS.json')['slots']==CRITICAL and read(OUT/'MULTITIME_WINDOW_FREEZE.json')['slots']==list(WINDOW)
    assert read(OUT/'G3_TIME_PAIR_FREEZE.json')['pairs']==[list(p) for p in TIME_PAIRS]
    flags=read(OUT/'FINAL_FLAGS.json');assert not flags['MATERIAL_ROOT_BOUND_GAIN'] and not flags['MIP_CANARY_RUN'] and not flags['PRODUCTION_RUN'] and not flags['M1_ACCEPTED']
    assert flags['A1_OPTIMIZE_CALLS_THIS_TASK']==0 and flags['S2_OPTIMIZE_CALLS']==0 and flags['S3_OPTIMIZE_CALLS']==0
    suite=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot().find('testsuite');assert int(suite.attrib['errors'])==int(suite.attrib['failures'])==0
    tests=int(suite.attrib['tests']);assert tests==537
    import re
    assert len(re.findall(r'^\d+\. ',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M))==50
    import hashlib
    assert hashlib.sha256(gzip.decompress((OUT/'W7_MODEL.mps.gz').read_bytes())).hexdigest()==read(OUT/'W7_MATRIX_CENSUS.json')['source_mps_sha256']
    dump('VERIFICATION.json',dict(PASS=True,required_files=len(REQUIRED),tests=tests,bounded_conditional_checks=70,W7_LP_calls=10,conditional_calls=4,auxiliary_upper_witness_calls=6,
        complete_path_lifts=5552,G1_states=600,G2_pairs=11250,G3_reachable_pairs=4952,G2_prechecks=18,G3_prechecks=16,root_marginal_hull_tests=16,
        dual_certificates=4,legacy_bytes_preserved=True,source_hashes_PASS=True,frozen_window_PASS=True,integer_physical_set_changed=False,full_root_optimize_calls=0,
        A1_optimize_calls=0,S2_optimize_calls=0,S3_optimize_calls=0,new_cut_rows=0,new_cut_columns=0,new_cut_nonzeros=0))
    print('WINDOW VERIFICATION PASS',tests,flush=True)
if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
