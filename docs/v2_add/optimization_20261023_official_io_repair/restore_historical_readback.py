"""Restore exact historical immutable bytes after failed diagnostic overwrite."""
from pathlib import Path
import sys,json,hashlib,shutil
H=Path(__file__).parent
ROOT=H.parents[2]/'V2_add'
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT))
from v2_add_preflight.stage_common import WORK,OUT,read,record
from v2_add_preflight.prestart_execution import atomic
assert read(OUT/'JOINT_NATIVE0_AFTER_20261023.json')['PASS']
new=H/'JOINT_NATIVE0_AFTER/DIRECT_JOINT/NATIVE0'
old=WORK/'DIRECT_JOINT/NATIVE0'
assert read(new/'READBACK/ACTUAL_CSR_READBACK.json')['canonical_CSR_sha256']=='e47d287bb577206eb5d76a7c78d30807ceffe8a4c2ba253880bfaf0ca4b7fa7b'
receipt=H/'HISTORICAL_READBACK_RESTORATION.json'
if receipt.exists():
    previous=read(receipt);assert previous['PASS']
    for item in [previous['new_exhaustive_actual_readback'],previous['restored_Native_call'],*previous['restored_bins']]:
        assert record(item['path'])==item,'PREVIOUS_RESTORATION_ARTIFACT_DRIFT'
    assert record(old/'NATIVE_READBACK.json')['sha256']=='3852c83444663badad4af6127cf7bee154bbc96204c3bfd5826dc6ea9e3cb605'
    assert record(old/'READBACK/ACTUAL_CSR_READBACK.json')['sha256']=='60f6af0a51c8d22b2c89d5183eca723fdd009e7df93458a4658556f036a054a9'
    print('HISTORICAL_RESTORATION_ALREADY_COMPLETE_ALL_BYTES_REVERIFIED',flush=True)
    raise SystemExit(0)
archive=H/'FAILED_JOINT_READBACK_BEFORE_RESTORATION';archive.mkdir(exist_ok=False)
for name in ('NATIVE_CALL.json','READBACK/ACTUAL_INDICES.bin','READBACK/ACTUAL_VALUES.bin'):
    target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old/name,target)
baseline=read(H/'BASELINE_EVIDENCE_4ff700b/BEAM_DIRECT_JOINT_MESS8_BINDING.json')['source_Native0_result']
expected='a1f3cec3290fe6db7f7a9207d9e28bf5752f255c5ac001bd959501556a0363f7'
variants=[(json.dumps(baseline,ensure_ascii=a,indent=i,sort_keys=s)+e).replace('\n',nl).encode('utf8')
          for a in (True,False) for i in (None,2,4) for s in (False,True) for e in ('','\n') for nl in ('\n','\r\n')]
matching=[value for value in variants if hashlib.sha256(value).hexdigest()==expected]
assert matching,'EXACT_HISTORICAL_NATIVE_CALL_BYTES_NOT_RECOVERED'
assert record(old/'NATIVE_READBACK.json')['sha256']=='3852c83444663badad4af6127cf7bee154bbc96204c3bfd5826dc6ea9e3cb605'
assert record(old/'READBACK/ACTUAL_CSR_READBACK.json')['sha256']=='60f6af0a51c8d22b2c89d5183eca723fdd009e7df93458a4658556f036a054a9'
for name,width in (('ACTUAL_INDICES.bin',4),('ACTUAL_VALUES.bin',8)):
    src=new/'READBACK'/name;assert src.stat().st_size==49178740*width
    shutil.copyfile(src,old/'READBACK'/name)
    assert record(src)['sha256']==record(old/'READBACK'/name)['sha256']
(old/'NATIVE_CALL.json').write_bytes(matching[0])
assert record(old/'NATIVE_CALL.json')['sha256']==expected
atomic(H/'HISTORICAL_READBACK_RESTORATION.json',dict(PASS=True,
    failed_artifacts_preserved=str(archive),new_exhaustive_actual_readback=record(new/'READBACK/ACTUAL_CSR_READBACK.json'),
    identical_original_CSR_and_historical_metadata_preserved=True,
    restored_Native_call=record(old/'NATIVE_CALL.json'),
    restored_bins=[record(old/'READBACK'/n) for n in ('ACTUAL_INDICES.bin','ACTUAL_VALUES.bin')],
    no_solver_result_or_bound_fabricated=True))
print('HISTORICAL_IMMUTABLE_READBACK_RESTORED',flush=True)
