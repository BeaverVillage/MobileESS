"""One-time pre-fit transport correction; model/statistical semantics unchanged."""
from .common import *

def main():
    assert not list((OUT/'fits').glob('*/*_start.json')), 'Never revise a registration after fitting starts'
    old=git('rev-parse','HEAD');reg=read('V40R3_PREREGISTRATION.json')
    for p in OUT.rglob('*'):
        if p.is_file() and p.suffix in ['.json','.csv','.md']:
            text=p.read_text(encoding='utf-8-sig')
            p.write_text(text,encoding='utf-8',newline='\n')
    reg['frozen_source_and_data_SHA256']={p:sha(ROOT/p) for p in reg['frozen_source_and_data_SHA256']}
    reg['prefit_transport_correction']={'previous_commit':old,'reason':'Canonical LF bytes so Git blobs and working-copy SHA256 match on Windows; model/data/split/loss/budget unchanged','fits_before_correction':0}
    dump('V40R3_PREREGISTRATION.json',reg)
    dump('V40R3_PREFIT_TECHNICAL_CORRECTION.json',reg['prefit_transport_correction'])
    print('Canonical LF transport correction completed before all model fitting.')

if __name__=='__main__':main()
