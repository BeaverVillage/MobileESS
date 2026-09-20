import os,sys,json,csv,hashlib,time,math,gzip
from pathlib import Path
sys.dont_write_bytecode=True
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np
from scipy.spatial.distance import cdist,pdist,squareform
from scipy.stats import spearmanr
from scipy.optimize import linear_sum_assignment
H=Path(__file__).resolve().parent;ROOT=H.parent.parent
OLD=ROOT/'RESITING_SCREEN/IEEE8500_MAY01_20260916'
sys.path.insert(0,str(OLD))
from engine import ResiteEngine,replay,Engine,BASE_P,BASE_Q,AUTH,IDS,save,table,read,original,s
BASE=ROOT/'IEEE8500_scalability_20260910';ST=BASE/'station_selection_v1'
ANCHORS=sorted(read(ST/'STATIC_24_TRAFFIC_ANCHORS.json'),key=lambda r:(r['role']=='STA',r['location_id']))
LABELS=[r['location_id'] for r in ANCHORS]
T=np.array([[r['x_east_km'],r['y_north_km']] for r in ANCHORS]);TRMS=float(np.sqrt(np.mean(np.sum((T-T.mean(0))**2,axis=1))))
INV=read(OLD/'FINAL_NATIVE_CANDIDATE_INVENTORY.json');BY={r['bus']:r for r in INV}
P0=dict(pairwise_spearman_min=.90,pairwise_normalized_RMS_max=.20,all_kNN2_retention_min=.70,AIDC_kNN2_retention_min=.75,STA_AIDC_row_spearman_mean_min=.90,STA_AIDC_top2_retention_min=.75,STA_AIDC_nearest_identity_retention_min=2/3,proper_similarity_fit_RMS_max=.20,local_assignment_radius_RMS=.20,all_24_identities_required=True,identity_permutation=False,reflection=False)

def xy(buses):return np.array([[BY[b]['x'],BY[b]['y']] for b in buses])
def knn_ret(a,b,k=2):
 da=cdist(a,a);db=cdist(b,b);np.fill_diagonal(da,np.inf);np.fill_diagonal(db,np.inf);ia=np.argsort(da,axis=1,kind='stable')[:,:k];ib=np.argsort(db,axis=1,kind='stable')[:,:k]
 return float(np.mean([len(set(x)&set(y))/k for x,y in zip(ia,ib)]))
def fit(a,b,affine=False):
 if affine:
  X=np.c_[a,np.ones(len(a))];coef=np.linalg.lstsq(X,b,rcond=None)[0];pred=X@coef;A=coef[:2];translation=coef[2]
 else:
  ac=a-a.mean(0);bc=b-b.mean(0);u,sv,vt=np.linalg.svd(ac.T@bc);D=np.diag([1.,np.linalg.det(u@vt)]);rot=u@D@vt;scale=float(np.sum(sv*np.diag(D))/np.sum(ac*ac));A=scale*rot;translation=b.mean(0)-a.mean(0)@A;pred=a@A+translation
 denom=np.sqrt(np.mean(np.sum((b-b.mean(0))**2,axis=1)));err=np.linalg.norm(pred-b,axis=1)/denom
 return dict(matrix=A.tolist(),translation=translation.tolist(),RMS=float(np.sqrt(np.mean(err**2))),max_error=float(err.max()),determinant=float(np.linalg.det(A)),condition=float(np.linalg.cond(A)))
def metrics(buses,labels=LABELS):
 ind=[LABELS.index(x) for x in labels];a=T[ind];b=xy(buses);dt=pdist(a);dg=pdist(b);dist=float(np.sqrt(np.mean((dt/np.sqrt(np.mean(dt**2))-dg/np.sqrt(np.mean(dg**2)))**2)))
 aid=[i for i,l in enumerate(labels) if l.startswith('AIDC')];sta=[i for i,l in enumerate(labels) if l.startswith('STA')]
 cross=[]
 for j in sta:
  ta=np.linalg.norm(a[aid]-a[j],axis=1);ga=np.linalg.norm(b[aid]-b[j],axis=1);ti=np.argsort(ta);gi=np.argsort(ga)
  cross.append(dict(station=labels[j],traffic_nearest=labels[aid[ti[0]]],grid_nearest=labels[aid[gi[0]]],traffic_top2=[labels[aid[x]] for x in ti[:2]],grid_top2=[labels[aid[x]] for x in gi[:2]],rank_correlation=float(spearmanr(ta,ga).statistic),top2_retention=len(set(ti[:2])&set(gi[:2]))/2,nearest_match=bool(ti[0]==gi[0])))
 m=dict(identities=len(labels),pairwise_spearman=float(spearmanr(dt,dg).statistic),pairwise_distortion=dist,kNN2=knn_ret(a,b),AIDC_kNN2=knn_ret(a[aid],b[aid]),STA_AIDC_rank_mean=float(np.mean([r['rank_correlation'] for r in cross])) if cross else None,STA_AIDC_top2=float(np.mean([r['top2_retention'] for r in cross])) if cross else None,STA_AIDC_nearest=float(np.mean([r['nearest_match'] for r in cross])) if cross else None,similarity=fit(a,b),affine=fit(a,b,True),cross=cross)
 checks=dict(all_24=len(labels)==24,pairwise_rank=m['pairwise_spearman']>=P0['pairwise_spearman_min'],distortion=dist<=P0['pairwise_normalized_RMS_max'],knn=m['kNN2']>=P0['all_kNN2_retention_min'],aidc=m['AIDC_kNN2']>=P0['AIDC_kNN2_retention_min'],cross_rank=m['STA_AIDC_rank_mean'] is not None and m['STA_AIDC_rank_mean']>=P0['STA_AIDC_row_spearman_mean_min'],cross_kNN=m['STA_AIDC_top2'] is not None and m['STA_AIDC_top2']>=P0['STA_AIDC_top2_retention_min'],cross_nearest=m['STA_AIDC_nearest'] is not None and m['STA_AIDC_nearest']>=P0['STA_AIDC_nearest_identity_retention_min'],global_transform=m['similarity']['RMS']<=P0['proper_similarity_fit_RMS_max'])
 m['checks']=checks;m['coherence_pass']=all(checks.values());return m

