"""Reuse immutable control JSON across slot/event rows, preserving every byte."""
from v44_actual_audit_encoding import ExactImmutableEncoding
from v44_recovery_r029.immutable import FrozenDict,FrozenList


class SharedControlEncoding(ExactImmutableEncoding):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.shared_control_rows=0

    def canonical_list(self,rows,canonical):
        if not isinstance(rows,list):raise TypeError('R035_AUDIT_LIST_REQUIRED')
        parts=[]
        for row in rows:
            decomposed=(isinstance(row,dict) and all(isinstance(k,str) for k in row)
                and ('frozen_trajectory_SHA' in row or
                     any(type(v) in (FrozenDict,FrozenList) for v in row.values())))
            if decomposed:
                self.shared_control_rows+=int('controls' in row)
                parts.append('{'+','.join(canonical(k)+':'+
                    (self.encoded(v,canonical) if isinstance(v,(dict,list)) else canonical(v))
                    for k,v in sorted(row.items()))+'}')
            else:parts.append(self.encoded(row,canonical))
        return '['+','.join(parts)+']'
