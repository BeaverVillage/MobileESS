"""Read-only PR162 authority and isolated joint-formulation artifacts."""
import os
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
import sys,json,csv,hashlib,subprocess,time,re,itertools,importlib.util
from pathlib import Path
from datetime import datetime,timezone
from fractions import Fraction as F
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
prior=module('joint_read_only_authority',ROOT/'docs/v42_m_practical_exact_solver_overnight_20261008/practical_support.py')
hc=prior.hc;verifier=prior.verifier;sha=prior.sha;atomic=prior.atomic;read=prior.read;table=prior.table;clean=prior.clean;stamp=prior.stamp
BASE='f6d48e8892e1d36023f107130c2c9bfdfa5d4ebe';LB=.5687116104049206;UB=.6306505800203936
ARCHIVE=ROOT/'docs/v42_m_practical_exact_solver_overnight_20261008'
SETTINGS=dict(Threads=1,Method=2,NodeMethod=1,Crossover=0,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0,BarConvTol=1e-8,TimeLimit=600)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
def info(name):
    text=str(name);family=text.split('[')[0];args=text[text.find('[')+1:-1].split(',') if '[' in text else []
    unit=next((a for a in args if a.startswith('MESS')),None)
    slot=int(args[-1]) if args and args[-1].isdigit() and family!='route_flow' else None
    return family,unit,slot,args
def load():return hc.load()
def center():
    with np.load(ARCHIVE/'runs/native_production_initial/BEST_VALID_POINT.npz') as z:return z['x'].copy()
def root_point():
    with np.load(ARCHIVE/'external_production/external_nodes/0000/LP_POINT_PROOF.npz') as z:return z['x'].copy(),z['Pi'].copy()
def objective_identity(A,d):
    result=verifier.verify(ROOT,d,1);assert result['PASS'];return result
def forbid_optimize():
    import gurobipy as gp
    old=gp.Model.optimize
    def forbidden(*args,**kwargs):raise AssertionError('OPTIMIZE_FORBIDDEN_IN_EXACTNESS_OR_CERTIFICATE_RECOVERY')
    gp.Model.optimize=forbidden
    return gp,old
def save_vector(path,**arrays):
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:np.savez_compressed(f,**arrays);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
