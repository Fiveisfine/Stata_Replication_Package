import json
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from config import ROOT, RADII, CATEGORIES
from classify import fixture_check
from importlib import import_module

match=import_module('03_match')


def geometry_check():
    # Independent great-circle calculation, including points on both sides of
    # an administrative boundary (no city-based exclusion is applied).
    rng=np.random.default_rng(20261114)
    flon=rng.uniform(115.9,116.1,20);flat=rng.uniform(39.9,40.1,20)
    plon=rng.uniform(115.85,116.15,100);plat=rng.uniform(39.85,40.15,100)
    f=np.ones((100,len(match.FEATURES)),dtype=np.int64)
    got=match.count_batch(cKDTree(match.xyz(flon,flat)),plon,plat,f,20)
    p1=np.radians(flat[:,None]);p2=np.radians(plat[None,:]);dp=p2-p1;dl=np.radians(plon[None,:]-flon[:,None])
    a=np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    distances=6371.0088*2*np.arcsin(np.sqrt(a))
    for i,r in enumerate(RADII):assert np.array_equal(got[i,:,0],(distances<=r).sum(axis=1))
    return {'independent_haversine_vs_chord_counts':'passed','firm_points':20,'poi_points':100,'radii_km':RADII}


def validate_outputs():
    checks=[]
    for p in sorted((ROOT/'04_data').glob('poi_*.parquet')):
        d=pd.read_parquet(p)
        if d.empty:continue
        assert not d.duplicated(['id','year']).any(),p
        radii=[r for r in RADII if f'total_{r}km' in d]
        for r in radii:
            assert (d[f'combined_{r}km']<=sum(d[f'{c}_{r}km'] for c in CATEGORIES)).all(),p
            assert (d[f'combined_{r}km']<=d[f'total_{r}km']).all(),p
            assert (d[f'nonalcohol_total_{r}km']==d[f'total_{r}km']-d[f'combined_{r}km']).all(),p
            for c in CATEGORIES:
                assert (d[f'{c}_{r}km']<=d[f'combined_{r}km']).all(),p
                assert (d[f'without_{c}_{r}km']<=d[f'combined_{r}km']).all(),p
        for c in CATEGORIES+['combined','total','old_keyword','assisted_combined']:
            for a,b in zip(radii,radii[1:]):assert (d[f'{c}_{a}km']<=d[f'{c}_{b}km']).all(),p
        assert not d.loc[d.known_missing_province,'usable_experimental'].any(),p
        checks.append({'file':p.name,'N':len(d),'usable':int(d.usable_experimental.sum()),'invariants':'passed'})
    return checks


if __name__=='__main__':
    fixture_check()
    result={'geometry':geometry_check(),'classification_fixture':'passed','output_checks':validate_outputs()}
    (ROOT/'02_audit/validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'geometry':result['geometry'],'files_checked':len(result['output_checks'])}),flush=True)
