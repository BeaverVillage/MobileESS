"""Mandatory exact-AC admission before the final beam truncation.

Only already generated terminal children are considered; no new candidates,
dispatch edits, rating/setting changes, coefficient changes, or extra searches.
"""
from common8500 import *
import inspect,textwrap
from dayahead.v40a.recourse import validate_physics
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.tools import run_v35r3e_r1_beam as beam_module

def select_terminal(beam,pruned,aidc,folder):
    pool={s.beam_state_id:s for s in (*beam,*pruned)}
    ordered=sorted(pool.values(),key=lambda s:(s.current_planning_objective,s.beam_state_id))
    receipts=[];feasible=[]
    for i,s in enumerate(ordered):
        trajectory=MessTrajectory(tuple(beam_module._restore_slots(s.trajectory_slots)))
        physical=validate_physics(trajectory);assert physical['status']=='PASS'
        if {r.mess_id for r in trajectory.slots}!=set(beam_module.MESS_INITIAL):raise RuntimeError('TERMINAL_FLEET_AXIS_MISMATCH')
        state(status='RUNNING',stage=folder.name+':TERMINAL_AC_ADMISSION',search_started=False,terminal_candidate_index=i+1,terminal_candidates=len(ordered))
        ac=exact(aidc,trajectory.slots,folder/'terminal_AC'/f'{i:02}_{s.beam_state_id}')
        receipt=dict(state_id=s.beam_state_id,model_P1=s.current_planning_objective,status=ac['status'],metrics=ac['metrics'],violating_slots=[x['slot'] for x in ac['slots'] if not x['feasible']],trajectory_sha256=trajectory.canonical_sha256,exact=record(folder/'terminal_AC'/f'{i:02}_{s.beam_state_id}'/'AC_VALIDATION.json'))
        receipts.append(receipt)
        if ac['status']=='PASS':feasible.append(s)
    result=dict(status='PASS' if feasible else 'FAIL_CLOSE',rule='Minimum original model P1 among exact-AC-feasible already generated terminal children; state ID breaks ties',generated_terminal_count=len(ordered),new_candidates=0,dispatch_changes=0,receipts=receipts,selected_state=feasible[0].beam_state_id if feasible else None)
    save(folder/'TERMINAL_AC_ADMISSION.json',result)
    if not feasible:raise RuntimeError('IEEE8500_NO_EXACT_AC_FEASIBLE_GENERATED_TERMINAL_CHILD; no tuning or false PASS')
    return feasible[0]

def bind_final_selector(original,folder):
    source=textwrap.dedent(inspect.getsource(original))
    old='    final_state = min(beam, key=lambda state: state.current_planning_objective)'
    assert source.count(old)==1
    patched=source.replace(old,'    final_state = select_terminal(beam, pruned, aidc, ADMISSION_FOLDER)')
    namespace=dict(original.__globals__,select_terminal=select_terminal,ADMISSION_FOLDER=folder)
    exec(compile(patched,__file__+'::final_admission','exec'),namespace)
    save(folder/'FINAL_SELECTOR_CODE_AUDIT.json',dict(original_source=record(inspect.getsourcefile(original)),only_replacement=dict(before=old,after='select_terminal(beam, pruned, aidc, ADMISSION_FOLDER)'),patched_source_sha256=hashlib.sha256(patched.encode()).hexdigest(),nonterminal_search_unchanged=True,original_K_beam_seed_settings_unchanged=True))
    return namespace[original.__name__]
