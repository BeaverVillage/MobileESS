from pathlib import Path
root=Path(__file__).resolve().parents[2];target=root/'v44_recovery_r025a';target.mkdir(exist_ok=False)
for path in (root/'v44_recovery_r025').glob('*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r025','r025a').replace('R025','R025A')
    (target/path.name).write_text(text,encoding='utf-8')
for path in (root/'tests').glob('test_v44_recovery_r025*.py'):
    text=path.read_text(encoding='utf-8-sig').replace('r025','r025a').replace('R025','R025A')
    (path.parent/path.name.replace('r025','r025a')).write_text(text,encoding='utf-8')
print({'created':str(target)})
