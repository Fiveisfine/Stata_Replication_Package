import hashlib
import json
import os
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from config import ROOT, ORIGINAL, CONTROLS, RADII, CATEGORIES
from hdfe import fit,contrast

SAMPLES=ROOT/'05_results/estimation_samples'
SAMPLES.mkdir(exist_ok=True)
RESULTS=[]
DIAGNOSTICS=[]


def stata_percentile(s,p):
    """Stata summarize, detail percentile convention (no weights)."""
    x=np.sort(s.dropna().to_numpy());h=len(x)*p
    if not len(x):return np.nan
    if float(h).is_integer() and 0<int(h)<len(x):return (x[int(h)-1]+x[int(h)])/2
    return x[min(max(int(np.ceil(h))-1,0),len(x)-1)]


def prepare():
    base=pd.read_stata(ORIGINAL/'08_revision_experiments/outputs/review_analysis_panel.dta',convert_categoricals=False)
    # Restore uncapped controls from the original file, then fix one benchmark
    # capping sample for v3 experiments. Historical calibration remains separate.
    rawcols=['id','year']+CONTROLS+['投资者绿色关注']
    raw=pd.read_stata(ORIGINAL/'04_empirical_results/酒文化与评级分歧12-23年-漂绿进一步分析_poi合并.dta',columns=rawcols,convert_categoricals=False).dropna(subset=['id','year'])
    agg={c:('first' if c in ['SOE','Dual','Big4'] else 'mean') for c in CONTROLS+['投资者绿色关注']}
    raw=raw.groupby(['id','year'],as_index=False).agg(agg).rename(columns={'id':'firm_id','投资者绿色关注':'investor_green'})
    base=base.drop(columns=CONTROLS+['investor_green']).merge(raw,on=['firm_id','year'],validate='one_to_one')
    base['current']=base.mca_current_original
    base['official']=base.mca_official_scaled_original
    base['csmar']=base.alcohol_culture_original
    base['old_v2']=np.log1p(base.alcohol_poi_5km)
    files=sorted((ROOT/'04_data').glob('poi_*_as_provided.parquet'))
    poi=pd.concat([pd.read_parquet(p) for p in files],ignore_index=True).rename(columns={'id':'firm_id'})
    keep=['firm_id','year','usable_experimental','source_run_complete','observed_local_poi','known_missing_province']+[c for c in poi if c.endswith('km')]
    d=base.merge(poi[keep],on=['firm_id','year'],how='left',validate='one_to_one')
    for c in ['usable_experimental','source_run_complete','observed_local_poi','known_missing_province']:d[c]=d[c].fillna(False).astype(bool)
    # Per-year matcher files contain intermediate counters plus coverage flags.
    # The final analysis panel never presents uncovered locations as observed zeros.
    countcols=[c for c in poi if c.endswith('km')]
    d[countcols]=d[countcols].astype(float).where(d.usable_experimental,axis=0)
    main=d.usable_experimental&d.year.ne(2023)&d.year.ne(2019)&d.is_finance.ne(1)&d.is_stpt.ne(1)&d[['current','official','csmar']+CONTROLS].notna().all(axis=1)
    logcols=pd.DataFrame({'log_'+c:np.log1p(d[c]) for c in countcols},index=d.index)
    d=pd.concat([d,logcols],axis=1)
    continuous=[c for c in CONTROLS if c not in ['SOE','Dual','Big4']]+['current','official','csmar','old_v2','investor_green']+[c for c in d if c.startswith('log_') and c.endswith('km')]
    caps=[]
    for c in continuous:
        lo=stata_percentile(d.loc[main,c],.01);hi=stata_percentile(d.loc[main,c],.99)
        caps.append({'variable':c,'reference_sample':'common_current_official_csmar_and_v3_no2019_no2023_before_singletons','reference_N':int(d.loc[main,c].notna().sum()),'p1':lo,'p99':hi})
        d[c]=d[c].clip(lo,hi)
    pd.DataFrame(caps).to_csv(ROOT/'02_audit/winsorization_thresholds.csv',index=False,encoding='utf-8-sig')
    zref=d.loc[main,'investor_green'].dropna();d['green_z']=(d.investor_green-zref.mean())/zref.std()
    d['v3_main_eligible']=main
    d['temporal_metadata_risk']=d.year.eq(2021)
    for c in ['current','official']:
        d['ln_'+c]=np.log1p(d[c]);d['asinh_'+c]=np.arcsinh(d[c])
        ref=d[c].where(main)
        means=ref.groupby(d.year).transform('mean');sds=ref.groupby(d.year).transform('std')
        d[c+'_annual_z']=(d[c]-means)/sds
        rank=ref.groupby(d.year).rank(method='average');n=ref.groupby(d.year).transform('count')
        d[c+'_annual_percentile']=(rank-1)/(n-1)
    prev=d[['firm_id','year','log_combined_5km']].copy()
    prev.loc[d.year.eq(2019),'log_combined_5km']=np.nan
    prev['year']=prev.year+1
    d=d.merge(prev.rename(columns={'log_combined_5km':'lag_new_poi'}),on=['firm_id','year'],how='left',validate='one_to_one')
    d.to_parquet(ROOT/'04_data/experiment_panel.parquet',index=False)
    return d


