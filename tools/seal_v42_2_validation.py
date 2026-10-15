"""Bind actual Native0/regression evidence to one current V42.2 release."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.table_v_launch import release_identity


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def require(ok,reason):
    if not ok:raise ValueError(reason)


def seal(b1,m,regression,output):
    b1,m,regression=map(Path,(b1,m,regression))
    a=read(b1/'RESULT.json');mproof=read(m/'RESULT.json');tests=read(regression/'RESULTS.json')
    require(a.get('Native_calls')==0 and a.get('day')=='2025-05-01','ACTUAL_MAY01_B1_NATIVE0_REQUIRED')
    rows=[r for r in a['rows'] if (r['arm'],r['stage'])==('B1','A1')]
    require(len(rows)==1 and rows[0]['status']=='PASS_NATIVE0_MATRIX'
        and rows[0]['mathematical_matrix_equivalence']=='PASS_INDEPENDENT_ALL_UID_ACTUAL_A_B_RHS_BOUNDS_OBJECTIVE'
        and rows[0]['FULL_integer_compression_rows_removed']==0
        and rows[0]['FULL_integer_compression_columns_removed']==0,'B1_ORIGINAL_INTEGER_AND_LP_EQUIVALENCE_REQUIRED')
    require(isinstance(rows[0].get('source_sha'),str) and bool(rows[0]['source_sha'])
        and rows[0]['source_sha']==mproof.get('source_sha'),
        'A_AND_M_NATIVE0_MUST_SHARE_EXACT_CURRENT_SCIENTIFIC_SOURCE')
    definitions=read(b1/'B1/A1/DW/PCC_HARD_DEFINITIONS.json')
    require(definitions.get('PASS') is True and definitions.get('original_identity_rows_preserved') is True
        and len(definitions.get('definitions',[]))==1152,'ALL_12_BY_96_PCC_DEFINITIONS_REQUIRED')
    pcc=read(b1/'B1/A1/DW/PCC_FORMULATION_NATIVE0_COMPARISON.json')
    require(pcc.get('Native_calls')==0 and pcc.get('selected')=='HARD_ORIGINAL_IDENTITY_EQUALITIES'
        and pcc.get('hard',{}).get('coefficient_changes')==0,'LITERAL_PCC_HARD_FORM_REQUIRED')
    require(mproof.get('status')=='PASS' and mproof.get('Native_calls')==0
        and not mproof.get('blocked_Native_attempts'),'ACTUAL_M_SEEDLESS_NATIVE0_REQUIRED')
    k=mproof.get('K16',{})
    require(k.get('PASS') is True and k.get('original_domain_projection_included') is True
        and k.get('independent_original_geometry_replayed') is True
        and k.get('current_FULL_UB') is None,'SEEDLESS_UNIVERSAL_K_RELAXATION_PROOF_REQUIRED')
    iterations=mproof.get('seedless_iterations',[])
    require(len(iterations)==2 and len({r['pool_sha'] for r in iterations})==2
        and all(r['charge_modes']==384 and r['MIP_Start_present'] is False for r in iterations),
        'TWO_DISTINCT_FOUR_MESS_SEEDLESS_JOINT_POOLS_REQUIRED')
    require(all(r.get('exact_same_matrix_domain_lift_start') is True for r in mproof.get('Direct_same_pool_AB',[]))
        and len(mproof.get('Direct_same_pool_AB',[]))==2,'EXACT_SAME_POOL_DIRECT_AB_REQUIRED')
    require(tests.get('status')=='PASS' and tests.get('baseline_IDs_preserved')==682
        and tests.get('tests',0)>=1247 and not tests.get('failures') and not tests.get('skipped')
        and not tests.get('blocked_real_native_attempts') and tests.get('historical_ledgers_byte_preserved') is True,
        'FULL_CURRENT_REGRESSION_AND_HISTORICAL_LEDGER_INTEGRITY_REQUIRED')
    scientific_manifest=read(b1/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json')
    require(scientific_manifest.get('source_sha')==rows[0]['source_sha'],
        'AUDIT_RESULT_AND_SCIENTIFIC_MANIFEST_SOURCE_MUST_MATCH')
    science_records=scientific_manifest.get('science_derivation',{}).get('source_records')
    require(isinstance(science_records,list) and bool(science_records),'ACTUAL_SCIENTIFIC_SOURCE_RECORDS_REQUIRED')
    records=read(b1/'B1/A1/DW/DW_SOURCE_FREEZE.json')['sources']+mproof['current_source_records']+science_records
    require(all(file_record(r['path'])==r for r in records),'NATIVE0_CURRENT_SOURCE_BYTES_REQUIRED')
    proof=dict(schema='V42_2_CURRENT_RELEASE_NATIVE0_REGRESSION_GATE_V1',PASS=True,release=release_identity(),
        scientific_source_sha=rows[0]['source_sha'],
        evidence=[file_record(p) for p in (b1/'RESULT.json',m/'RESULT.json',regression/'RESULTS.json',
            b1/'B1/A1/DW/PCC_HARD_DEFINITIONS.json',b1/'B1/A1/DW/PCC_FORMULATION_NATIVE0_COMPARISON.json')],
        verified_source_records=records,Native_calls=0,FULL_UB_claimed=False,Actual_Fresh_PASS_claimed=False,
        dynamic_M2_and_A2_original_replay_required_at_runtime=True)
    with Path(output).open('x',encoding='utf8') as stream:json.dump(proof,stream,ensure_ascii=False,indent=2)
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--b1-native0',type=Path,required=True)
    p.add_argument('--m-native0',type=Path,required=True);p.add_argument('--regression',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=seal(a.b1_native0,a.m_native0,a.regression,a.output);print(json.dumps(dict(PASS=result['PASS'],output=str(a.output))))
