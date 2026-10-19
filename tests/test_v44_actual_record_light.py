import json
import pytest
from v44_actual_record_light import SharedControlEncoding
from v44_actual_audit_encoding import ExactImmutableEncoding
from v44_recovery_r029.immutable import freeze

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def test_shared_controls_across_slot_and_events_keep_exact_bytes():
    old,new=ExactImmutableEncoding(),SharedControlEncoding()
    controls=freeze({'settings':{'한국어':'값'},'tap':-0.0,'v':1.0000000000000002})
    slots=[dict(slot=0,frozen_trajectory_SHA='a',original_initial_solve_controls=controls)]
    events=[dict(slot=0,kind='INITIAL',completed=True,controls=controls)]
    assert new.canonical_list(slots,canonical)==old.canonical_list(slots,canonical)==canonical(slots)
    hits=new.identity_hits
    assert new.canonical_list(events,canonical)==old.canonical_list(events,canonical)==canonical(events)
    assert new.identity_hits>hits and new.shared_control_rows==1
    events[0]['completed']=False;events[0]['controls']=freeze({'tap':1.})
    assert new.canonical_list(events,canonical)==canonical(events)

def test_mutable_nested_controls_are_never_assumed_immutable():
    new=SharedControlEncoding();event=dict(slot=0,controls={'tap':[1.]})
    for x in (1.,2.,-0.):
        event['controls']['tap'][0]=x
        assert new.canonical_list([event],canonical)==canonical([event])
    assert new.shared_control_rows==0

def test_small_cache_and_non_string_dictionary_keys_keep_original_fallback():
    old,new=ExactImmutableEncoding(128),SharedControlEncoding(128)
    for i in range(10):
        rows=[{'controls':freeze({'large':'x'*200,'i':i})},{1:'one'}]
        assert new.canonical_list(rows,canonical)==old.canonical_list(rows,canonical)
        assert new.bytes<=128
