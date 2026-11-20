"""Compare CSV samples to same-package GCJ02/WGS84-labelled point geometries.

These are local consistency probes, not independent geodetic ground truth.
"""
import csv
import struct
from pathlib import Path
import numpy as np
import pandas as pd
from config import ROOT,POI_ROOT


def dbf_sample(p,n=100):
    with p.open('rb') as f:
        h=f.read(32);total,hl,rl=struct.unpack('<IHH',h[4:12]);fields=[];off=1
        while f.tell()<hl:
            b=f.read(32)
            if not b or b[0]==13:break
            raw=b[:11].split(b'\0')[0]
            try:name=raw.decode('utf-8')
            except UnicodeDecodeError:name=raw.decode('gb18030',errors='replace')
            fields.append((name,off,b[16]));off+=b[16]
        enc=p.with_suffix('.cpg').read_text().strip() if p.with_suffix('.cpg').exists() else 'gb18030'
        f.seek(hl);rows=[]
        for _ in range(min(n,total)):
            a=f.read(rl);rows.append({k:a[o:o+l].strip().decode(enc,errors='replace') for k,o,l in fields})
    coords=[]
    with p.with_suffix('.shp').open('rb') as f:
        f.seek(100)
        for _ in rows:
            header=f.read(8)
            if not header:break
            _,words=struct.unpack('>II',header);b=f.read(words*2);kind=struct.unpack('<I',b[:4])[0]
            coords.append(struct.unpack('<dd',b[4:20]) if kind in [1,11,21] else (np.nan,np.nan))
    d=pd.DataFrame(rows[:len(coords)]);d['ref_lon']=[x[0] for x in coords];d['ref_lat']=[x[1] for x in coords];return d


if __name__=='__main__':
    sets=[('南京市',POI_ROOT/'2022/华东poi1/江苏省/南京shp'),('武汉市',POI_ROOT/'2022/华中poi/湖北省/武汉')]
    details=[]
    for city,folder in sets:
        csvs=list((POI_ROOT/'2022').rglob(f'{city}POI数据.csv'))
        if not csvs:continue
        c=pd.read_csv(csvs[0],nrows=1000,encoding='utf-8-sig')
        for dbf in folder.rglob('*.dbf'):
            try:
                r=dbf_sample(dbf)
                if '名称' not in r:continue
                joined=r.merge(c[['名称','经度','纬度']],on='名称')
                if joined.empty:continue
                dx=(joined.ref_lon-joined.经度)*111320*np.cos(np.radians(joined.纬度));dy=(joined.ref_lat-joined.纬度)*111320
                joined['difference_m']=np.sqrt(dx*dx+dy*dy)
                for _,row in joined.iterrows():details.append({'city':city,'csv_path':str(csvs[0]),'reference_path':str(dbf),'poi_name':row['名称'],'difference_m':row.difference_m,'note':'Same-name sample match; paired package labels are reference declarations, not independent ground truth.'})
            except Exception as e:details.append({'city':city,'reference_path':str(dbf),'error':str(e)})
    d=pd.DataFrame(details);d.to_csv(ROOT/'02_audit/coordinate_reference_sample_details.csv',index=False,encoding='utf-8-sig')
    if 'difference_m' in d:
        summary=d.groupby(['city','reference_path']).difference_m.agg(['count','median','max']).reset_index();summary.to_csv(ROOT/'02_audit/coordinate_reference_probe_summary.csv',index=False,encoding='utf-8-sig');print(summary.to_string(index=False),flush=True)
