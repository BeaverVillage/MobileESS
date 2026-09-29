from common16 import *
sys.path.insert(0,str(V13))
import train13

def main():
    output=[];receipts=[]
    old=pd.read_csv(V15/'RUNTIME_MODEL_COMPARISON.csv').set_index('arm')
    for arm in ['R0','R1','R2']:
        fs=[];ps=[]
        for i in range(1,6):
            directory=V13/'.local'/f'fold{i}' if arm=='R0' else V15/'.local'/f'runtime_fold{i}'
            name='EXPANDING_S4' if arm=='R0' else arm
            s=read(directory/(name+'.json'));p=pd.read_parquet(directory/(name+'.parquet'))
            fs.append(s);ps.append(p);receipts.extend([rec(directory/(name+'.json')),rec(directory/(name+'.parquet'))])
        m=train13.summarize(arm,fs,ps)
        for key in ['Q90_coverage','Q90_pinball','min_fold_coverage','gt4h_coverage','gt12h_coverage','gt24h_coverage','reservation_actual_GPUh','proper_interval_NLL']:
            assert np.isclose(m[key],old.loc[arm,key],rtol=1e-12,atol=1e-10),(arm,key)
        for g in 'ABCDEFGHI':assert m['gate_'+g]==old.loc[arm,'gate_'+g]
        output.append(m)
    write('R0_PR89_BASELINE_REPRODUCTION.json',dict(time=now(),PASS=True,model_refits=0,independently_recomputed_arms=output,sources=receipts,
        CC4_C0='Frozen T0/B0 preserved; no T2_F0/T3_F2 promotion',CC4_prior_receipt=rec(V15/'CC4_C0_REPRODUCTION.json')))
    print('R0_PR89_REPRODUCED',[(r['arm'],r['min_fold_coverage'],r['Q90_pinball']) for r in output],flush=True)

if __name__=='__main__':main()
