from pathlib import Path
root=Path(__file__).resolve().parents[2];target=root/'v44_recovery_r024b';target.mkdir(exist_ok=False)
for path in (root/'v44_recovery_r024a').glob('*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r024a','r024b').replace('R024A','R024B')
    (target/path.name).write_text(text,encoding='utf-8')
for path in (root/'tests').glob('test_v44_recovery_r024a*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r024a','r024b').replace('R024A','R024B')
    (path.parent/path.name.replace('r024a','r024b')).write_text(text,encoding='utf-8')
print({'created':str(target),'algorithm':'r024a','Native':5400,'Phase_I_cutoff':None})
