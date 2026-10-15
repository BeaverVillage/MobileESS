"""One admitted Table V Actual/Fresh run; no native optimizer is entered."""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.release_date_case import load_date_case
from v42_integration.table_v_flex_planning import compile_table_v_flex_context
from v42_integration.tablev_actual import run_tablev_actual,run_tablev_fresh
from v42_integration.actual_validation import read
from v42_integration.release_ac_contract import CONTRACT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-case',type=Path,required=True)
    parser.add_argument('--flex-case',type=Path,required=True)
    parser.add_argument('--reference-result',type=Path,required=True)
    parser.add_argument('--reference-acceptance',type=Path,required=True)
    parser.add_argument('--arm',choices=('B0','B1','B2','B3'),required=True)
    parser.add_argument('--m-result',type=Path)
    parser.add_argument('--m-acceptance',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--slots',type=int,choices=(16,96),default=96)
    parser.add_argument('--actual-only',action='store_true')
    args=parser.parse_args()
    base=load_date_case('2025-05-01',args.base_case)
    with TemporaryDirectory(prefix='tablev_public_context_') as temporary:
        context=compile_table_v_flex_context(base,output=Path(temporary)/'FULL_FLEX')
        if context['manifest']!=read(args.flex_case/'TABLE_V_FLEX_CASE_MANIFEST.json'):
            raise ValueError('TABLE_V_EXECUTION_REQUIRES_EXACT_FROZEN_FULL_FLEX_CONTEXT')
        m=read(args.m_result) if args.m_result else None
        ma=read(args.m_acceptance) if args.m_acceptance else None
        actual=run_tablev_actual(context=context,arm=args.arm,reference_result=read(args.reference_result),
            reference_acceptance=read(args.reference_acceptance),m_result=m,m_acceptance=ma,
            output=args.output/'ACTUAL',slots=args.slots,
            gate=dict(Gate_contract=CONTRACT,official_contract_authorized=True))
        print('TABLE_V_ACTUAL_COMPLETE',actual['status'],flush=True)
        if not args.actual_only:
            fresh=run_tablev_fresh(context=context,actual_result=actual,output=args.output/'FRESH',
                m_result=m,m_acceptance=ma,slots=args.slots)
            print('TABLE_V_FRESH_COMPLETE',fresh['status'],flush=True)


if __name__=='__main__':main()
