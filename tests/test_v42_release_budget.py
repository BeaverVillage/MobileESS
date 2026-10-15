import json
import pytest
from v42_integration.release_budget import ReleaseP1Budget


def make(tmp_path):
    binding=dict(Threads=1,objective_sense=1,matrix_sha='matrix',domain_sha='domain')
    authorization=dict(scope='D0_A1_P1_EXACTLY_ONE_CALL',limit_seconds=180.,call_cap_seconds=120.,
        return_reserve_seconds=30.,overshoot_buffer_seconds=30.,max_optimize_calls=1,Threads=1,native_binding=binding)
    canonical=tmp_path/'old.json';canonical.write_text('{"used":318.681}')
    budget=ReleaseP1Budget(tmp_path/'new.json',authorization=authorization,canonical_ledger=canonical)
    return budget,binding,canonical


def test_exact_single_p1_authorization_does_not_spend_or_reset_old_ledger(tmp_path):
    b,binding,old=make(tmp_path);before=old.read_bytes()
    b.validate_call(label='D0_A1_P1_RELEASE_120_20261015',cap=120.,binding=binding)
    assert b.remaining()==180 and b.document['calls']==[] and old.read_bytes()==before
    with b._transaction():b.document['authorization_consumed']=True
    with pytest.raises(RuntimeError,match='ALREADY_CONSUMED'):
        b.validate_call(label='D0_A1_P1_RELEASE_120_20261015',cap=120.,binding=binding)
    recovered=ReleaseP1Budget(b.path,authorization=b.authorization,canonical_ledger=old)
    with pytest.raises(RuntimeError,match='ALREADY_CONSUMED'):
        recovered.validate_call(label='D0_A1_P1_RELEASE_120_20261015',cap=120.,binding=binding)


@pytest.mark.parametrize('label,cap,bad',[('M1',120,False),('D0_A1_P1_RELEASE_120_20261015',121,False),
    ('D0_A1_P1_RELEASE_120_20261015',120,True)])
def test_later_stages_changed_matrix_and_larger_cap_cannot_use_permission(tmp_path,label,cap,bad):
    b,binding,_=make(tmp_path)
    if bad:binding=dict(binding,matrix_sha='other')
    with pytest.raises(ValueError,match='EXACT_P1'):
        b.validate_call(label=label,cap=cap,binding=binding)


def test_canonical_mutation_blocks_even_unused_permission(tmp_path):
    b,binding,old=make(tmp_path);old.write_text('{"used":0}')
    with pytest.raises(ValueError,match='HISTORICAL_NATIVE_LEDGER_DRIFT'):
        b.validate_call(label='D0_A1_P1_RELEASE_120_20261015',cap=120.,binding=binding)
