from .common import *
import shutil
import subprocess

def prepare():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json');assert len(cp['pool'])==1604
    files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    frozen={p:sha(ROOT/p) for p in files if p}
    write(OUT/'PR152_BYTE_FREEZE.json',dict(head=BASE,files=frozen,columns=1604,
        checkpoint_SHA=sha(OLD/'DW_CHECKPOINT_LATEST.json'),LB=.5687115725336208,UB=cp['RMP']['objective']))
    source=Path('C:/v42_dw_multicolumn_microbenchmark/docs/v42_m1_dw_multicolumn_microbenchmark/clean_revalidation/baseline/live')
    columns=[]
    for unit in range(4):
        receipt=read(source/f'pricing_receipts/PRICE_{unit+1:04d}.json')
        chosen=[c for c in receipt['candidates'] if c['selected']][:3 if unit<2 else 2]
        for c in chosen:
            dst=OUT/'controlled_columns'/f'INPUT_{len(columns):02d}.npz'
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/c['point_file'],dst);dst.chmod(0o444)
            columns.append(dict(unit=unit,file=dst.relative_to(OUT).as_posix(),file_SHA=sha(dst),
                column_SHA=c['column_SHA'] if 'column_SHA' in c else c['trajectory_SHA'],
                source_PR153='d10077da9646ee7a60a0fdc9efcf8f8bb1bc94b1',role='controlled independently reaudited input, not authority'))
    assert len(columns)==10
    write(OUT/'CONTROLLED_INPUTS.json',dict(columns=columns,selection='first selected baseline receipt entries, deterministic 3/3/2/2; batches first5/last5'))
    print('PR152_FREEZE',len(frozen),'CONTROLLED_INPUTS',len(columns),flush=True)

if __name__=='__main__':prepare()
