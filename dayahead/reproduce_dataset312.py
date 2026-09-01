"""Raw NVML + RAPL-package reproduction of frozen Dataset312 kappa."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from .aidc_power_response import CPU_SOCKET_IDLE_W, CPU_SOCKETS_PER_NODE, GPU_IDLE_W, GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file

RAPL_COLUMNS = ["timestamp", "reading-time[ns]", "cpu-0[uJ]", "cpu-0-core[uJ]", "cpu-1[uJ]", "cpu-1-core[uJ]", "cpu-0[W]", "cpu-0-core[W]", "cpu-1[W]", "cpu-1-core[W]"]


def _find(raw_root: Path) -> Path:
    for path in sorted(raw_root.rglob("dataset.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                if "01_aggregated_datasets/training/metadata.csv" not in archive.namelist():
                    continue
            if sha256_file(path) != NLR_SOURCE_SHA256["dataset312_zip"]:
                raise RuntimeError("FAIL_DATASET312_SHA_MISMATCH")
            return path
        except zipfile.BadZipFile:
            continue
    raise RuntimeError("DATASET312_RAW_NOT_FOUND")


def reproduce(raw_root: Path = DEFAULT_RAW_ROOT) -> dict[str, object]:
    import pandas as pd
    pattern=re.compile(r"^00_raw_datasets/training_(?P<model>.+?)/(?P<nodes>\d+)node/(?P<device>nvml|rapl)_.*?slurmid_(?P<slurmid>\d+)_node_(?P<node>[^/]+)\.log$")
    path=_find(raw_root); groups=defaultdict(lambda:{"nvml":[],"rapl":[]})
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            match=pattern.match(name)
            if match and int(match.group("nodes")) in KAPPA_KW_PER_ACTIVE_H100_NODE:
                groups[(match.group("model"),int(match.group("nodes")),match.group("slurmid"))][match.group("device")].append(name)
        by_nodes=defaultdict(list); core_diagnostic=defaultdict(list); parsed_runs=0
        for (_model,nodes,_slurmid),members in sorted(groups.items()):
            if len(members["nvml"]) != nodes or len(members["rapl"]) != nodes:
                continue
            gpu_w=0.0; package_w=0.0; core_w=0.0
            for member in sorted(members["nvml"]):
                with archive.open(member) as stream:
                    header=stream.readline().decode("utf-8",errors="replace").replace("# ","").strip().split()
                    frame=pd.read_csv(stream,sep=r"\s+",header=None,names=header,comment="#",low_memory=False)
                cols=[f"gpu-{index}[mW]" for index in range(4)]
                gpu_w += float(frame[cols].apply(pd.to_numeric,errors="coerce").sum(axis=1).dropna().mean()/1000.0)
            for member in sorted(members["rapl"]):
                with archive.open(member) as stream:
                    frame=pd.read_csv(stream,sep=r"\s+",header=None,names=RAPL_COLUMNS,comment="#",low_memory=False)
                package_w += float(frame[["cpu-0[W]","cpu-1[W]"]].apply(pd.to_numeric,errors="coerce").sum(axis=1).dropna().mean())
                core_w += float(frame[["cpu-0-core[W]","cpu-1-core[W]"]].apply(pd.to_numeric,errors="coerce").sum(axis=1).dropna().mean())
            incremental=(gpu_w-nodes*GPU_PER_NODE*GPU_IDLE_W + package_w-nodes*CPU_SOCKETS_PER_NODE*CPU_SOCKET_IDLE_W)/1000.0/nodes
            by_nodes[nodes].append(incremental); core_diagnostic[nodes].append(core_w); parsed_runs += 1
    reproduced={nodes:statistics.median(values) for nodes,values in sorted(by_nodes.items())}
    failures=[nodes for nodes,expected in KAPPA_KW_PER_ACTIVE_H100_NODE.items() if nodes not in reproduced or abs(reproduced[nodes]-expected)>1e-12]
    return {"authority_id":"NLR_D312_INCREMENTAL_POWER_V1", "source_sha256":sha256_file(path), "parsed_complete_runs":parsed_runs, "kappa_kw_per_active_h100_node":reproduced, "rapl_cpu_domain":"PACKAGE_ONLY", "cpu_core_subdomain_role":"DIAGNOSTIC_NOT_ADDED", "cpu_core_median_w":{nodes:statistics.median(values) for nodes,values in core_diagnostic.items()}, "status":"PASS" if not failures else "FAIL", "failed_node_classes":failures}


def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--raw-root",type=Path,default=DEFAULT_RAW_ROOT); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args(argv)
    result=reproduce(args.raw_root); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps({"status":result["status"],"failed_node_classes":result["failed_node_classes"]})); return 0 if result["status"]=="PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
