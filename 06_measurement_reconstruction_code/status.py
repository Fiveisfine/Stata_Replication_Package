import json
from collections import Counter
from pathlib import Path
import pandas as pd
from config import ROOT

inv=pd.read_csv(ROOT/'02_audit/source_inventory.csv')
for year in sorted(inv.year.unique()):
    ps=list((ROOT/'03_cache'/str(year)).glob('s*.json'))
    ms=[json.loads(p.read_text(encoding='utf-8')) for p in ps]
    print(json.dumps({'year':int(year),'expected':int(inv.year.eq(year).sum()),'done':len(ms),'status':dict(Counter(x['status'] for x in ms)),'retained_million':round(sum(x['retained_rows'] for x in ms)/1e6,2)},ensure_ascii=False))
for log in ['cache_early.log','cache_late.log','match.log','experiments.log']:
    p=ROOT/'06_logs'/log
    if p.exists():print(log,p.read_text(encoding='utf-8',errors='replace').splitlines()[-1:])
