import hashlib,os
from pathlib import Path
from unittest.mock import patch
import pytest
from v44_actual_content_store import ExactContentStore,cleanup

def raw(root,name='a'):return root/name/'VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS.json'

def test_identical_bytes_keep_all_paths_and_one_inode(tmp_path):
    store=ExactContentStore(tmp_path);a,b=raw(tmp_path,'a'),raw(tmp_path,'b')
    try:
        store.write(a,b'abc\r\n');store.write(b,b'abc\r\n')
        assert a.read_bytes()==b.read_bytes()==b'abc\r\n' and os.path.samefile(a,b)
        store.write(b,b'changed')
        assert a.read_bytes()==b'abc\r\n' and b.read_bytes()==b'changed'
        assert not os.path.samefile(a,b)
    finally:store.close()

def test_missing_or_modified_canonical_never_substitutes_wrong_content(tmp_path):
    store=ExactContentStore(tmp_path);a,b=raw(tmp_path,'a'),raw(tmp_path,'b')
    try:
        store.write(a,b'abc');a.write_bytes(b'bad')
        store.write(b,b'abc')
        assert b.read_bytes()==b'abc' and a.read_bytes()==b'bad'
        b.unlink();store.write(raw(tmp_path,'c'),b'abc')
        assert raw(tmp_path,'c').read_bytes()==b'abc'
        assert store.counts['collision_or_stale_entries']==2
    finally:store.close()

def test_links_not_supported_falls_back_to_complete_independent_file(tmp_path):
    store=ExactContentStore(tmp_path);a,b=raw(tmp_path,'a'),raw(tmp_path,'b')
    try:
        store.write(a,b'abc')
        with patch('os.link',side_effect=OSError('unsupported')):store.write(b,b'abc')
        assert a.read_bytes()==b.read_bytes() and not os.path.samefile(a,b)
    finally:store.close()

def test_unknown_and_outside_paths_are_rejected(tmp_path):
    store=ExactContentStore(tmp_path)
    try:
        with pytest.raises(ValueError):store.write(tmp_path/'source.py',b'x')
        with pytest.raises(ValueError):store.write(tmp_path.parent/'outside.json',b'x')
    finally:store.close()

def test_text_matches_existing_write_text_including_newlines_and_unicode(tmp_path):
    store=ExactContentStore(tmp_path);expected=tmp_path/'expected';actual=raw(tmp_path)
    try:
        text='{"한국어":-0.0}\n';expected.write_text(text,encoding='utf8')
        assert store.write_text(actual,text)==len(text)
        assert actual.read_bytes()==expected.read_bytes()
    finally:store.close()

def test_cleanup_checks_receipts_and_preserves_missing_or_partial_audits(tmp_path):
    import json
    for folder in ('a','b'):
        p=raw(tmp_path,folder);p.parent.mkdir();p.write_bytes(b'abc')
        (p.parent/'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json').write_text(json.dumps(dict(
            slots_receipt=dict(path=str(p),bytes=3,sha256=hashlib.sha256(b'abc').hexdigest()),
            physical_solve_events_receipt=dict(path=str(p),bytes=3,sha256=hashlib.sha256(b'abc').hexdigest()))))
    (tmp_path/'partial').mkdir();partial=raw(tmp_path,'partial');partial.write_bytes(b'partial')
    result=cleanup(tmp_path)
    assert result['PASS'] and result['shared_files']==1
    assert os.path.samefile(raw(tmp_path,'a'),raw(tmp_path,'b'))
    assert partial.read_bytes()==b'partial'
