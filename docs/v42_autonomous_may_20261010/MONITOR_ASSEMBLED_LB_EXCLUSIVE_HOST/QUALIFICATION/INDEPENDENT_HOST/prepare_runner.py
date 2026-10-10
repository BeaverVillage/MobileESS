from pathlib import Path

source=Path('D:/v42_monitor_assembled_lb_review_20261010_01/run_native_denied_review_03.py').read_text(encoding='utf-8')
def replace(old,new):
    global source
    assert old in source,old
    source=source.replace(old,new)
replace('import hashlib\n','import hashlib\nimport importlib\nimport os\n')
replace('def main():\n    import pytest','def main():\n    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1"\n    os.chdir(REPO)\n    preloads=[]\n    for name in ("v42_autonomous_b2.pricing_cache","v42_autonomous_b2.rmp_presolve",\n                 "v42_autonomous_b2.worker","v42_autonomous_b2.f1_basis",\n                 "v42_autonomous_b2.f1_state","v42_autonomous_b2.dw_native",\n                 "v42_autonomous_b2.f1_price_seed"):\n        importlib.import_module(name);preloads.append(name)\n    import pytest')
replace("xml_path = OUT / 'selected_native_denied_03.xml'","xml_path = OUT / 'INDEPENDENT_SELECTED_NATIVE_DENIED_103.xml'")
replace("[*selected, '-q', '--junitxml='", "[*selected, '-q', '-p', 'no:cacheprovider', '--junitxml='")
replace("tmp/monitor_exclusive_host_native_denied_03","tmp/monitor_exclusive_host_independent_20261010_01")
replace("selected_tests_PASS=exit_code == 0 and stats['tests'] > 0", "selected_tests_PASS=exit_code == 0 and stats['tests'] == 103 and stats['skipped'] == 0")
replace("producer=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),", "producer=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),\n                   protected_science_preloads_before_retained_descriptors_and_denial=preloads,\n                   original_repo_science1007_not_current_execution99_binding=True,")
replace("path = OUT / 'MONITOR_EXCLUSIVE_HOST_NATIVE_DENIED_REVIEW_RECEIPT.json'", "path = OUT / 'MONITOR_EXCLUSIVE_HOST_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json'\n    assert not path.exists()")
path=Path(__file__).resolve().parent/'run_independent_review.py'
assert not path.exists()
path.write_text(source,encoding='utf-8')
print(path)
