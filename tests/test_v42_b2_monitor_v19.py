from test_v42_b2_monitor_v18 import fixture,write
from v42_b2_monitor_v18 import monitor
import json


def test_v19_monitor_selects_actual_dates_and_initialization_cap(tmp_path):
    nested=tmp_path/'initialization_benchmark_v19_01';root,attempt=fixture(nested)
    cp=json.loads((root/'CHECKPOINT_V17.json').read_text());manifest=json.loads((root/'CONTINUATION_V17_MANIFEST.json').read_text())
    manifest.update(benchmark_initialization_only=True,canary_days=['2025-05-03','2025-05-04'],initialization_native_limit_seconds=1500.)
    write(root/'CONTINUATION_V19_MANIFEST.json',manifest)
    request=json.loads((attempt/'request.json').read_text());request.update(day='2025-05-03',manifest=str(root/'CONTINUATION_V19_MANIFEST.json'))
    write(attempt/'request.json',request);cp['workers']={'2025-05-03':dict(request=str(attempt/'request.json'))}
    write(root/'CHECKPOINT_V19.json',cp)
    write(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=120.,calls=[],inflight=None))
    value=monitor.view(tmp_path)
    assert value['canary_label']=='May03/04' and value['runtime_root']==str(nested)
    assert value['workers'][0]['native_limit_seconds']==1500.
    assert value['workers'][0]['reported_native_remaining_seconds']==1380.
    assert value['worker_slots'][0]['day']=='2025-05-03'
    assert value['worker_slots'][1]['day']=='2025-05-04'
