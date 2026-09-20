"""May21 immutable input binding; no model solve or electrical replay."""
import sys,json,gzip,hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
sys.dont_write_bytecode=True
HOME=Path(__file__).absolute().parent
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
sys.path.insert(0,str(ROOT))
DOMAIN=ROOT/'frozen_artifacts/v41r4_may/audit/2025-05-01/domain'
INPUT=ROOT/'frozen_artifacts/v41r3_may/inputs/2025-05-01'
EXPECTED='07e2d7d515915477ce79ffc6a99b6bb7715ec8c4104be6576ac17f727f4875cd'
WORKSPACE=HOME.parent.parent
def sha(p):
    p=Path(p)
    if not p.exists():
        aliases=read(HOME/'SOURCE_PATH_ALIASES.json')
        entry=aliases[str(p)];p=Path(entry['local_copy'])
        assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256']
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()
def record(p):p=Path(p);return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(name,v):
    p=HOME/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def context():
    from dayahead.v38.authority import CapacityAuthority,RackPool,load_wan_authority
    from dayahead.v41r1.migration import FrozenWanView
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v40g.domain import Option
    authority=read(DOMAIN/'DAILY_DOMAIN_AUTHORITY.json')
    for r in [authority['capacity'],authority['rack'],authority['reference'],*authority['sources']]:assert sha(r['path'])==r['sha256']
    cap=read(authority['capacity']['path']);racks=read(authority['rack']['path'])
    from headroom_authority import capacity_binding,install_power_binding
    install_power_binding()
    capacity=capacity_binding(cap,racks)
    weather_path=WORKSPACE/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days/2025-05-01/gfs_d1_weather.parquet'
    weather=pd.read_parquet(weather_path)
    c1_path=ROOT/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json'
    params=load_c1(c1_path);tables={}
    for site,n in capacity.site_capacity.items():
        it=np.array([float(site_it_power_kw(n,g)) for g in range(n+1)])
        tables[site]=2*np.array([exact_c1_pcc_kw(it,float(w.t_wb_c),float(w.rh_pct),params) for w in weather.itertuples()])
    ctx=SimpleNamespace(day='2025-05-01',capacity=capacity,wan=FrozenWanView(load_wan_authority(ROOT)),tables=tables,reference=read(authority['reference']['path']),v41_bounded_compute=dict(total_seconds=600.,fix_and_optimize=True))
    ctx.elapsed={r['job_uid']:r['r1_elapsed_seconds_at_issue'] for r in ctx.reference if 'r1_elapsed_seconds_at_issue' in r}
    from headroom_authority import bind_future_capacity
    original_snapshot=INPUT/'V41_ML_SNAPSHOT_2025-05-01.json'
    snapshot=bind_future_capacity(ctx,original_snapshot);bind(ctx,snapshot,sha(snapshot))
    ctx.jobs=import_frozen(ctx.reference);ctx.power=planning_power(ctx.jobs,ctx);ctx.options={};ctx.candidate_rows={};h=hashlib.sha256()
    manifest=read(DOMAIN/'combined/V41R1_FULL_CANDIDATE_MANIFEST.json');rows={r['job_id']:r for r in manifest['jobs']}
    assert sha(manifest['candidate_artifact']['path'])==manifest['candidate_artifact']['sha256']
    with gzip.open(manifest['candidate_artifact']['path'],'rb') as f:
        for raw in f:
            h.update(raw);v=json.loads(raw);uid=v['job_id'];assert hashlib.sha256(raw).hexdigest()==rows[uid]['candidate_row_SHA']
            ctx.candidate_rows[uid]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),options=len(v['options']))
            ctx.options[uid]=tuple(Option(*o) for o in v['options'])
    assert h.hexdigest()==EXPECTED and sum(map(len,ctx.options.values()))==7563689
    assert set(ctx.options)=={r['job_uid'] for r in ctx.reference}
    ctx.references={r['job_uid']:r for r in ctx.reference}
    ctx.input_sources=[record(authority['reference']['path']),record(snapshot),record(weather_path),record(c1_path),record(authority['capacity']['path']),record(authority['rack']['path']),record(manifest['candidate_artifact']['path']),record(DOMAIN/'DAILY_DOMAIN_AUTHORITY.json')]
    return ctx
def option_reader(ctx):
    def options(row,capacity,wan,elapsed,temporal_only=False):
        assert not temporal_only and row==ctx.references[row['job_uid']]
        assert capacity is ctx.capacity and wan is ctx.wan and elapsed==ctx.elapsed
        return ctx.options[row['job_uid']]
    return options