def main():
 start=time.perf_counter();save(H/'P0_RULE_PRE_SEARCH.json',dict(criteria=P0,note='Engineering screening thresholds declared before new placement search or AC. Pairwise 0.20 bound follows existing geometric methodology; joint-neighborhood and cross-layer gates are explicit additional screening conventions, not pre-existing physical laws. No threshold will be relaxed to improve electrical results.',time=time.time()))
 # Check projected coordinates against archived authoritative input rows and the
 # actual May-1 mobility service-node identifiers, without changing any table.
 nodes={r['transport_node_id']:r for r in csv.DictReader((BASE/'static_reference/v01_reduced48_nodes_v2.csv').open(encoding='utf-8-sig'))};services=list(csv.DictReader((BASE/'static_reference/final_service_nodes_24.csv').open(encoding='utf-8-sig')))
 for a in ANCHORS:
  row=nodes[a['traffic_node']];assert float(row['longitude'])==a['longitude'] and float(row['latitude'])==a['latitude']
 traf=read(AUTH/'MESS_TRAFFIC_AUTHORITY.json');routes=json.load(gzip.open(traf['files'][1]['path'],'rt'));road={r['origin_service_id']:r['road_origin_node'] for r in routes['routes']}
 for a in ANCHORS:assert road[a['location_id'][1:] if a['role']=='AIDC' else a['location_id']]==a['traffic_node']
 files=[BASE/'static_reference/v01_reduced48_nodes_v2.csv',BASE/'static_reference/final_service_nodes_24.csv',ST/'STATIC_24_TRAFFIC_ANCHORS.json',AUTH/'MESS_TRAFFIC_AUTHORITY.json',AUTH/'FLEET_AUTHORITY.json',Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/mess_physics.py'),OLD/'placements/legal_mixed_M1/LAYOUT.json',OLD/'placements.py',ROOT/'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912/select_mapping.py']+[Path(r['path']) for r in traf['files']]
 for r in traf['files']:assert original.sha(Path(r['path']))==r['sha256']
 save(H/'IMMUTABLE_INPUTS_BEFORE.json',[dict(path=str(p),sha256=original.sha(p)) for p in files]+read(OLD/'SOURCE_MANIFEST.json'))
 # Preserve complete original travel-time and mobility-energy matrices as
 # diagnostic exports; these exports never become replacement authority.
 route_rows=routes['routes'];travel=np.zeros((96,24,24));energy=np.zeros_like(travel);distance=np.zeros_like(travel)
 aliases={l[1:] if l.startswith('AIDC') else l:i for i,l in enumerate(LABELS)}
 for r in route_rows:
  t=r['departure_slot_15'];i=aliases[r['origin_service_id']];j=aliases[r['destination_service_id']];travel[t,i,j]=r['route_safe_eta_sec'];energy[t,i,j]=r['energy_safe_kwh'];distance[t,i,j]=r['route_distance_km']
 np.savez_compressed(H/'AUTHORITATIVE_TRANSPORT_DIAGNOSTICS.npz',labels=LABELS,coordinates=T,euclidean_distance=cdist(T,T),safe_eta_sec=travel,energy_safe_kwh=energy,route_distance_km=distance)
 lay=read(OLD/'placements/legal_mixed_M1/LAYOUT.json');labels=LABELS[:12]+IDS;buses=lay['aidc']+[r['bus'] for r in lay['mess']];m=metrics(buses,labels);am=metrics(lay['aidc'],LABELS[:12]);missing=[l for l in LABELS if l not in labels]
 # No inherited PCCs are invented for the six absent STA identities.
 audit=dict(candidate='legal_mixed_M1',AIDC_identity_permutation=False,AIDC_provenance='Previous fixed-identity geographic constrained host assignment retained; only AIDC02 replaced internal bus with adjacent legal e184626. Prior selector used fixed row identities, no label permutation.',MESS_provenance='Previous placements.py assigned first four high-loading leaf PCCs and two MV support PCCs to the frozen initial-station list [STA01,STA12,STA08,STA06,STA03,STA10], without transport coordinates or joint spatial gate.',missing_electrical_station_mappings=missing,metrics_18=m,AIDC_only=am,transport_authority_verified=True,feeder_coordinates='Native planar Buscoords available and non-degenerate; CRS and real geographic units unknown. Usable for normalized layout coherence, not actual road distance.',runtime_seconds=time.perf_counter()-start)
 save(H/'LEGAL_MIXED_M1_AUDIT.json',audit);table(H/'LEGAL_MIXED_M1_CROSS_PROXIMITY.csv',m['cross']);save(H/'TRAFFIC_ANCHORS.json',ANCHORS)
 print(json.dumps(dict(AIDC=am,joint18=m,missing=missing)),flush=True)
if __name__=='__main__':main()
