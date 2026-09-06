from __future__ import annotations
from pathlib import Path
import logging, shutil, time, traceback, zipfile
from .context import PipelineContext
from .locate import locate_inputs
from .data import load_data
from .modeling import run_modeling
from .validate import validate_stage
from .report import write_report
from .utils import sha256_file,write_json,zip_review

def publish(ctx,logger):
    if ctx.publish_dir.exists(): raise FileExistsError(ctx.publish_dir)
    ctx.publish_dir.mkdir(parents=True)
    for n in ['outputs','models','predictions','metrics','reports','logs']:
        s=ctx.run_dir/n
        if s.exists(): shutil.copytree(s,ctx.publish_dir/n)
    shutil.copy2(ctx.config_path,ctx.publish_dir/'pipeline_used.yaml')
    manifest=[]
    for p in sorted(ctx.publish_dir.rglob('*')):
        if p.is_file(): manifest.append({'relative_path':str(p.relative_to(ctx.publish_dir)),'size_bytes':p.stat().st_size,'sha256':sha256_file(p)})
    write_json(ctx.publish_dir/'manifest.json',manifest)
    rz=ctx.review_root/f'stage_k5b2_kestrel_forecasting_review_{ctx.run_tag}.zip'; zip_review(ctx.publish_dir,rz)
    logger.info('Published: %s',ctx.publish_dir); logger.info('Review ZIP: %s',rz)
def failure_zip(ctx):
    p=ctx.review_root/f'stage_k5b2_kestrel_forecasting_failure_{ctx.run_tag}.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for r in ['reports','logs']:
            d=ctx.run_dir/r
            if d.exists():
                for f in d.rglob('*'):
                    if f.is_file(): z.write(f,f.relative_to(ctx.run_dir))
        z.write(ctx.config_path,'pipeline_used.yaml')
    return p
def run_pipeline(ctx,logger):
    start=time.time(); times={}
    try:
        t=time.time(); locate_inputs(ctx,logger); times['locate']=time.time()-t
        t=time.time(); data=load_data(ctx,logger); times['load']=time.time()-t
        t=time.time(); res=run_modeling(ctx,data,logger); times['modeling']=time.time()-t
        t=time.time(); val=validate_stage(ctx,data,res,logger); write_report(ctx,data,res,val); times['validate_report']=time.time()-t
        write_json(ctx.report_dir/'run_timing.json',{'stage_seconds':times,'elapsed_before_publish':time.time()-start})
        publish(ctx,logger); write_json(ctx.run_dir/'run_complete.json',{'status':'success','run_tag':ctx.run_tag,'elapsed_seconds':time.time()-start,'publish_dir':ctx.publish_dir})
    except Exception as e:
        write_json(ctx.report_dir/'failure.json',{'status':'failure','error_type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc(),'stage_seconds':times})
        p=failure_zip(ctx); logger.exception('Stage K5-B2 failed; failure ZIP: %s',p); raise
