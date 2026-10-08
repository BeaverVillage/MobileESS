from v42_a_stage_acceptance import memory

def test_zero_free_memory_never_enables_a_limit_or_stop(monkeypatch):
    def zero(ptr):
        status=ptr._obj
        status.ullAvailPhys=0;status.ullAvailPageFile=0
        return 1
    monkeypatch.setattr(memory.ctypes.windll.kernel32,'GlobalMemoryStatusEx',zero)
    s=memory.sample()
    assert s['available_RAM_bytes']==0 and s['available_commit_bytes']==0
    assert s['memory_limits_enabled'] is False and s['automatic_memory_stop'] is False
    assert 'reserve_bytes' not in s and 'unsafe' not in s

def test_memory_telemetry_failure_does_not_abort_execution(monkeypatch):
    monkeypatch.setattr(memory.ctypes.windll.kernel32,'GlobalMemoryStatusEx',lambda ptr:0)
    s=memory.sample()
    assert s['automatic_memory_stop'] is False and 'system_memory_telemetry_error' in s
