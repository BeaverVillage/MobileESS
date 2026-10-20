import json,os
from copy import deepcopy
import pytest
from v44_audit_chunk_store import ChunkStore
from v44_actual_record_light import SharedControlEncoding

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def test_changed_trajectory_shares_past_rows_and_restores_exact_complete_raw(tmp_path):
    store=ChunkStore(tmp_path);encoder=SharedControlEncoding()
    rows=[dict(slot=i,frozen_trajectory_SHA='first',physical={'v':-0.,'name':'한국어','all':[1.0000000000000002]*100}) for i in range(8)]
    first=tmp_path/'a_MANIFEST.json';store.write(first,rows,encoder,canonical)
    assert store.restore(first)==(canonical(rows)+os.linesep).encode('utf-8')
    changed=deepcopy(rows)
    for row in changed:row['frozen_trajectory_SHA']='second'
    changed[-1]['physical']['v']=.975
    second=tmp_path/'b_MANIFEST.json';store.write(second,changed,encoder,canonical)
    assert store.restore(second)==(canonical(changed)+os.linesep).encode('utf-8')
    assert store.counts['new_chunks']==9 and store.counts['reused_chunks']==7
    assert store.restore(first)==(canonical(rows)+os.linesep).encode('utf-8')

def test_events_and_empty_raw_arrays_round_trip(tmp_path):
    s=ChunkStore(tmp_path);e=SharedControlEncoding()
    for i,rows in enumerate(([],[{'slot':1,'completed':False,'controls':None}])):
        p=tmp_path/f'{i}_MANIFEST.json';s.write(p,rows,e,canonical)
        assert s.restore(p)==(canonical(rows)+os.linesep).encode('utf-8')

def test_chunk_or_manifest_corruption_is_detected(tmp_path):
    s=ChunkStore(tmp_path);p=tmp_path/'a_MANIFEST.json'
    m=s.write(p,[{'v':1}],SharedControlEncoding(),canonical)
    target=s.chunk_path(m['rows'][0]['sha256']);target.write_bytes(b'broken')
    with pytest.raises(Exception):s.restore(p)

def test_path_escape_and_invalid_chunk_id_are_rejected(tmp_path):
    s=ChunkStore(tmp_path)
    with pytest.raises(ValueError):s.chunk_path('../outside')
    with pytest.raises(ValueError):s.write(tmp_path.parent/'outside_MANIFEST.json',[],SharedControlEncoding(),canonical)

def test_manifest_token_mutation_cannot_pass_original_raw_digest(tmp_path):
    s=ChunkStore(tmp_path);p=tmp_path/'a_MANIFEST.json'
    m=s.write(p,[{'slot':0,'frozen_trajectory_SHA':'one'}],SharedControlEncoding(),canonical)
    m['trajectory_tokens']=['"different"'];p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='RECONSTRUCTION_DRIFT'):s.restore(p)
