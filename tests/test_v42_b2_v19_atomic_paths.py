from pathlib import Path
import json
from v42_b2_seed_recovery_v19 import common

def test_atomic_writer_uses_short_unique_temp_and_cleans_it(tmp_path,monkeypatch):
    target=tmp_path/('a'*140)/'MODEL_POLICY.json';seen=[]
    replace=common.replace_file
    def record(temp,destination):
        seen.append(Path(temp).name);replace(temp,destination)
    monkeypatch.setattr(common,'replace_file',record)
    common.atomic(target,dict(Native_Runtime=120.059,terminal_slot=96))
    assert common.read(target)['terminal_slot']==96
    assert len(seen[0])==37 and 'MODEL_POLICY' not in seen[0]
    assert len(list(target.parent.iterdir()))==1

def test_windows_writer_handles_deep_actual_stage_record_path(tmp_path):
    target=tmp_path/('b'*95)/('c'*95)/'FEASIBILITY_STAGES'/'F1_TERMINAL_REPAIRED_BEFORE_PEAK'/'MODEL_POLICY.json'
    common.atomic(target,{'PASS':True})
    assert json.loads(common.io_path(target).read_text(encoding='utf-8'))=={'PASS':True}
