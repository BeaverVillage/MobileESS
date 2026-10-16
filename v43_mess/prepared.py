"""Reuse this attempt's certified Native0 K16 packet, never an old bound."""
from pathlib import Path
from types import FunctionType

from v43.common import atomic


def run_prepared_k48(module,case,packet,certificate,budget,output):
    source=module.identity(case)
    def prepared(current,point,target):
        if (current is not case or point is not None or packet['source']!=source
                or packet['K']!=16 or packet['start'] is not None):
            raise ValueError('ONLY_CURRENT_NATIVE0_SEEDLESS_K16_PACKET_CAN_BE_REUSED')
        proof=module.verify_packet(current,packet)
        if proof!=certificate:raise ValueError('PREPARED_K16_CERTIFICATE_DRIFT')
        atomic(Path(target)/'CURRENT_NATIVE0_PACKET_REUSED.json',dict(PASS=True,source=source,
            certificate_sha=certificate['certificate_sha'],packet_math_rebuilt=False,
            old_point_UB_LB_or_Native_clock_reused=False,Native_calls=0))
        return packet,certificate
    original=module.run_current_k48
    namespace=dict(original.__globals__,prepare_k16=prepared)
    function=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    function.__kwdefaults__=original.__kwdefaults__
    return function(case,None,budget,output)
