"""Preserve executed Source Rev1; check Rev2 admission-only fixes without solving."""
from pathlib import Path
import json
import shutil
import sys
import argparse
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.d0_case import REPORT,build_planning_inputs,require_case,read
from v42_integration.d0_a_planning import build_d0_native_model,write_d0_a_planning_audit
from v42_integration.d0_resource import native_binding
from v42_integration.unified_resource import UnifiedResearchBudget
from v42_integration.m_engine import _write,file_record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--revision',default='SOURCE_REV2',choices=('SOURCE_REV2','SOURCE_REV3','FINAL_NATIVE0'))
    revision=parser.parse_args().revision
    out=REPORT/revision
    if out.exists():raise FileExistsError('D0_SOURCE_REVISION_EVIDENCE_MUST_NOT_BE_OVERWRITTEN')
    out.mkdir()
    budget=UnifiedResearchBudget();before=read(budget.path)
    _write(out/'RESOURCE_BEFORE_NATIVE0_BUILD.json',budget.preflight())
    context=build_planning_inputs(output=out)
    case=context['make_a_case']('A1',folder=out/'NATIVE0_MATRIX')
    require_case(context['manifest'])
    import gurobipy as gp
    originals={name:getattr(gp.Model,name) for name in ('optimize','presolve','computeIIS')}
    attempts=[]
    def blocked(*args,**kwargs):
        attempts.append('FORBIDDEN_NATIVE');raise RuntimeError('D0_REVISION_NATIVE0_GUARD')
    built=None;began=perf_counter()
    try:
        for name in originals:setattr(gp.Model,name,blocked)
        built=build_d0_native_model(case,build_admission=dict(status='PASS',operation='D0_A_NATIVE0_BUILD',
            case_sha=case.case_sha,concurrent_heavy_solver=False))
        model=built[0];model.Params.Threads=1
        model.setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);model.update()
        current=native_binding(model)
        require_case(context['manifest'])
        previous=before['calls'][-1]['stage_context']['current_native_binding']
        assert all(current[k]==previous[k] for k in current)
        after=read(budget.path);assert before==after and not attempts
        proof=dict(status='PASS',scope='IDENTICAL_ORIGINAL_D0_P1_MATH_NOT_PRIMAL_OR_BOUND_TRANSFER',
            previous_identity=before['calls'][-1]['D0_identity'],current_identity=context['manifest']['identity'],
            source_revision_reason=['STRICT_NATIVE_OPTION_CLOCK','EXACT_BOOLEAN_FULL_FEASIBLE','FINITE_RETURN_RESERVE']+
                (['ORIGINAL_M_INTEGRATION_FLAT_STAGE_AND_ANCHOR_BINDING',
                  'ATOMIC_SUCCESSFUL_M1_REGISTRY_BEFORE_A2_HANDOFF'] if revision!='SOURCE_REV2' else []),
            previous_binding=previous,current_binding=current,Native_calls=0,blocked_attempts=attempts,
            canonical_ledger_unchanged=True,old_bound_or_point_transferred=False,
            current_FULL_primal='NOT_RUN',current_native_solve='NOT_RUN',wall_seconds=perf_counter()-began,
            executed_Source_snapshot=file_record(REPORT/'A1_PILOT01/EXECUTED_CASE/EXACT_EXECUTED_SOURCE_SNAPSHOT.json'))
        _write(out/'EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json',proof)
        matrix=built[-1];matrix['build_wall_seconds']=proof['wall_seconds']
        _write(out/'NATIVE0_MATRIX_RECEIPT.json',matrix)
        write_d0_a_planning_audit(out,context['classification'],context['input_audit'],matrix_receipt=matrix)
        for name in ('D0_CASE_MANIFEST.json','D0_INITIAL_STATE_AUTHORITY.json','D0_TIME_AXIS.json',
            'D0_BACKLOG_RESEARCH_CONTRACT.json','D0_CC4_FORECAST_RECEIPT.json','D0_SOURCE_FREEZE.json',
            'D0_PLANNING_INPUT_AUDIT.json','D0_KNOWN_BACKLOG_CLASSIFICATION.csv','D0_KNOWN_CC4_PLANNING_AUDIT.json'):
            shutil.copyfile(out/name,REPORT/name)
        print(json.dumps(proof,indent=2))
    finally:
        if built is not None:built[0].dispose()
        for name,method in originals.items():setattr(gp.Model,name,method)


if __name__=='__main__':main()
