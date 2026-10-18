"""Create a separate repair revision; never mutate an active sealed source."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
source=root/'v44_recovery_r026f1'; target=root/'v44_recovery_r027'
target.mkdir(exist_ok=False)
for path in source.glob('*.py'):
    body=path.read_text(encoding='utf8').replace('v44_recovery_r026f1','v44_recovery_r027').replace('R026F1','R027').replace('r026f1','r027')
    (target/path.name).write_text(body,encoding='utf8')
# Repair records are a shared campaign queue, with immutable original failures.
path=target/'failure_continue.py'
body=path.read_text().replace('R027_REPAIR_QUEUE','R026F1_REPAIR_QUEUE').replace('R027_REPAIR_RELEASES','R026F1_REPAIR_RELEASES').replace('R027_FAILURE_DEFERRED','R026F1_FAILURE_DEFERRED')
path.write_text(body,encoding='utf8')
# No automatic repeat of May02's scientific time limit.
path=target/'operations.py'; body=path.read_text()
body=body.replace("(parent/'R027_FAILURE_DEFERRED.json')","(parent/'R026F1_FAILURE_DEFERRED.json')")
anchor="    if parent is None or int(parent.name[-3:])>=3:return False"
assert body.count(anchor)==1
body=body.replace(anchor,"    if parent is not None and int(parent.name[-3:])<3:\n        from .repairs import legacy_retry\n        if legacy_retry(parent,result,OPS,PERMIT):return True\n"+anchor)
body=body.replace("from .conditional_campaign import run_case","from .conditional_campaign import run_case\n    from .integer_repair import install as integer_install")
body=body.replace('with voltage_install(),source_io_install', 'with integer_install(),voltage_install(),source_io_install')
# Permission is explicit in the new recorded instruction; keep all science policy.
body=body.replace("first_task='MAY02_B3_A2_FRESH_NATIVE0'", "first_task='DIAGNOSED_IMPLEMENTATION_ERRORS_NEW_ATTEMPTS_ONLY'")
path.write_text(body,encoding='utf8')
