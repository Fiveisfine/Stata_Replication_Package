"""Remove finished v3 staging copies only after both local audits are complete."""
import json
import hashlib
from pathlib import Path
import pandas as pd

from config import ROOT


def main():
    stage = (ROOT/'03_cache/staging').resolve()
    audit = ROOT/'02_audit/query_time_2021'
    inv = pd.read_csv(ROOT/'02_audit/source_inventory.csv').set_index('source_id')
    removed = []
    for receipt in audit.glob('s*.json'):
        folder = (stage/receipt.stem).resolve()
        if folder.parent != stage:
            raise RuntimeError(f'Unexpected staging folder: {folder}')
        marker = folder/'copy_complete.json'
        parsed = ROOT/'03_cache/2021'/receipt.name
        normalized = parsed.with_suffix('.parquet')
        if not (folder.is_dir() and parsed.exists() and normalized.exists()):
            continue
        p = json.loads(parsed.read_text(encoding='utf-8'))
        expected = inv.loc[receipt.stem]
        original = Path(expected.path)
        if p['status']!='ok' or Path(p['path'])!=original:
            continue
        local = (folder/original.name).resolve()
        if local.parent != folder or not local.is_file() or local.stat().st_size != expected.actual_bytes:
            continue
        if marker.exists():
            m = json.loads(marker.read_text(encoding='utf-8'))
            if m['sha256']!=p.get('raw_source_sha256') or Path(m['original_path'])!=original:
                continue
            digest = m['sha256']
        else:
            # Interrupted pre-marker staging copy. The completed matching
            # cache and independent timestamp receipt both survive.
            st = original.stat()
            if st.st_size!=expected.actual_bytes or st.st_mtime_ns!=int(expected.mtime_ns):
                continue
            with local.open('rb') as f:
                digest = hashlib.file_digest(f,'sha256').hexdigest()
        local.unlink()
        cpg = local.with_suffix('.cpg')
        if cpg.is_file() and cpg.resolve().parent == folder:
            cpg.unlink()
        marker.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
        removed.append({'source_id':receipt.stem,'bytes':int(expected.actual_bytes),'local_staging_sha256':digest})
    total = sum(x['bytes'] for x in removed)
    if removed:
        (ROOT/'06_logs/released_staging_copies.json').write_text(
            json.dumps({'files':len(removed),'bytes':total,'records':removed},indent=2),encoding='utf-8')
    print(f'Released {len(removed)} verified v3 staging files ({total} bytes).',flush=True)


if __name__ == '__main__':
    main()
