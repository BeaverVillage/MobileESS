"""Recover recorded request descriptors only; never read start/end/runtime."""
from dataclasses import replace
from pathlib import Path
import math
import zipfile

from v43.common import read,record,verify_records,atomic,ROOT
from v43_actual.case import BUNDLE
from v43_actual.io import checked

COLUMNS=('id','submit_time','gpus_requested','qos','partition','wallclock_req')
PROTECTION_RULE='EXISTING_V42_MAY01_QOS_NORMAL_STANDBY_ELSE_PROTECTED'


def build(destination):
    """Offline immutable input adapter. Controllers see each row at arrival."""
    import pyarrow.parquet as pq
    destination=Path(destination)
    if destination.exists():
        saved=read(destination);verify_records(saved['sources']);return saved
    bundle=read(BUNDLE/'ACTUAL_INPUT_BUNDLE.json');provenance=read(BUNDLE/'SOURCE_PROVENANCE.json')
    source=provenance['archive'];path=checked(source);members={}
    for r in bundle['post_issue_arrivals']:
        members.setdefault(r['source_member'],{})[int(r['source_row'])]=r
    records={}
    with zipfile.ZipFile(path) as archive:
        for member,wanted in sorted(members.items()):
            offset=0
            with archive.open(member) as stream:
                for batch in pq.ParquetFile(stream).iter_batches(columns=list(COLUMNS),batch_size=32768,use_threads=False):
                    # A projection at the reader excludes private outcome
                    # columns, even though they exist in the same archive.
                    for index,row in enumerate(batch.to_pylist(),offset):
                        if index not in wanted:continue
                        expected=wanted[index];uid=str(row['id'])
                        if uid!=expected['job_uid'] or uid in records:raise ValueError('REQUEST_DESCRIPTOR_EXACT_ROW_UID_JOIN')
                        submit=row['submit_time'].timestamp()
                        if submit!=__import__('datetime').datetime.fromisoformat(expected['submit_time']).timestamp():
                            raise ValueError('REQUEST_DESCRIPTOR_SUBMIT_DRIFT')
                        if int(row['gpus_requested'])!=expected['GPU_gang']:raise ValueError('REQUEST_DESCRIPTOR_GPU_DRIFT')
                        qos=str(row['qos']).lower();wall=row['wallclock_req'].total_seconds()
                        if not math.isfinite(wall) or wall<=0:raise ValueError('REQUESTED_WALLTIME_INVALID')
                        records[uid]=dict(uid=uid,submit_seconds=submit,qos=qos,partition=str(row['partition']),
                            requested_walltime_seconds=wall,protected=qos not in ('normal','standby'),
                            source_member=member,source_row=index,protection_rule=PROTECTION_RULE,
                            Source_protection_flag_observed=False,protection_is_existing_research_classification=True,
                            source_descriptor_history='UNVERIFIED_SOURCE_PROXY_NOT_HISTORICAL_VERSION_CERTIFICATE')
                    offset+=batch.num_rows
    if set(records)!={r['job_uid'] for r in bundle['post_issue_arrivals']}:raise ValueError('REQUEST_DESCRIPTOR_JOIN_INCOMPLETE')
    doc=dict(columns_read=list(COLUMNS),private_outcome_columns_read=[],
        sources=[record(BUNDLE/'ACTUAL_INPUT_BUNDLE.json'),source,record(ROOT/'v42_may01/state.py')],
        descriptors=records,participant_selection_performed=False,
        research_classification_not_customer_Source_permission=True)
    atomic(destination,doc);return doc


def attach(args,document):
    updated=[]
    for request in args['requests']:
        if request.metadata.get('origin_unknown') is not True:
            updated.append(request);continue
        row=document['descriptors'][request.uid]
        if row['submit_seconds']!=request.submit:raise ValueError('ARRIVAL_DESCRIPTOR_SUBMIT_DRIFT')
        m=dict(request.metadata)
        # Preserve any explicit source protection already present. No Known
        # attributes, Q50 values, UID classes or submission times change.
        m['qos']=row['qos'] if m.get('qos') in (None,'UNCONFIRMED') else m['qos']
        m['partition']=m.get('partition') or row['partition']
        m['requested_walltime_seconds']=m.get('requested_walltime_seconds') or row['requested_walltime_seconds']
        m['protected']=row['protected'] if m.get('protected') is None else m['protected']
        m['recorded_request_descriptor']=dict(row)
        updated.append(replace(request,metadata=m))
    args['requests']=updated
