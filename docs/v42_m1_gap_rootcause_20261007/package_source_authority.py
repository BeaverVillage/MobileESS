"""Copy frozen existing authority bytes for offline reproducibility; no solves."""
from common import *
import shutil

def main():
    target=OUT/'source_authority';target.mkdir(exist_ok=True)
    freeze=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')
    expected={'FULL_A.npz':history_authority.FULL_A_SHA,'FULL_DATA.npz':history_authority.FULL_DATA_SHA,'DATA.pkl':freeze['source_data_sha256']}
    records=[]
    for name,digest in expected.items():
        source=ORIGINAL_SOURCE_LOCATION/name;destination=target/name
        assert sha(source)==digest
        if destination.exists():assert sha(destination)==digest
        else:shutil.copyfile(source,destination)
        assert sha(destination)==digest
        records.append(dict(name=name,original_path=str(source),committed_path=destination.relative_to(OUT).as_posix(),SHA256=digest,bytes=destination.stat().st_size,byte_identical=True))
    write('SOURCE_AUTHORITY_COPIES.json',dict(PASS=True,optimize_calls=0,model_or_formulation_modified=False,original_source_files_untouched=True,source_files_copied_byte_identically=records,source_location_override='common.py prefers committed source_authority when present; optional V42_SOURCE_AUTHORITY_DIR. All existing source SHA guards still apply.'))
    print('FROZEN_SOURCE_AUTHORITY_PACKAGED',records,flush=True)

if __name__=='__main__':main()
