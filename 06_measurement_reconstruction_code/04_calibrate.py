import json
import numpy as np
import pandas as pd
from config import ROOT, ORIGINAL, CONTROLS
from hdfe import fit,contrast


def main():
    d=pd.read_stata(ORIGINAL/'08_revision_experiments/outputs/review_analysis_panel.dta',convert_categoricals=False)
    models=[]
    expected=pd.read_csv(ORIGINAL/'08_revision_experiments/outputs/review_driven_model_results.csv')
    for period in ['full','no2023']:
        q=d[d.sample_current.eq(1)&(d.year.ne(2023) if period=='no2023' else True)]
        m=fit(q,'mca_current',['alcohol_culture']+CONTROLS,['firm_id','industry_year']);c=contrast(m,{'alcohol_culture':1})
        e=expected[(expected.analysis=='average_core')&(expected.outcome=='mca_current')&(expected['sample']==period)].iloc[0]
        item={'model':period,**c,'N':m['N'],'firms':m['firms'],'df_absorbed':m['df_absorbed'],'stata_b':e.b,'stata_se':e.se,'stata_p':e.p,'b_difference':c['b']-e.b,'se_difference':c['se']-e.se,'singleton_count':m['singletons_removed']}
        item['passed']=bool(abs(item['b_difference'])<1e-6 and abs(item['se_difference'])<1e-5 and m['N']==e.N)
        models.append(item)
    exact=pd.read_csv(ORIGINAL/'05_tables/sustainability_revision_stata/exact_revision_results.csv')
    ref=d.loc[d.sample_current.eq(1),'investor_green']
    d['green_z_calibration']=(d.investor_green-ref.mean())/ref.std()
    for moderator,prefix in [('Pollute','Pollute'),('green_z_calibration','InvestorGreen')]:
        for period in ['original','no2023']:
            q=d[d.sample_current.eq(1)&(d.year.ne(2023) if period=='no2023' else True)].copy()
            q['interaction']=q.alcohol_culture*q[moderator]
            m=fit(q,'mca_current',['alcohol_culture',moderator,'interaction']+CONTROLS,['firm_id','industry_year'])
            c=contrast(m,{'interaction':1})
            contrast_name='Difference in slopes' if prefix=='Pollute' else 'Interaction'
            e=exact[(exact.specification==f'{prefix} {period}')&(exact.contrast==contrast_name)].iloc[0]
            item={'model':f'{prefix}_{period}',**c,'N':m['N'],'firms':m['firms'],'df_absorbed':m['df_absorbed'],'stata_b':e.b,'stata_se':e.se,'stata_p':e.p,'b_difference':c['b']-e.b,'se_difference':c['se']-e.se,'singleton_count':m['singletons_removed']}
            item['passed']=bool(abs(item['b_difference'])<1e-6 and abs(item['se_difference'])<1e-5 and m['N']==e.N)
            models.append(item)
    pd.DataFrame(models).to_csv(ROOT/'02_audit/estimator_calibration.csv',index=False,encoding='utf-8-sig')
    print(pd.DataFrame(models).to_string(index=False),flush=True)
    if not all(x['passed'] for x in models):raise RuntimeError('Calibration failed: investigate before interpreting new regressions')


if __name__=='__main__':main()
