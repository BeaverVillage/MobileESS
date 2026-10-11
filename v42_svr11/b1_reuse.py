"""Same-epoch B1 FULL A1 reuse; Actual physical PASS is a separate result."""
from pathlib import Path
from v42_pr134_b1.common import read,record
from v42_autonomous_b3.reuse import B1A1ReuseBridge
from .authority import active

class CurrentEpochB1Reuse(B1A1ReuseBridge):
    @classmethod
    def from_campaign(cls,request):
        m=active();root=Path(m['root'])
        row=read(root/'CAMPAIGN_LEDGER.json')['dates']['B1/'+request['day']]
        path=Path(row['result']);result=read(path)
        if record(path)['sha256']!=row['result_SHA'] or result['source_SHA']!=m['execution_SHA']:
            raise PermissionError('SVR11_B1_A1_SAME_SOURCE_BYTES_REQUIRED')
        science=result.get('scientific',{})
        if science.get('PASS') is not True or science.get('accepted') is not True:
            raise ValueError('SVR11_B3_DEPENDENCY_FAILED_NO_VALID_B1_A1')
        # Only A1's independently reverified matrix/domain/point decides reuse.
        # Date-level Actual FAIL cannot invalidate a valid Planning A1 point.
        out=cls(path.parent/'output');out.origin=record(path)
        out.expected_source=m['execution_SHA'];out.expected_day=request['day']
        return out

    def _verify_origin(self,context,output=None):
        r=read(self.origin['path'])
        if record(self.origin['path'])!=self.origin or r['source_SHA']!=self.expected_source or r['day']!=self.expected_day:
            raise PermissionError('SVR11_B1_REUSE_ORIGIN_DRIFT')
        if context.request.authority.source_sha!=self.expected_source:
            raise PermissionError('SVR11_B1_REUSE_EPOCH_DRIFT')
        return super()._verify_origin(context,output)

    def _gap_accepted(self,context,result,lower,upper):
        if super()._gap_accepted(context,result,lower,upper):return True
        m=active()
        return bool(m and m['execution_SHA']==self.expected_source and m.get('A_anytime_FULL_feasible')
            and result.get('FULL_feasible_certified') is True)
