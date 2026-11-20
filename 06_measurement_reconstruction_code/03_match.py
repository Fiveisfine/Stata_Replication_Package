import argparse
import json
import re
import os
import time
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree

from config import ROOT, RADII, CATEGORIES
from classify import classify
from importlib import import_module

xyz=import_module('02_build_cache').xyz
R=6371.0088
FEATURES=CATEGORIES+['combined','nightlife','assisted_combined','old_keyword','total','restaurant','entertainment','shopping','nonalcohol_total']+['without_'+c for c in CATEGORIES]


def gcj_to_wgs(lon,lat):
    # Standard approximate inverse; scenario only, never represented as recovered metadata.
    x=np.asarray(lon,dtype=float)-105;y=np.asarray(lat,dtype=float)-35
    dl=-100+2*x+3*y+.2*y*y+.1*x*y+.2*np.sqrt(np.abs(x))
    dl+=(20*np.sin(6*x*np.pi)+20*np.sin(2*x*np.pi))*2/3
    dl+=(20*np.sin(y*np.pi)+40*np.sin(y/3*np.pi))*2/3
    dl+=(160*np.sin(y/12*np.pi)+320*np.sin(y*np.pi/30))*2/3
    dn=300+x+2*y+.1*x*x+.1*x*y+.1*np.sqrt(np.abs(x))
    dn+=(20*np.sin(6*x*np.pi)+20*np.sin(2*x*np.pi))*2/3
    dn+=(20*np.sin(x*np.pi)+40*np.sin(x/3*np.pi))*2/3
    dn+=(150*np.sin(x/12*np.pi)+300*np.sin(x/30*np.pi))*2/3
    rad=np.radians(lat);magic=1-.00669342162296594323*np.sin(rad)**2;root=np.sqrt(magic)
    dl=dl*180/((6378245*(1-.00669342162296594323))/(magic*root)*np.pi)
    dn=dn*180/(6378245/root*np.cos(rad)*np.pi)
    return np.asarray(lon)-dn,np.asarray(lat)-dl


def bd_to_wgs(lon,lat):
    x=np.asarray(lon)-.0065;y=np.asarray(lat)-.006
    z=np.sqrt(x*x+y*y)-.00002*np.sin(y*np.pi*3000/180)
    theta=np.arctan2(y,x)-.000003*np.cos(x*np.pi*3000/180)
    return gcj_to_wgs(z*np.cos(theta),z*np.sin(theta))


