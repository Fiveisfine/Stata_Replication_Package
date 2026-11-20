"""Reuse completed integer counts only after point-content equivalence checks.

The optimized SQL replaces a concatenated string grouping key with an equivalent
tuple of its original components. The distance and counting kernel is unchanged.
A full exact EXCEPT ALL test is separately retained for 2012; all completed years
also receive independent multiset checksums of every geometry/flag row.
"""
import hashlib
import importlib
import json

import duckdb
import pandas as pd
from config import ROOT


def fingerprint(p):
    c=duckdb.connect();c.execute("SET memory_limit='2GB'");c.execute('SET threads=2')
    c.from_parquet(str(p)).create_view('points')
    row=c.execute('''select count(*),sum(hash(lon,lat,wgs_lon,wgs_lat,mask,assisted_mask,record_multiplicity)),
      bit_xor(hash(record_multiplicity,assisted_mask,mask,wgs_lat,wgs_lon,lat,lon)),sum(record_multiplicity)
      from points''').fetchone();c.close()
    return {'N':int(row[0]),'row_hash_sum':str(row[1]),'reverse_row_hash_xor':str(row[2]),'total_multiplicity':str(row[3])}


if __name__=='__main__':
    matching=importlib.import_module('03_match');pipeline=importlib.import_module('06_pipeline')
    archive=ROOT/'01_code/archive/03_match_string_key_dense.py'
    checks=[]
    for marker in sorted((ROOT/'06_logs').glob('match_complete_*.json')):
        year=int(marker.stem.split('_')[-1]);old_marker=json.loads(marker.read_text(encoding='utf-8'))
        paths=sorted((ROOT/'03_cache'/str(year)).glob('s*.json'))
        h=hashlib.sha256()
        for p in paths:h.update(p.read_bytes())
        h.update((ROOT/'01_code/classify.py').read_bytes());h.update(archive.read_bytes())
        if old_marker['signature']!=h.hexdigest():
            print(f'SKIP_MIGRATION {year}: old source/implementation fingerprint not matched',flush=True);continue
        target=ROOT/f'03_cache/{year}/deduplicated.parquet'
        if year==2012:
            reference=ROOT/'02_audit/key_equivalence/2012_reference.parquet'
            before=fingerprint(reference)
        else:
            before=fingerprint(target)
            matching.deduplicate(year)
        after=fingerprint(target);same=before==after
        record={'year':year,'passed':same,'before':before,'after':after,'method':'point multiset count, independent row-hash sum and reverse-order row-hash XOR, plus total multiplicity','exact_test_receipt_2012':'02_audit/group_key_equivalence.json'}
        (ROOT/f'02_audit/key_equivalence_{year}.json').write_text(json.dumps(record,indent=2),encoding='utf-8');checks.append(record)
        if same:
            marker.write_text(json.dumps({'year':year,'signature':pipeline.signature(year,paths),'status':'complete','spatial_counts_reused_after_point_equivalence':True,'previous_signature':old_marker['signature'],'archived_implementation_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'equivalence_receipt':f'02_audit/key_equivalence_{year}.json'},indent=2),encoding='utf-8')
        print(f'KEY_LAYOUT_EQUIVALENCE {year} passed={same} N={after["N"]}',flush=True)
    (ROOT/'02_audit/completed_year_key_equivalence.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
