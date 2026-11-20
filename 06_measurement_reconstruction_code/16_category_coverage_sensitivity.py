"""Check whether coarse 2022 category labels drive the five-category findings."""
import json

import pandas as pd

from config import CONTROLS, ROOT
from hdfe import contrast, fit


def main():
    results = ROOT/'05_results'
    panel = pd.read_parquet(ROOT/'04_data/experiment_panel.parquet')
    models = []
    membership = results/'category_coverage_samples'
    membership.mkdir(exist_ok=True)
    exposures = ['csmar','old_v2','log_combined_5km','log_assisted_combined_5km','log_old_keyword_5km']
    keep = panel.v3_main_eligible & panel[exposures].notna().all(axis=1)
    window = {'no2022_no2023':(2022,), 'no2021_no2022_no2023':(2021,2022)}
    rows = []
    for tag, dropped in window.items():
        d = panel[keep & ~panel.year.isin(dropped)].copy()
        for outcome in ['current','official']:
            for exposure in exposures:
                for mod in ['', 'Pollute', 'green_z']:
                    model_id = f'{tag}_{outcome}_{exposure}_{mod or "none"}'
                    xs = [exposure] + CONTROLS
                    tests = {'average slope':{exposure:1}}
                    if mod:
                        d['interaction'] = d[exposure]*d[mod]
                        xs = [exposure,mod,'interaction'] + CONTROLS
                        tests = {'interaction':{'interaction':1}}
                        if mod == 'Pollute':
                            tests = {'difference in slopes':{'interaction':1}, 'slope Pollute=0':{exposure:1},
                                     'slope Pollute=1':{exposure:1,'interaction':1}}
                    m = fit(d,outcome,xs,['firm_id','industry_year'])
                    sample = m['sample'].sort_values(['firm_id','year'],ignore_index=True)
                    if outcome=='current' and exposure=='csmar':
                        sample.to_parquet(membership/f'{tag}_{mod or "none"}.parquet',index=False)
                    else:
                        assert sample.equals(pd.read_parquet(membership/f'{tag}_{mod or "none"}.parquet'))
                    for name, w in tests.items():
                        rows.append({'model_id':model_id,'sample':tag,'outcome':outcome,'exposure':exposure,'moderator':mod,
                                     'contrast':name,**contrast(m,w),'N':m['N'],'N_input':m['N_input'],'firms':m['firms'],
                                     'cities':m['cities'],'df_cluster':m['df_resid_cluster']})
                    models.append({'model_id':model_id,'sample_file':f'{tag}_{mod or "none"}.parquet','clusters':m['cluster_counts'],
                                   'df_absorbed':m['df_absorbed'],'omitted':m['omitted']})
        print('CATEGORY_COVERAGE_SENSITIVITY', tag, 'complete', flush=True)
    assert len(models)==60 and len(rows)==100 and not any(x['not_identified'] for x in rows)
    pd.DataFrame(rows).to_csv(results/'category_coverage_sensitivity.csv',index=False,encoding='utf-8-sig')
    (results/'category_coverage_sensitivity_models.json').write_text(json.dumps(models,indent=2,default=int),encoding='utf-8')


if __name__=='__main__':
    main()
