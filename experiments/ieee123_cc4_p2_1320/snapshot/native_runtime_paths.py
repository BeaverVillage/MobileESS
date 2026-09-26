"""Native DSS receives exact original PCC bytes at an isolated D: path."""
from pathlib import Path
from dataclasses import replace
import runtime_environment as env
from authority_recovery import sha

def install(output):
    output=Path(output);native=output/'native_dss';native.mkdir(parents=True,exist_ok=True)
    import opendssdirect as dss
    dss.Basic.AllowChangeDir(False);dss.Basic.DataPath(str(native))
    original=dss.NewContext
    def context(*a,**k):
        x=original(*a,**k);x.Basic.AllowChangeDir(False);x.Basic.DataPath(str(native));return x
    dss.NewContext=context
    pcc=output/'dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss'
    source=env.PR/'dayahead/artifacts/v16_2'/pcc.name
    assert sha(source)=='ba13e3081df606c18d61f1e02300b23f7be00dc2d22bc4c8064d04f40beec719'
    pcc.parent.mkdir(parents=True,exist_ok=True)
    if not env.exists(pcc):pcc.write_bytes(source.read_bytes())
    assert sha(pcc)==sha(source)
    from dayahead import full_ieee123_g11_v16_1 as grid
    compile_original=grid._compile
    grid._compile=lambda assets,contract,pcc_asset:compile_original(assets,contract,pcc)
    from dayahead.v28r2 import opendss_mapping as mapping
    assets_original=mapping.FeederAssets.from_repo
    mapping.FeederAssets.from_repo=classmethod(lambda cls,repo:replace(assets_original(repo),pcc=pcc))
    return pcc
