"""Logging-only diagnostic; frozen operating cases remain byte-identical.

Original Reg/Cap EventLog=No cannot prove within-timestamp action order. Two
anchor replays enable only observability flags, then require bitwise physical
array/state equality to the original logged-off cases.
"""
from pathlib import Path
import sys,numpy as np
from . import correction as c
from . import correction_svr_run as runner
from .correction_svr_implicit import source_svr
from .correction_svr import SV,save,table
from .audit import read,sha

class ActionTracePhysical(runner.Instrumented):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name in self.original12:self.d.Text.Command('Edit RegControl.'+name+' EventLog=Yes')
        for name in self.d.CapControls.AllNames():self.d.Text.Command('Edit CapControl.'+name+' EventLog=Yes')
        if self.bank:
            for row in self.bank.installation_receipt['original_seven_control_parameters']:row['properties']['EventLog']='Yes'
        self.initial_audit=runner.regulator_readback(self)

def main(config):
    c.priority();runner.seal_s0();runner.source_svr=source_svr
    runner.RUN=c.RUNTIME/'correction_action_trace';runner.RUN.mkdir(exist_ok=True);runner.install(config)
    c.CorrectedPhysical=ActionTracePhysical
    c.trajectory=lambda schedule:(np.zeros((96,8)),np.zeros((96,8)),np.full((97,8),760.))
    original=c.fingerprint
    def fingerprint():
        v=original();v['logging_only_diagnostic']=sha(Path(__file__).read_bytes());return v
    c.fingerprint=fingerprint
    amendment=dict(status='LOGGING_ONLY_REPLAY_DECLARED_BEFORE_AC',configuration=config,beta=2.,
        original_EventLog='No for original12RegControls and9CapControls',diagnostic_EventLog='Yes',
        physical_parameters_changed=0,scope='Within-native-timestamp action-order evidence for S0/S1_03 beta2 anchors; not all40 original cases',
        acceptance='Require bit-identical line/voltage/transformer arrays, clock event axis and tap/cap states versus original EventLog=No archive')
    p=SV/f'ACTION_LOG_AMENDMENT_{config}.json'
    if p.exists():assert read(p)==amendment
    else:save(p.name,amendment)
    _,receipt=c.run_case(2.,'ACTUAL',schedule=dict(name=config+'_ACTIONLOG',discharge_begin=[68]*8,duration=8))
    folder=Path(receipt['archive_path']).parent;old=c.RUNTIME/'correction_svr'/f'TIME_2.00_ACTUAL_{config}'
    checks={}
    with np.load(folder/'AC_FULL.npz') as a,np.load(old/'AC_FULL.npz') as b:
        for key in a.files:checks[key]=bool(np.array_equal(a[key],b[key]))
    same=read(folder/'STATES.json')==read(old/'STATES.json');assert all(checks.values()) and same
    logs=[]
    for slot in read(folder/'EVENTS.json'):
        for event in slot['events']:
            for order,text in enumerate(event['native_event_log']):
                logs.append(dict(configuration=config,slot=slot['slot'],evaluation_slot=slot['slot']-24,
                    seconds=event['absolute_seconds'],native_order_in_solve=order+1,native_event_log=text))
    assert logs
    table(f'NATIVE_ACTION_ORDER_{config}.csv',logs)
    save(f'ACTION_LOG_NONINTERFERENCE_{config}.json',dict(PASS=True,arrays_bit_identical=checks,control_states_identical=same,
        native_action_log_rows=len(logs),original_reference=str(old/'RECEIPT.json'),logging_receipt=str(folder/'RECEIPT.json'),Native_optimizer_calls=0))
    print('LOGGING ONLY ACTION ORDER CERTIFIED',config,len(logs),flush=True)

if __name__=='__main__':main(sys.argv[1])
