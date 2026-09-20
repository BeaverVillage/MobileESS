from engine import *

def main():
 cc=read(H/'SENSITIVITY_CANDIDATES.json');by={x['key']:x for x in cc}
 old=[x['host_bus'] for x in read(AUTH/'PCC_OVERLAY_INVENTORY.json') if x['PCC_role']=='AIDC'];old[1]='e184626'
 inv={x['bus']:x for x in read(H/'NATIVE_BUS_INVENTORY.json')}
 leaves=[]
 for r in read(H/'HIGH_LOADING_LINES.json'):
  if 'tpx' in r['line']:
   bus=r['buses'][-1].split('.')[0];node=int(r['witness'].split('node')[-1]);key=f'{bus}.{node}'
   if key in by:leaves.append(key)
 maps=[('legal_mixed',old),('stress_pair',[('n1144668' if i==3 else 'n1138607' if i==8 else b) for i,b in enumerate(old)]),('remote_receivers',[('m1009763' if i==9 else 'm1069310' if i==3 else 'm1209791' if i==8 else b) for i,b in enumerate(old)])]
 messsets=[leaves[:4]+['m1009763.1.2.3','n1144668.1.2.3'],leaves[:3]+['sx2748781a.2','m1009763.1.2.3','n1144668.1.2.3'],leaves[:5]+['m1009763.1.2.3']]
 results=[]
 for name,aidc in maps:
  assert len(set(aidc))==12 and all(inv[b]['AIDC_candidate'] for b in aidc)
  for k,keys in enumerate(messsets):
   layout=dict(name=f'{name}_M{k+1}',aidc=aidc,mess=[by[key] for key in keys],s_DC=1.,s_MESS=1.,phase_interface_adaptation_authorized=True,station_ids=IDS,initial_locations_preserved_by_station_ID=True)
   folder=H/'placements'/layout['name'];result=replay(layout,BASE_P,folder/'B0');save(folder/'LAYOUT.json',layout)
   results.append(dict(placement=layout['name'],**result));print(json.dumps(results[-1]),flush=True)
 table(H/'B0_PLACEMENT_GATES.csv',results);save(H/'B0_PLACEMENT_GATES.json',results)
if __name__=='__main__':main()
