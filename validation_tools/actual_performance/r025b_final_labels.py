from pathlib import Path
root=Path(__file__).resolve().parents[2]
for name in ('operations.py','handover.py','reporting.py'):
    path=root/'v44_recovery_r025b'/name;text=path.read_text(encoding='utf-8')
    text=text.replace('PHASE400','PHASE1000').replace('Phase400','Phase1000').replace('Native400','Phase I Native1000')
    text=text.replace('Native342.117','Native414.457').replace('342.1169981956482','414.4569981098175')
    text=text.replace('attempt007의 측정','attempt008의 측정').replace('attempt007 A2','attempt009 A2')
    path.write_text(text,encoding='utf-8')
print({'PASS':True})
