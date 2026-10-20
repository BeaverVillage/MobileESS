"""Isolated native TIME test: circuit JSON is not a complete runtime checkpoint."""
import sys,json
from pathlib import Path
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
import opendssdirect as d
from dss.enums import DSSJSONFlags
from v44.common import atomic,now,record

out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
left=d.NewContext();right=d.NewContext()
commands=[
    'new circuit.checkpoint basekv=12.47 pu=1 phases=3 bus1=sourcebus',
    'new transformer.tx phases=3 windings=2 buses=[sourcebus loadbus] conns=[wye wye] kvs=[12.47 .48] kvas=[500 500] xhl=1',
    'new load.x phases=3 bus1=loadbus conn=wye kv=.48 kw=100 kvar=30',
    'new regcontrol.rc transformer=tx winding=2 vreg=126 band=1 ptratio=2.309401076758503 delay=15 tapdelay=2 maxtapchange=1',
    'set mode=snapshot controlmode=time hour=0 sec=0 maxcontroliter=100 maxiter=15',
]
for command in commands:left.Text.Command(command)
left.Solution.SolveSnap()
assert left.Solution.Converged()
before=list(left.CtrlQueue.Queue());size=int(left.CtrlQueue.QueueSize())
assert size>0,'Native fixture must contain a pending delayed tap action'
serialized=left.Circuit.ToJSON(int(DSSJSONFlags.Full|DSSJSONFlags.SkipRedundant))
full_import_error=None;export_mode='Full|SkipRedundant'
try:
    right.Circuit.FromJSON(serialized)
except Exception as error:
    full_import_error=str(error);right.Basic.ClearAll()
    serialized=left.Circuit.ToJSON();export_mode='default'
    right.Circuit.FromJSON(serialized)
(out/'CIRCUIT_JSON.json').write_text(serialized,encoding='utf8')
restored=list(right.CtrlQueue.Queue());restored_size=int(right.CtrlQueue.QueueSize())
assert restored_size!=size,'If this changes, inspect whether runtime state export was added'
def tap(engine):
    engine.Transformers.Name('tx');engine.Transformers.Wdg(2)
    return float(engine.Transformers.Tap())
initial_taps=[tap(left),tap(right)]
for engine in [left,right]:
    engine.Solution.ControlMode(2);engine.Solution.Hour(0);engine.Solution.Seconds(15)
    engine.Solution.SolveSnap()
following_taps=[tap(left),tap(right)]
result=dict(UTC=now(),PASS=True,engine_version=left.Basic.Version(),source=record(__file__),
    fixture='Independent minimal native TIME RegControl; not an IEEE campaign equivalence result',
    export_mode=export_mode,Full_JSON_import_error=full_import_error,
    queue_count_before=size,queue_before=before,queue_count_after_JSON_restore=restored_size,queue_after=restored,
    taps_before_next_event=initial_taps,taps_after_same_15second_step=following_taps,
    same_next_tap=following_taps[0]==following_taps[1],
    conclusion='Circuit JSON roundtrip did not preserve native pending queue; it cannot be assumed to be an exact candidate checkpoint.',
    architecture='One committed observed history state per timestamp; independent exact checkpoint branches for candidates; rejected trials discarded; final independent Fresh once.',
    interim_path='Retain cheap native chronological solves while certifying/reusing identical historical audit evidence; validate separately before deployment.',
    production_source_or_process_changed=False,r016_handover_changed=False)
atomic(out/'RESULT.json',result)
print(json.dumps(result,ensure_ascii=False,indent=2))
left.Basic.ClearAll();right.Basic.ClearAll()
