from pathlib import Path

src=Path('D:/v42_source35_deployment_independent_audit_20261010_01/audit_deployment.py').read_text(encoding='utf-8')
src=src.replace('Source35','Source36').replace('SOURCE35','SOURCE36').replace('V35','V36').replace('v35','v36').replace('v42run35','v42run36')
src=src.replace('Source32','Source35').replace('SOURCE32','SOURCE35').replace('source32_workers','source35_workers').replace('v42run32','v42run35')
src=src.replace('Source34','Source35').replace('v42run34','v42run35')
def replace(old,new):
    global src
    assert old in src,old
    src=src.replace(old,new)
replace("evidence_names=['V36_ZERO_START_RETRY_DEPLOYMENT.json','V36_ZERO_START_RETRY_PREPARATION.json',",
 "evidence_names=['V36_ZERO_START_RETRY_DEPLOYMENT.json','V36_ZERO_START_RETRY_PREPARATION_02.json','V36_ZERO_START_RETRY_PREPARATION.json',")
replace("'V36_VERIFIED_REPAIR_VALIDATION.json','SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json']",
 "'V36_VERIFIED_REPAIR_VALIDATION_02.json','V36_VERIFIED_REPAIR_VALIDATION.json','SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json','SOURCE36_POST_ENQUEUE_NATIVE_CONTINUITY_VERIFICATION.json']")
replace("prep=evidence['V36_ZERO_START_RETRY_PREPARATION.json']", "prep=evidence['V36_ZERO_START_RETRY_PREPARATION_02.json']")
replace("validation=evidence['V36_VERIFIED_REPAIR_VALIDATION.json']", "validation=evidence['V36_VERIFIED_REPAIR_VALIDATION_02.json']")
replace("810f98a5da7eb09f61354bbfa67bc3945951f0d7", "68b8903c1184a958c16dd7976044716bdff091c6")
replace("a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14", "4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39")
replace("assert (validation['RMP_Method'],validation['RMP_Presolve'],validation['RMP_LPWarmStart'],validation['RMP_original_required_seconds'])==(1,0,2,30.)",
 "assert 'RMP_Method' not in validation\n    assert (validation['original_RMP_budget_entry_Method'],validation['eligible_current_complete_start_RMP_Native_Method'],validation['cold_ineligible_or_nonfeasible_RMP_fallback_Method'])==(1,0,1)\n    assert (validation['RMP_Presolve'],validation['RMP_LPWarmStart'],validation['RMP_original_required_seconds'])==(0,2,30.)\n    assert validation['metadata_only_correction'] is True\n    check_record(validation['historical_validation_with_ambiguous_RMP_Method'])\n    check_record(validation['metadata_finalizer_source_script'])\n    assert all(check_record(row) for row in validation['original_executed_helper_records'].values())\n    oldprep=evidence['V36_ZERO_START_RETRY_PREPARATION.json'];oldvalidation=evidence['V36_VERIFIED_REPAIR_VALIDATION.json']\n    assert oldvalidation['RMP_Method']==1\n    assert prep['original_preparation']['sha256']=='35e43065bcfe3fc5012bac3109c555a4f571a11583b0aa2972613c9d0b989814'\n    check_record(prep['original_preparation']);check_record(prep['original_validation'])\n    assert prep['requests_by_day_and_slot']==oldprep['requests_by_day_and_slot'] and prep['deployment']==oldprep['deployment']\n    assert prep['admissions_rerun_by_metadata_finalizer'] is False and prep['new_Native_calls_or_models_by_metadata_finalizer']==0\n    assert prep['original_prepare_exit_code_confirmed_by_operator']==0\n    assert check_record(template['source_script'])['sha256']=='3c7499660720a9cb1304ba5f446896565bb8d0d66b16170096db93c0bc9fdd82'\n    pinned={'V36_ZERO_START_RETRY_DEPLOYMENT.json':'6a6320699efe7452243e1625b8b41b29c1a7adc445a92f2567607a2233f84536','V36_ZERO_START_RETRY_PREPARATION_02.json':'1d58a1db37afefa46cff3fc5d1a3e0bac3d64267ca997713423cb1aeb16f1417','V36_VERIFIED_REPAIR_VALIDATION_02.json':'016b629f39a22c33814e943cb67f9df5a9f8f8f8b46d11ad2c8fb08423969c15','SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json':'443be4d5ef7f3b70985fe82acec522e3d64d4f9a7e5f08ad459495a294b2f931','SOURCE36_POST_ENQUEUE_NATIVE_CONTINUITY_VERIFICATION.json':'c53e42007e9822106c835f3f88f627449546e11bd90174e8af39e654a1c20456'}\n    assert all(rec(AUTO/name)['sha256']==sha for name,sha in pinned.items())\n    assert deployment['deployment']['sha256']=='ca3840a26a3da80393c5416728ef17b398572366274a7c812fa5cbda8c5a100e'")
replace('27b5a0fed3ea491e78d6f2c8bca315546e88e950a26cfff627af04f71c43229d','3ff0607e176918b08d63aeeced4667e687609dc72e33180321a82ba8924557ac')
replace('cb5b009e1f1b0fefdbe064f3c45dd3bc56a30b5e1c683dd9cb915374f4c1547c','c74bc9a9c721106e3bba4ee8094a2cad3a7ad46b61702aaf0af07f61f4187605')
replace('==335','==369')
replace('ae7e1dc7dabe4431841c30ae011a0289','de36f19fd14e4710af54525dfb15b48c')
replace("assert len(old)==9 and len(superseded)==9 and {v['date'] for v in superseded}==set(requests)",
 "assert len(old)==9 and len(superseded)==6 and {v['date'] for v in superseded}==set(sorted(requests)[3:])\n    active_old=[v for v in old if v['verification_status']=='WORKER_ENTERED'];assert len(active_old)==3 and {v['date'] for v in active_old}==set(sorted(requests)[:3])")
replace("before=[v for v in previous['calls'] if v.get('status')=='FINISHED'];after=[v for v in ledger['calls'] if v.get('status')=='FINISHED']", "before=previous['calls'];after=ledger['calls']")
replace("'RMP_Method','RMP_Presolve'", "'original_RMP_budget_entry_Method','eligible_current_complete_start_RMP_Native_Method','cold_ineligible_or_nonfeasible_RMP_fallback_Method','RMP_Presolve'")
replace("assert scientific==end", "assert scientific==end\n    assert all(check_record(row) for row in frozen.values())\n    assert len(continuity)==3\n    post=evidence['SOURCE36_POST_ENQUEUE_NATIVE_CONTINUITY_VERIFICATION.json']\n    assert post['supervisor_PID']==supervisor['PID'] and post['exact9_READY_Verified_Repair'] is True\n    assert all(post['workers'][key]['PID']==v['actual_process']['PID'] and post['workers'][key]['completed_Native_prefix_preserved'] is True and v['current_measured_Native_Runtime']>=post['workers'][key]['current_known_Native'] for key,v in continuity.items())")
replace("receipt.write_text(json.dumps(r", "assert not receipt.exists()\nreceipt.write_text(json.dumps(r")
path=Path(__file__).resolve().parent/'audit_deployment.py';assert not path.exists();path.write_text(src,encoding='utf-8');print(path)
