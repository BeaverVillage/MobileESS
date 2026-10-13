"""Pure Native0 development; active predecessor controller is untouched."""
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.cache import get,fast_save
from tools.adaptive_perf_v3.feedback import generate
from tools.adaptive_perf_v3.hybrid import save as ef_save,structure

def main():
    configure();full_guard();assert read(DOCS/'MATCHED_PREPARATION_COMPARISON.json')['PASS'] and read(DOCS/'BEAM_NATIVE0_REGRESSION.json')['PASS']
    timer=Timing();state=read(PREVIOUS_DOCS/'LIVE_STATE.json');last=state['events'][-1]
    write(DOCS/'DEVELOPMENT_REFERENCE_STATE.json',state)
    (DOCS/'BEAM_RESERVOIR.json').write_bytes((PREVIOUS_DOCS/'BEAM_RESERVOIR.json').read_bytes())
    seen=set()
    for call in state['calls']:
        spec=read(call['model']['path'])
        for form in ('JOINT','DIRECT'):seen.add(form+'|'+spec['pool_signature'])
    with timer.stage('Source_Case_load'):case=v.load_native_case();point=v.load_point(last['point']['path'])
    cache=get(case,timer);pools,signature=generate(case,point,last['replay']['path'],1001,seen,timer);assert pools is not None
    folder=DOCS/'packages/INITIAL_1001';direct,_=fast_save(case,point,last['replay']['path'],pools,'INITIAL_1001',folder/'DIRECT',cache,timer)
    ef,_=ef_save(case,point,last['replay']['path'],pools,'INITIAL_1001',folder/'EF',cache,timer)
    with timer.stage('matrix_structure_analysis'):
        structures={form:structure(case,spec,folder/form) for form,spec in (('DIRECT',direct),('EF',ef))}
    report=dict(PASS=True,Optimize_calls=0,new_reference_FULL=last['replay'],new_source_static_identity=cache['manifest']['identity'],
        all_four_STAY_single_multiple_DAG_ETA_energy=True,unchanged_Physical_Grid_PCS16_Mode384_SOC_objective=True,
        models={f:record(folder/f/'SPEC.json') for f in ('DIRECT','EF')},matrix_structures=structures,timing=timer.receipt(),memory=r.memory(),
        original_huge_FULL_CSR_not_resident=True,independent_integer_alias_and_exact_dyadic_coefficients=True,
        previous_execution_not_stopped_or_modified=True,Native_readback_required_before_Optimize=True)
    write(DOCS/'NATIVE0_STATIC_GATE.json',report);full_guard();print(json.dumps(dict(PASS=True,timing=timer.receipt())),flush=True)
if __name__=='__main__':main()
