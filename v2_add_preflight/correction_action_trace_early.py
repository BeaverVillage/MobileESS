"""Enable diagnostic logging before series-model initialization, not after it."""
from pathlib import Path
import numpy as np
from . import correction as c
from . import correction_svr_run as runner
from .correction_svr_implicit import source_svr
from .correction_svr import SV,save,table
from .audit import read,sha

class EarlyTrace(runner.Instrumented):
    def _line_static(self,name):
        if not getattr(self,'_logging_enabled',False):
            self._logging_enabled=True
            for n in self.original12:self.d.Text.Command('Edit RegControl.'+n+' EventLog=Yes')
            for n in self.d.CapControls.AllNames():self.d.Text.Command('Edit CapControl.'+n+' EventLog=Yes')
        return super()._line_static(name)

def main():
    c.priority();runner.seal_s0();runner.source_svr=source_svr
    runner.RUN=c.RUNTIME/'correction_action_trace_early';runner.RUN.mkdir(exist_ok=True);runner.install('S1_03');c.CorrectedPhysical=EarlyTrace
    c.trajectory=lambda schedule:(np.zeros((96,8)),np.zeros((96,8)),np.full((97,8),760.))
    original=c.fingerprint
    def fingerprint():
        v=original();v['logging_before_initialization']=sha(Path(__file__).read_bytes());return v
    c.fingerprint=fingerprint
    # Preserve failed strict equivalence of the late logging edit. It changed
    # no discrete control states, but did invalidate bitwise-array acceptance.
    late=c.RUNTIME/'correction_action_trace/TIME_2.00_ACTUAL_S1_03_ACTIONLOG';base=c.RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03'
    diffs={}
    with np.load(late/'AC_FULL.npz') as a,np.load(base/'AC_FULL.npz') as b:
        for k in a.files:diffs[k]=float(np.max(abs(a[k]-b[k])))
    save('LATE_ACTION_LOG_STRICT_EQUIVALENCE_FAILURE.json',dict(status='STRICT_BITWISE_NONINTERFERENCE_FAIL',max_absolute_differences=diffs,
        control_states_identical=read(late/'STATES.json')==read(base/'STATES.json'),archive=str(late),
        interpretation='No physical change is inferred from tiny solver differences; strict bitwise acceptance is nevertheless not claimed. Late Edit after model preparation is retained as a failed diagnostic.'))
    amendment=dict(status='DECLARED_BEFORE_EARLY_LOGGING_AC',beta=2.,configuration='S1_03',EventLog_changes=21,
        timing='Before series installation and initialization solve; all physical parameters and injections unchanged',
        strict_acceptance='Bit-identical arrays, event-slot axis and complete tap/cap states versus frozen B0')
    p=SV/'EARLY_ACTION_LOG_AMENDMENT.json'
    if p.exists():assert read(p)==amendment
    else:save(p.name,amendment)
    _,receipt=c.run_case(2.,'ACTUAL',schedule=dict(name='S1_03_ACTIONLOG_EARLY',discharge_begin=[68]*8,duration=8))
    folder=Path(receipt['archive_path']).parent;checks={}
    with np.load(folder/'AC_FULL.npz') as a,np.load(base/'AC_FULL.npz') as b:
        for k in a.files:checks[k]=bool(np.array_equal(a[k],b[k]))
    states=read(folder/'STATES.json')==read(base/'STATES.json');assert all(checks.values()) and states,checks
    rows=[]
    for slot in read(folder/'EVENTS.json'):
        for event in slot['events']:
            for order,text in enumerate(event['native_event_log']):rows.append(dict(configuration='S1_03',slot=slot['slot'],evaluation_slot=slot['slot']-24,seconds=event['absolute_seconds'],native_order_in_solve=order+1,native_event_log=text))
    table('NATIVE_ACTION_ORDER_S1_03_EARLY.csv',rows)
    save('ACTION_LOG_NONINTERFERENCE_S1_03_EARLY.json',dict(PASS=True,arrays_bit_identical=checks,control_states_identical=states,
        native_action_log_rows=len(rows),original_reference=str(base/'RECEIPT.json'),logging_receipt=str(folder/'RECEIPT.json'),Native_optimizer_calls=0))
    print('EARLY LOGGING ACTION ORDER CERTIFIED',len(rows),flush=True)

if __name__=='__main__':main()
