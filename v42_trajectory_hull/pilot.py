"""One pre-registered 600-second cumulative-native DW research pilot."""
from pathlib import Path
from time import perf_counter
from fractions import Fraction as F
import argparse
import json
import os
import tempfile
import subprocess
import numpy as np
from v42_m1_hybrid.pricing import make_prices
from v42_m1_hybrid.dw import build_master
from .case import load, read
from .budget import Budget, write
from .pricing import integer_price
from .certificate import check_global, rounded_down


def run(spec, output):
    start = perf_counter()
    budget = Budget(output)
    output = budget.output
    producer = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    write(output/'PRODUCER.json', dict(head=producer, baseline=spec['source_head'],
                                      preregistered_configuration='PREREGISTRATION.json'))
    temporary = output/'tmp'
    temporary.mkdir()
    os.environ.update(TEMP=str(temporary), TMP=str(temporary))
    tempfile.tempdir = str(temporary)
    case, decomp, full, admission = load(spec)
    write(output/'ORIGINAL_ADMISSION.json', admission)
    old = F(admission['baseline']['exact_bound'])
    best = old
    catalog = {unit:[] for unit in decomp.units}
    results = []
    eta = None
    write(output/'MODEL_SIZE_ESTIMATE.json', dict(
        master_rows=len(decomp.nonunit_block.original_rows)+len(decomp.coupling_rows)+4,
        master_nonunit_columns=len(decomp.nonunit_columns),
        master_columns_formula='nonunit_columns + generated_column_count',
        trajectory_catalog_preallocated=False,
        local_pricing={u:dict(rows=b.A.shape[0], columns=b.A.shape[1], nnz=b.A.nnz,
                             binary_columns=int(np.sum(b.d['types']=='B')))
                       for u,b in decomp.units.items()}))
    stop = 'MAX_REGISTERED_ROUNDS'
    # This is one dynamic CG pilot, not repeated independent experiments.
    for iteration in range(3):
        if budget.used > 560:
            stop = 'NATIVE_BUDGET_FRONTIER_RETAINED'
            break
        prices = make_prices(case, decomp, full)
        packet = dict(case_sha=case.case_sha, coupling_dual=prices.coupling_dual,
                      nonunit_dual=prices.seed_nonunit_dual, units={})
        for unit, block in decomp.units.items():
            if budget.used > 590:
                # The seed signed dual is already a complete-domain LP lower bound.
                packet['units'][unit] = dict(exact_price={str(j):str(v) for j,v in prices.exact_objectives[unit].items()},
                    tree={'r':dict(fixes={}, proof=dict(kind='DUAL',dual=prices.seed_unit_duals[unit]),split=None)},
                    integer_optimum='NOT_PROVEN')
                continue
            record = integer_price(block,
                {str(j):str(v) for j,v in prices.exact_objectives[unit].items()},
                prices.seed_unit_duals[unit], case.point[block.original_columns], budget,
                output/f'round_{iteration}'/unit, label=f'R{iteration}_{unit}')
            packet['units'][unit] = record
            catalog[unit].extend(record['columns'])
        begin = perf_counter()
        exact = check_global(case, decomp, packet)
        if eta is not None:
            reduced = {u:str(F(exact['exact_integer_price_bounds'][u])-F(eta[u])) for u in decomp.units}
            exact['missing_trajectory_reduced_cost_lower_bounds'] = reduced
            exact['pricing_closure_at_current_prices'] = ('PASS' if all(F(v)>=0 for v in reduced.values())
                                                         else 'NOT_PROVEN')
        budget.certificate_seconds += perf_counter()-begin
        best = max(best, F(exact['exact_bound']))
        write(output/f'round_{iteration}_CERTIFICATE_PACKET.json', packet)
        write(output/f'round_{iteration}_EXACT_GLOBAL_LB.json', exact)
        results.append(dict(round=iteration, certificate=exact))
        if exact.get('pricing_closure_at_current_prices') == 'PASS':
            stop = 'MISSING_INTEGER_TRAJECTORY_CLOSURE_CERTIFIED_AT_CURRENT_PRICES'
            break
        if budget.used > 570 or iteration == 2:
            stop = 'NATIVE_BUDGET_OR_ROUND_LIMIT'
            break
        begin = perf_counter()
        model, variables, rows, identity, source_rows = build_master(
            case, decomp, catalog, output/f'round_{iteration}'/'master')
        budget.build_seconds += perf_counter()-begin
        try:
            model.Params.OutputFlag = 0
            master = budget.optimize(model, f'R{iteration}_MASTER', min(90., 590.-budget.used))
            record = dict(native=master, identity=identity, objective_authority=False,
                          pricing_closure='NOT_PROVEN')
            if int(model.Status) != 2:
                stop = 'MASTER_NOT_OPTIMAL_NO_RAW_DUAL_PROMOTION'
                write(output/f'round_{iteration}_MASTER_RESULT.json', record)
                break
            pi = np.asarray(rows.Pi)
            senses = case.d['sense'][source_rows]
            bad = ((senses=='<') & (pi[:len(source_rows)]>0)) | ((senses=='>') & (pi[:len(source_rows)]<0))
            record['invalid_dual_signs'] = int(bad.sum())
            if not np.isfinite(pi).all() or bad.any():
                stop = 'MASTER_DUAL_SIGN_GATE_FAIL'
                write(output/f'round_{iteration}_MASTER_RESULT.json', record)
                break
            # Raw master coefficients are diagnostic. Reconstruct prices on original rows.
            full = {str(int(i)):str(F(float(v))) for i,v in zip(source_rows,pi) if v}
            for unit, block in decomp.units.items():
                for k, v in prices.seed_unit_duals[unit].items():
                    full[str(int(block.original_rows[int(k)]))] = v
            eta = {unit:str(F(float(pi[len(source_rows)+j]))) for j,unit in enumerate(decomp.units)}
            record.update(convexity_prices=eta, native_objective_diagnostic=float(model.ObjVal))
            write(output/f'round_{iteration}_MASTER_RESULT.json', record)
            write(output/f'round_{iteration}_NEXT_ORIGINAL_PRICES.json', full)
        finally:
            model.dispose()
    ub = F(spec['ub_exact'])
    required = F(97,100)*ub
    result = dict(case_sha=case.case_sha, stage=spec['stage'], old_exact_LB=str(old),
        new_exact_LB=str(best), Certified_Global_LB=rounded_down(best),
        Certified_Delta_LB=rounded_down(best-old), Global_Gap_percent=float(100*(ub-best)/ub),
        target_gap_percent=3, required_LB_for_3pct=str(required),
        additional_LB_required=rounded_down(max(F(0),required-best)),
        pricing_integer_optimality='NOT_PROVEN',
        missing_trajectory_closure=results[-1]['certificate'].get('pricing_closure_at_current_prices','NOT_PROVEN'),
        full_DW_optimality='NOT_PROVEN',
        result='MATERIAL_CERTIFIED_GAIN' if best-old>=F('0.001') else 'NO_MATERIAL_GAIN',
        stop_reason=stop, native_runtime=budget.used, native_calls=len(budget.calls),
        model_build_seconds=budget.build_seconds, independent_certificate_seconds=budget.certificate_seconds,
        wall_seconds=perf_counter()-start, rounds=results,
        B3_M1='NOT_RUN_NO_CURRENT_FIXED_INPUT', B3_M2='NOT_RUN_NO_CURRENT_FIXED_INPUT',
        production_promoted=False, production_native_contract_seconds=5400)
    write(output/'RESULT.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(read(args.spec), args.output)
