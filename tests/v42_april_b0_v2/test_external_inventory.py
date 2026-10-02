import io
import json
import zipfile
from pathlib import Path
from docs.v42_april_b0_voltage_margin_calibration_v2 import scan_external as scan


def test_schema_discovers_resource_fields_in_later_JSON_rows():
    data=[{'job_uid':'x'}, {'job_uid':'y','submission_time':'2025-04-01T00:00:00Z','request':{'ReqTRES':'gres/gpu=3'}}]
    result=scan.schema(io.BytesIO(json.dumps(data).encode()),'jobs.json')
    assert '[].request.ReqTRES' in result['columns']
    assert '[].request.ReqTRES' in result['GPU_related_fields']


def test_archive_members_are_inspected_without_extracting_raw_files(tmp_path,monkeypatch):
    monkeypatch.setattr(scan,'RAW_ROOT',tmp_path)
    archive=tmp_path/'accounting.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('jobs.csv','job_uid,submit_time,ReqGRES\nj,2025-04-01T00:00:00Z,gpu:h100:2\n')
        z.writestr('another/jobs.json',json.dumps([{'RegTRES':'unknown semantics','job_uid':'k'}]))
    result=scan.inspect_file(archive)
    assert result['SHA256'] and len(result['archive_members'])==2
    assert result['archive_members'][0]['GPU_related_fields']==['ReqGRES']
    assert set(tmp_path.iterdir())=={archive}


def test_unreadable_source_is_recorded_not_silently_discarded(tmp_path,monkeypatch):
    monkeypatch.setattr(scan,'RAW_ROOT',tmp_path)
    result=scan.inspect_file(tmp_path/'missing.parquet')
    assert result['status']=='READ_ERROR' and result['SHA256'] is None and result['errors']


def test_path_metadata_is_not_claimed_as_row_date_coverage():
    assert scan.coverage('year=2025/month=4/jobs.parquet')['status']=='PATH_METADATA_ONLY'
    assert scan.coverage('unknown.csv')['status']=='NOT_DECLARED'