def run(d,outcome,exposure,sample,analysis,moderator=None,fe=None,clusters=('firm_id',),extra=None):
    fe=fe or ['firm_id','industry_year'];extra=extra or []
    label=f'{analysis}|{outcome}|{exposure}|{sample}|{moderator}|{fe}|{clusters}|{extra}'
    eligible=d.is_finance.ne(1)&d.is_stpt.ne(1)&d.usable_experimental&d.year.ne(2019)
    # Every main/vintage comparison uses the exact same candidate observations.
    if sample.startswith('common'):eligible &= d[['current','official','csmar','old_v2','log_combined_5km']+CONTROLS].notna().all(axis=1)
    if 'no2023' in sample:eligible &= d.year.ne(2023)
    if 'no2021' in sample:eligible &= d.year.ne(2021)
    if sample=='pre2019':eligible &= d.year.lt(2019)
    if sample=='post2019_no2023':eligible &= d.year.between(2020,2022)
    if sample=='include_valid2019_no2023':eligible=d.is_finance.ne(1)&d.is_stpt.ne(1)&d.usable_experimental&d.year.ne(2023)
    if sample=='stable_city_no2023':
        b=d[d.usable_experimental].groupby('firm_id')[['city_id']].nunique();stable=b.index[b.city_id.eq(1)]
        eligible &= d.year.ne(2023)&d.firm_id.isin(stable)
    if sample.startswith('leave_'):eligible &= d.year.ne(2023)&d.year.ne(int(sample.split('_')[1]))
    q=d.loc[eligible].copy()
    xs=[exposure]+CONTROLS+extra
    contrasts={'average slope':{exposure:1}}
    if moderator:
        q['interaction']=q[exposure]*q[moderator];xs=[exposure,moderator,'interaction']+CONTROLS+extra
        if moderator=='Pollute':contrasts={'slope Pollute=0':{exposure:1},'slope Pollute=1':{exposure:1,'interaction':1},'difference in slopes':{'interaction':1}}
        else:contrasts={'interaction':{'interaction':1},'slope green=-1SD':{exposure:1,'interaction':-1},'slope green=mean':{exposure:1},'slope green=+1SD':{exposure:1,'interaction':1}}
    hashed_columns=list(dict.fromkeys(['firm_id','year',outcome]+xs+fe+list(clusters)))
    data_hash=hashlib.sha256(pd.util.hash_pandas_object(q[hashed_columns],index=False).values.tobytes()).hexdigest()
    model_id=hashlib.sha256((label+data_hash).encode()).hexdigest()[:16]
    marker=ROOT/f'05_results/estimation_samples/{model_id}.json'
    if marker.exists():
        z=json.loads(marker.read_text(encoding='utf-8'));RESULTS.extend(z['results']);DIAGNOSTICS.append(z['diagnostics']);return
    try:
        m=fit(q,outcome,xs,fe,clusters)
        rows=[]
        for name,weights in contrasts.items():
            rows.append({'model_id':model_id,'analysis':analysis,'outcome':outcome,'exposure':exposure,'sample':sample,'moderator':moderator or '', 'fixed_effects':'+'.join(fe),'clusters':'+'.join(clusters),'contrast':name,**contrast(m,weights),'N':m['N'],'firms':int(m['firms']),'cities':int(m['cities']),'N_input':m['N_input'],'singletons_removed':m['singletons_removed'],'df_absorbed':int(m['df_absorbed']),'df_cluster':m['df_resid_cluster'],'exposure_sd':m['exposure_sd'],'outcome_sd':m['outcome_sd']})
        diagnostics={k:v for k,v in m.items() if k not in ['beta','cov','sample']}
        diagnostics.update(model_id=model_id,label=label,estimator='Python pyhdfe OLS, firm-clustered primary; calibrated separately to archived Stata',all_coefficients=m['beta'].to_dict())
        m['sample'].to_parquet(SAMPLES/f'{model_id}.parquet',index=False)
        marker.write_text(json.dumps({'diagnostics':diagnostics,'results':rows},ensure_ascii=False,indent=2,default=lambda v:int(v) if isinstance(v,np.integer) else float(v)),encoding='utf-8')
        RESULTS.extend(rows);DIAGNOSTICS.append(diagnostics)
        print(f'MODEL {model_id} {analysis} {outcome} {exposure} {sample} N={m["N"]}',flush=True)
    except Exception:
        error={'model_id':model_id,'label':label,'error':traceback.format_exc()}
        (ROOT/f'06_logs/model_failure_{model_id}.json').write_text(json.dumps(error,indent=2),encoding='utf-8');print(error['error'],flush=True)


