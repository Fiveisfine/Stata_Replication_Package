import argparse
import gc
import json
import os
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

from config import ROOT
from classify import RULE_VERSION, classify, fixture_check
from parsers import batches
from staging import staged_source


def xyz(lon,lat):
    lo=np.radians(lon);la=np.radians(lat)
    return np.column_stack([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])


def source_token(s):
    return f"{s['source_id']}:{int(s['actual_bytes'])}:{int(s['mtime_ns'])}:{RULE_VERSION}:cache12km-v2"


def process_year(year,limit=None,kinds=None,source_ids=None):
    inventory=pd.read_csv(ROOT/'02_audit/source_inventory.csv')
    sources=inventory[inventory.year.eq(year)]
    if source_ids:sources=sources[sources.source_id.isin(source_ids.split(','))]
    if kinds:sources=sources[sources.kind.isin(kinds.split(','))]
    if limit:sources=sources.head(limit)
    firms=pd.read_parquet(ROOT/'04_data/firm_coordinates.parquet')
    q=firms[firms.year.eq(year)&firms.coord_valid]
    dest=ROOT/'03_cache'/str(year);dest.mkdir(exist_ok=True)
    if not len(q):
        (dest/'NO_COORDINATES.json').write_text(json.dumps({'year':year,'firm_years':int(firms.year.eq(year).sum()),'reason':'All office coordinates missing. Raw POI files are present; not interpreted as zero.'}),encoding='utf-8')
        print(f'YEAR {year}: no office coordinates, no spatial counts generated',flush=True);return
    tree=cKDTree(xyz(q.lon.to_numpy(),q.lat.to_numpy()))
    threshold=2*np.sin(12.0/6371.0088/2)
    def prefilter(lon,lat):
        d,_=tree.query(xyz(lon,lat),k=1,distance_upper_bound=threshold,workers=1)
        return np.isfinite(d)
    for _,s in sources.iterrows():
        source=s.to_dict();sid=s.source_id;target=dest/f'{sid}.parquet';status=dest/f'{sid}.json';token=source_token(source)
        if status.exists() and os.environ.get('POI_FORCE_REBUILD')!='1':
            old=json.loads(status.read_text(encoding='utf-8'))
            if old.get('token')==token and old.get('status')=='ok' and target.exists():continue
            if old.get('status')=='failed':(ROOT/f'02_audit/source_failure_before_recovery_{sid}.json').write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
        meta={'source_id':sid,'year':year,'path':s.path,'kind':s.kind,'city_label':s.city,'status':'running','token':token,'rule_version':RULE_VERSION,'raw_rows':0,'valid_rows':0,'retained_rows':0,'malformed_rows':0,'malformed_examples':[]}
        start=time.monotonic();writer=None;temp=target.with_suffix('.partial.parquet');compatibility_retry=False
        print(f'START {year} {sid} {Path(s.path).name}',flush=True)
        try:
            with staged_source(source,meta) as local_source:
              for frame in batches(local_source,meta,prefilter):
                if s.kind!='dbf_early':
                    valid=frame.lon.between(70,140)&frame.lat.between(0,60)
                    meta['valid_rows']+=int(valid.sum());frame=frame.loc[valid].reset_index(drop=True)
                    if not len(frame):continue
                    frame=frame.loc[prefilter(frame.lon.to_numpy(),frame.lat.to_numpy())].reset_index(drop=True)
                if not len(frame):continue
                frame['name']=frame.name.fillna('').str.normalize('NFKC').str.strip()
                frame['category']=frame.category.fillna('').str.normalize('NFKC').str.strip()
                frame['city']=frame.city.fillna('').str.strip()
                flags,assisted=classify(frame);frame['mask']=flags;frame['assisted_mask']=assisted
                normalized=frame.name.str.lower().str.replace(r'\s+','',regex=True)
                keyframe=pd.DataFrame({'name':normalized,'lon':frame.lon.round(6),'lat':frame.lat.round(6)})
                frame['physical_key']=pd.util.hash_pandas_object(keyframe,index=False).to_numpy(dtype=np.uint64)
                pid=frame.poi_id.fillna('').astype(str).str.strip()
                stable_id=pid.str.match(r'^[Bb][A-Za-z0-9]{6,}$')
                frame['poi_key']=np.where(stable_id,'id:'+pid,'physical:'+frame.physical_key.astype(str))
                frame['source_id']=sid
                frame=frame[['poi_key','physical_key','name','category','typecode','city','address','poi_id','lon','lat','wgs_lon','wgs_lat','mask','assisted_mask','source_id']]
                table=pa.Table.from_pandas(frame,preserve_index=False)
                if writer is None:writer=pq.ParquetWriter(temp,table.schema,compression='zstd')
                writer.write_table(table);meta['retained_rows']+=len(frame)
            if writer is None:
                empty=pd.DataFrame({'poi_key':pd.Series(dtype=str),'physical_key':pd.Series(dtype='uint64'),'name':pd.Series(dtype=str),'category':pd.Series(dtype=str),'typecode':pd.Series(dtype=str),'city':pd.Series(dtype=str),'address':pd.Series(dtype=str),'poi_id':pd.Series(dtype=str),'lon':pd.Series(dtype=float),'lat':pd.Series(dtype=float),'wgs_lon':pd.Series(dtype=float),'wgs_lat':pd.Series(dtype=float),'mask':pd.Series(dtype='uint16'),'assisted_mask':pd.Series(dtype='uint16'),'source_id':pd.Series(dtype=str)})
                pq.write_table(pa.Table.from_pandas(empty,preserve_index=False),temp,compression='zstd')
            else:writer.close();writer=None
            os.replace(temp,target);meta['status']='ok'
        except Exception as exc:
            meta['status']='failed';meta['error']=traceback.format_exc()
            if writer:writer.close()
            compatibility_retry=str(s.path).lower().endswith('.csv') and isinstance(exc,(pa.ArrowInvalid,UnicodeDecodeError)) and os.environ.get('POI_CSV_PARSER')!='python'
        meta['seconds']=round(time.monotonic()-start,2)
        status.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"DONE {year} {sid} {meta['status']} raw={meta['raw_rows']} retained={meta['retained_rows']} sec={meta['seconds']}",flush=True)
        if meta['status']=='failed':print(meta['error'],flush=True)
        if compatibility_retry:
            # Restart the whole source, never append a second parser's rows to a
            # partially written cache. Keep the original error as audit evidence.
            (ROOT/f'02_audit/parser_recovery_{sid}.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
            previous=os.environ.get('POI_CSV_PARSER')
            os.environ['POI_CSV_PARSER']='python'
            try:process_year(year,source_ids=sid)
            finally:
                if previous is None:os.environ.pop('POI_CSV_PARSER',None)
                else:os.environ['POI_CSV_PARSER']=previous
        if int(sid[1:])%20==0:gc.collect()


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--years',default='2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023');a.add_argument('--limit',type=int);a.add_argument('--kinds');a.add_argument('--source-ids');args=a.parse_args()
    fixture_check().to_csv(ROOT/'02_audit/classification_fixtures.csv',index=False,encoding='utf-8-sig')
    for year in map(int,args.years.split(',')):process_year(year,args.limit,args.kinds,args.source_ids)
