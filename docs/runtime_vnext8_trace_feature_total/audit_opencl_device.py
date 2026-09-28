"""Read-only OpenCL device enumeration; no model fit or data access."""
from common8 import *
import ctypes as c
def main():
    lib=c.WinDLL('OpenCL.dll');uint=c.c_uint;size=c.c_size_t;void=c.c_void_p
    lib.clGetPlatformIDs.argtypes=[uint,c.POINTER(void),c.POINTER(uint)];lib.clGetPlatformIDs.restype=c.c_int
    lib.clGetDeviceIDs.argtypes=[void,c.c_ulonglong,uint,c.POINTER(void),c.POINTER(uint)];lib.clGetDeviceIDs.restype=c.c_int
    lib.clGetDeviceInfo.argtypes=[void,uint,size,void,c.POINTER(size)];lib.clGetDeviceInfo.restype=c.c_int
    n=uint();assert lib.clGetPlatformIDs(0,None,c.byref(n))==0;platforms=(void*n.value)();lib.clGetPlatformIDs(n,platforms,None);rows=[]
    for i,p in enumerate(platforms):
        count=uint();ret=lib.clGetDeviceIDs(p,4,0,None,c.byref(count))
        if ret==-1:continue
        assert ret==0;devices=(void*count.value)();assert lib.clGetDeviceIDs(p,4,count,devices,None)==0
        for j,d in enumerate(devices):
            def info(code):
                length=size();assert lib.clGetDeviceInfo(d,code,0,None,c.byref(length))==0;b=c.create_string_buffer(length.value);assert lib.clGetDeviceInfo(d,code,length,b,None)==0;return b.value.decode()
            rows.append(dict(platform_index=i,device_index=j,name=info(0x102B),vendor=info(0x102C),driver=info(0x102D)))
    write('OPENCL_DEVICE_AUDIT.json',dict(time=now(),devices=rows,only_one_GPU_device=len(rows)==1,benchmark_default_device_identified=len(rows)==1 and '4060' in rows[0]['name'],
      method='Read-only OpenCL ICD enumeration. No post-freeze training. Default OpenCL GPU unambiguous only if single GPU enumerated.'))
    print(rows,flush=True)
if __name__=='__main__':main()