def deduplicate(year):
    dest=ROOT/'03_cache'/str(year);files=sorted(p for p in dest.glob('s*.parquet') if re.fullmatch(r's\d+\.parquet',p.name))
    if not files:return None
    con=duckdb.connect();con.execute("SET memory_limit='6GB'");con.execute('SET threads=4')
    temp=ROOT/'03_cache/duckdb_temp';temp.mkdir(exist_ok=True)
    con.execute('SET temp_directory=?',[str(temp)])
    filelist=[str(f) for f in files]
    con.from_parquet(filelist).create_view('raw')
    n=con.execute('select count(*) from raw').fetchone()[0]
    conflict=con.execute("select poi_key,count(*) n,max(lon)-min(lon) lon_range,max(lat)-min(lat) lat_range from raw where starts_with(poi_key,'id:') group by poi_key having lon_range>.001 or lat_range>.001").df()
    conflict.to_csv(ROOT/f'02_audit/id_coordinate_conflicts_{year}.csv',index=False,encoding='utf-8-sig')
    con.register('conflicts',conflict)
    query="""with g as (select
      case when starts_with(r.poi_key,'physical:') then '' else r.poi_key end as stable_id,
      case when starts_with(r.poi_key,'physical:') or c.poi_key is not null then r.physical_key else 0::UBIGINT end as physical_group_key,
      case when starts_with(r.poi_key,'physical:') then hash(lower(trim(coalesce(r.address,'')))) else 0::UBIGINT end as address_group_key,
      arg_min(struct_pack(lon:=r.lon,lat:=r.lat,wgs_lon:=r.wgs_lon,wgs_lat:=r.wgs_lat),r.source_id) as coord,
      bit_or(r.mask) as mask,bit_or(r.assisted_mask) as assisted_mask,count(*) as record_multiplicity
      from raw r left join conflicts c on r.poi_key=c.poi_key group by stable_id,physical_group_key,address_group_key)
      select stable_id,physical_group_key,address_group_key,coord.lon lon,coord.lat lat,coord.wgs_lon wgs_lon,coord.wgs_lat wgs_lat,mask,assisted_mask,record_multiplicity from g"""
    target=dest/'deduplicated.parquet'
    con.execute('COPY ('+query+') TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(target)])
    n2=con.execute('select count(*) from read_parquet(?)',[str(target)]).fetchone()[0]
    con.execute("COPY (select category,typecode,count(*) as raw_record_n,bit_or(mask) mask,bit_or(assisted_mask) assisted_mask from raw group by category,typecode order by raw_record_n desc) TO ? (HEADER, DELIMITER ',')",[str(ROOT/f'02_audit/category_code_profile_{year}.csv')])
    con.execute("COPY (select name,category,typecode,city,address,lon,lat,mask,assisted_mask from raw where (mask & 31)>0 limit 1000) TO ? (HEADER, DELIMITER ',')",[str(ROOT/f'02_audit/category_examples_{year}.csv')])
    status={'year':year,'retained_raw_records':n,'deduplicated_records':n2,'duplicates_removed':n-n2,'id_coordinate_conflict_keys':len(conflict),'source_cache_files':len(files),'fallback_key':'normalized name + exact normalized address + coordinates rounded to six decimals; distinct addresses retained','note':'Duplicates are evaluated only within the cached office-neighborhood universe; not a national duplicate rate.'}
    (ROOT/f'02_audit/deduplication_{year}.json').write_text(json.dumps(status,indent=2),encoding='utf-8');con.close()
    return target


def feature_matrix(frame):
    mask=frame['mask'].to_numpy(dtype=np.int64);assisted=frame.assisted_mask.to_numpy(dtype=np.int64)
    a=[((mask>>i)&1) for i in range(5)]
    combined=(mask&31)!=0
    a += [combined,(mask&30)!=0,(assisted&31)!=0,((mask>>8)&1),np.ones(len(frame),dtype=np.int64),((mask>>5)&1),((mask>>6)&1),((mask>>7)&1),~combined]
    a += [(mask&(31^(1<<i)))!=0 for i in range(5)]
    return np.column_stack(a).astype(np.int64)


def count_batch(tree,lon,lat,features,nfirms,radii=RADII):
    counts=np.zeros((len(radii),nfirms,len(FEATURES)),dtype=np.int64)
    ptree=cKDTree(xyz(lon,lat))
    pairs=tree.sparse_distance_matrix(ptree,2*np.sin(max(radii)/R/2),output_type='coo_matrix')
    for k,radius in enumerate(radii):
        keep=pairs.data<=2*np.sin(radius/R/2)
        a=coo_matrix((np.ones(int(keep.sum()),dtype=np.int64),(pairs.row[keep],pairs.col[keep])),shape=(nfirms,len(lon))).tocsr()
        counts[k]=a@features
    return counts


def init_count_worker(year,scenarios,nfirms):
    global WORK_YEAR,WORK_TREES,WORK_NFIRMS
    WORK_YEAR=year;WORK_NFIRMS=nfirms
    WORK_TREES={key:cKDTree(xyz(*value)) for key,value in scenarios.items()}


def count_payload(payload):
    rawlon,rawlat,wgslon,wgslat,mask,assisted=payload
    features=feature_matrix(pd.DataFrame({'mask':mask,'assisted_mask':assisted}))
    result={}
    for key,tree in WORK_TREES.items():
        lon=rawlon;lat=rawlat
        if key!='as_provided' and WORK_YEAR>2017:
            lon,lat=gcj_to_wgs(lon,lat);explicit=np.isfinite(wgslon)&np.isfinite(wgslat)
            lon=np.where(explicit,wgslon,lon);lat=np.where(explicit,wgslat,lat)
        result[key]=count_batch(tree,lon,lat,features,WORK_NFIRMS,radii=RADII if key=='as_provided' else [5])
    return len(rawlon),result


def match_year(year,only_native=False):
    start=time.monotonic();p=deduplicate(year)
    firms=pd.read_parquet(ROOT/'04_data/firm_coordinates.parquet');allq=firms[firms.year.eq(year)].copy();q=allq[allq.coord_valid].reset_index(drop=True)
    if p is None or not len(q):return
    inv=pd.read_csv(ROOT/'02_audit/source_inventory.csv');expected=inv[inv.year.eq(year)]
    meta=[json.loads(x.read_text(encoding='utf-8')) for x in (ROOT/'03_cache'/str(year)).glob('s*.json')]
    dedup_status=json.loads((ROOT/f'02_audit/deduplication_{year}.json').read_text(encoding='utf-8'))
    complete=len(meta)==len(expected) and all(x['status']=='ok' for x in meta) and dedup_status['source_cache_files']==len(expected)
    scenarios={'as_provided':(q.lon.to_numpy(),q.lat.to_numpy())}
    if not only_native:
        scenarios['poi_wgs_office_wgs_assumed']=(q.lon.to_numpy(),q.lat.to_numpy())
        scenarios['poi_wgs_office_bd09_assumed']=bd_to_wgs(q.lon.to_numpy(),q.lat.to_numpy())
    counts={k:np.zeros((4,len(q),len(FEATURES)),dtype=np.int64) for k in scenarios}
    pf=pq.ParquetFile(p);done=0
    workers=int(os.environ.get('MATCH_WORKERS','2'))
    columns=['lon','lat','wgs_lon','wgs_lat','mask','assisted_mask']
    def payloads():
        for batch in pf.iter_batches(batch_size=50000,columns=columns):
            f=batch.to_pandas()
            yield tuple(f[c].to_numpy() for c in columns)
    def accumulate(answer):
        nonlocal done
        n,values=answer
        for key,value in values.items():
            if key=='as_provided':counts[key]+=value
            else:counts[key][2]+=value[0]
        done+=n
        if done%500000==0:print(f'MATCH {year} points={done} workers={workers} sec={time.monotonic()-start:.1f}',flush=True)
    if workers<=1:
        init_count_worker(year,scenarios,len(q))
        for payload in payloads():accumulate(count_payload(payload))
    else:
        with ProcessPoolExecutor(max_workers=workers,initializer=init_count_worker,initargs=(year,scenarios,len(q))) as pool:
            iterator=iter(payloads());pending=set();exhausted=False
            while pending or not exhausted:
                while not exhausted and len(pending)<workers*2:
                    try:payload=next(iterator)
                    except StopIteration:exhausted=True;break
                    pending.add(pool.submit(count_payload,payload))
                if pending:
                    finished,pending=wait(pending,return_when=FIRST_COMPLETED)
                    for future in finished:accumulate(future.result())
    for key,a in counts.items():
        out=q[['row_id','id','year','CITYCODE','PROVINCECODE','coord_valid']].copy()
        for ri,radius in enumerate(RADII):
            if key!='as_provided' and radius!=5:continue
            for fi,feature in enumerate(FEATURES):out[f'{feature}_{radius}km']=a[ri,:,fi]
        out['source_run_complete']=complete
        out['observed_local_poi']=a[3 if key=='as_provided' else 2,:,FEATURES.index('total')]>0
        out['known_missing_province']=(year==2023)&q.PROVINCECODE.eq(440000)
        out['usable_experimental']=out.source_run_complete&out.observed_local_poi&~out.known_missing_province
        out['coordinate_scenario']=key
        out.to_parquet(ROOT/f'04_data/poi_{year}_{key}.parquet',index=False)
    print(f'MATCH_DONE {year} points={done} firms={len(q)} complete={complete} seconds={time.monotonic()-start:.1f}',flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--years',default='2012,2013,2015,2016,2017,2018,2019,2020,2021,2022,2023');a.add_argument('--native-only',action='store_true');args=a.parse_args()
    for year in map(int,args.years.split(',')):match_year(year,args.native_only)
