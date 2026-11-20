from pathlib import Path
import pandas as pd
from config import ROOT,POI_ROOT


if __name__=='__main__':
    chosen=pd.read_csv(ROOT/'02_audit/source_inventory.csv')
    lookup={str(Path(r.path).resolve()).lower():r.source_id for r in chosen.itertuples()}
    rows=[]
    for year in sorted(POI_ROOT.iterdir()):
        if not year.is_dir():continue
        for p in year.rglob('*'):
            if not p.is_file():continue
            key=str(p.resolve()).lower();selected=key in lookup;ext=p.suffix.lower()
            if selected:reason='selected canonical source family'
            elif ext in ['.shp','.shx','.prj','.cpg','.sbn','.sbx']:reason='vector geometry/reference companion; not counted again as POI records'
            elif ext=='.dbf':reason='alternate vector/table release; not blended with selected CSV or canonical nested DBF family without version reconciliation'
            elif ext in ['.zip','.rar']:reason='archive not ingested in addition to extracted source records'
            elif ext in ['.pdf','.html','.xml']:reason='ancillary documentation; not POI observations'
            elif ext=='.bak_zeroed_header':reason='historical backup; never modified or ingested'
            else:reason='unselected alternate workbook/table; requires schema and release reconciliation'
            rows.append({'year':year.name,'path':str(p),'extension':ext,'bytes':p.stat().st_size,'selected':selected,'source_id':lookup.get(key,''),'selection_note':reason})
    d=pd.DataFrame(rows);d.to_csv(ROOT/'02_audit/all_raw_files_selection.csv',index=False,encoding='utf-8-sig');print('SOURCE_SELECTION_INVENTORY',len(d),'files',int(d.selected.sum()),'selected',flush=True)
