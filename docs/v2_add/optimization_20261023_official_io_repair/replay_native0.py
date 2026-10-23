from pathlib import Path
import sys,os,shutil,types,json,time
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT));H=Path(__file__).parent
from v2_add_preflight.stage_common import RUN,WORK,OUT,read,record,put
from v2_add_preflight.prestart_execution import atomic
from v2_add_preflight.stage_campaign import source_files
entered_sources=source_files()
target=sys.argv[1];assert target in ('M1','M2','JOINT')
new=H/(target+'_NATIVE0_AFTER');new.mkdir(exist_ok=False)
if target=='JOINT':
    from v2_add_preflight import stage_m_binding as module
    folder=new/'DIRECT_JOINT';folder.mkdir()
    for name in ('A.npz','D.npz','LIFT.npz','PROOF.json'):os.link(WORK/'DIRECT_JOINT'/name,folder/name)
    fn=types.FunctionType(module.joint_native0.__code__,dict(module.joint_native0.__globals__,WORK=new))
    fn();report=read(OUT/'BEAM_DIRECT_JOINT_MESS8_BINDING.json');assert report['PASS']
    csr=read(folder/'NATIVE0/READBACK/ACTUAL_CSR_READBACK.json')
    assert csr['canonical_CSR_sha256']=='e47d287bb577206eb5d76a7c78d30807ceffe8a4c2ba253880bfaf0ca4b7fa7b'
    atomic(new/'EXACT_BASELINE_CSR_VERIFIED.json',dict(PASS=True,readback=record(folder/'NATIVE0/READBACK/ACTUAL_CSR_READBACK.json'),
        historical_CSR_hash_equal=True,Native_calls=0))
    put('JOINT_NATIVE0_AFTER_20261023.json',dict(report,exhaustive_actual_CSR=csr,own_output=str(new),
        validation_source_files=entered_sources,validation_source_snapshot_unchanged=source_files()==entered_sources))
else:
    from v2_add_preflight import static_native as module
    from v2_add_preflight.static_pack import PACK
    source=RUN if target=='M1' else WORK/'M2'
    pack=PACK if target=='M1' else source/'SOURCE_YY_FULL96'
    docs=OUT if target=='M1' else OUT/'stage_m2';proof=new/'proof';proof.mkdir()
    for name in ('ORIGINAL_STATIC_PRESOLVE_MESS8.json','IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json'):
        shutil.copyfile(docs/name,proof/name)
    (new/'mobility').mkdir()
    for path in (source/'mobility').iterdir():
        if path.is_file():os.link(path,new/'mobility'/path.name)
    from v2_add_preflight import static_screen
    from v2_add_preflight.may01_compact import load as original_load
    loader=types.FunctionType(original_load.__code__,dict(original_load.__globals__,PACK=pack))
    def output(name,value):atomic(proof/name,value);return value
    namespace=dict(module.build.__globals__,RUN=new,PACK=pack,CACHE=source/'screen',OUT=proof,
        load=loader,put=output,init=lambda:module.resources())
    fn=types.FunctionType(module.build.__code__,namespace);fn()
    report=read(proof/'IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json');assert report['PASS'],report.get('error')
    comparisons={}
    for name in ('COMPLETE_A.npz','COMPLETE_DOMAIN.npz'):
        before=record(source/'native'/name);after=record(new/'native'/name)
        assert before['sha256']==after['sha256'] and before['bytes']==after['bytes']
        comparisons[name]=dict(before=before,after=after,byte_equal=True)
    report.update(stage=target,own_output=str(new),same_current_case_arrays=comparisons,
        validation_source_files=entered_sources,validation_source_snapshot_unchanged=source_files()==entered_sources,
        independent_FULL_static_equivalence=record(docs/'IEEE8500_EXACT_COMPACT_EQUIVALENCE.json'))
    put(target+'_STATIC_NATIVE0_AFTER_20261023.json',report)
print('ISOLATED_NATIVE0_REPLAY_PASS',target,flush=True)
