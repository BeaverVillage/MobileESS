from pathlib import Path
import numpy as np
import pytest,json
from v42_pr134_b1.common import clean,digest,atomic
from v42_autonomous_b2 import canonical_stream as stream


@pytest.mark.parametrize('value',[
    {'z':None,'a':['한글',True,False,0,1,-0.,1e-300,1e308]},
    {'array':np.array([[0.,-0.],[np.inf,np.nan]]),'nested':(np.int64(9),np.bool_(False),Path('D:/증거/a'))},
    {1:'first','1':'last',False:np.float32(.1),'𐀀':'🌍'},
    {'empty':{},'l':[],'tuple':(),'shared':{'fraction':'123/456'}},
    [np.float64(np.nan),np.float64(-np.inf),np.float64(np.inf),np.float32(1e-30)],
    {'nested':[{str(i):np.array([i,i+1])} for i in range(30)]}
])
def test_exact_original_canonical_and_pretty_bytes(value,tmp_path):
    assert ''.join(stream.chunks(value,canonical=True))==json.dumps(clean(value),sort_keys=True,separators=(',',':'))
    assert stream.digest(value)==digest(value)
    before=tmp_path/'before.json';after=tmp_path/'after.json'
    atomic(before,value);stream.atomic(after,value)
    assert after.read_bytes()==before.read_bytes()


def test_shared_identity_and_invalid_payload_never_replaces_packet(tmp_path):
    value={'scalar':np.int64(4)};root=[value,value]
    assert stream.digest(root)==digest(root)
    path=tmp_path/'P.json';path.write_bytes(b'original\n')
    with pytest.raises(TypeError):stream.atomic(path,{'unsupported':object()})
    assert path.read_bytes()==b'original\n' and not list(tmp_path.glob('*.tmp'))


def test_large_steps_are_cleaned_lazily_without_full_tree_copy():
    payload={'steps':[{'column':i,'bounds':[np.int64(i),np.float64(i+.5)]} for i in range(10000)]}
    iterator=stream.chunks(payload,canonical=True)
    assert next(iterator)=='{'
    payload['steps'][0]['column']=123456
    encoded='{'+''.join(iterator)
    assert json.loads(encoded)['steps'][0]['column']==123456
    assert stream.digest(payload)==digest(payload)
