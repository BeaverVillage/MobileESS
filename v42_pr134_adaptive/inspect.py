import pickle,json
from pathlib import Path
from collections import Counter
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[1]
CASE=Path('C:/v42_b1_may17_may19_repair_20261007')
def main():
    for day in ('2025-05-17','2025-05-19'):
        with (CASE/day/'DATA.pkl').open('rb') as f:bundle,jobs,bounds,r,raw,graphs,old,prep=pickle.load(f)
        classes=prep['classes'];positive=list(jobs.values())
        print(day,'classes',len(classes),'jobs',len(jobs),'states',Counter((j.state,j.qos,j.protected) for j in positive),flush=True)
        print('domains',Counter((len(bounds[u].allowed_starts),len(graphs[u].events['y']),bool(graphs[u].fixed),bool(graphs[u].events['w'])) for u in jobs),flush=True)
        reference=Path(bundle['reference']['path'])
        print('reference',reference,reference.exists(),flush=True)
        source={str(x['job_uid']):x for x in json.loads(reference.read_text(encoding='utf-8'))}
        print('migration',Counter((j.state,j.qos,j.protected,j.checkpoint_authorized) for j in positive),flush=True)
        print('ranges',Counter((j.qos,j.reference_start,j.service_slots,j.gpu) for j in positive).most_common(12),flush=True)
        print('refs_source_equal',sum(j.reference_start==int(source[u]['RSP_start_slot']) for u,j in jobs.items()),flush=True)
if __name__=='__main__':main()
