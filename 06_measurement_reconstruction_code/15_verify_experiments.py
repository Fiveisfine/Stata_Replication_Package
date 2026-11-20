"""Validate the stored experimental results and reconcile targeted round-2 counts."""
import hashlib
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pyhdfe

from config import CONTROLS, ORIGINAL, ROOT
from hdfe import contrast, fit


AUDIT = ROOT / '02_audit'
RESULTS = ROOT / '05_results'
SAMPLES = RESULTS / 'estimation_samples'


def csv(table, path):
    pd.DataFrame(table).to_csv(path, index=False, encoding='utf-8-sig')


def main():
    panel = pd.read_parquet(ROOT / '04_data/experiment_panel.parquet')
    results = pd.read_csv(RESULTS / 'model_results.csv', keep_default_na=False)
    models = results.drop_duplicates('model_id').copy()
    diagnostics = json.loads((RESULTS / 'model_diagnostics.json').read_text(encoding='utf-8'))
    assert not list((ROOT / '06_logs').glob('model_failure_*.json'))
    assert len(models) == len(diagnostics) == 256
    assert len(results) == 558 and not results.not_identified.any()
    assert all(pd.to_numeric(results[col], errors='coerce').notna().all() for col in ('b', 'se', 'p', 'ci_low', 'ci_high'))
    assert results.p.between(0, 1).all() and results.se.gt(0).all()
    assert not panel.duplicated(['firm_id', 'year']).any()
    keys = pd.MultiIndex.from_frame(panel[['firm_id', 'year']])
    mask = ~panel.usable_experimental
    new_counts = [c for c in panel if re.fullmatch(
        r'(log_)?(retail|bar|nightclub|ktv|disco|combined|nightlife|assisted_combined|old_keyword|total|restaurant|entertainment|shopping|nonalcohol_total|without_\w+)_(1|3|5|10)km', c)]
    assert len(new_counts) == 152
    assert panel.loc[mask, new_counts].isna().all().all()
    q = panel.loc[~mask]
    for r in (1, 3, 5, 10):
        assert q[f'nonalcohol_total_{r}km'].eq(q[f'total_{r}km'] - q[f'combined_{r}km']).all()
    assert panel.loc[panel.year.eq(2014), 'usable_experimental'].eq(False).all()
    assert panel.loc[panel.year.eq(2023) & panel.province_id.eq(440000), 'usable_experimental'].eq(False).all()
    per_model = []
    for rec in models.itertuples(index=False):
        key = pd.read_parquet(SAMPLES / f'{rec.model_id}.parquet').sort_values(['firm_id', 'year'])
        assert len(key) == rec.N == rec.N_input - rec.singletons_removed
        assert not key.duplicated().any() and pd.MultiIndex.from_frame(key).isin(keys).all()
        h = hashlib.sha256(key.to_numpy(dtype='<i8').tobytes()).hexdigest()
        if rec.sample.startswith('common') and 'no2023' in rec.sample:
            assert not key.year.eq(2023).any()
        if rec.sample.startswith('common') and 'no2021' in rec.sample:
            assert not key.year.eq(2021).any()
        per_model.append({'model_id': rec.model_id, 'firm_year_sha256': h, 'N_verified': len(key)})
    csv(per_model, AUDIT / 'estimation_sample_fingerprints.csv')
    models = models.merge(pd.DataFrame(per_model), on='model_id', validate='one_to_one')
    paired = []
    for (sample, moderator), group in models[models.analysis.eq('measurement_comparison')].groupby(['sample', 'moderator']):
        assert len(group) == 10 and group.firm_year_sha256.nunique() == 1
        paired.append({'sample': sample, 'moderator': moderator or 'none', 'models': len(group),
                       'N_verified': group.N_verified.iloc[0], 'identical_firm_years': True})
    csv(paired, AUDIT / 'common_sample_exact_verification.csv')
    for analysis, groupby in {'radius':['outcome', 'moderator'], 'category':['outcome','moderator'],
                              'leave_one_category_out':['outcome','moderator'],
                              'coordinate_scenario':['outcome','moderator'],
                              'strict_FE':['outcome','moderator'],
                              'commercial_controls':['outcome','moderator'],
                              'joint_commercial_controls':['outcome','moderator'],
                              'calendar_lag_common_sample':['outcome','moderator']}.items():
        assert models[models.analysis.eq(analysis)].groupby(groupby).firm_year_sha256.nunique().eq(1).all(), analysis
    a = pd.read_csv(AUDIT / 'parser_execution.csv')
    inventory = pd.read_csv(AUDIT / 'source_inventory.csv')
    assert len(a) == 9234 and a.status.eq('ok').all() and a.source_id.is_unique
    assert set(a.source_id) == set(inventory.loc[inventory.year.ne(2014), 'source_id'])
    val = json.loads((AUDIT / 'validation.json').read_text(encoding='utf-8'))
    assert len(val['output_checks']) == 33 and all(x['invariants']=='passed' for x in val['output_checks'])
    assert pd.read_csv(AUDIT / 'estimator_calibration.csv').passed.all()

    fe = ['firm_id', 'industry_year']
    archived = pd.read_stata(ORIGINAL/'08_revision_experiments/outputs/review_analysis_panel.dta', convert_categoricals=False)
    old = archived[archived.sample_current.eq(1)].copy()
    xs = ['alcohol_culture'] + CONTROLS
    full = fit(old, 'mca_current', xs, fe)
    excl = fit(old[old.year.ne(2023)], 'mca_current', xs, fe)
    other = full['sample'][full['sample'].year.ne(2023)]
    after_direct = len(other)
    omitted = other.merge(excl['sample'], how='left', on=['firm_id','year'], indicator=True)
    lost = omitted[omitted._merge.eq('left_only')][['firm_id','year']]
    assert after_direct == 24199 and len(lost) == 492 and excl['N'] == 23707
    assert pd.MultiIndex.from_frame(excl['sample']).isin(pd.MultiIndex.from_frame(other)).all()
    csv(lost, AUDIT/'archived_extra_singletons_without_2023.csv')
    csv([
        {'step':'full before singleton removal','N':full['N_input']},
        {'step':'full estimated','N':full['N']},
        {'step':'2023 observations in full estimation sample','N':full['N']-after_direct},
        {'step':'full estimated physically removing 2023','N':after_direct},
        {'step':'no2023 before fresh singleton removal','N':excl['N_input']},
        {'step':'no2023 fresh singleton removal','N':excl['singletons_removed']},
        {'step':'additional lost relative to deleting 2023 from full estimation','N':len(lost)},
        {'step':'no2023 estimated','N':excl['N']},
    ], AUDIT/'archived_2023_sample_reconciliation.csv')

    old['zero'] = old.alcohol_culture.eq(0)
    py = old.groupby(['province_id','year'], dropna=False).zero.agg(N='size', zero_share='mean').reset_index()
    py['flag'] = py.N.ge(20) & py.zero_share.ge(.90)
    csv(py[py.flag], AUDIT/'archived_high_zero_province_years.csv')
    screen = old.merge(py[['province_id','year','flag']], on=['province_id','year'], validate='many_to_one')
    highzero = fit(screen[~screen.flag], 'mca_current', xs, fe)
    assert highzero['N'] == 26897 and abs(contrast(highzero,{'alcohol_culture':1})['b'] + .0281106) < 1e-6
    archive2023 = old[old.year.isin([2022,2023])][['firm_id','year','province_id','zero','poi_source_available']]
    coverage = archive2023.merge(panel[['firm_id','year','usable_experimental','observed_local_poi',
                  'known_missing_province','combined_5km']], on=['firm_id','year'], validate='one_to_one')
    coverage['v3_zero'] = coverage.combined_5km.eq(0).where(coverage.usable_experimental)
    counts = coverage.groupby(['year','province_id'], dropna=False).agg(N=('firm_id','size'),
                archived_zero_share=('zero','mean'), old_source_share=('poi_source_available','mean'),
                v3_usable=('usable_experimental','sum'), local_poi=('observed_local_poi','sum'),
                known_missing_province=('known_missing_province','sum'), v3_zero_share=('v3_zero','mean')).reset_index()
    csv(counts, AUDIT/'archived_sample_province_year_coverage.csv')

    hist = []
    for window, q in [('original', old), ('no2023', old[old.year.ne(2023)])]:
        for cov in [('firm_id',), ('city_id',), ('firm_id','city_id')]:
            m = (full if window=='original' else excl) if cov==('firm_id',) else fit(q, 'mca_current', xs, fe, cov)
            est = q.merge(m['sample'], on=['firm_id','year'], validate='one_to_one')
            hist.append({'sample':window, 'clustering':'+'.join(cov), 'N':m['N'],
                         'firm_clusters':est.firm_id.nunique(), 'city_clusters':est.city_id.nunique(),
                         'firm_city_pairs':len(est.drop_duplicates(['firm_id','city_id'])),
                         'cross_city_firms_in_estimation':est.groupby('firm_id').city_id.nunique().gt(1).sum(),
                         **contrast(m, {'alcohol_culture':1})})
    csv(hist, RESULTS/'archived_clustering_and_mobility.csv')
    trust = fit(old, 'mca_current', xs+['trust1','trust2'], fe)
    tq = old.merge(trust['sample'], on=['firm_id','year'], validate='one_to_one')
    within = tq[['trust1','trust2']]-tq.groupby('firm_id')[['trust1','trust2']].transform('mean')
    r = pyhdfe.create(tq[fe].to_numpy(), drop_singletons=False, compute_degrees=False).residualize(tq[['trust1','trust2']].to_numpy())
    csv([{'regressor':c,'N':len(tq),'firms_with_variation':int(tq.groupby('firm_id')[c].nunique().gt(1).sum()),
          'sd_after_firm_FE':within[c].std(), 'sd_after_full_FE':r[:,i].std(ddof=1),
          'omitted_in_this_specification':c in trust['omitted'],
          'controls':'archived firm controls and both trust indices; not the historical sequential-control table'}
         for i,c in enumerate(['trust1','trust2'])], AUDIT/'archived_trust_identification.csv')

    workbook = ORIGINAL/'08_revision_experiments/source/Managerial-climate-attention-index-2001-2023.xlsx'
    mch = pd.read_excel(workbook, sheet_name='firm-level').rename(columns={
        'Stock_code':'firm_id', 'Year':'year', 'MCA_raw':'raw_workbook', 'Scaled_MCA_raw':'scaled_workbook'})
    mch.firm_id = pd.to_numeric(mch.firm_id)
    assert not mch.duplicated(['firm_id','year']).any()
    merged = panel[['firm_id','year','mca_current_original','mca_official_raw_original','mca_official_scaled_original',
                    'sample_common']].merge(mch,on=['firm_id','year'],how='left',validate='one_to_one')
    for col, orig in [('raw_workbook','mca_official_raw_original'),('scaled_workbook','mca_official_scaled_original')]:
        assert np.allclose(merged[col], merged[orig], equal_nan=True, rtol=2e-7, atol=1e-10)
    ms = merged[merged.sample_common.eq(1)].copy()
    # A5 counts the project-MCA baseline candidates; Table 7 first intersects
    # the two MCA series and adds 2022 from the updated release.
    assert len(old[old.year.le(2021)]) == 20218
    assert len(ms[ms.year.le(2021)]) == 19112
    ma = merged.groupby('year').agg(panel_N=('firm_id','size'), project_N=('mca_current_original','count'),
          workbook_match_N=('scaled_workbook','count')).join(ms.groupby('year').size().rename('archived_common_pre_FE')).reset_index()
    ma['archived_common_pre_FE'] = ma.archived_common_pre_FE.fillna(0).astype(int)
    ma = ma.merge(old.groupby('year').size().rename('archived_A5_baseline_pre_FE'),on='year',how='left')
    ma['archived_A5_baseline_pre_FE']=ma.archived_A5_baseline_pre_FE.fillna(0).astype(int)
    ma = ma.merge(mch.groupby('year').size().rename('full_workbook_N'),on='year',how='right')
    for col in ma.columns.drop('year'):
        ma[col]=ma[col].astype('Int64')
    csv(ma, AUDIT/'mca_workbook_annual_reconciliation.csv')
    source = archived[archived.sample_common.eq(1) & archived.year.ne(2023)]
    mrows = []
    for label, frame in [('through_2021', source[source.year.le(2021)]), ('through_2022', source)]:
        for y in ['mca_current','mca_official_scaled']:
            m = fit(frame,y,xs,fe)
            mrows.append({'sample':label,'outcome':y,'N_input':m['N_input'],'N':m['N'],'firms':m['firms'],
                         **contrast(m, {'alcohol_culture':1})})
    assert len(source) == 22745 and mrows[-1]['N'] == 22385
    csv(mrows, RESULTS/'archived_mca_overlap_baselines.csv')

    status = {'status':'complete','verified_utc':datetime.now(timezone.utc).isoformat(),
              'source_files_parsed':len(a),'years_reconstructed':sorted(a.year.unique().astype(int).tolist()),
              'validated_match_files':len(val['output_checks']),'models':len(models),'contrasts':len(results),
              'models_with_matched_sample_receipts':len(per_model),'reviewer_archive_checks':'passed',
              'manuscript_changes':False}
    (ROOT/'06_logs/SESSION_STATE.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    print(json.dumps(status,indent=2), flush=True)


if __name__ == '__main__':
    main()
