"""Inspect the real P1-only release path; execution requires explicit files.

The default command never constructs a model or starts a solver/campaign.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.release_production_campaign import preflight,read,run_production,run_planning_p1,production_sources


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--planning-only',action='store_true',help='Only original A1/M1/A2/M2; no Actual/Fresh/K48 calls')
    p.add_argument('--plan',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--physical-gate',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--budget-ledger',type=Path)
    a=p.parse_args()
    plan=read(a.plan) if a.plan else dict(schema='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1',dates=['2025-05-01'],
        Worker=1,Threads=1,P2_calls=0,automatic_start=False,source_snapshot=production_sources())
    approval=read(a.approval) if a.approval else dict(approved=False)
    gate=read(a.physical_gate) if a.physical_gate else {}
    if not a.execute:
        print(json.dumps(preflight(plan,approval,gate,planning_only=a.planning_only),indent=2));return
    if not all((a.plan,a.approval,a.output,a.budget_ledger)):
        raise PermissionError('EXPLICIT_PLAN_NEW_APPROVAL_OUTPUT_AND_LEDGER_REQUIRED_NO_AUTOLAUNCH')
    if a.planning_only:
        print(json.dumps(run_planning_p1(plan,authorization=approval,folder=a.output,budget_ledger=a.budget_ledger),indent=2));return
    if not a.physical_gate:
        raise PermissionError('EXPLICIT_PLAN_NEW_APPROVAL_PHYSICAL_GATE_OUTPUT_AND_LEDGER_REQUIRED_NO_AUTOLAUNCH')
    ledger=read(a.budget_ledger) if plan.get('schema')=='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1' else a.budget_ledger
    print(json.dumps(run_production(plan,authorization=approval,gate=gate,folder=a.output,
        budget_ledger=ledger),indent=2))


if __name__=='__main__':main()
