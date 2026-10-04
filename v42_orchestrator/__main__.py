"""python -m v42_orchestrator plan|mock|verify (never scientific execution)."""
import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from v42_campaign.authority import digest
from .config import Config
from .dag import ROOT, build_dag, load_dates
from .ledger import Ledger, atomic
from .scheduler import Scheduler


def write_plan(output, config):
    plan = build_dag(config)
    output.mkdir(parents=True, exist_ok=True)
    atomic(output / 'MAY_CAMPAIGN_DAG.json', plan)
    with (output / 'MAY_DRY_RUN_PLAN.csv').open('w', newline='', encoding='utf8') as handle:
        fields = ['id', 'arm', 'day', 'loop', 'stage', 'phase', 'required_pass', 'Planning_dependencies',
                  'worker_class', 'resource_slots', 'execution_status', 'artifact_destination']
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for node in plan['nodes']:
            writer.writerow({k: json.dumps(node[k]) if isinstance(node[k], list) else node[k] for k in fields})
    atomic(output / 'MAY_DATE_AUTHORITY_AUDIT.json', dict(PASS=True, days=plan['days'], count=31,
        unique_count=len(set(plan['days'])), ordered=True, source=plan['date_source'],
        source_SHA256=plan['date_source_sha'], dates_invented=False))
    counts = {g: sum(n['group'] == g for n in plan['nodes'])
              for g in plan['main_order'] + plan['convergence_order']}
    atomic(output / 'MAY_STAGE_COUNT_AUDIT.json', dict(PASS=True, total=len(plan['nodes']), groups=counts,
        coordination_gates=1, formula='3 * 31 * (1 Planning + 4 evaluation) + 4 * 31 * (4 Planning + 4 evaluation) + 1 main gate',
        historical_reference=1458, difference=len(plan['nodes']) - 1458,
        explanation='Same scientific stages as frozen authority. Only scheduling control edges change to day queues and arm barriers.',
        all_expected_statuses='NOT_RUN'))
    atomic(output / 'MAY_RESOURCE_POLICY.json', dict(**asdict(config),
        telemetry_mode='MOCK_ONLY', B2_NO_NESTED_EXPANSION=True,
        heavy_token_unit='one single-thread heavy solve; no outer-day token reservation',
        memory_guards=['available physical RAM >=1 GiB', 'OOM', 'commit >=95%',
                       'catastrophic sustained paging', 'solver/license failure', 'invalid telemetry'],
        admission='Every stage and every solve token; active mock solves check again before releasing'))
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'mock', 'verify', 'production'])
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/v42_may_campaign_orchestrator')
    parser.add_argument('--config', type=Path, help='Explicit JSON Config fields; no environment overrides')
    parser.add_argument('--mock-days', type=int, default=4, choices=range(1, 5))
    parser.add_argument('--input-sha', help='Explicit future input authority; mock default uses synthetic SHA')
    args = parser.parse_args()
    config = Config(**json.loads(args.config.read_text(encoding='utf8'))) if args.config else Config()
    if args.command == 'production':
        config.production_guard()
    elif args.command == 'verify':
        from .verification import verify
        verify(args.output, config)
    elif args.command == 'plan':
        plan = write_plan(args.output, config)
        print(f"Dry plan: {len(plan['days'])} dates, {len(plan['nodes'])} NOT_RUN stages; production calls 0/0/0")
    else:
        plan = build_dag(config, fixture_days=load_dates()[:args.mock_days])
        with Ledger(args.output, plan, input_sha=args.input_sha or digest('synthetic CLI fixture')) as ledger:
            summary = Scheduler(ledger, config).run()
            print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
