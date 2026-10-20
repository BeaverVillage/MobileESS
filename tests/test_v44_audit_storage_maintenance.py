import os,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v44_audit_storage_maintenance import candidates,compact,fingerprint
from v44_recovery_r036 import operations as op

def raw(root,name,age=3600,complete=True):
    folder=root/name;folder.mkdir();p=folder/'VOLTAGE_CONTROL_ACTUAL_SLOTS.json';p.write_bytes(b'x'*1100000)
    os.utime(p,(time.time()-age,time.time()-age))
    if complete:(folder/'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json').write_text('{}')
    return p

def test_only_closed_old_complete_unique_inodes_are_selected(tmp_path):
    p=raw(tmp_path,'a');alias=tmp_path/'b';alias.mkdir()
    os.link(p,alias/p.name);(alias/'VOLTAGE_CONTROL_ACTUAL_PHYSICAL_AUDIT.json').write_text('{}')
    raw(tmp_path,'recent',age=1);raw(tmp_path,'unfinished',complete=False)
    assert len(candidates(tmp_path,set()))==1
    assert candidates(tmp_path,{fingerprint(p)})==[]

def test_compaction_keeps_content_and_records_allocation_saving(tmp_path):
    p=raw(tmp_path,'a');before=p.read_bytes()
    with patch('v44_audit_storage_maintenance.subprocess.run',return_value=SimpleNamespace(returncode=0,stderr=b'')),patch('v44_audit_storage_maintenance.allocated',side_effect=[100,40]):
        result=compact(p,tmp_path)
    assert result['PASS'] and result['bytes_released']==60 and p.read_bytes()==before

def test_failed_native_compaction_keeps_original_file(tmp_path):
    p=raw(tmp_path,'a')
    with patch('v44_audit_storage_maintenance.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr=b'locked')):
        result=compact(p,tmp_path)
    assert not result['PASS'] and p.exists()

def test_compressor_cannot_escape_authorized_root(tmp_path):
    p=raw(tmp_path,'a')
    with pytest.raises(ValueError):compact(p,tmp_path/'elsewhere')

def test_post_case_maintenance_starts_only_after_inherited_cleanup_succeeds():
    with patch.object(op.previous,'cleanup_after_case',side_effect=PermissionError('live worker')),patch.object(op.storage_maintenance,'start') as start:
        with pytest.raises(PermissionError):op.cleanup_after_case()
        start.assert_not_called()
    with patch.object(op.previous,'cleanup_after_case',return_value={'PASS':True}),patch.object(op.storage_maintenance,'start') as start:
        assert op.cleanup_after_case()=={'PASS':True};start.assert_called_once()

@pytest.mark.parametrize('n',range(29,36))
def test_worker_dispatch_preserves_input(n):
    args=['python','-u','-m',f'v44_recovery_r{n:03d}.operations','--worker','request.json']
    result=op.command(args)
    assert result[3]==op.ENTRY and result[4:6]==args[4:6]

def test_installation_keeps_r035_storage_and_restores_hooks():
    from v44_recovery_r029 import current_ac_performance as p
    from v44_actual_record_light import SharedControlEncoding
    original=p.audit_writer
    with op.install():assert p.ExactAuditEncoding is SharedControlEncoding and p.audit_writer is not original
    assert p.audit_writer is original
