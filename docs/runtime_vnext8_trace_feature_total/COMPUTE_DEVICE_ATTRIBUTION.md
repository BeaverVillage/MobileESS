# 계산 장치 귀속 한계

CPU single/4-thread 및 `device_type=gpu, gpu_use_dp=True`로 동일 TRAIN·M3_F2 두 quantile을 재학습해 pre-April DEV 예측 동등성을 확인했다. 원래 선택된 CPU model bytes를 유지했다. 벤치마크 이름은 RTX4060_OpenCL_GPU지만 explicit platform/device index를 고정하지 않았다. verbosity=-1로 runtime device-name 로그도 없다.

사후 **무학습** OpenCL 열거 결과 platform0=device0 NVIDIA GeForce RTX4060 Laptop, platform1=device0 Intel UHD다. LightGBM4.6 GPUTreeLearner::InitGPU는 index=-1이면 Boost.Compute default_device를 사용한다. 기본 GPU 순서상 NVIDIA 사용을 추정할 수 있으나, 빌드된 Boost 버전과 당시 device-name 로그까지 확보한 직접 관측은 아니다. 6.67초는 OpenCL GPU 경로 실측, 정확한 RTX4060 귀속은 이 한계를 명시한다. CPU4-thread 선택은 CPU 측정과 동등성만으로도 유지된다. freeze 이후 이 문제를 이유로 다시 fit하거나 모델을 교체하지 않았다.

공식 코드: https://github.com/microsoft/LightGBM/blob/v4.6.0/src/treelearner/gpu_tree_learner.cpp#L652 ; https://github.com/boostorg/compute/blob/boost-1.84.0/include/boost/compute/system.hpp . `OPENCL_DEVICE_AUDIT.json`이 실제 열거 결과다.
