from common import *
import urllib.request,urllib.error,concurrent.futures
urls=['https://api.crossref.org/works/10.1145/3731599.3767563','https://www.osti.gov/api/v1/records?doi=10.1145%2F3731599.3767563','https://huggingface.co/api/models/Linq-AI-Research/Linq-Embed-Mistral','https://data.nlr.gov/search?search=RADDiT']
def fetch(url):
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'MobileESS-provenance-audit/1.0','Accept':'application/json,text/html'})
        with urllib.request.urlopen(req,timeout=15) as r:
            b=r.read(2_000_001);status=r.status
        if len(b)>2_000_000:return dict(url=url,status='SIZE_LIMIT_METADATA_ONLY')
        text=b.decode('utf-8',errors='replace')
        try:data=json.loads(text)
        except ValueError:data=dict(title=re.findall(r'<title>(.*?)</title>',text,re.S),raddit_mentions=len(re.findall('raddit',text,re.I)),note='Landing HTML only; no authenticated/private data retrieved')
        if 'huggingface' in url:data={k:data.get(k) for k in ['id','sha','lastModified','library_name','pipeline_tag']}
        return dict(url=url,http_status=status,data=data,body_sha256=hashlib.sha256(b).hexdigest())
    except Exception as ex:return dict(url=url,status='UNAVAILABLE',error=str(ex))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:receipts=list(ex.map(fetch,urls))
github=[]
for endpoint in ['repos/NatLabRockies/raddit/branches?per_page=100','repos/NatLabRockies/raddit/tags?per_page=100','repos/NatLabRockies/raddit/issues?state=all&per_page=100','repos/NatLabRockies/raddit/pulls?state=all&per_page=100','repos/NatLabRockies/raddit/forks?per_page=100']:
    d=json.loads(subprocess.check_output(['gh','api',endpoint],cwd=REPO))
    if '/forks?' in endpoint:d=[{k:x.get(k) for k in ['full_name','default_branch','pushed_at']} for x in d]
    github.append(dict(url='https://api.github.com/'+endpoint,response=d))
write('PUBLIC_SOURCE_RECEIPTS.json',dict(retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),official_metadata_queries=receipts,github=github,historical_export_revision_inference_from_current_model_commit=False))
for r in receipts:
    d=r.get('data',{});print(r['url'],r.get('http_status',r.get('status')),str(d)[:900])
