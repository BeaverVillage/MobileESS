"""Operational resource measurements; no scientific inputs or model changes."""
from pathlib import Path
import re
import math
import psutil


def persist_model(model,output):
    """Lossless MPS persistence using Python gzip, including a full byte read-back."""
    import gzip,hashlib,shutil
    from dayahead.paper_analysis.storage import atomic,write_json,sha
    output=Path(output);raw=output/'_PRIMARY_MODEL_BUILD.mps'
    require_new=not raw.exists()
    if not require_new:raise RuntimeError('PRESERVE_INCOMPLETE_MODEL_SERIALIZATION')
    model.write(str(raw.resolve()))
    original=dict(bytes=raw.stat().st_size,sha256=sha(raw))
    packed=output/'PRIMARY_MODEL.mps.gz'
    with atomic(packed) as target:
        with gzip.GzipFile(fileobj=target,mode='wb',compresslevel=1,mtime=0) as compressed:
            with raw.open('rb') as source:shutil.copyfileobj(source,compressed,8*1024*1024)
    digest=hashlib.sha256();size=0
    with gzip.open(packed,'rb') as stream:
        while block:=stream.read(8*1024*1024):digest.update(block);size+=len(block)
    if original!={'bytes':size,'sha256':digest.hexdigest()}:raise RuntimeError('MODEL_GZIP_READBACK_DRIFT')
    write_json(output/'MODEL_PERSISTENCE.json',dict(status='PASS',uncompressed=original,
        gzip_bytes=packed.stat().st_size,gzip_sha256=sha(packed),lossless_reopen_equality=True))
    raw.resolve().relative_to(output.resolve());raw.unlink()


def process_measure():
    memory=psutil.Process().memory_info()._asdict();host=psutil.virtual_memory()
    return dict(process_memory_bytes=memory,process_peak_RAM_bytes=memory.get('peak_wset',memory['rss']),
        host_physical_RAM_bytes=host.total,host_available_RAM_bytes=host.available,
        host_swap=psutil.swap_memory()._asdict())


def measure(model,log=None):
    memory=psutil.Process().memory_info()._asdict();host=psutil.virtual_memory()
    value=dict(total_variables=model.NumVars,binary_variables=model.NumBinVars,
        integer_variables=model.NumIntVars,continuous_variables=model.NumVars-model.NumIntVars,
        linear_constraints=model.NumConstrs,general_constraints=model.NumGenConstrs,
        matrix_nonzeros=model.NumNZs,Gurobi_current_memory_GB=float(model.MemUsed),
        Gurobi_peak_memory_GB=float(model.MaxMemUsed),process_memory_bytes=memory,
        process_peak_RAM_bytes=memory.get('peak_wset',memory['rss']),
        host_physical_RAM_bytes=host.total,host_available_RAM_bytes=host.available,
        MemLimit_GB='UNLIMITED' if math.isinf(model.Params.MemLimit) else model.Params.MemLimit,
        SoftMemLimit_GB='UNLIMITED' if math.isinf(model.Params.SoftMemLimit) else model.Params.SoftMemLimit,Threads=model.Params.Threads,Method=model.Params.Method,
        NodefileStart_GB=model.Params.NodefileStart,NodefileDir=model.Params.NodefileDir)
    if log and Path(log).exists():
        text=Path(log).read_text(errors='replace')
        matches=list(re.finditer(r'Presolved: ([\d,]+) rows, ([\d,]+) columns, ([\d,]+) nonzeros',text))
        if matches:
            last=matches[-1];n=lambda x:int(x.replace(',',''))
            value['presolved']=dict(constraints=n(last[1]),variables=n(last[2]),matrix_nonzeros=n(last[3]))
            types=re.search(r'Variable types: ([\d,]+) continuous, ([\d,]+) integer \(([\d,]+) binary\)',text[last.end():])
            if types:value['presolved'].update(continuous_variables=n(types[1]),integer_variables=n(types[2]),binary_variables=n(types[3]))
    return value
