"""Isolate the sign convention in first-round annual-percentile outcomes."""
import pandas as pd

from config import CONTROLS, ROOT
from hdfe import contrast, fit


def main():
    panel = pd.read_parquet(ROOT/'04_data/experiment_panel.parquet')
    panel = panel[panel.sample_common_no2023.eq(1)].copy()
    panel['interaction'] = panel.alcohol_culture*panel.Pollute
    n = panel.groupby('year').firm_id.transform('size')
    out = []
    for y in ['mca_current','mca_official_scaled']:
        grouped = panel.groupby('year')[y]
        samples = {}
        for tag, method, ascending in [('stata_field_descending_min','min',False),
                                        ('ascending_average_rank','average',True)]:
            panel['percentile']=(grouped.rank(method=method,ascending=ascending)-1)/(n-1)
            m=fit(panel,'percentile',['alcohol_culture','Pollute','interaction']+CONTROLS,['firm_id','industry_year'])
            samples[tag]=m['sample']
            out.append({'outcome':y,'rank_convention':tag,'N':m['N'],'firms':m['firms'],**contrast(m,{'interaction':1})})
        assert samples['stata_field_descending_min'].equals(samples['ascending_average_rank'])
    table=pd.DataFrame(out)
    for y,b in [('mca_current',-.0062),('mca_official_scaled',-.0101)]:
        got=table.loc[table.outcome.eq(y)&table.rank_convention.eq('stata_field_descending_min'),'b'].iloc[0]
        assert abs(got-b)<.0001, (y,got,b)
    table.to_csv(ROOT/'05_results/archived_percentile_rank_direction.csv',index=False,encoding='utf-8-sig')
    print(table.to_string(index=False),flush=True)


if __name__=='__main__':
    main()
