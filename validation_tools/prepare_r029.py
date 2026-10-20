"""Build a separate performance revision without editing sealed/running code."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];target=r/'v44_recovery_r029';target.mkdir(exist_ok=False)
for p in (r/'v44_recovery_r028').glob('*.py'):
    body=p.read_text(encoding='utf8').replace('v44_recovery_r028','v44_recovery_r029').replace('R028','R029').replace('r028','r029')
    if p.name=='handover.py':
        body=body.replace('R027_VALIDATED_REPAIRS_SAFE_HANDOVER','R028_VALIDATED_REPAIRS_SAFE_HANDOVER').replace('supersedes_pending_r027','supersedes_pending_r028').replace('R027_PENDING_HANDOVER_ONLY','R028_PENDING_HANDOVER_ONLY').replace('SUPERSEDED_R027','SUPERSEDED_R028')
    (target/p.name).write_text(body,encoding='utf8')
