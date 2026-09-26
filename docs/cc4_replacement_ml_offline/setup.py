from pathlib import Path
import subprocess,tarfile,io,json,hashlib,shutil,datetime
out=Path('CC4_REPLACEMENT_ML_OFFLINE_20260924_180000'); repo=Path('v41r4_final_results_pr')
refs={'A':'04f9c738ad80786b3860638304043b06129c04ef','B':'2d6e22e2b448454bb4a860a07f38c20ad3ef834d','C':'4309a4e5ea2c7893f79bcc7e747ca7d13fc5de42','D':'43710c96c36f7e66257885a56ef6df697b3c53bb'}
manifest={}
for k,ref in refs.items():
    meta=json.loads(subprocess.check_output(['gh','api',f'repos/BeaverVillage/MobileESS/commits/{ref}']))
    manifest[k]={'ref':ref,'github_sha':meta['sha'],'url':meta['html_url'],'message':meta['commit']['message']}
    roots={'A':['dayahead/v41','dayahead/v41r2/authority.py','dayahead/v40r6'], 'B':['dayahead/v40r6','dayahead/v40r5','dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork','dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'], 'C':['dayahead/v40r6r1','dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork'], 'D':['dayahead/v40r3','dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml']}[k]
    data=subprocess.check_output(['git','-C',str(repo),'archive',ref,*roots]); dest=out/'history'/k; dest.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:t.extractall(dest,filter='data')
    print(k,len(data),flush=True)
for pr in [42,33,34]:
    meta=json.loads(subprocess.check_output(['gh','api',f'repos/BeaverVillage/MobileESS/pulls/{pr}']))
    manifest[f'PR{pr}']={k:meta[k] for k in ['number','html_url','state','merged_at']};manifest[f'PR{pr}']['head']=meta['head']['sha']
(out/'GITHUB_VERIFICATION.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('OK')
