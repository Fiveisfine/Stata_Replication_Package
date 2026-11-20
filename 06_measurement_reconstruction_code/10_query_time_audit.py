"""Full 2021-labelled archive query-time profile, independent of outcomes."""
import csv
import codecs
import importlib
import json
from collections import Counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pc
from scipy.spatial import cKDTree

from config import ROOT
from parsers import location
from staging import staged_source

xyz=importlib.import_module('02_build_cache').xyz


def main():
    inv=pd.read_csv(ROOT/'02_audit/source_inventory.csv');inv=inv[inv.year.eq(2021)]
    f=pd.read_parquet(ROOT/'04_data/firm_coordinates.parquet');q=f[f.year.eq(2021)&f.coord_valid]
    tree=cKDTree(xyz(q.lon.to_numpy(),q.lat.to_numpy()));threshold=2*np.sin(12/6371.0088/2)
    rows=[]
    dest=ROOT/'02_audit/query_time_2021';dest.mkdir(exist_ok=True)
    for _,s in inv.iterrows():
        marker=dest/f'{s.source_id}.json'
        if marker.exists():rows.append(json.loads(marker.read_text(encoding='utf-8')));continue
        meta={};overall=Counter();near=Counter();malformed=[0]
        with staged_source(s.to_dict(),meta) as source:
            with open(source['path'],'rb') as handle:prefix=handle.read(65536)
            try:codecs.getincrementaldecoder('utf-8-sig')().decode(prefix,final=False);encoding='utf-8-sig'
            except UnicodeDecodeError:encoding='gb18030'
            def invalid(row):malformed[0]+=1;return 'skip'
            def consume(d):
                years=d['查询时间'].fillna('').str.extract(r'^(20\d{2})',expand=False).fillna('unknown')
                overall.update(years.value_counts().to_dict())
                lon,lat=location(d['经纬度']);valid=lon.between(70,140)&lat.between(0,60)
                if valid.any():
                    dis,_=tree.query(xyz(lon[valid].to_numpy(),lat[valid].to_numpy()),distance_upper_bound=threshold)
                    near.update(years.loc[valid].loc[np.isfinite(dis)].value_counts().to_dict())
            reader=None
            try:
                reader=pc.open_csv(source['path'],read_options=pc.ReadOptions(block_size=8*1024*1024,encoding='utf8' if encoding=='utf-8-sig' else encoding),parse_options=pc.ParseOptions(newlines_in_values=True,invalid_row_handler=invalid),convert_options=pc.ConvertOptions(include_columns=['查询时间','经纬度'],column_types={'查询时间':pa.string(),'经纬度':pa.string()},strings_can_be_null=False))
                for b in reader:consume(b.to_pandas())
                parser='arrow_utf8_selected_metadata_columns'
            except (pa.ArrowInvalid,pa.ArrowKeyError,UnicodeDecodeError):
                if reader is not None:reader.close()
                overall=Counter();near=Counter();csv.field_size_limit(512*1024*1024)
                with open(source['path'],'r',encoding=encoding,errors='replace',newline='') as handle:
                    data=[]
                    for row in csv.DictReader(handle):
                        data.append({'查询时间':row.get('查询时间',''),'经纬度':row.get('经纬度','')})
                        if len(data)>=100000:consume(pd.DataFrame(data));data=[]
                    if data:consume(pd.DataFrame(data))
                parser='python_metadata_fallback'
            finally:
                if reader is not None:reader.close()
        result={'source_id':s.source_id,'path':s.path,'folder_year':2021,'query_year_counts_raw_records':dict(overall),'query_year_counts_near_offices':dict(near),'malformed_rows':malformed[0],'parser':parser,'note':'Query timestamp is not automatically an opening/closing date or proof of a complete annual snapshot.'}
        marker.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');rows.append(result)
        print('TIMESTAMP',s.source_id,dict(overall),flush=True)
    table=[]
    for row in rows:
        for scope,field in [('all_source_records','query_year_counts_raw_records'),('within_12km_offices','query_year_counts_near_offices')]:
            for year,n in row[field].items():table.append({'source_id':row['source_id'],'scope':scope,'query_year':year,'records':n})
    d=pd.DataFrame(table);d.to_csv(ROOT/'02_audit/2021_query_time_full_profile.csv',index=False,encoding='utf-8-sig')
    summary=d.groupby(['scope','query_year'],as_index=False).records.sum();summary.to_csv(ROOT/'02_audit/2021_query_time_summary.csv',index=False,encoding='utf-8-sig')
    print(summary.to_string(index=False),flush=True)


if __name__=='__main__':main()
