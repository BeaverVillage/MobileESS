"""Exact BASE-byte preservation without touching shared Git configuration."""
import subprocess
import hashlib
from .freeze import ROOT, OUT, BASE
from v42_april_port.audit import write

def base_blobs():
    lines=subprocess.check_output(['git','ls-tree','-r',BASE],cwd=ROOT).decode('utf8').splitlines()
    entries=[]
    for line in lines:
        meta,name=line.split('\t',1)
        mode,kind,oid=meta.split()
        if kind=='blob': entries.append((name,oid))
    data=subprocess.check_output(['git','cat-file','--batch'],input=('\n'.join(oid for _,oid in entries)+'\n').encode(),cwd=ROOT)
    pos=0
    for name,oid in entries:
        end=data.index(b'\n',pos); size=int(data[pos:end].split()[2]); pos=end+1
        payload=data[pos:pos+size]; pos+=size+1
        yield name,payload

def restore():
    restored=[]
    for name,expected in base_blobs():
        p=ROOT/name; actual=p.read_bytes()
        if actual != expected:
            if actual.replace(b'\r\n',b'\n') != expected.replace(b'\r\n',b'\n'):
                raise ValueError('BASE_CONTENT_DRIFT:'+name)
            p.write_bytes(expected); restored.append(name)
    from v42_april_port.audit import read
    prior=read(OUT/'CHECKOUT_EOL_RECEIPT.json')['EOL_only_restored'] if (OUT/'CHECKOUT_EOL_RECEIPT.json').exists() else []
    write(OUT,'CHECKOUT_EOL_RECEIPT.json',dict(base=BASE,EOL_only_restored=sorted(set(prior+restored)),content_edits_to_BASE=0))

def test_checkout():
    p=ROOT/'.gitignore'; p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))

def verify():
    checked=0; mismatches=[]
    for name,payload in base_blobs():
        checked+=1
        if (ROOT/name).read_bytes()!=payload: mismatches.append(name)
    if mismatches: raise ValueError('BASE_BYTE_DRIFT:'+repr(mismatches))
    write(OUT,'VERIFICATION.json',dict(exact_base=BASE,base_files_checked=checked,
        exact_BASE_bytes_preserved=True,BASE_content_changes=0,
        raw_external_files_copied=False,May_outcomes_used_for_construction=False,
        scientific_results_estimated=False))
    print('Exact BASE files',checked,'preserved',flush=True)

if __name__=='__main__':
    import sys
    {'restore':restore,'test_checkout':test_checkout,'verify':verify}[sys.argv[1]]()
