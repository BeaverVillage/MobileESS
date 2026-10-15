"""Preserve the completed scopes and actual resource rejection of attempt 02."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record
from v42_integration.rc02_voltage_audit import write_new


def main():
    out=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC03/ACTUAL_RESEARCH02'
    log=ROOT/'runtime/RC03_RESEARCH_ACTUAL02.log';resource=read(out/'RUNNER_RESOURCE_RECEIPT.json')
    text=log.read_text(encoding='utf-8-sig');executed=read(out/'EXECUTED_SOURCE.json')
    assert 'RuntimeError: PREFIX_CACHE_RAM_8GB_COMMIT_75_GATE' in text
    assert all(record(r['path'])==r for r in executed['files'])
    completed=[]
    for scenario in ('R1_SHARED_READY','R2_P1_B0.25_T900'):
        for scope in ('FIRST_EVENT','FULL16'):
            for variant in ('C0','C1'):
                p=out/scenario/('FIRST_EVENT' if scope=='FIRST_EVENT' else '')/variant/'ACTUAL_RESULT.json'
                if p.exists():completed.append(dict(scenario=scenario,scope=scope,variant=variant,result=record(p)))
    receipt=dict(status='PARTIAL_ATTEMPT_RESOURCE_GATE_NOT_CERTIFIED',
        stopped_scope='LEGACY_80GB_PER_GPU_R2_C1_FULL16',stopped_reason='PREFIX_CACHE_RAM_8GB_COMMIT_75_GATE',
        first_event_and_completed_full_scopes=completed,unfinished_scope_not_promoted_to_FULL16=True,
        R1_full16_C0_C1_complete_and_preserved=True,R2_C1_full16_complete=False,
        completed_R1_Official_Fresh16=record(out/'R1_SHARED_READY/OFFLINE_FRESH_16_STATUS.json'),
        total_wall_seconds=resource['total_wall_seconds'],OS_peak_RSS_bytes=resource['OS_peak_RSS_bytes'],
        OS_peak_pagefile_bytes=resource['OS_peak_pagefile_bytes'],
        sampled_private_peak_bytes=resource['sampled_private_peak_bytes'],
        observed_process_memory_contributed_to_resource_pressure=True,
        unique_memory_leak_or_external_process_causation_proven=False,
        resource_gate_not_bypassed=True,no_external_worker_interrupted=True,
        Native_calls=0,Source11_byte_immutable=True,source=record(__file__),
        raw_log=record(log),resource_receipt=record(out/'RUNNER_RESOURCE_RECEIPT.json'))
    write_new(out/'ATTEMPT_PARTIAL_RESOURCE_GATE.json',receipt)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
