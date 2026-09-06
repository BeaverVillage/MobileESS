"""Pre-registered DayAhead-only choice-domain diagnostics; no Actual imports."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.electrical import load
from dayahead.v41.reserve import bind
from dayahead.v41.common import build
from dayahead.v41.execution import science
from dayahead.v40g_segments.canonical import import_frozen,planning_power
from dayahead.v40g import optimizer
from dayahead.v40g.domain import Option


def main(mode):
    registration=read(OUT/'V41R1_ABLATION_REGISTRATION.json')
    assert mode in registration['modes']
    frozen=read(RUNTIME/'V41R1_SCIENTIFIC_REVISION_FREEZE.json')
    assert science()==frozen['science'] and record(__file__)==registration['runner']
    day='2025-05-01';context=load(day)
    snapshot=RUNTIME/'inputs'/day/f'V41_ML_SNAPSHOT_{day}.json'
    bind(context,snapshot,record(snapshot)['sha256'])
    reference,common=build(day,snapshot,context.capacity)
    pcc=planning_power(import_frozen(reference),context)['pcc']
    original=optimizer.options
    def choices(row,capacity,wan,elapsed,temporal_only=False):
        opts=original(row,capacity,wan,elapsed,temporal_only)
        if mode=='NO_RUNNING_MIGRATION':opts=tuple(o for o in opts if not o.migrated)
        if mode=='OLD_POST_H_FREEZE_WITH_PRE_D00_FIXED' and row['state_at_issue']=='PENDING' and row['end_slot']>120:
            ref=Option(row['AIDC_site'],row['start_slot'],row['end_slot'])
            opts=tuple(o for o in opts if o==ref)
        assert opts
        return opts
    out=RUNTIME/'diagnostics'/mode
    write_json(out/'EXPERIMENT_CONTRACT.json',dict(mode=mode,registration=record(OUT/'V41R1_ABLATION_REGISTRATION.json'),
        policy_execution=False,diagnostic_only=True,production_decisions_modified=False,Actual_reads=0,
        caveat='Inner solver PASS is an optimum certificate for this restricted diagnostic model, not a policy-phase acceptance.',
        lower_priority_tie_values_not_comparable_between_different_option_domains=True))
    optimizer.options=choices
    try:
        result=optimizer.solve(reference,pcc,context,out/'solve',temporal_only=mode=='TEMPORAL_ONLY')
        report=dict(mode=mode,diagnostic_only=True,Actual_reads=0,scientific_commit=frozen['scientific_commit'],
            registration=record(OUT/'V41R1_ABLATION_REGISTRATION.json'),
            result=record(out/'solve/ACCEPTED_AIDC.json'),rho=result['grid']['rho_max'],primary_bound=result['primary_bound'],
            primary_optimum=result['primary_optimum'],solver_stages=result['solver_stages'],
            snapshot=record(snapshot),common_reference_SHA=common['COMMON_DA_DURATION_SHA'])
        write_json(out/'DIAGNOSTIC_RESULT.json',report)
        print(mode,report['rho'],flush=True)
    finally:
        optimizer.options=original
        context.electrical.voltage.close();context.electrical.current.close()
    assert science()==frozen['science']


if __name__=='__main__':main(sys.argv[1])
