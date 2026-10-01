"""Completed native run evidence and the user's sequential execution policy."""
import gzip,json
import numpy as np
from v42_certificate.common import OUT,LOCAL,S2,START_UB,MATERIAL,OBJ_TOL,read,load_start,sha

def certs():return {a:read(OUT/(a+suffix+'_CERTIFICATE.json')) for a,suffix in [('B1','_ROUTE'),('B2','_ROUTE_MODE'),('B3','_BUFFER')]}
def test_real_native_start_acceptance_not_only_import_validation():
    r=read(OUT/'MIP_START_NATIVE_ACCEPTANCE.json');b3=read(OUT/'B3_OPTIMIZATION.json')
    log=gzip.decompress((OUT/'B3_SOLVER.log.gz').read_bytes()).decode()
    assert 'Loaded user MIP start with objective' in log
    assert r['PASS'] and r['first_incumbent']['objective']<=START_UB+OBJ_TOL and r['SolCount']>0
    assert r['folded_into_B3'] and not r['original_full_binary_model'] and r['initial_point_all_original_binaries_integer']
    assert r['initial_original_integer_validation']['valid_new_UB'] and b3['initial_start_acceptance']['PASS']
def test_no_separate_full_MIP_probe_or_production_or_fallback():
    markers={p.name.split('_')[0] for p in LOCAL.glob('*_OPTIMIZE_STARTED.json')}
    assert 'B3' in markers and markers<={'B3','B2','B1'}
    f=read(OUT/'FINAL_FLAGS.json');assert f['FALLBACK_RUNS']==0 and not f['NATIVE_FULL_BINARY_ACCEPTANCE_OPTIMIZATION_RUN']
    assert not f['PRODUCTION_M1_RUN'] and not f['P2_RUN'] and not f['A2_ALLOWED']
    assert not f['ACTUAL_P_CORRECTION_ENABLED'] and not f['ACTUAL_Q_CORRECTION_ENABLED']
def test_sequential_marker_gates_are_satisfied():
    c=certs()
    if c['B2']['run']:assert c['B3']['material']
    if c['B1']['run']:assert c['B2']['run'] and c['B2']['material']
    if not c['B3']['material']:assert not c['B2']['run'] and not c['B1']['run']
    if c['B3']['negative_certificate']:assert c['B2']['execution']==c['B1']['execution']=='NOT_RUN_NESTING_CERTIFIED'
def test_no_false_nonmaterial_or_false_increment_from_timeout():
    for c in certs().values():
        assert c['negative_certificate']==(c['upper']-S2<=MATERIAL)
        assert c['material']==(c['lower']-S2>=MATERIAL)
        assert c['lower']<=c['upper']+OBJ_TOL
        if c['negative_certificate']:assert c['certificate_valid'] and c['certificate_type']
def test_partial_interval_and_original_global_bound_are_separate():
    c=certs();f=read(OUT/'FINAL_FLAGS.json')
    assert f['BEST_CERTIFIED_ORIGINAL_M1_LB']==max([S2]+[r['lower'] for r in c.values()])
    assert f['BEST_VALIDATED_ORIGINAL_M1_UB']>=f['BEST_CERTIFIED_ORIGINAL_M1_LB']-OBJ_TOL
    assert abs(f['FINAL_IMPLIED_GAP']-(f['BEST_VALIDATED_ORIGINAL_M1_UB']-f['BEST_CERTIFIED_ORIGINAL_M1_LB'])/f['BEST_VALIDATED_ORIGINAL_M1_UB'])<1e-14
def test_actual_accepted_vector_axis_is_complete():
    names,values=load_start()
    with np.load(OUT/'MIP_START_NATIVE_ACCEPTED.npz',allow_pickle=False) as z:assert np.array_equal(z['names'],names) and len(z['values'])==316743
def test_preregistered_source_is_unchanged_through_execution():
    marker=read(OUT/'B3_EXECUTION_MARKER.json');freeze=read(OUT/'EXECUTION_FREEZE.json')
    assert marker['scope_addendum_sha256']==sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json')==freeze['scope_addendum_sha256']
    assert marker['preregistration_sha256']==sha(OUT/'PREREGISTRATION.json')
    assert read(OUT/'PRODUCTION_AUTHORIZATION.json')['original_preregistration_production_gate_superseded']
