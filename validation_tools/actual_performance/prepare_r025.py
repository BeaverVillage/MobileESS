from pathlib import Path

root=Path(__file__).resolve().parents[2]
target=root/'v44_recovery_r025'
target.mkdir(exist_ok=False)
for path in (root/'v44_recovery_r024a').glob('*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r024a','r025').replace('R024A','R025')
    (target/path.name).write_text(text,encoding='utf-8')
for path in (root/'tests').glob('test_v44_recovery_r024a*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r024a','r025').replace('R024A','R025')
    (path.parent/path.name.replace('r024a','r025')).write_text(text,encoding='utf-8')
print({'created':str(target)})
