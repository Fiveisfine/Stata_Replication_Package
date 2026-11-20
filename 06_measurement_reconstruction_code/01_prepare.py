import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import ROOT, ORIGINAL, V2, POI_ROOT


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def main():
    source = ORIGINAL / '03_data_audit/poi_full_file_manifest.csv'
    old = pd.read_csv(source)
    old['canonical_path'] = old.path.map(lambda x: str(Path(x).resolve()).lower())
    old[old.canonical_path.duplicated(False)].to_csv(ROOT/'02_audit/old_repeated_file_references.csv', index=False, encoding='utf-8-sig')
    sources = old.drop_duplicates('canonical_path').copy().reset_index(drop=True)
    # The old inventory selected cities with offices. Include other city files
    # as well, because a neighboring city's POIs can fall inside an office buffer.
    seen=set(sources.canonical_path)
    additions=[]
    for year in [2020,2021,2022]:
        for p in sorted((POI_ROOT/str(year)).rglob('*.csv')):
            key=str(p.resolve()).lower()
            if key not in seen:
                additions.append({'year':year,'city':'additional_neighbor_source','kind':f'csv_{year}','path':str(p),'canonical_path':key,'raw_rows':np.nan,'valid_rows':np.nan})
                seen.add(key)
    if additions:sources=pd.concat([sources,pd.DataFrame(additions)],ignore_index=True)
    sources['source_id'] = [f's{i:05d}' for i in range(len(sources))]
    sources['exists'] = sources.path.map(lambda x: Path(x).exists())
    sources['actual_bytes'] = sources.path.map(lambda x: Path(x).stat().st_size if Path(x).exists() else 0)
    sources['mtime_ns'] = sources.path.map(lambda x: Path(x).stat().st_mtime_ns if Path(x).exists() else 0)
    sources[['source_id','year','city','kind','path','exists','actual_bytes','mtime_ns','raw_rows','valid_rows','canonical_path']].to_csv(ROOT/'02_audit/source_inventory.csv',index=False,encoding='utf-8-sig')
    inp = ORIGINAL/'03_data_audit/poi_full_firm_year_input.csv'
    firms = pd.read_csv(inp)
    assert not firms.duplicated(['id','year']).any()
    firms['row_id'] = np.arange(len(firms))
    firms['coord_valid'] = firms.lon.between(70,140)&firms.lat.between(0,60)
    firms.to_parquet(ROOT/'04_data/firm_coordinates.parquet',index=False)
    firms.groupby('year').agg(firm_years=('id','size'),coordinate_valid=('coord_valid','sum')).to_csv(ROOT/'02_audit/firm_coordinate_coverage.csv',encoding='utf-8-sig')
    paths = [source, inp, ORIGINAL/'04_empirical_results/酒文化与评级分歧12-23年-漂绿进一步分析_poi合并.dta', ORIGINAL/'08_revision_experiments/outputs/review_analysis_panel.dta', ORIGINAL/'08_revision_experiments/source/Managerial-climate-attention-index-2001-2023.xlsx']
    paths += [ORIGINAL/'02_code'/n for n in ['09_build_poi_pilot.py','15_build_poi_full.py','16_convert_and_merge_poi_full.do','37_sustainability_revision_exact_tests.do','41_review_driven_mca_validation.do','42_pollute_followup_validation.do']]
    pd.DataFrame([{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths]).to_csv(ROOT/'02_audit/referenced_input_sha256.csv',index=False,encoding='utf-8-sig')
    packages = {}
    for p in ['numpy','pandas','scipy','pyarrow','duckdb','python-calamine','xlrd','lxml','pyhdfe','linearmodels','statsmodels']:
        try: packages[p] = importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError: packages[p] = None
    (ROOT/'06_logs/environment.json').write_text(json.dumps({'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'packages':packages},indent=2),encoding='utf-8')
    print(json.dumps({'sources_unique':len(sources),'old_repeated_references':int(old.canonical_path.duplicated().sum()),'missing_paths':int((~sources.exists).sum()),'firm_years':len(firms),'missing_2014_coordinates':int(((firms.year==2014)&~firms.coord_valid).sum())}),flush=True)


if __name__ == '__main__':
    main()
