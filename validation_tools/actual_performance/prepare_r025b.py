from pathlib import Path
root=Path(__file__).resolve().parents[2];target=root/'v44_recovery_r025b';target.mkdir(exist_ok=False)
for path in (root/'v44_recovery_r025a').glob('*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r025a','r025b').replace('R025A','R025B')
    (target/path.name).write_text(text,encoding='utf-8')
for path in (root/'tests').glob('test_v44_recovery_r025a*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r025a','r025b').replace('R025A','R025B')
    (path.parent/path.name.replace('r025a','r025b')).write_text(text,encoding='utf-8')
print({'created':str(target)})
