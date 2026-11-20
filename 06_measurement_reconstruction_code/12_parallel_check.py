import importlib
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from config import ROOT


def main():
    m=importlib.import_module('03_match');f=pd.read_parquet(ROOT/'04_data/firm_coordinates.parquet');q=f[f.year.eq(2019)&f.coord_valid]
    scenarios={'as_provided':(q.lon.to_numpy(),q.lat.to_numpy()),'poi_wgs_office_wgs_assumed':(q.lon.to_numpy(),q.lat.to_numpy()),'poi_wgs_office_bd09_assumed':m.bd_to_wgs(q.lon.to_numpy(),q.lat.to_numpy())}
    columns=['lon','lat','wgs_lon','wgs_lat','mask','assisted_mask']
    d=next(pq.ParquetFile(ROOT/'03_cache/2019/s00196.parquet').iter_batches(batch_size=5000,columns=columns)).to_pandas()
    payload=tuple(d[c].to_numpy() for c in columns)
    m.init_count_worker(2019,scenarios,len(q));expected=m.count_payload(payload)
    with ProcessPoolExecutor(max_workers=2,initializer=m.init_count_worker,initargs=(2019,scenarios,len(q))) as p:
        got=p.submit(m.count_payload,payload).result()
    assert expected[0]==got[0]
    for key in expected[1]:assert np.array_equal(expected[1][key],got[1][key])
    result={'passed':True,'pois':len(d),'firms':len(q),'scenarios':list(scenarios),'comparison':'serial vs spawned-process exact integer count arrays, all features and requested radii'}
    (ROOT/'02_audit/parallel_count_equivalence.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result,flush=True)


if __name__=='__main__':main()
