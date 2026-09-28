from common9 import *
from fit9 import *
import argparse,ctypes as c
def cuda_device():
    lib=c.WinDLL('nvcuda.dll');assert lib.cuInit(0)==0
    dev=c.c_int();assert lib.cuDeviceGet(c.byref(dev),0)==0
    b=c.create_string_buffer(256);assert lib.cuDeviceGetName(b,256,dev)==0
    return b.value.decode()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm');ap.add_argument('--threads',type=int);ap.add_argument('--device');ap.add_argument('--dest');a=ap.parse_args()
    f=pd.read_parquet(LOCAL/'final/TRAIN.parquet');prep=read(ROOT/'FINAL_PREPROCESSING.json')
    identity=cuda_device() if a.device=='gpu' else 'CPU'
    print('EXPLICIT_DEVICE_REQUEST',a.device,identity,'GPU index0; OpenCL platform0/device0 for D1',flush=True)
    m=fit(f,prep,a.arm,a.threads,a.device);m.save(Path(a.dest))
    if a.device=='gpu' and a.arm.startswith('D2'):
        actual=m.meta['xgboost_config']['learner']['generic_param']['device'];assert actual=='cuda:0','GPU_FALLBACK'
        print('ACTUAL_XGBOOST_DEVICE',actual,identity,flush=True)
    print('TRAINING_SECONDS',m.meta['training_seconds'],flush=True)
if __name__=='__main__':main()
