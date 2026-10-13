"""Create/check a byte-exact source snapshot and preserve historical controls."""
from pathlib import Path
import json
from .a_engine import digest
from .m_engine import file_record


def freeze_sources(output, root=None, *, science_version='V42_COMMON_AM_JOB_ACTUAL_EMPIRICAL_QOS_V1'):
    root=Path(root or Path(__file__).resolve().parents[1]).resolve()
    files=sorted(p for p in root.rglob('*.py') if p.parts[len(root.parts)].startswith('v42_')
        or p.parts[len(root.parts)] in ('tools','tests'))
    records=[file_record(p) for p in files]
    result=dict(schema='V42_COMMON_AM_INTEGRATION_SOURCE_FREEZE_V1',
        base_commit='12594e281bb89611331950f11f775a2612d3cb48',
        science_version=science_version,files=records,
        source_sha=digest({str(Path(r['path']).relative_to(root)):r['sha256'] for r in records}),
        campaign_HOLD=True,campaign_auto_restart_authorized=False,
        A_operational_seconds=5400,M_operational_seconds=1800,integration_total_solve_seconds=3600)
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf8')
    return result


def preservation_snapshot():
    root=Path('D:/v42_may_joint_repair_campaign_20261013')
    names=('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','STOP_REQUEST.json',
        'B2_CAMPAIGN_DIAGNOSTIC_STOP_RECEIPT.json','MONITOR_ADAPTER.py','MONITOR_ADAPTER_FREEZE.json')
    return dict(files=[file_record(root/name) for name in names],
        existing_B2_Native_seconds={'2025-05-01':1003.5010001659393,'2025-05-02':943.4019999504089},
        PR221_historical_research_seconds=1790.197,merged_into_integration_budget=False,
        monitor=dict(url='http://127.0.0.1:8793',PID=35740),new_scheduler_created=False)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--science-version',default='V42_COMMON_AM_JOB_ACTUAL_EMPIRICAL_QOS_V1')
    args=parser.parse_args();print(freeze_sources(args.output,science_version=args.science_version)['source_sha'])
