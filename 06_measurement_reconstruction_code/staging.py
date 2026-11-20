"""Serialize USB source reads; parse temporary copies on the local SSD.

Copies are per source, bounded by free disk space, and removed after use.
No original file is edited. A completed copy can be reused after interruption.
"""
import hashlib
import json
import msvcrt
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from config import ROOT

STAGE=ROOT/'03_cache/staging'
STAGE.mkdir(exist_ok=True)


@contextmanager
def copy_lock():
    lock=STAGE/'usb_copy.lock'
    handle=open(lock,'a+b')
    if lock.stat().st_size==0:handle.write(b'0');handle.flush()
    while True:
        try:
            handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);break
        except OSError:time.sleep(.02)
    try:yield
    finally:
        handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1);handle.close()


@contextmanager
def staged_source(source,meta):
    original=Path(source['path'])
    folder=STAGE/source['source_id'];folder.mkdir(exist_ok=True)
    local=folder/original.name
    marker=folder/'copy_complete.json'
    fingerprint={'source_bytes':original.stat().st_size,'source_mtime_ns':original.stat().st_mtime_ns,'original_path':str(original)}
    reused=False
    while True:
        with copy_lock():
            if marker.exists() and local.exists():
                old=json.loads(marker.read_text(encoding='utf-8'))
                if all(old.get(k)==v for k,v in fingerprint.items()) and local.stat().st_size==fingerprint['source_bytes']:
                    meta['raw_source_sha256']=old['sha256'];reused=True;break
            # Keep enough space for result files and the database spill area.
            if shutil.disk_usage(ROOT).free < fingerprint['source_bytes']+12*1024**3:
                ready=False
            else:
                ready=True;start=time.monotonic();h=hashlib.sha256()
                print(f"STAGE_START {source['source_id']} bytes={fingerprint['source_bytes']}",flush=True)
                with original.open('rb') as src,local.open('wb') as dst:
                    for block in iter(lambda:src.read(4*1024*1024),b''):
                        dst.write(block);h.update(block)
                if local.stat().st_size!=fingerprint['source_bytes']:raise IOError('Incomplete local source copy')
                if original.stat().st_mtime_ns!=fingerprint['source_mtime_ns']:raise IOError('Source changed during read')
                meta['raw_source_sha256']=h.hexdigest();meta['staging_copy_seconds']=round(time.monotonic()-start,2)
                marker.write_text(json.dumps({**fingerprint,'sha256':h.hexdigest()}),encoding='utf-8')
                for ext in ['.cpg']:
                    companion=original.with_suffix(ext)
                    if companion.exists():shutil.copyfile(companion,local.with_suffix(ext))
                print(f"STAGE_DONE {source['source_id']} sec={meta['staging_copy_seconds']}",flush=True)
                break
        if not ready:time.sleep(2)
    meta['staging_copy_reused']=reused
    temp_source=dict(source);temp_source['path']=str(local)
    try:yield temp_source
    finally:
        # Targeted removal of generated temporary copies only; never recursive.
        for p in [local,local.with_suffix('.cpg'),marker]:
            if not p.resolve().is_relative_to(STAGE.resolve()):raise RuntimeError('Staging cleanup escaped workspace')
            if p.exists():
                try:p.unlink()
                except PermissionError:
                    # A reader or virus scanner may briefly hold a Windows
                    # handle. Keep this local copy and report cleanup pending;
                    # never turn successful source parsing into fake data loss.
                    meta.setdefault('staging_cleanup_pending',[]).append(str(p))
        try:folder.rmdir()
        except OSError:pass
