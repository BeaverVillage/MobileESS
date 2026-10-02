import csv,gzip,json
import numpy as np
from v42_benders.canonical import digest_arrays
from v42_benders_fullscale.common import ROOT,OUT,read,sha

def test_actual_fullscale_x0_before_recourse():
    r=read('MASTER_X_000_RECEIPT.json');started=read('RECOURSE_000_STARTED.json')
    assert r['persisted_before_recourse'] and r['label']=='NEW_V2_EXPERIMENT_X0'
    assert r['vector_length']==85744 and r['master_settings']['Threads']==1
    assert started['persisted_receipt_sha256']==sha(OUT/'MASTER_X_000_RECEIPT.json')
    assert started['source_x_hash']==r['vector_sha256'] and started['started_UTC']>=r['created_UTC']
    assert not r['historical_PR115_x'] and r['active_cut_IDs']==[]

def test_actual_binary_and_axis_fidelity():
    r=read('MASTER_X_000_RECEIPT.json')
    with np.load(OUT/'MASTER_X_000.npz') as z:
        x=z['values'];names=z['names'];indices=z['original_column_indices'];bits=z['bits']
    assert x.dtype==np.float64 and bits.dtype==np.uint8 and x.shape==(85744,)
    assert np.isin(x,[0,1]).all() and np.array_equal(bits,x)
    assert digest_arrays(x)==r['vector_sha256'] and digest_arrays(names,indices)==r['axis_hash']
    with np.load(ROOT/'docs/v42_mess_exact_benders/PARTITION_AXIS.npz') as z:
        assert np.array_equal(names,z['names'][z['B3_master']])
        assert np.array_equal(indices,np.flatnonzero(z['B3_master']))

def test_actual_recourse_exact_x_and_raw_persistence():
    r=read('MASTER_X_000_RECEIPT.json');receipt=read('RECOURSE_000_NATIVE_RAW_RECEIPT.json')
    assert receipt['source_x_hash']==r['vector_sha256']
    p=receipt['persistence'];assert p['persisted_before_validation']
    with gzip.open(p['journal'],'rt') as f:raw=json.loads(next(f))
    with np.load(OUT/'MASTER_X_000.npz') as z:assert np.array_equal(raw['source_x'],z['values'])
    assert raw['Method']==1 and raw['Seed']==20260929 and raw['InfUnbdInfo']==1 and raw['DualReductions']==0
    assert sha(raw['axis_npz'])==raw['axis_npz_sha256']

def test_no_uncertified_insertion_or_automatic_downstream():
    f=read('FINAL_FLAGS.json')
    assert f['uncertified_cuts_inserted']==0 and not f['speedup_causal_claim']
    assert all(f[k] is False for k in ['M1_ACCEPTED','P2_RUN','A2_RUN','M2_RUN','PROBLEM13_FINAL_VALIDATED','Actual_P_correction','Actual_Q_correction','B0_B1_RUN'])
    with (OUT/'FULLSCALE_CUT_LEDGER.csv').open() as stream:
        for r in csv.DictReader(stream):
            assert r['validator_result']=='True'
            if r['type']!='OPTIMALITY':assert float(r['strict_margin'])>1e-8

def test_pilot_progress_requires_cut_and_changed_candidate_or_certificate():
    p=read('PILOT_PROGRESS.json');f=read('PILOT_FINAL_FLAGS.json')
    if f['PILOT_PROGRESS_GATE']:
        assert p['validated_witness'] or p['global_master_infeasible'] or (p['inserted_valid_cuts']>=1 and p['distinct_persisted_candidates']>=2)
    if not f['PILOT_PROGRESS_GATE']:
        assert not read('B3_FULL_RUN_AUTHORIZATION.json')['authorized']
        assert not read('FULL_M1_CANARY_AUTHORIZATION.json')['authorized']

def test_fullscale_source_model_unchanged():
    a=read('B3_MODEL_AUTHORITY.json');assert a['PASS'] and a['scientific_source_matches_PR116']
    assert (a['master_columns'],a['columns'],a['rows'])==(85744,230999,954561)
    assert a['grid_rows_deleted']==0 and not a['route_pruning'] and a['outside_B3_relaxed']==122568
