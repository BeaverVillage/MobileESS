"""Lossless Git-size transport, after completed capture; no solver calls."""
from common import *

def main():
    bundle=OUT/'MULTIWINDOW_STRENGTHENED_LP_DUAL_RC_SLACK.npz'
    assert not read(OUT/'MULTIWINDOW_STRENGTHENED_LP.json').get('postprocessing_pending',False)
    if bundle.stat().st_size<100*1024**2:
        print('CAPTURE_BUNDLE_WITHIN_GIT_LIMIT',bundle.stat().st_size);return
    pieces=[]
    with np.load(bundle) as z:
        for key in z.files:
            arr=z[key];name=f'MULTIWINDOW_CAPTURE_{key.upper()}.npz';p=OUT/name
            np.savez_compressed(p,**{key:arr})
            with np.load(p) as reloaded:assert np.array_equal(arr,reloaded[key])
            assert p.stat().st_size<100*1024**2
            pieces.append(dict(array=key,file=name,shape=list(arr.shape),dtype=str(arr.dtype),array_bytes_SHA256=hashlib.sha256(arr.tobytes()).hexdigest(),file_SHA256=sha(p)))
    write('MULTIWINDOW_CAPTURE_TRANSPORT.json',dict(PASS=True,optimize_calls=0,lossless_array_equality_verified=True,original_local_bundle=bundle.name,original_bundle_SHA256=sha(bundle),original_bundle_bytes=bundle.stat().st_size,original_bundle_retained_locally=True,original_bundle_ignored_only_for_Git_size=True,pieces=pieces,reconstruction='Load each piece by its array key. Optional np.savez_compressed(bundle,**arrays) recreates identical arrays; ZIP archive bytes are not promised identical.'))
    ignore=OUT/'.gitignore';text=ignore.read_text(encoding='utf-8')
    line=bundle.name+'\n'
    if line not in text:ignore.write_text(text+line,encoding='utf-8')
    print('CAPTURE_SPLIT_LOSSLESSLY',pieces,flush=True)

if __name__=='__main__':main()
