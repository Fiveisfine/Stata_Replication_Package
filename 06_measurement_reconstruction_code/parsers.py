"""Read-only source adapters. No mutation of DBF headers or source workbooks."""
import csv
import codecs
import itertools
import os
import re
import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
from python_calamine import CalamineWorkbook

CHUNK = 100_000


def number(s):
    return pd.to_numeric(s,errors='coerce')


def location(s):
    z=s.fillna('').astype(str).str.extract(r'(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)')
    return number(z[0]),number(z[1])


def standardize(d,kind,source):
    d=d.reset_index(drop=True)
    def field(*names):
        for n in names:
            if n in d.columns:return d[n].fillna('').astype(str)
        return pd.Series('',index=d.index)
    o=pd.DataFrame(index=d.index)
    if kind in ['csv_2019','xls_2019']:
        d.columns=[f'f{i}' for i in range(d.shape[1])]
        o['name']=field('f1');o['category']=field('f6');o['lon']=number(field('f4'));o['lat']=number(field('f3'))
        o['city']=field('f5').str.split(';').str[0];o['poi_id']='';o['typecode']='';o['address']=field('f2')
    elif kind=='poi_2023_headerless':
        o['name']=field('f2');o['category']=field('f3');o['lon'],o['lat']=location(field('f5'))
        o['city']=field('f10');o['poi_id']=field('f0');o['typecode']=field('f6');o['address']=field('f4')
    else:
        o['name']=field('name','名称','NAME');o['category']=field('type','类别','dtype')
        if o.category.eq('').all():o['category']=field('大类')+';'+field('中类')+';'+field('小类')
        o['city']=field('cityname','城市','CITY');o['poi_id']=field('PoiID','id','_id');o['typecode']=field('typecode','TYPECODE')
        o['address']=field('address','地址','ADDRESS')
        if 'wgs84lon' in d:
            # Retain native and explicitly supplied WGS84 coordinates separately.
            o['lon']=number(field('marlon'));o['lat']=number(field('marlat'))
            o['wgs_lon']=number(field('wgs84lon'));o['wgs_lat']=number(field('wgs84lat'))
            o['lon']=o.lon.fillna(o.wgs_lon);o['lat']=o.lat.fillna(o.wgs_lat)
        elif any(x in d for x in ['location','经纬度']):o['lon'],o['lat']=location(field('location','经纬度'))
        else:o['lon']=number(field('经度','LON'));o['lat']=number(field('纬度','LAT'))
    if 'wgs_lon' not in o:o['wgs_lon']=np.nan;o['wgs_lat']=np.nan
    return o


