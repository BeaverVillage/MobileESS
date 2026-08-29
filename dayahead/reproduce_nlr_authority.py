"""Focused raw-source reproduction of the V7 sharing and V16 volume gates."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence

from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file

EXPECTED_SHARING = {
    "total_valid_H100_jobs": 279456,
    "share_count_NULL": 58229,
    "share_count_ZERO": 0,
    "share_count_POSITIVE": 221227,
    "triple_no_share_evidence": 58229,
    "positive_share_evidence": 221227,
    "sharing_conflicts": 0,
}
EXPECTED_PERIODS = {
    "TRAIN_2024AUG19_2025MAR31": (31993, 98.35393621883169, 0.19231559314722785),
    "VALIDATION_2025APR": (3541, 22.82939363233247, 0.14918647550897673),
    "PRIMARY_2025MAY": (3123, 31.859787525160876, 0.17600187342556192),
    "REPLICATION_2025JUN01_25": (3742, 17.8815071201498, 0.18458121626311927),
}
KAPPA_GPU = {
    1: 2.1816052764508407, 2: 2.090650297635585, 4: 1.9732668756360066,
    8: 1.8939576000745455, 16: 1.8394878438844762,
}


def object_empty(value: object) -> bool:
    try:
        import pandas as pd
        if pd.isna(value) is True:
            return True
    except (ImportError, TypeError, ValueError):
        pass
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    try:
        return len(value) == 0  # numpy arrays
    except TypeError:
        return str(value).strip().casefold() in {"", "[]", "{}", "null", "none", "nan", "<na>"}


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _find_kestrel(raw_root: Path) -> Path:
    matches = sorted(raw_root.rglob("esif.hpc.kestrel.job-anon.zip"))
    if not matches or any(sha256_file(path) != NLR_SOURCE_SHA256["kestrel_jobs_zip"] for path in matches):
        raise RuntimeError("FAIL_KESTREL_RAW_SHA_REPRODUCTION")
    return matches[0]


def reproduce(raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, object]:
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq
    from zoneinfo import ZoneInfo

    mountain = ZoneInfo("America/Denver")
    periods = {
        "TRAIN_2024AUG19_2025MAR31": (pd.Timestamp("2024-08-19", tz=mountain), pd.Timestamp("2025-04-01", tz=mountain)),
        "VALIDATION_2025APR": (pd.Timestamp("2025-04-01", tz=mountain), pd.Timestamp("2025-05-01", tz=mountain)),
        "PRIMARY_2025MAY": (pd.Timestamp("2025-05-01", tz=mountain), pd.Timestamp("2025-06-01", tz=mountain)),
        "REPLICATION_2025JUN01_25": (pd.Timestamp("2025-06-01", tz=mountain), pd.Timestamp("2025-06-26", tz=mountain)),
    }
    overall_start = min(value[0] for value in periods.values()).tz_convert("UTC")
    overall_end = max(value[1] for value in periods.values()).tz_convert("UTC")
    counts = {key: 0 for key in EXPECTED_SHARING}
    retained = []
    kestrel = _find_kestrel(raw_root)
    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(prefix="nlr-v16-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in archive.infolist():
            if not info.filename.casefold().endswith(".parquet"):
                continue
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if not match or not (202408 <= int(match.group(1)) * 100 + int(match.group(2)) <= 202506):
                continue
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = set(pq.ParquetFile(local).schema_arrow.names)
            required = {"partition", "state_simple", "start_time", "end_time", "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared"}
            if not required.issubset(schema):
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{sorted(required-schema)}")
            frame = pq.read_table(local, columns=sorted(required)).to_pandas()
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            valid = frame["partition"].apply(_h100) & frame["state_simple"].astype(str).str.upper().eq("COMPLETED") & start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
            x = frame.loc[valid, ["nodes_shared", "jobs_shared"]].copy()
            x["start_utc"] = start[valid]; x["end_utc"] = end[valid]; x["nodes"] = nodes[valid]; x["gpus"] = gpus[valid]; x["share"] = sharing[valid]
            ne = x["nodes_shared"].apply(object_empty); je = x["jobs_shared"].apply(object_empty)
            null = x["share"].isna(); zero = x["share"].eq(0); positive = x["share"].gt(0)
            no_share = (null | zero) & ne & je
            positive_evidence = positive | ~ne | ~je
            conflict = no_share & positive_evidence
            counts["total_valid_H100_jobs"] += len(x)
            counts["share_count_NULL"] += int(null.sum()); counts["share_count_ZERO"] += int(zero.sum()); counts["share_count_POSITIVE"] += int(positive.sum())
            counts["triple_no_share_evidence"] += int(no_share.sum()); counts["positive_share_evidence"] += int(positive_evidence.sum()); counts["sharing_conflicts"] += int(conflict.sum())
            eligible = np.isclose(x["gpus"], 4 * x["nodes"]) & x["nodes"].isin(KAPPA_KW_PER_ACTIVE_H100_NODE) & no_share & ~conflict
            y = x.loc[eligible, ["start_utc", "end_utc", "nodes", "gpus"]]
            y = y[y["end_utc"].gt(overall_start) & y["start_utc"].lt(overall_end)]
            if len(y): retained.append(y)
    jobs = pd.concat(retained, ignore_index=True)
    period_results = {}
    for name, (local_start, local_end) in periods.items():
        start = local_start.tz_convert("UTC"); end = local_end.tz_convert("UTC")
        x = jobs[jobs["end_utc"].gt(start) & jobs["start_utc"].lt(end)]
        slots = pd.date_range(start, end, freq="15min", inclusive="left")
        power = np.zeros(len(slots)); energy_kwh = 0.0; node_hours = 0.0
        for row in x.itertuples(index=False):
            a=max(start,row.start_utc); b=min(end,row.end_utc); duration=(b-a).total_seconds()/3600.0
            nodes_i=int(row.nodes); p=float(nodes_i*KAPPA_KW_PER_ACTIVE_H100_NODE[nodes_i])
            energy_kwh += p*duration; node_hours += nodes_i*duration
            slot=a.floor("15min")
            while slot < b:
                slot_end=slot+pd.Timedelta(minutes=15); overlap=max(0.0,(min(b,slot_end)-max(a,slot)).total_seconds())
                index=int((slot-start).total_seconds()//900)
                if 0 <= index < len(power): power[index] += p*overlap/900.0
                slot=slot_end
        period_results[name] = {"eligible_jobs": int(len(x)), "node_hours": float(node_hours), "incremental_total_energy_MWh": energy_kwh/1000.0, "peak_15min_total_MW": float(power.max()/1000.0)}
    failures=[]
    if counts != EXPECTED_SHARING: failures.append("SHARING_COUNTS_MISMATCH")
    for name,(jobs_expected,energy_expected,peak_expected) in EXPECTED_PERIODS.items():
        actual=period_results[name]
        if actual["eligible_jobs"] != jobs_expected or abs(actual["incremental_total_energy_MWh"]-energy_expected)>1e-9 or abs(actual["peak_15min_total_MW"]-peak_expected)>1e-9:
            failures.append(f"PERIOD_REPRODUCTION_MISMATCH:{name}")
    return {"authority_id":"NLR_V16_RAW_REPRODUCTION", "raw_kestrel_sha256":sha256_file(kestrel), "sharing":counts, "periods":period_results, "status":"PASS" if not failures else "FAIL", "failures":failures}


def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--raw-root",type=Path,default=DEFAULT_RAW_ROOT); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args(argv)
    result=reproduce(args.raw_root); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps({"status":result["status"],"failures":result["failures"]})); return 0 if result["status"]=="PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
