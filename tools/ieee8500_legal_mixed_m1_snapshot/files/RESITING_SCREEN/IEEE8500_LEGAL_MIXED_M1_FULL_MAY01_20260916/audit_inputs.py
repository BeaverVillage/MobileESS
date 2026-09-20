import sys,json,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).absolute().parent;ROOT=H.parent.parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 old=ROOT/'RESITING_SCREEN/IEEE8500_MAY01_20260916';a=ROOT/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
 source=read(old/'SOURCE_MANIFEST.json')+read(H/'SOURCE_COPY_MANIFEST.json')['files']+read(a/'MESS_TRAFFIC_AUTHORITY.json')['files']
 checks=[dict(path=r['path'],expected=r['sha256'],actual=sha(r['path']),PASS=sha(r['path'])==r['sha256']) for r in source]
 layout=read(H/'LAYOUT.json');assert layout==read(old/'placements/legal_mixed_M1/LAYOUT.json')
 before=read(a/'PCC_OVERLAY_INVENTORY.json');now=read(H/'PCC_OVERLAY_INVENTORY.json');selected=set(layout['station_ids']);inherited=[]
 for r in now:
  q=next(x for x in before if (x['PCC_role'],x['location_id'])==(r['PCC_role'],r['location_id']))
  if r['PCC_role']=='MESS' and r['location_id'] not in selected:
   keys=['host_bus','PCC_bus','phases','primary_kv','secondary_kv','rating_kva','transformer'];assert all(r[k]==q[k] for k in keys);inherited.append(r['location_id'])
 assert len(inherited)==18 and len(now)==36
 result=dict(status='PASS' if all(r['PASS'] for r in checks) else 'FAIL',fixed_layout_equal=True,unchanged_inherited_MESS_ports=inherited,original_sources=checks,Actual=False,traffic_modified=False,identity_permutation=False)
 (H/'INPUT_AUTHORITY_AUDIT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');assert result['status']=='PASS'
 print('INPUT_AUTHORITY_PASS',len(checks),'source files; 18 inherited ports')
if __name__=='__main__':main()
