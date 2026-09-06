from copy import deepcopy
import numpy as np
import pytest
from dayahead.v40i.may01_forensic import vector, downstream, observed_service_no_delay, hybrid_jobs
from dayahead.v40i.electrical import generation_release
from dayahead.v40h.identity import IntegrityError


def test_issue_axis_slot_97_is_operating_slot_73_and_gap_is_zero():
    parts=[{'site':'AIDC05','start':0,'end':97},{'site':'AIDC01','start':100,'end':120}]
    assert vector(parts,4).sum()==0
    assert vector(parts,4,96)[4]==4 and vector(parts,4,100)[0]==4


def test_overlapping_segments_and_active_unknown_sites_are_rejected():
    with pytest.raises(ValueError,match='OVERLAPPING'):
        vector([{'site':'AIDC01','start':0,'end':120}]*2,1)
    with pytest.raises(ValueError,match='AUTHORITY'):
        vector([{'site':'UNASSIGNED','start':0,'end':120}],1)


def test_short_observed_runtime_does_not_execute_destination_migration():
    job={'migration_selected':True,'migration_checkpoint_slot':25,'initial_AIDC':'AIDC05',
         'frozen_execution_ready_slot':28,'AIDC_site':'AIDC01'}
    parts=observed_service_no_delay(job,{'status':'EXECUTION_ACCOUNTED','actual_service_seconds':20000})
    assert len(parts)==1 and parts[0]['site']=='AIDC05'
    assert parts[0]['end']==20000/900


def test_factorial_intervention_retains_common_service_and_does_not_mutate_policy():
    a={'job_uid':'a','state_at_issue':'PENDING','start_slot':1,'end_slot':6,
       'safe_duration_slots':5,'AIDC_site':'AIDC01','Rack_label':'R1'}
    b={**a,'start_slot':9,'end_slot':14,'AIDC_site':'AIDC02','Rack_label':'R2'}
    before=deepcopy([a,b])
    temporal=hybrid_jobs([a],[b],True,False)[0]
    spatial=hybrid_jobs([a],[b],False,True)[0]
    assert (temporal['start_slot'],temporal['AIDC_site'],temporal['end_slot'])==(9,'AIDC01',14)
    assert (spatial['start_slot'],spatial['AIDC_site'],spatial['end_slot'])==(1,'AIDC02',6)
    assert [a,b]==before


def test_frozen_topology_cut_requires_upstream_separation():
    elements=[{'name':'line.sw2','buses':['13','152']},
      {'name':'transformer.idc09','buses':['152','idc_idc09_pcc']}]
    assert downstream(elements)['sites']['AIDC09']
    elements.append({'name':'line.bypass','buses':['13','152']})
    with pytest.raises(AssertionError,match='NONRADIAL'):downstream(elements)


def test_generation_remains_on_hold_without_explicit_forensic_completion(tmp_path):
    with pytest.raises(IntegrityError,match='HOLD_FORENSIC_PENDING'):generation_release(tmp_path)
