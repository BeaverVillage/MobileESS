from types import SimpleNamespace
import json
import numpy as np
import pytest
from dayahead.v38.authority import canonical_sha256
from dayahead.v40a.accepted_initial import materialize_accepted_a0
from dayahead.v40a.context import file_sha


def source(tmp_path, wrong_power=False):
    sites=tuple(f'AIDC{i:02d}' for i in range(1,13))
    context=SimpleNamespace(day='2025-04-01',capacity=SimpleNamespace(aidc_ids=sites,site_capacity={s:64 for s in sites}),
                            tables={s:np.tile(np.arange(65),(96,1)) for s in sites})
    ledger=[{'job_id':'a','state_at_issue':'RUNNING','qos':'normal','duration_authority':'SAFE_RUNNING',
             'requested_gpus':8,'RSP_duration_slots':10,'RSP_duration_seconds':9000,
             'RSP_scheduled_start':30,'RW_scheduled_completion':40}]
    assignment={'job_uid':'a','destination_AIDC':'AIDC02','initial_AIDC':'AIDC01','migration_selected':True,
                'logical_Rack_compatibility_label':'R02','fixed_WAN_path_id':'p12',
                'fixed_WAN_path_links':['e1','e2'],'WAN_bytes_by_slot':[0,10,0],
                'migration_checkpoint_slot':1,'destination_READY_slot':3,'restart_complete_slot':4}
    decision={'status':'PASS','temporal_mode':'RSP','operating_day':'2025-04-01',
              'temporal_schedule':[{'job_id':'a','scheduled_start_slot':30,'scheduled_end_slot':40}],
              'AIDC_assignments':[assignment],
              'site_PCC_power_trajectory':[{'slot':t,'AIDC':s,'PCC_P_kW':8 if 6<=t<16 and s=='AIDC02' else 0}
                                            for t in range(96) for s in sites]}
    if wrong_power:decision['site_PCC_power_trajectory'][0]['PCC_P_kW']=999
    path=tmp_path/'accepted.json'
    path.write_text(json.dumps({'decision':decision,'DA_decision_SHA256':canonical_sha256(decision)}))
    return path,ledger,context,assignment


def test_existing_migration_and_wan_state_survive_a0_import(tmp_path):
    path,ledger,context,assignment=source(tmp_path)
    result=materialize_accepted_a0(path,file_sha(path),ledger,context)
    assert result['jobs'][0]['accepted_A0_assignment_and_WAN']==assignment
    assert result['RUNNING_migrations_selected_in_A0']==1
    assert result['jobs'][0]['migration_destination']=='AIDC02'
    assert result['new_migration_optimization_calls']==0


def test_accepted_a0_must_reproduce_frozen_pcc(tmp_path):
    path,ledger,context,_=source(tmp_path,wrong_power=True)
    with pytest.raises(ValueError,match='PCC_RECONSTRUCTION'):
        materialize_accepted_a0(path,file_sha(path),ledger,context)


def test_wrong_a0_file_hash_is_rejected(tmp_path):
    path,ledger,context,_=source(tmp_path)
    with pytest.raises(ValueError,match='FILE_SHA'):
        materialize_accepted_a0(path,'f'*64,ledger,context)
