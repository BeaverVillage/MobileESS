"""Invalid Native0 evidence must never authorize a production attempt."""
import json
import pytest
from tools import seal_v42_2_validation as gate


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf8')


def evidence(tmp_path,monkeypatch):
    a,m,r=tmp_path/'A',tmp_path/'M',tmp_path/'R'
    source=tmp_path/'source.txt';source.write_text('literal source',encoding='utf8');records=[gate.file_record(source)]
    put(a/'RESULT.json',dict(Native_calls=0,day='2025-05-01',rows=[dict(arm='B1',stage='A1',source_sha='fixture-source',
        status='PASS_NATIVE0_MATRIX',mathematical_matrix_equivalence='PASS_INDEPENDENT_ALL_UID_ACTUAL_A_B_RHS_BOUNDS_OBJECTIVE',
        FULL_integer_compression_rows_removed=0,FULL_integer_compression_columns_removed=0)]))
    put(a/'B1/A1/DW/PCC_HARD_DEFINITIONS.json',dict(PASS=True,original_identity_rows_preserved=True,
        definitions=[dict(row=i,pivot=i) for i in range(1152)]))
    put(a/'B1/A1/DW/PCC_FORMULATION_NATIVE0_COMPARISON.json',dict(Native_calls=0,
        selected='HARD_ORIGINAL_IDENTITY_EQUALITIES',hard=dict(coefficient_changes=0)))
    put(a/'B1/A1/DW/DW_SOURCE_FREEZE.json',dict(sources=records))
    put(a/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',dict(source_sha='fixture-source',
        science_derivation=dict(source_records=records)))
    put(m/'RESULT.json',dict(status='PASS',Native_calls=0,blocked_Native_attempts=[],source_sha='fixture-source',
        K16=dict(PASS=True,original_domain_projection_included=True,independent_original_geometry_replayed=True,current_FULL_UB=None),
        seedless_iterations=[dict(pool_sha=str(i),charge_modes=384,MIP_Start_present=False) for i in (1,2)],
        Direct_same_pool_AB=[dict(exact_same_matrix_domain_lift_start=True)]*2,current_source_records=records))
    put(r/'RESULTS.json',dict(status='PASS',baseline_IDs_preserved=682,tests=1247,failures=[],skipped=[],
        blocked_real_native_attempts=[],historical_ledgers_byte_preserved=True))
    monkeypatch.setattr(gate,'release_identity',lambda:dict(release_sha='fixture-release'))
    return a,m,r,source


@pytest.mark.parametrize('mutation',['fabricated-UB','wrong-mode-domain','duplicate-pool','new-source','skipped-regression','integer-row-deleted','m-source-mismatch'])
def test_validation_rejects_non_equivalent_or_unverified_evidence(tmp_path,monkeypatch,mutation):
    a,m,r,source=evidence(tmp_path,monkeypatch)
    if mutation=='new-source':source.write_text('changed source',encoding='utf8')
    elif mutation=='skipped-regression':
        doc=gate.read(r/'RESULTS.json');doc['skipped']=['incomplete'];put(r/'RESULTS.json',doc)
    elif mutation=='integer-row-deleted':
        doc=gate.read(a/'RESULT.json');doc['rows'][0]['FULL_integer_compression_rows_removed']=1;put(a/'RESULT.json',doc)
    else:
        doc=gate.read(m/'RESULT.json')
        if mutation=='fabricated-UB':doc['K16']['current_FULL_UB']=1.
        if mutation=='wrong-mode-domain':doc['seedless_iterations'][0]['charge_modes']=383
        if mutation=='duplicate-pool':doc['seedless_iterations'][1]['pool_sha']='1'
        if mutation=='m-source-mismatch':doc['source_sha']='stale-scientific-source'
        put(m/'RESULT.json',doc)
    with pytest.raises(ValueError):gate.seal(a,m,r,tmp_path/'GATE.json')
    assert not (tmp_path/'GATE.json').exists()


def test_current_validated_evidence_seals_without_claiming_UB(tmp_path,monkeypatch):
    a,m,r,_=evidence(tmp_path,monkeypatch)
    proof=gate.seal(a,m,r,tmp_path/'GATE.json')
    assert proof['PASS'] and not proof['FULL_UB_claimed'] and not proof['Actual_Fresh_PASS_claimed']
    assert len(proof['evidence'])==5


@pytest.mark.parametrize('source',[None,'','different-source','fixture-source'])
def test_new_attempt_requires_the_actually_audited_scientific_source(tmp_path,source):
    from tools.run_v42_2_campaign import require_validation_source
    put(tmp_path/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',dict(source_sha='fixture-source'))
    if source=='fixture-source':
        require_validation_source(tmp_path,dict(scientific_source_sha=source))
    else:
        with pytest.raises(PermissionError,match='FRESH_ATTEMPT_MUST_MATCH_AUDITED'):
            require_validation_source(tmp_path,dict(scientific_source_sha=source))


def test_scientific_manifest_drift_cannot_seal(tmp_path,monkeypatch):
    a,m,r,_=evidence(tmp_path,monkeypatch)
    path=a/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json'
    doc=gate.read(path);doc['source_sha']='different-source';put(path,doc)
    with pytest.raises(ValueError,match='SCIENTIFIC_MANIFEST_SOURCE'):
        gate.seal(a,m,r,tmp_path/'GATE.json')


def test_scientific_producer_outside_dw_records_is_still_byte_pinned(tmp_path,monkeypatch):
    a,m,r,_=evidence(tmp_path,monkeypatch)
    science=tmp_path/'scientific_policy.py';science.write_text('original policy',encoding='utf8')
    path=a/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json'
    doc=gate.read(path);doc['science_derivation']['source_records']=[gate.file_record(science)];put(path,doc)
    science.write_text('changed policy',encoding='utf8')
    with pytest.raises(ValueError,match='NATIVE0_CURRENT_SOURCE_BYTES_REQUIRED'):
        gate.seal(a,m,r,tmp_path/'GATE.json')