def main():
    cal=pd.read_csv(ROOT/'02_audit/estimator_calibration.csv')
    if not cal.passed.all():raise RuntimeError('Estimator calibration is a required gate')
    d=prepare()
    # Freeze and save the matrix before looking at any new regression results.
    matrix={'outcomes':['current','official'],'common_samples':['common_full','common_no2023','common_no2021_no2023'],'exposures':['csmar','old_v2','log_combined_5km','log_assisted_combined_5km','log_old_keyword_5km'],'radii':RADII,'categories':CATEGORIES,'primary_SE':'firm cluster','primary_FE':['firm_id','industry_year'],'primary_outcome':'official','primary_exposure':'log_combined_5km','primary_sample':'common_no2023_provisional_archive_labels','new_metadata_risk_sensitivity':'common_no2021_no2023: added before new outcome models after independent query-time audit identified old query dates in the 2021-labelled archive; no automatic re-dating','annual_outcome_scales':['within-year z-score','within-year average-rank percentile'],'coordinate_scenarios':['as_provided','poi_wgs_office_wgs_assumed','poi_wgs_office_bd09_assumed'],'causal_claims':False,'coordinate_status':'as-provided main with explicitly hypothetical transformed scenarios'}
    (ROOT/'02_audit/experiment_matrix.json').write_text(json.dumps(matrix,indent=2),encoding='utf-8')
    for outcome in matrix['outcomes']:
        for sample in matrix['common_samples']:
            for exposure in matrix['exposures']:
                for moderator in [None,'Pollute','green_z']:run(d,outcome,exposure,sample,'measurement_comparison',moderator)
        for radius in RADII:
            for moderator in [None,'Pollute']:run(d,outcome,f'log_combined_{radius}km','common_no2023','radius',moderator)
        for category in CATEGORIES+['nightlife']:
            for moderator in [None,'Pollute']:run(d,outcome,f'log_{category}_5km','common_no2023','category',moderator)
        for category in CATEGORIES:
            for moderator in [None,'Pollute']:run(d,outcome,f'log_without_{category}_5km','common_no2023','leave_one_category_out',moderator)
        for sample in ['pre2019','post2019_no2023','include_valid2019_no2023','stable_city_no2023']:
            for moderator in [None,'Pollute']:run(d,outcome,'log_combined_5km',sample,'period_and_location',moderator)
        for year in sorted(d.loc[d.v3_main_eligible,'year'].unique()):run(d,outcome,'log_combined_5km',f'leave_{int(year)}_no2023','leave_one_year_out')
        for exposure in ['csmar','log_combined_5km']:
            for moderator in [None,'Pollute']:
                run(d,outcome,exposure,'common_no2023','strict_FE',moderator,fe=['firm_id','industry_year','city_year'])
                run(d,outcome,exposure,'common_no2023','commercial_controls',moderator,extra=['log_nonalcohol_total_5km'])
                run(d,outcome,exposure,'common_no2023','joint_commercial_controls',moderator,extra=['log_total_5km','log_restaurant_5km','log_entertainment_5km'])
                run(d,outcome,exposure,'common_no2023','two_way_clustering',moderator,clusters=('firm_id','city_id'))
        for transformed in [outcome+'_annual_z',outcome+'_annual_percentile']:
            for exposure in ['csmar','log_combined_5km']:run(d,transformed,exposure,'common_no2023','annual_outcome_scale','Pollute')
        for transformed in ['ln_'+outcome,'asinh_'+outcome]:
            for exposure in ['csmar','log_combined_5km']:
                for moderator in [None,'Pollute']:run(d,transformed,exposure,'common_no2023','functional_form',moderator)
        lag_common=d[d.lag_new_poi.notna()]
        for exposure in ['log_combined_5km','lag_new_poi']:run(lag_common,outcome,exposure,'common_no2023','calendar_lag_common_sample')
    coordinate_names=[];coordinate_caps=[]
    for scenario in matrix['coordinate_scenarios']:
        files=sorted((ROOT/'04_data').glob(f'poi_*_{scenario}.parquet'))
        q=pd.concat([pd.read_parquet(p,columns=['id','year','combined_5km','usable_experimental']) for p in files]).rename(columns={'id':'firm_id'})
        name='coord_'+scenario
        # Use the common primary coverage flag in run(); zero POIs inside a
        # transformed 5-km buffer must not become missing merely because the
        # as-provided source evidence was established within 10 km.
        q[name]=np.log1p(q.combined_5km)
        d=d.merge(q[['firm_id','year',name]],on=['firm_id','year'],how='left',validate='one_to_one')
        lo=stata_percentile(d.loc[d.v3_main_eligible,name],.01);hi=stata_percentile(d.loc[d.v3_main_eligible,name],.99)
        coordinate_caps.append({'variable':name,'reference_sample':'v3_main_eligible_before_singletons','reference_N':int(d.loc[d.v3_main_eligible,name].notna().sum()),'p1':lo,'p99':hi})
        d[name]=d[name].clip(lo,hi);coordinate_names.append(name)
    pd.DataFrame(coordinate_caps).to_csv(ROOT/'02_audit/coordinate_scenario_caps.csv',index=False,encoding='utf-8-sig')
    q=d[d[coordinate_names].notna().all(axis=1)]
    for outcome in matrix['outcomes']:
        for exposure in coordinate_names:
            for moderator in [None,'Pollute']:run(q,outcome,exposure,'common_no2023','coordinate_scenario',moderator)
    pd.DataFrame(RESULTS).to_csv(ROOT/'05_results/model_results.csv',index=False,encoding='utf-8-sig')
    (ROOT/'05_results/model_diagnostics.json').write_text(json.dumps(DIAGNOSTICS,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(f'EXPERIMENTS_DONE contrasts={len(RESULTS)} models={len(DIAGNOSTICS)}',flush=True)


if __name__=='__main__':main()