def dbf_batches(path,meta,prefilter):
    with open(path,'rb') as f:
        h=f.read(32);n,hl,rl=struct.unpack('<IHH',h[4:12]);fields={};offset=1
        while f.tell()<hl:
            desc=f.read(32)
            if not desc or desc[0]==13:break
            name=desc[:11].split(b'\0')[0].decode('latin1').upper();length=desc[16]
            fields[name]=(offset,length);offset+=length
    physical=(Path(path).stat().st_size-hl)//rl
    meta.update(header_rows=int(n),physical_rows=int(physical),header_row_discrepancy=int(physical-n))
    if n!=physical:raise ValueError(f'DBF header/physical record mismatch {n}/{physical}; source left unchanged')
    if not {'LON','LAT'}.issubset(fields):raise ValueError('DBF missing LON/LAT')
    dtype=np.dtype({'names':['deleted']+list(fields),'formats':['S1']+[f'S{v[1]}' for v in fields.values()],'offsets':[0]+[v[0] for v in fields.values()],'itemsize':rl})
    enc=Path(path).with_suffix('.cpg').read_text().strip() if Path(path).with_suffix('.cpg').exists() else 'utf-8'
    meta['encoding']=enc
    # Explicit bounded reads avoid retaining multi-GB mapped file pages in a
    # worker's Windows working set while another year is being deduplicated.
    with open(path,'rb') as handle:
        handle.seek(hl)
        for start in range(0,n,CHUNK):
            expected=min(CHUNK,n-start)*rl
            block=handle.read(expected)
            if len(block)!=expected:raise IOError('Truncated DBF data block')
            a=np.frombuffer(block,dtype=dtype);meta['raw_rows']+=len(a)
            lon=number(pd.Series(np.char.strip(a['LON']))).to_numpy();lat=number(pd.Series(np.char.strip(a['LAT']))).to_numpy()
            valid=(a['deleted']!=b'*')&np.isfinite(lon)&np.isfinite(lat)&(lon>=70)&(lon<=140)&(lat>=0)&(lat<=60)
            meta['valid_rows']+=int(valid.sum())
            keep=valid&prefilter(np.nan_to_num(lon),np.nan_to_num(lat))
            if not keep.any():continue
            a=a[keep]
            def text(k):
                return pd.Series(a[k]).str.decode(enc,errors='replace').str.strip() if k in fields else pd.Series('',index=range(len(a)))
            o=pd.DataFrame({'name':text('NAME'),'category':text('BASETYPE')+';'+text('SUBTYPE')+';'+text('CATEGORY'), 'typecode':text('TYPECODE'),'city':text('CITY'),'address':text('ADDRESS'),'poi_id':'','lon':lon[keep],'lat':lat[keep],'wgs_lon':np.nan,'wgs_lat':np.nan})
            yield o


def csv_batches(path,kind,meta):
    with open(path,'rb') as f:sample=f.read(65536)
    try:codecs.getincrementaldecoder('utf-8-sig')().decode(sample,final=False);enc='utf-8-sig'
    except UnicodeDecodeError:enc='gb18030'
    meta['encoding']=enc
    headerless=kind=='csv_2019' or kind=='poi_2023'
    if os.environ.get('POI_CSV_PARSER')=='python':
        csv.field_size_limit(512*1024*1024)
        meta['parser']='python_csv_compatibility'
        with open(path,'r',encoding=enc,errors='replace',newline='') as f:
            class BufferedLines:
                def __init__(self,handle):self.handle=handle;self.buffer=[];self.line_count=0
                def __iter__(self):return self
                def __next__(self):
                    line=next(self.handle);self.buffer.append(line);self.line_count+=1;return line
                def take(self):
                    result=self.buffer;self.buffer=[];return result
            lines=BufferedLines(f)
            reader=csv.reader(lines);first=next(reader);first_lines=lines.take()
            cols=[f'f{i}' for i in range(len(first))] if headerless else first
            paired=((row,lines.take()) for row in reader)
            rows=itertools.chain([(first,first_lines)],paired) if headerless else paired
            chunk=[]
            for row,physical_lines in rows:
                meta['python_logical_records']=meta.get('python_logical_records',0)+1
                replacement_chars=sum(value.count('\ufffd') for value in row)
                if replacement_chars:
                    meta['raw_rows']+=1;meta['malformed_rows']+=1
                    meta['invalid_encoding_records']=meta.get('invalid_encoding_records',0)+1
                    meta['encoding_replacement_chars']=meta.get('encoding_replacement_chars',0)+replacement_chars
                    continue
                recovered=None
                if len(row)!=len(cols) or len(physical_lines)>8:
                    candidates=[]
                    for line in physical_lines:
                        try:single=next(csv.reader([line]))
                        except csv.Error:continue
                        if len(single)==len(cols):candidates.append(single)
                    if candidates and (len(row)!=len(cols) or len(candidates)>=2):recovered=candidates
                if recovered is not None:
                    meta['raw_rows']+=len(physical_lines)
                    meta['recovered_physical_records']=meta.get('recovered_physical_records',0)+len(recovered)
                    meta['malformed_rows']+=len(physical_lines)-len(recovered)
                    if len(meta['malformed_examples'])<3:meta['malformed_examples'].append(f'logical_record_fields={len(row)} physical_lines={len(physical_lines)} schema_accepted_recovered_records={len(recovered)}')
                    chunk.extend(recovered)
                else:
                    meta['raw_rows']+=1
                    if len(row)!=len(cols):
                        meta['malformed_rows']+=1
                        if len(meta['malformed_examples'])<3:meta['malformed_examples'].append(f'field_count={len(row)} expected={len(cols)}')
                        continue
                    chunk.append(row)
                if len(chunk)>=CHUNK:
                    yield standardize(pd.DataFrame(chunk,columns=cols),'poi_2023_headerless' if kind=='poi_2023' else kind,meta);chunk=[]
            if chunk:yield standardize(pd.DataFrame(chunk,columns=cols),'poi_2023_headerless' if kind=='poi_2023' else kind,meta)
            meta['physical_lines_read']=lines.line_count
        return
    meta['parser']='pyarrow_csv'
    def invalid(row):
        meta['malformed_rows']+=1
        if len(meta['malformed_examples'])<3:meta['malformed_examples'].append(row.text[:180])
        return 'skip'
    arrow_encoding='utf8' if enc=='utf-8-sig' else enc
    read=pacsv.ReadOptions(block_size=8*1024*1024,encoding=arrow_encoding,autogenerate_column_names=headerless,use_threads=False)
    parse=pacsv.ParseOptions(newlines_in_values=True,invalid_row_handler=invalid)
    with open(path,'r',encoding=enc,errors='strict',newline='') as f:first=next(csv.reader(f))
    cols=[f'f{i}' for i in range(len(first))] if headerless else first
    types={c:pa.string() for c in cols if c}
    wanted={'name','名称','NAME','type','类别','dtype','大类','中类','小类','cityname','城市','CITY','PoiID','id','_id','typecode','TYPECODE','address','地址','ADDRESS','marlon','marlat','wgs84lon','wgs84lat','location','经纬度','经度','纬度','LON','LAT'}
    included=cols if kind=='csv_2019' else ([f'f{i}' for i in [0,2,3,4,5,6,10]] if kind=='poi_2023' else [c for c in cols if c in wanted])
    convert=pacsv.ConvertOptions(column_types=types,strings_can_be_null=False,include_columns=included)
    reader=pacsv.open_csv(path,read_options=read,parse_options=parse,convert_options=convert)
    try:
        for batch in reader:
            meta['raw_rows']+=len(batch)
            yield standardize(batch.to_pandas(), 'poi_2023_headerless' if kind=='poi_2023' else kind,meta)
    finally:reader.close()


