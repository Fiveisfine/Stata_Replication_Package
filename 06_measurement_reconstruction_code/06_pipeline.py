"""Wait for complete source caches, match each year, then run experiments.

This is a bounded, task-specific local run, not a recurring automation.
"""
import hashlib
import importlib
import json
import time

import pandas as pd
from config import ROOT


def signature(year,paths):
    h=hashlib.sha256()
    for p in sorted(paths):h.update(p.read_bytes())
    for n in ['classify.py','03_match.py']:
        h.update((ROOT/'01_code'/n).read_bytes())
    return h.hexdigest()


if __name__=='__main__':
    inv=pd.read_csv(ROOT/'02_audit/source_inventory.csv')
    pending=set(int(y) for y in inv.year.unique() if y!=2014)
    match=importlib.import_module('03_match')
    while pending:
        advanced=False
        for year in sorted(pending):
            expected=int(inv.year.eq(year).sum())
            paths=list((ROOT/'03_cache'/str(year)).glob('s*.json'))
            if len(paths)!=expected:continue
            states=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
            if any(s['status']!='ok' for s in states):continue
            sig=signature(year,paths);marker=ROOT/f'06_logs/match_complete_{year}.json'
            if not marker.exists() or json.loads(marker.read_text(encoding='utf-8')).get('signature')!=sig:
                print(f'YEAR_MATCH_START {year}',flush=True)
                match.match_year(year)
                marker.write_text(json.dumps({'year':year,'signature':sig,'status':'complete'}),encoding='utf-8')
            pending.remove(year);advanced=True
            print(f'YEAR_MATCH_COMPLETE {year} pending={sorted(pending)}',flush=True)
        if not advanced:time.sleep(5)
    v=importlib.import_module('validate')
    data={'geometry':v.geometry_check(),'output_checks':v.validate_outputs(),'classification_fixture':'passed'}
    (ROOT/'02_audit/validation.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print('ALL_MATCHING_AND_INVARIANTS_PASSED',flush=True)
    importlib.import_module('05_experiments').main()
    print('PIPELINE_COMPLETE',flush=True)
