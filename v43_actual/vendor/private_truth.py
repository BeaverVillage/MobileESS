from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from v43_actual.io import checked, record
def require(value, reason):
    if not value: raise ValueError(reason)
def _resolve(receipt):
    return checked(receipt)


def _truth(population,archive):
    """Source-row private completion extraction, performed only after Freeze."""
    import pyarrow.parquet as pq
    wanted={};members={}
    for r in population:
        key=(r["source_member"],int(r["source_row"]));uid=r["job_uid"]
        require(key not in wanted or wanted[key]==uid,"B0_NEW_ACTUAL_SOURCE_ROW_CONFLICT")
        wanted[key]=uid;members.setdefault(key[0],set()).add(key[1])
    path=_resolve(archive);truth={}
    columns=["id","submit_time","start_time","end_time"]
    with zipfile.ZipFile(path) as z:
        for member,indices in sorted(members.items()):
            require(any(f"/year=2025/month={m}/" in member for m in (4,5)),"B0_NEW_RAW_MONTH_AUTHORITY_REQUIRED")
            with z.open(member) as stream:
                offset=0
                for batch in pq.ParquetFile(stream).iter_batches(columns=columns,batch_size=32768,use_threads=False):
                    frame=batch.to_pandas();frame["source_row"]=np.arange(offset,offset+len(frame));offset+=len(frame)
                    for r in frame[frame.source_row.isin(indices)].to_dict("records"):
                        uid=str(r["id"]);key=(member,int(r["source_row"]))
                        require(wanted[key]==uid and uid not in truth,"B0_NEW_EXACT_REALIZED_UID_SOURCE_JOIN")
                        start,end,submit=r["start_time"],r["end_time"],r["submit_time"]
                        require(pd.notna(start) and pd.notna(end) and end>=start>=submit,
                                "B0_NEW_REALIZED_SERVICE_MISSING_NO_IMPUTATION")
                        truth[uid]=dict(job_uid=uid,start_time=start.isoformat(),end_time=end.isoformat(),
                            realized_seconds=(end-start).total_seconds(),source_member=member,source_row=key[1],
                            source_SHA=archive["sha256"],private_future_duration_hidden_from_controller=True)
    require(set(truth)==set(wanted.values()),"B0_NEW_PRIVATE_SOURCE_REALIZATION_POPULATION_INCOMPLETE")
    return truth,record(path)