def excel_batches(path,kind,meta):
    with CalamineWorkbook.from_path(str(path)) as book:
        for sheetname in book.sheet_names:
            sheet=book.get_sheet_by_name(sheetname);rows=iter(sheet.iter_rows());first=next(rows,None)
            if not first:continue
            if kind=='xls_2019':columns=[f'f{i}' for i in range(len(first))];rows=itertools.chain([first],rows)
            else:
                if {'name','type','location'}.issubset(set(str(v).strip() for v in first)):
                    columns=[str(v).strip() for v in first];previous_columns=columns
                elif 'previous_columns' in locals():columns=previous_columns;rows=itertools.chain([first],rows)
                else:raise ValueError(f'Unrecognized Excel header in {sheetname}')
            while True:
                chunk=list(itertools.islice(rows,CHUNK))
                if not chunk:break
                meta['raw_rows']+=len(chunk)
                # Range widths may include an empty first column, which is retained.
                chunk=[r[:len(columns)]+['']*max(0,len(columns)-len(r)) for r in chunk]
                yield standardize(pd.DataFrame(chunk,columns=columns),kind,meta)


def batches(source,meta,prefilter):
    path=source['path'];kind=source['kind']
    if kind=='dbf_early':yield from dbf_batches(path,meta,prefilter)
    elif str(path).lower().endswith(('.xls','.xlsx')):yield from excel_batches(path,kind,meta)
    else:yield from csv_batches(path,kind,meta)
