# V22S Melbourne 12-site scale artifacts

이 디렉터리는 2025년 4월 Melbourne 12-site facility identity, capacity boundary, matched host denominator, IEEE123 equivalent capacity 후보를 보존한다.

엄격 원칙: actual load와 capacity를 혼용하지 않고, 미확인값을 0으로 만들지 않으며, MVA/nameplate를 IT MW로 바꾸지 않는다. ML·forecast·GPU-h·B0–B3·OpenDSS·grid science는 실행하지 않았다.

재현: `python dayahead/tools/build_v22s_scale_authority.py`
검증: `python -m unittest tests.test_v22s_scale_authority -v`
