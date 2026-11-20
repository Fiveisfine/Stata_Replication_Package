"""Small read-only metadata probes; not a substitute for provider documentation."""
import codecs
import csv
import itertools
import json
from pathlib import Path

import pandas as pd
from config import ROOT,ORIGINAL,POI_ROOT


def main():
    records=[]
    for p in ORIGINAL.parent.glob('*.dta'):
        try:
            with pd.io.stata.StataReader(p,convert_categoricals=False) as reader:
                labels=reader.variable_labels();cols=[x for x in labels if any(k in x for k in ['办公地','地址','经度','纬度'])]
            if not cols:continue
            d=pd.read_stata(p,columns=['id','year']+cols,convert_categoricals=False);q=d[d.year.eq(2014)]
            records.append({'path':str(p),'year':2014,'N':len(q),'coordinate_or_address_nonmissing':json.dumps(q[cols].count().to_dict(),ensure_ascii=False)})
        except Exception as e:records.append({'path':str(p),'error':str(e)})
    pd.DataFrame(records).to_csv(ROOT/'02_audit/2014_additional_input_search.csv',index=False,encoding='utf-8-sig')
    rows=[]
    for year in [2018,2019,2020,2021,2022,2023]:
        candidates=list((POI_ROOT/str(year)).rglob('*.csv'))
        if year==2019:candidates=[p for p in candidates if p.name.startswith('d_')]
        for p in candidates[:3]:
            with p.open('rb') as f:b=f.read(65536)
            try:codecs.getincrementaldecoder('utf-8-sig')().decode(b,final=False);enc='utf-8-sig'
            except UnicodeDecodeError:enc='gb18030'
            with p.open('r',encoding=enc,newline='') as f:a=list(itertools.islice(csv.reader(f),4))
            header=a[0]
            selected=[i for i,c in enumerate(header) if any(k in c.lower() for k in ['timestamp','publish_time','查询时间','采集时间'])]
            rows.append({'year':year,'path':str(p),'encoding':enc,'header':json.dumps(header,ensure_ascii=False),'timestamp_columns':json.dumps([header[i] for i in selected],ensure_ascii=False),'timestamp_examples':json.dumps([[r[i] if i<len(r) else '' for i in selected] for r in a[1:]],ensure_ascii=False),'note':'Small schema probe only; examples do not establish an annual snapshot or full-file date range.'})
    pd.DataFrame(rows).to_csv(ROOT/'02_audit/source_timestamp_schema_probes.csv',index=False,encoding='utf-8-sig')
    docs=[]
    for year in [2012,2013,2014,2015,2016,2017]:
        folder=POI_ROOT/str(year)
        if year==2016:folder=folder/'2016'
        for p in list(folder.glob('*.prj'))[:2]:docs.append({'year':year,'path':str(p),'declaration':p.read_text(errors='replace'),'interpretation':'Declared spatial reference; not independent verification of coordinate provenance.'})
    pd.DataFrame(docs).to_csv(ROOT/'02_audit/coordinate_reference_declarations.csv',index=False,encoding='utf-8-sig')
    print('METADATA_PROBES_COMPLETE',flush=True)


if __name__=='__main__':main()
