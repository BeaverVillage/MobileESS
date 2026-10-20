from pathlib import Path
ops=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY')
for name in ('collect_watchdog','audit_active_revision'):
    old=ops/(name+'_r024a.py');new=ops/(name+'_r025.py')
    assert not new.exists()
    text=old.read_text(encoding='utf-8-sig').replace('r024a','r025').replace('R024A','R025')
    new.write_text(text,encoding='utf-8')
print({'PASS':True,'collectors':'r025'})
