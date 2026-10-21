"""Seal V2_add files, and optionally verify staged Git blob byte preservation."""
import argparse
import hashlib
import json
import subprocess
from .audit import ROOT,DOC,save


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--index',action='store_true');args=ap.parse_args()
    paths=sorted(p for parent in (DOC,ROOT/'v2_add_preflight') for p in parent.rglob('*')
                 if p.is_file() and p.name!='V2_ADD_SHA256_MANIFEST.json' and '__pycache__' not in p.parts)
    rows=[]
    for p in paths:
        rel=p.relative_to(ROOT).as_posix();b=p.read_bytes();h=hashlib.sha256(b).hexdigest()
        if args.index:
            staged=subprocess.check_output(['git','-C',str(ROOT),'show',':'+rel])
            if staged!=b:raise ValueError('Git staging changed artifact bytes: '+rel)
        rows.append(dict(path=rel,bytes=len(b),sha256=h))
    if args.index:
        prior=json.loads((DOC/'V2_ADD_SHA256_MANIFEST.json').read_text(encoding='utf-8'))
        if prior['files']!=rows:raise ValueError('Sealed file set or bytes changed')
        print(f'Git staged bytes and seal PASS: {len(rows)} files')
    else:
        save('V2_ADD_SHA256_MANIFEST.json',dict(experiment_id='V2_add',files=rows,
             manifest_excludes_itself=True,scope='V2_add code and report files; external Runtime separately identified'))
        print(f'Sealed {len(rows)} files')


if __name__=='__main__':main()
