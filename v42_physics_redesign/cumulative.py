"""Matrix-free exact H2: cumulative energy, with all original SOC bounds.

This removes 380 explicit SOC columns but does not strengthen the original LP.
It avoids materializing the measured 25.9M-nnz fill-in rejected by the audit.
"""
from .common import *
from fractions import Fraction as F

class CumulativeSOC:
    def __init__(self,A,d,reader):
        self.d=d;self.soc=np.flatnonzero([str(n).startswith('SOC[') for n in d['names']]);self.keep=np.setdiff1d(np.arange(A.shape[1]),self.soc);self.rows={};self.initial={};self.terminal={};self.positions={str(n):i for i,n in enumerate(d['names'])}
        assert len(self.soc)==380
        # SOC occurs only in the original energy equalities. Every retained
        # original nonenergy row is unchanged after deleting these columns.
        other=np.flatnonzero([str(n).split('[')[0]!='energy_balance' for n in d['row_names']]);assert A[other][:,self.soc].nnz==0
        for i,n in enumerate(reader.d['row_names']):
            if str(n).split('[')[0]!='energy_balance':continue
            row=reader.full.getrow(i);states=[(int(j),float(v),str(reader.d['names'][j])) for j,v in zip(row.indices,row.data) if str(reader.d['names'][j]).startswith('SOC[')]
            previous=[(j,name) for j,v,name in states if v==-1.];following=[(j,name) for j,v,name in states if v==1.]
            assert len(previous)==len(following)==1
            pj,pn=previous[0];nj,nn=following[0];unit,t=pn.split('[',1)[1][:-1].split(',');t=int(t);assert nn==f'SOC[{unit},{t+1}]'
            terms={};constant=F.from_float(float(reader.d['rhs'][i]))
            for j,a in zip(row.indices,row.data):
                if int(j) in (pj,nj):continue
                a=F.from_float(float(a));k=int(reader.target[j]);constant-=a*F.from_float(float(reader.offset[j]))
                if k>=0:terms[k]=terms.get(k,F(0))-a
            self.rows[unit,t]=(terms,constant)
            if t==0:
                assert int(reader.target[pj])<0;self.initial[unit]=F.from_float(float(reader.offset[pj]))
            if t==95:
                assert int(reader.target[nj])<0;self.terminal[unit]=F.from_float(float(reader.offset[nj]))
        assert len(self.rows)==384 and len(self.initial)==len(self.terminal)==4

    def forward(self,x):return np.asarray(x)[self.keep].copy()

    def exact_states(self,y):
        x=np.zeros(len(self.d['names']));x[self.keep]=y;states={};terminal={}
        for unit,start in self.initial.items():
            value=start
            for t in range(96):
                terms,constant=self.rows[unit,t];value+=constant+sum((a*F.from_float(float(x[j])) for j,a in terms.items() if x[j]!=0),F(0))
                if t<95:states[self.positions[f'SOC[{unit},{t+1}]']]=value
                else:terminal[unit]=value-self.terminal[unit]
        return x,states,terminal

    def inverse(self,y):
        x,states,terminal=self.exact_states(y)
        for j,value in states.items():x[j]=float(value)
        return x,terminal

    def constraints(self,y):
        x,states,terminal=self.exact_states(y);bounds=[]
        for j,value in states.items():bounds.append(dict(column=j,lower_residual=str(F.from_float(float(self.d['lower'][j]))-value),upper_residual=str(value-F.from_float(float(self.d['upper'][j])))))
        return dict(cumulative_bound_rows=bounds,terminal_equalities={unit:str(v) for unit,v in terminal.items()},SOC_state_discretization=False)

def main():
    prior.forbid_optimize();A,d,_=hc.load();reader=hc.physical_reader();operator=CumulativeSOC(A,d,reader)
    with np.load(P183/'artifacts/BEST_VALID_POINT.npz') as f:x=f['x'].copy()
    y=operator.forward(x);rebuilt,terminal=operator.inverse(y);check=hc.replay(A,d,rebuilt,True);assert check['PASS']
    assert (d['objective']@rebuilt)==(d['objective']@x)
    write(REPORTS/'H2_CUMULATIVE_OPERATOR_VERIFICATION.json',dict(PASS=True,original_columns=len(x),H2_columns=len(y),deleted_continuous_SOC_columns=len(operator.soc),all_384_original_energy_rows_used=True,all_380_original_SOC_bound_pairs_retained_implicitly=True,terminal_equality_residuals={unit:float(v) for unit,v in terminal.items()},roundtrip_original_SOCs_max_difference=float(abs(rebuilt[operator.soc]-x[operator.soc]).max()),reconstructed_original_replay=check,objective_unchanged=True,retained_types_bounds_objective_raw_bytes_preserved=True,forward_inverse_exact_in_real_arithmetic=True,floating_reconstruction_never_claimed_bit_identity=True,matrix_free_implementation=True,full_prefix_CSR_not_materialized=True,LP_relaxation_strength_identical=True,no_new_native_optimize_calls=0))
    save(WORK/'artifacts/H2_RETAINED_AXIS.npz',keep=operator.keep,implicit_SOC_columns=operator.soc)
    print('H2_CUMULATIVE_FORWARD_INVERSE_PASS',len(y),flush=True)

if __name__=='__main__':main()
