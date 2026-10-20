import hashlib,json,sqlite3
from pathlib import Path
from unittest.mock import patch
import pytest
import v44_audit_archive as archive
from v44_audit_chunk_store import ChunkStore

def encoded(rows):return (json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\r\n').encode('utf-8')

def test_receipts_source_text_and_unknown_path_lists_all_protect_candidates(tmp_path):
    key='2025-05-02/B3/'+'a'*32
    path='D:/root/AC_PROBES/'+key+'/VOLTAGE_CONTROL_ACTUAL_SLOTS.json'
    receipt=tmp_path/'proof.json';receipt.write_text(json.dumps({'raw':{'path':path,'sha256':'b'*64,'bytes':100}}))
    assert archive.references(receipt)=={key}
    inventory=tmp_path/'disk_inventory.json';inventory.write_text(json.dumps({'paths':[path]}))
    assert archive.references(inventory)=={key}
    source=tmp_path/'source.py';source.write_text(repr(path))
    assert archive.references(source)=={key}

@pytest.mark.parametrize('newline',[b'\r\n',b'\n',b''])
def test_legacy_bytes_retain_float_tokens_unicode_and_line_endings(tmp_path,newline):
    store=ChunkStore(tmp_path);raw=b'[{"PASS":true,"arm":"B3","capcontrol":null,"frozen_trajectory_SHA":"abc","v":1e-07},{"PASS":false,"arm":"B3","capcontrol":null,"frozen_trajectory_SHA":"abc","v":-0.0}]'+newline
    path=tmp_path/'test_MANIFEST.json';archive.pack_legacy(path,raw,store)
    assert store.restore(path)==raw and store.counts['new_chunks']==2

def test_unknown_legacy_layout_is_kept_byte_exact(tmp_path):
    store=ChunkStore(tmp_path);raw='[ {"한국어":1.0}, {"other":true} ]\n'.encode('utf-8')
    path=tmp_path/'test_MANIFEST.json';archive.pack_legacy(path,raw,store)
    assert store.restore(path)==raw

def make_case(root):
    folder=root/'AC_PROBES'/'2025-05-02'/'B3'/('a'*32);folder.mkdir(parents=True)
    values={};audit={}
    for name,key,rows in [
        ('VOLTAGE_CONTROL_ACTUAL_SLOTS.json','slots_receipt',[{'PASS':True,'arm':'B3','capcontrol':None,'frozen_trajectory_SHA':'abc','v':-0.}]),
        ('VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS.json','physical_solve_events_receipt',[{'completed':True,'controls':{'v':1e-7}}])]:
        p=folder/name;raw=encoded(rows);p.write_bytes(raw);values[p]=raw
        audit[key]=dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    manifest=folder/'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json';manifest.write_text(json.dumps(audit))
    return folder,values,manifest

def test_verified_migration_removes_only_original_raw_and_keeps_restorable_records(tmp_path):
    folder,values,metadata=make_case(tmp_path);before=metadata.read_bytes();dbpath=tmp_path/'catalog.sqlite3'
    db=sqlite3.connect(dbpath);db.execute('CREATE TABLE archived (legacy TEXT PRIMARY KEY,manifest TEXT,sha TEXT,bytes INTEGER,UTC TEXT,released INTEGER,state TEXT)')
    try:
        with patch.object(archive,'ROOT',tmp_path),patch.object(archive,'CATALOG',dbpath),patch.object(archive,'guard'):
            result=archive.migrate_one(folder,ChunkStore(tmp_path),db)
            assert result['deleted_legacy_copies']==2 and metadata.read_bytes()==before
            for path,raw in values.items():
                assert not path.exists()
                output=tmp_path/(path.name+'.restored');archive.restore_legacy(path,output)
                assert output.read_bytes()==raw
    finally:db.close()

def test_original_receipt_drift_never_deletes_legacy_file(tmp_path):
    folder,values,metadata=make_case(tmp_path);path=next(iter(values));path.write_bytes(b'changed')
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE archived (legacy TEXT PRIMARY KEY,manifest TEXT,sha TEXT,bytes INTEGER,UTC TEXT,released INTEGER,state TEXT)')
    with patch.object(archive,'ROOT',tmp_path),patch.object(archive,'guard'):
        with pytest.raises(ValueError,match='ORIGINAL_RECEIPT_DRIFT'):archive.migrate_one(folder,ChunkStore(tmp_path),db)
    assert path.read_bytes()==b'changed'
    db.close()

def test_guard_rejects_live_case_even_if_user_requested_cleanup(tmp_path):
    (tmp_path/'STOP_AUTONOMY.json').write_text('{"user_dispatch_pause":true}')
    with patch.object(archive.op,'OPS',tmp_path),patch.object(archive.op.previous,'ready',return_value=False):
        with pytest.raises(PermissionError,match='NO_LIVE_CASE'):archive.guard()

def test_failed_durable_flush_never_removes_original_raw(tmp_path):
    folder,values,metadata=make_case(tmp_path)
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE archived (legacy TEXT PRIMARY KEY,manifest TEXT,sha TEXT,bytes INTEGER,UTC TEXT,released INTEGER,state TEXT)')
    with patch.object(archive,'ROOT',tmp_path),patch.object(archive,'guard'),patch.object(archive,'durable_archive',side_effect=OSError('flush failed')):
        with pytest.raises(OSError):archive.migrate_one(folder,ChunkStore(tmp_path),db)
    assert all(path.read_bytes()==raw for path,raw in values.items())
    db.close()
