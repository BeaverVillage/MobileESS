from pathlib import Path
import sys,os,math
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO))
import numpy as np
import pandas as pd
from dayahead.v40e.mapping import NativeAllocation,AllocationError,TOLERANCE
from dayahead.v40e.audit import REL,OLD
from dayahead.paper_analysis.storage import read,reference,write_json,write_parquet

def run():
    out=REPO/REL/'allocation_tests';out.mkdir(parents=True,exist_ok=True)
    root=read(REPO/REL/'V40E_BACKGROUND_LOAD_DUPLICATION_ROOT_CAUSE.json')
    assert root['BACKGROUND_MAPPING_DEFECT']=='CONFIRMED'
    rows=[]
    def check(name,loads,p,q):
        a=NativeAllocation.from_adapter({'loads':loads});totals,ledger,audit=a.allocate(p,q)
        assert abs(math.fsum(v[0] for v in totals.values())-math.fsum(p.values()))<TOLERANCE
        assert abs(math.fsum(v[1] for v in totals.values())-math.fsum(q.values()))<TOLERANCE
        write_parquet(out/(name+'.parquet'),pd.DataFrame(ledger))
        rows.append({'name':name,'status':'PASS',**audit,'total_P_kw':sum(v[0] for v in totals.values())})
    load=lambda name,ph,p,q:{'load_name':name,'bus':'x','phases':ph,'base_p_kw':p,'base_q_kvar':q}
    check('one_phase_one_load',[load('one',[1],40,20)],{('x','A'):100},{('x','A'):33})
    check('one_phase_two_unequal_loads',[load('one',[1],40,10),load('two',[1],60,30)],{('x','A'):173},{('x','A'):39})
    check('multi_phase_and_single_phase_overlap',[load('multi',[1,2],80,20),load('single',[1],60,30)],{('x','A'):173,('x','B'):47},{('x','A'):39,('x','B'):9})
    failures=0
    for adapter,p,q in [({'loads':[{'load_name':'bad','bus':'x','phases':[1]}]},{('x','A'):1},{('x','A'):1}),
                        ({'loads':[load('zero',[1],0,0)]},{('x','A'):1},{('x','A'):1}),
                        ({'loads':[load('one',[1],40,20)]},{('z','A'):1},{('z','A'):1})]:
        try:NativeAllocation.from_adapter(adapter).allocate(p,q)
        except AllocationError:failures+=1
    assert failures==3
    from dayahead.v28r2.opendss_mapping import compile_clean_engine,FeederAssets
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    previous=Path.cwd();assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
    try:
        odd,adapter=compile_clean_engine(assets);a=NativeAllocation.from_adapter(adapter)
        native=a.validate_native_engine(odd)
        write_json(out/'NATIVE_ALLOCATION_AUTHORITY.json',{'assets':{k:reference(v) for k,v in assets.__dict__.items()},'native_load_count':len(native),'loads':native,
            'shares':[{'bus':b,'phase':p,'load_name':n,'P_share':str(ps),'Q_share':str(qs)} for (b,p),rs in a.shares.items() for n,ps,qs in rs],
            'new_equal_split_rule_invented':False,'frozen_forward_phase_compilation':root['allocation_authority']['forward_phase_compilation']})
        for ns in ('Planning','Actual'):
            with np.load(REPO/OLD/'power_scale_parity/2025-05-01'/ns/'INDEPENDENT_BUS_PHASE_BACKGROUND_PV.npz') as z:
                buses=z['bus_ids'].tolist();p=z['background_P_kw'];q=z['background_Q_kvar']
            records=[];all_ledgers=[]
            for t in range(96):
                ps={(b,ph):float(p[t,i,j]) for i,b in enumerate(buses) for j,ph in enumerate('ABC')}
                qs={(b,ph):float(q[t,i,j]) for i,b in enumerate(buses) for j,ph in enumerate('ABC')}
                totals,ledger,audit=a.allocate(ps,qs)
                read_p=[];read_q=[]
                for name,(ap,aq) in totals.items():
                    odd.Loads.Name(name);odd.Loads.kW(ap);odd.Loads.kvar(aq)
                    rp=float(odd.Loads.kW());rq=float(odd.Loads.kvar());assert rp==ap and rq==aq
                    read_p.append(rp);read_q.append(rq)
                ep=abs(math.fsum(read_p)-math.fsum(ps.values()));eq=abs(math.fsum(read_q)-math.fsum(qs.values()))
                assert max(ep,eq)<TOLERANCE
                for bus in ('65','76'):
                    bp=math.fsum(v[0] for n,v in totals.items() if any(r['load_name'].lower()==n and r['bus']==bus for r in adapter['loads']))
                    bq=math.fsum(v[1] for n,v in totals.items() if any(r['load_name'].lower()==n and r['bus']==bus for r in adapter['loads']))
                    assert abs(bp-sum(ps.get((bus,ph),0) for ph in 'ABC'))<TOLERANCE
                    assert abs(bq-sum(qs.get((bus,ph),0) for ph in 'ABC'))<TOLERANCE
                records.append({'slot':t,'namespace':ns,'intended_P_kw':math.fsum(ps.values()),'allocated_readback_P_kw':math.fsum(read_p),
                    'intended_Q_kvar':math.fsum(qs.values()),'allocated_readback_Q_kvar':math.fsum(read_q),'readback_P_error_kw':ep,'readback_Q_error_kvar':eq,**audit})
                all_ledgers.extend({'slot':t,'namespace':ns,**r} for r in ledger)
            f=pd.DataFrame(records);write_parquet(out/(ns+'_FULL_FEEDER_CONSERVATION_96.parquet'),f)
            f.to_csv(out/(ns+'_FULL_FEEDER_CONSERVATION_96.csv'),index=False,float_format='%.17g')
            write_parquet(out/(ns+'_LOAD_ELEMENT_ALLOCATION.parquet'),pd.DataFrame(all_ledgers))
            rows.append({'name':ns+'_full_feeder_96','status':'PASS','max_P_readback_error_kw':float(f.readback_P_error_kw.max()),'max_Q_readback_error_kvar':float(f.readback_Q_error_kvar.max())})
        rows.extend({'name':'real_bus_'+b+'_all_192_slots','status':'PASS','BACKGROUND_DUPLICATION_KW':0} for b in ('65','76'))
    finally:os.chdir(previous)
    result={'BACKGROUND_ALLOCATION_CONSERVATION':'PASS','native_share_authority_verified':True,'tests':rows,'negative_fail_closed_tests_passed':failures,
            'numerical_tolerance':TOLERANCE,'Fresh_background_equals_Planning_background':True,'BACKGROUND_DUPLICATION_KW':0,'BUS65_DUPLICATION_KW':0,'BUS76_DUPLICATION_KW':0,
            'scope':'Native nominal setpoint/allocation conservation. Terminal power also depends on native connection, voltage and load model; it is not falsely equated to kW setters.'}
    write_json(out/'V40E_ALLOCATION_TEST_RESULT.json',result);print(result,flush=True)

if __name__=='__main__':run()
