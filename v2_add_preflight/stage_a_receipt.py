"""Summarize the real source canonical Native0 architecture, without a solve."""
import gzip,pickle,sys
import numpy as np
from .stage_common import *


def report(tag='A1'):
    preparation=read(OUT/(tag+'_ORIGINAL_P1_FULL_PREPARATION.json'))
    if preparation['PASS'] is not True:raise ValueError('COMPLETE_ORIGINAL_CANONICAL_PREPARATION_REQUIRED')
    source=preparation['state'];assert record(source['path'])==source
    with gzip.open(source['path'],'rb') as f:state=pickle.load(f)
    root=Path(state['_campaign']['output']);roster=read(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    assert len(roster['records'])==117 and all(r['PASS'] for r in roster['records'])
    grid=read(OUT/(tag+'_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json'));assert grid['PASS']
    snapshot=state['compact'];types=snapshot.vtypes
    result=dict(PASS=True,Native_optimize_calls=0,Native_presolve_calls=0,official_campaign_executed=False,
        scope='Original r043 canonical active kernel plus all original complete Native local pricing blocks; no single huge monolithic Job model claimed',
        canonical_source_Native0_PASS=True,single_monolithic_Native0_PASS=False,
        original_source_algorithm=record(ROOT/'v42_may_campaign_native90/a_stage.py'),
        source_CANARY_PREPARE=record(ROOT/'v42_a_stage_canary/prepare.py'),
        source_preparation=record(OUT/(tag+'_ORIGINAL_P1_FULL_PREPARATION.json')),
        canonical_kernel=dict(variables=snapshot.matrix.shape[1],rows=snapshot.matrix.shape[0],nonzeros=snapshot.matrix.nnz,
            binary=int(np.sum(types=='B')),integer=int(np.sum(types=='I')),continuous=int(np.sum(types=='C')),
            initial_LP_kernel_integer_restoration_is_original_later_phase=True),
        complete_full_pricing_blocks=dict(classes=117,rows=sum(r['complete_native_local_rows'] for r in roster['records']),
            primitive_columns=sum(r['complete_native_primitive_columns'] for r in roster['records']),
            nonzeros=sum(r['complete_nnz'] for r in roster['records']),source=record(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json')),
        original_complete_domain=preparation['verification'],
        all96_variable_C1_PQ_to_grid_connected=True,all96_Native_grid_rows_readback_at_insertion=True,
        independent_full_grid_projection=record(OUT/(tag+'_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json')),
        original_Job_GPU_Rack_CC4_Runtime_WAN_service_and_tail_builders_reused=True,
        original_WINDOW_authority=record(OUT/'A_STAGE_SOURCE_WINDOW_AUTHORITY_AUDIT.json'),
        original_r043_broader_physical_start_universe_equivalence_claimed=False,
        original_source_files_edited=False,new_Grid_row_generation=False,
        source_P1_complete_pricing_and_integer_acceptance_prepared=True,
        numerical_Global_LB_UB_Gap=None,optimized_A1_or_A2_result_claimed=False,
        state=source,peak_RSS_bytes=preparation['peak_RSS_bytes'],wall_seconds=preparation['wall_seconds'])
    if tag=='A2':result.update(fixed_M1_fixture=preparation['M1_fixture'],production_M1_acceptance_claimed=False)
    name='A1_VARIABLE_AIDC_FULL_NATIVE0.json' if tag=='A1' else 'A2_FIXED_M1_FULL_NATIVE0.json'
    return put(name,result)


if __name__=='__main__':report(sys.argv[1] if len(sys.argv)>1 else 'A1')
