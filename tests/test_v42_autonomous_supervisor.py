from copy import deepcopy
from v42_autonomous.supervisor import sweep_complete, transition, next_day, DAYS

def checkpoint():
    return dict(state='B2_RUNNING',workers={},dates={a+'/'+d:dict(status='PENDING') for a in ('B2','B3') for d in DAYS})

def test_failure_quarantine_and_budget_terminal_do_not_block_sweep():
    cp=checkpoint()
    for row in cp['dates'].values():row['status']='PASS'
    cp['dates']['B2/'+DAYS[2]]['status']='QUARANTINE'
    cp['dates']['B2/'+DAYS[0]]['status']='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    assert sweep_complete(cp,'B2')
    cp['dates']['B2/'+DAYS[4]]['status']='RUNNING'
    assert not sweep_complete(cp,'B2')

def test_transition_is_idempotent_and_history_is_preserved():
    cp=checkpoint();transition(cp,'B2_FINALIZING');transition(cp,'B2_FINALIZING')
    assert len(cp['transition_history'])==1
    transition(cp,'B2_SWEEP_COMPLETE_WITH_FAILURES');transition(cp,'B3_STARTING')
    assert len(cp['transition_history'])==3

def test_dates_are_ordered_and_terminal_dates_are_never_redispatched():
    cp=checkpoint();cp['dates']['B2/'+DAYS[0]]['status']='QUARANTINE'
    assert next_day(cp,'B2')==DAYS[1]
