#!/usr/bin/env python3
"""Fail-closed topology-aware 4-process x 4-thread CPU partition."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def groups_4x4() -> list[list[int]]:
    allowed = sorted(os.sched_getaffinity(0))
    by_core: dict[tuple[int, int], list[int]] = {}
    cpu_to_core: dict[int, tuple[int, int]] = {}
    for cpu in allowed:
        base = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        key = (int((base / "physical_package_id").read_text()), int((base / "core_id").read_text()))
        by_core.setdefault(key, []).append(cpu)
        cpu_to_core[cpu] = key
    cores = [sorted(v) for _, v in sorted(by_core.items())]
    if len(allowed) != 16 or len(cores) != 8 or any(len(v) != 2 for v in cores):
        raise RuntimeError(f"expected 16 logical CPUs as 8 SMT pairs; allowed={allowed} topology={cores}")
    primary = [v[0] for v in cores]
    sibling = [v[1] for v in cores]
    layout = [primary[:4], primary[4:8], sibling[:2] + sibling[4:6], sibling[2:4] + sibling[6:8]]
    if sorted(x for group in layout for x in group) != allowed:
        raise RuntimeError("CPU partition is not a disjoint cover of the allowed affinity")
    if any(len({cpu_to_core[cpu] for cpu in group}) != 4 for group in layout):
        raise RuntimeError("a worker group contains SMT siblings from the same physical core")
    return layout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plain", action="store_true")
    args = ap.parse_args()
    groups = groups_4x4()
    if args.plain:
        for group in groups:
            print(",".join(map(str, group)))
    else:
        print(json.dumps({"status": "PASS", "groups": groups, "threads_per_process": 4}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
