"""Separate correction of over-broad numerical solver policy routing."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];target=r/'v44_recovery_r028';target.mkdir(exist_ok=False)
for p in (r/'v44_recovery_r027').glob('*.py'):
    body=p.read_text(encoding='utf8').replace('v44_recovery_r027','v44_recovery_r028').replace('R027','R028').replace('r027','r028')
    (target/p.name).write_text(body,encoding='utf8')
