import json
import platform
import re
from pathlib import Path

import numpy as np
import pandas as pd

from config import ROOT,ORIGINAL,RADII,CATEGORIES,CONTROLS


def markdown(d):
    # Avoid optional rendering dependencies for a reproducible plain-text report.
    a=d.copy()
    for c in a.select_dtypes(include='number'):
        if c not in ['N','firms','cities','year','before','after','removed']:a[c]=a[c].map(lambda x:f'{x:.5g}' if pd.notna(x) else '')
    return '| '+' | '.join(a.columns)+' |\n| '+' | '.join(['---']*len(a.columns))+' |\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in a.itertuples(index=False,name=None))


def main():
    d=pd.read_parquet(ROOT/'04_data/experiment_panel.parquet')
    # Stata-friendly local data, keeping short explicit variable names.
    keep=['firm_id','year','industry_year','city_year','city_id','province_id','current','official','csmar','old_v2','Pollute','green_z','v3_main_eligible','usable_experimental']+CONTROLS+[c for c in d if c.startswith('log_') and c.endswith('km')]
    d[keep].to_csv(ROOT/'04_data/experiment_panel_stata.csv',index=False,encoding='utf-8-sig')
    d[keep].to_stata(ROOT/'04_data/experiment_panel_stata.dta',write_index=False,version=118)
    codebook=[]
    for name in d.columns:
        match=re.fullmatch(r'(retail|bar|nightclub|ktv|disco|combined|nightlife|assisted_combined|old_keyword|total|restaurant|entertainment|shopping|nonalcohol_total|without_\w+)_(1|3|5|10)km',name)
        if match:codebook.append({'variable':name,'definition':match.group(1),'radius_km':int(match.group(2)),'unit':'POI count; missing if unusable coverage','rule_source':'01_code/classify.py; 01_code/03_match.py','note':'Independent local-source reconstruction, not a reproduced CSMAR field.'})
        elif name.startswith('log_') and name.endswith('km'):codebook.append({'variable':name,'definition':'ln(1 + '+name[4:]+')','unit':'log count, capped at fixed benchmark p1/p99','rule_source':'02_audit/winsorization_thresholds.csv','note':'Underlying counts are retained separately.'})
    codebook.extend([
        {'variable':'csmar','definition':'Original supplier aggregate field, capped for the v3 experiment','unit':'log supplier count','rule_source':'referenced original combined DTA','note':'Supplier snapshots and processing rules remain incompletely documented.'},
        {'variable':'old_v2','definition':'ln(1 + old v2 reconstructed broad-keyword count)','unit':'log count, capped','rule_source':'original alcohol_poi_5km','note':'Kept separate from the same-pipeline v3 old_keyword construction.'},
        {'variable':'usable_experimental','definition':'All selected source files processed, observed local POIs, no known missing province','unit':'0/1','rule_source':'03_match.py','note':'Technical availability flag, not proof of complete historical coverage or construct validity.'},
        {'variable':'temporal_metadata_risk','definition':'2021 archive labelled with mixed/older query timestamps','unit':'0/1','rule_source':'2021_query_time_summary.csv','note':'Query dates are not opening/closing dates. No automatic source-year reassignment.'},
    ])
    pd.DataFrame(codebook).to_csv(ROOT/'02_audit/v3_variable_codebook.csv',index=False,encoding='utf-8-sig')
    availability=d.assign(green_available=d.investor_green.notna(),green_old_baseline=d.investor_green.notna()&d.sample_current.eq(1),green_v3_primary=d.investor_green.notna()&d.v3_main_eligible,current_available=d.current.notna(),official_available=d.official.notna())
    annual=availability.groupby('year').agg(firm_years=('firm_id','size'),current_available=('current_available','sum'),official_available=('official_available','sum'),green_available=('green_available','sum'),green_old_baseline=('green_old_baseline','sum'),green_v3_primary=('green_v3_primary','sum'),v3_usable=('usable_experimental','sum'),primary_eligible=('v3_main_eligible','sum'))
    annual.to_csv(ROOT/'02_audit/annual_measure_availability.csv',encoding='utf-8-sig')
    source_meta=[]
    for p in (ROOT/'03_cache').glob('*/s*.json'):source_meta.append(json.loads(p.read_text(encoding='utf-8')))
    pd.DataFrame(source_meta).drop(columns=['malformed_examples'],errors='ignore').to_csv(ROOT/'02_audit/parser_execution.csv',index=False,encoding='utf-8-sig')
    recovered=[{'year':m['year'],'source_id':m['source_id'],'recovered_records':m.get('recovered_physical_records',0),'remaining_malformed_records':m.get('malformed_rows',0),'raw_records_after_recovery':m['raw_rows']} for m in source_meta if m.get('recovered_physical_records',0)>0]
    recovery_table=pd.DataFrame(recovered)
    recovery_table.to_csv(ROOT/'02_audit/recovered_csv_records.csv',index=False,encoding='utf-8-sig')
    dedup=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'02_audit').glob('deduplication_*.json'))]
    pd.DataFrame(dedup).to_csv(ROOT/'02_audit/deduplication_summary.csv',index=False,encoding='utf-8-sig')
    desc=[]
    for year,q in d[d.usable_experimental].groupby('year'):
        for c in CATEGORIES+['combined','assisted_combined','old_keyword','total']:
            v=q[f'{c}_5km'];desc.append({'year':int(year),'category':c,'N':len(q),'mean':v.mean(),'median':v.median(),'zero_share':v.eq(0).mean(),'p99':v.quantile(.99)})
    pd.DataFrame(desc).to_csv(ROOT/'05_results/annual_category_descriptives.csv',index=False,encoding='utf-8-sig')
    corr=[]
    for grouping in ['all','year','province_id']:
        groups=[('all',d[d.v3_main_eligible])] if grouping=='all' else d[d.v3_main_eligible].groupby(grouping)
        for label,q in groups:
            for other in ['old_v2','log_combined_5km','log_assisted_combined_5km','log_old_keyword_5km']:
                corr.append({'grouping':grouping,'group':label,'comparison':other,'N':len(q),'pearson':q.csmar.corr(q[other]),'spearman':q.csmar.corr(q[other],method='spearman')})
    pd.DataFrame(corr).to_csv(ROOT/'05_results/exposure_correlations.csv',index=False,encoding='utf-8-sig')
    province=[]
    for (year,region),q in d.groupby(['year','province_id']):
        province.append({'year':year,'province_id':region,'N':len(q),'original_nonmissing':q.csmar.notna().sum(),'original_zero_share':q.csmar.eq(0).where(q.csmar.notna()).mean(),'v3_usable':q.usable_experimental.sum(),'v3_zero_share':q.loc[q.usable_experimental,'combined_5km'].eq(0).mean()})
    pd.DataFrame(province).to_csv(ROOT/'02_audit/province_year_comparison.csv',index=False,encoding='utf-8-sig')
    selection=[]
    for c in ['current','csmar']+CONTROLS:
        q=d[d.v3_main_eligible];a=q.loc[q.investor_green.notna(),c];b=q.loc[q.investor_green.isna(),c]
        selection.append({'variable':c,'available_N':a.notna().sum(),'missing_N':b.notna().sum(),'available_mean':a.mean(),'missing_mean':b.mean(),'standardized_difference':(a.mean()-b.mean())/np.sqrt((a.var()+b.var())/2)})
    pd.DataFrame(selection).to_csv(ROOT/'02_audit/investorgreen_selection.csv',index=False,encoding='utf-8-sig')
    q=d[d.v3_main_eligible].dropna(subset=['Pollute']).sort_values(['firm_id','year']).copy()
    prev=q.groupby('firm_id')[['Pollute','year']].shift()
    consecutive=(q.year==prev.year+1)&prev.Pollute.notna()
    switches=q.Pollute.ne(prev.Pollute)&consecutive
    mixed=q.groupby('industry_year').Pollute.nunique()
    import pyhdfe
    alg=pyhdfe.create(q[['firm_id','industry_year']].to_numpy(),cluster_ids=q[['firm_id']].to_numpy())
    residual=alg.residualize(q[['Pollute']].to_numpy())
    pollute_diag={'candidate_firms':int(q.firm_id.nunique()),'firms_with_any_status_change':int(q.groupby('firm_id').Pollute.nunique().gt(1).sum()),'firms_with_consecutive_year_status_change':int(q.loc[switches,'firm_id'].nunique()),'industry_year_cells':len(mixed),'mixed_industry_year_cells':int(mixed.gt(1).sum()),'within_FE_residual_sd':float(residual.std(ddof=1)),'note':'Verifies variation in the supplied indicator; does not recover the supplier designation rules.'}
    (ROOT/'02_audit/pollute_variation_diagnostics.json').write_text(json.dumps(pollute_diag,indent=2),encoding='utf-8')
    results=pd.read_csv(ROOT/'05_results/model_results.csv')
    economic=results[(results.analysis=='measurement_comparison')&(results.contrast=='average slope')].copy()
    economic['change_y_per_1sd_exposure']=economic.b*economic.exposure_sd
    economic['change_in_y_sd']=economic.change_y_per_1sd_exposure/economic.outcome_sd
    economic.to_csv(ROOT/'05_results/economic_magnitudes.csv',index=False,encoding='utf-8-sig')
    baseline=economic[economic['sample']=='common_no2023'][['outcome','exposure','b','se','p','change_in_y_sd','N','firms','cities']]
    pollute=results[(results.analysis=='measurement_comparison')&(results['sample']=='common_no2023')&(results.contrast=='difference in slopes')][['outcome','exposure','b','se','p','N']]
    green=results[(results.analysis=='measurement_comparison')&(results.contrast=='interaction')][['outcome','exposure','sample','b','p','N']]
    baseline.to_csv(ROOT/'05_results/key_baselines.csv',index=False,encoding='utf-8-sig');pollute.to_csv(ROOT/'05_results/key_pollute_interactions.csv',index=False,encoding='utf-8-sig')
    risk=results[(results.analysis=='measurement_comparison')&(results['sample']=='common_no2021_no2023')&(results.contrast.isin(['average slope','difference in slopes']))][['outcome','exposure','contrast','b','se','p','N']]
    summaries=[]
    def selected(outcome, exposure, sample, contrast):
        q=results[(results.analysis=='measurement_comparison')&(results.outcome==outcome)&(results.exposure==exposure)&(results['sample']==sample)&(results.contrast==contrast)]
        row=q.iloc[0]
        return f"b={row.b:+.4f}，95% CI [{row.ci_low:+.4f}, {row.ci_high:+.4f}]，p={row.p:.3g}"
    no23='common_no2023'
    for title, outcome, contrast in [('H1：项目MCA','current','average slope'),('H1：更新工作簿MCA','official','average slope'),
            ('H3：项目MCA斜率差','current','difference in slopes'),('H3：更新工作簿MCA斜率差','official','difference in slopes'),
            ('H2：项目MCA交互','current','interaction'),('H2：更新工作簿MCA交互','official','interaction')]:
        summaries.append({'对照':title,'原CSMAR':selected(outcome,'csmar',no23,contrast),
            'v3严格五类5公里':selected(outcome,'log_combined_5km',no23,contrast)})
    supplemental_path=ROOT/'05_results/category_coverage_sensitivity.csv'
    if supplemental_path.exists():
        a=pd.read_csv(supplemental_path)
        a=a[a.exposure.isin(['csmar','log_combined_5km','log_assisted_combined_5km'])&a.contrast.isin(['average slope','difference in slopes','interaction'])]
        category_risk=markdown(a[['sample','outcome','exposure','contrast','b','ci_low','ci_high','p','N']])
    else:category_risk='2022标签风险的附加排除实验未生成。'
    old_reconciliation_path=ROOT/'02_audit/archived_2023_sample_reconciliation.csv'
    old_reconciliation=markdown(pd.read_csv(old_reconciliation_path)) if old_reconciliation_path.exists() else '未生成。'
    overlap_path=ROOT/'05_results/archived_mca_overlap_baselines.csv'
    overlap=markdown(pd.read_csv(overlap_path)[['sample','outcome','N_input','N','b','ci_low','ci_high','p']]) if overlap_path.exists() else '未生成。'
    rank_path=ROOT/'05_results/archived_percentile_rank_direction.csv'
    rank_check=markdown(pd.read_csv(rank_path)[['outcome','rank_convention','b','se','p','N']]) if rank_path.exists() else '未生成。'
    old_province_path=ROOT/'02_audit/archived_sample_province_year_coverage.csv'
    if old_province_path.exists():
        p=pd.read_csv(old_province_path)
        province_detail=markdown(p[(p.year==2023)&p.province_id.isin([320000,440000])][['province_id','N','archived_zero_share','old_source_share','v3_usable','v3_zero_share']].fillna('未覆盖'))
    else:province_detail='未生成。'
    time_path=ROOT/'02_audit/2021_query_time_summary.csv'
    time_summary=pd.read_csv(time_path) if time_path.exists() else None
    report=f'''# v3 POI实验报告

本次只生成代码、数据和实验结果，没有修改稿件。下列估计为Python HDFE实验；计算器已通过归档Stata基准系数、标准误及样本量校准，未声称重新运行Stata。

## 主要判断

在排除2023年的暂定共同样本（22,316个企业年度、3,593家企业）上，两个MCA序列的5公里平均关联均未达5%显著水平，适用于原CSMAR、旧宽关键词、v3严格五类、名称辅助及同流程宽关键词这五种空间口径。以更新工作簿MCA和v3严格5公里计，一个样本标准差的暴露对应约+0.58%的因变量样本标准差；不能将这一描述性量级解释为因果效应。10公里及个别分类有名义显著结果，但跨半径和两套MCA不一致，也没有作多重比较校正，不应据此改选主口径。

原稿归档基准（原样本、原缩尾）经再估计核对：含2023为 -0.0339（p=0.077），排除后为 -0.0077（p=0.798）。按v3共同样本和固定缩尾另比，项目MCA与原CSMAR在含2023时为 -0.0483（p=0.048），排除后为 -0.0166（p=0.592）；同样本的旧宽关键词与v3严格五类在含2023时也不显著。两条对照分别回答原稿复现和同样本测量差异，不能混用。

{markdown(pd.DataFrame(summaries))}

H3的正向斜率差依赖原CSMAR口径。项目MCA下，v3严格规则的差异甚至反向；换更新工作簿MCA、改用名称辅助或同流程宽关键词后，负向差异也不能稳定复现。H2应限于InvestorGreen实际可用子样本：主共同样本中两套MCA的五类规则均未达5%显著；个别进一步删年模型出现反向名义显著，不能作为稳定支持。完整主表报告交互、条件斜率和区间。

建议将原CSMAR、旧宽关键词、v3五类分别留档。按来源可核验性决定正文定位：更新工作簿MCA可追溯；v3五类是可审计的独立替代测量。当前不能以显著性为由替换指标、半径或年份，也不足以将严格五类在所有年份视为完整可比。

## 数据和方法边界

原CSMAR聚合指标、旧宽关键词指标、v3分类标签指标分别保存。v3严格类别规则以源分类文字为依据，类型代码保留并输出对照表；名称辅助识别单独报告。未把重建值填入供应商字段。

每年在企业附近12公里内保留原始字段缓存，再按1/3/5/10公里统计。去重在这一局部数据范围内进行，不能将删除比例称为全国去重比例。优先使用保留的稳定POI ID；缺少ID时使用标准化名称、地址和六位小数坐标，不合并不同地址。此保守规则可能保留地址写法不同的重复场所。ID坐标冲突单列，避免将明显不同位置强行合并。分类并集按POI计一次；逐类剔除直接对剩余类别并集计数，未用总数简单减去分项。

主空间口径是as-provided。早期.prj中的WGS84是文件声明；企业坐标和部分年份源坐标的真实体系仍未获得完整历史证明。两种坐标转换仅作为假设场景，5公里对照结果不能被描述为已经恢复真实坐标。

主比较在共同的可用企业年度样本中排除2019和2023。有源文件且有观测到的本地POI，不等于该地历史POI已被证明完整。2014年企业坐标缺失、2023年广东源文件缺失，均未插补。新指标的2019年结果另作扩展分析。

v3连续变量的缩尾基准统一固定为主共同样本、单例删除前的1%和99%阈值，具体值保存在winsorization_thresholds.csv；这与旧稿部分变量的全期缩尾参照可能不同，不能将系数差异全部归因于POI。每一模型另存实际估计样本、被省略变量、吸收自由度及簇数。

## 新发现的2021目录时间风险

对2021目录345份源文件首条记录的独立核查发现：327份首条查询时间为2020年、16份为2021年、2份为2019年。这个检查只说明首条记录，不能据此推断每份文件全部记录的年份。全量查询时间元数据统计如下（原始记录计数，尚未按POI去重）：

{markdown(time_summary) if time_summary is not None else '全量元数据统计尚未生成；不得将首条记录年份当成全文件年份。'}

查询时间不是场所开业/关停日期，也不自动证明年度完整快照。2021目录指标因此标为时间风险，未自动重派到2020年。新增排除2021及2023年的共同样本分析是在查看新回归结果之前根据元数据问题加入的；原有目录年份口径仍完整保留作为暂定实验。

## 2022分类标签断点

2022年4,610个可用公司年度的严格分类中，烟酒零售、夜总会、迪厅分别全为零；这些是规则在粗粒度源标签下未识别的计数，不能解释为三个类别没有场所。5公里严格合计均值为100.25，加入名称辅助后的均值为268.20；名称辅助多识别出的候选场所不是独立真值。以下排除2022、再同时排除2021的共同样本为看到描述性覆盖断点后加做的敏感性，并保存了逐模型样本及共同样本验证。其余两套空间口径结果见完整附加CSV。

两种排除窗口均未恢复平均关联。项目MCA下，v3严格5公里的Pollute斜率差由暂定主共同样本的 −0.1523（p=0.019）变为排除2022后的 −0.0394（p=0.611），再排除2021后为 +0.0191（p=0.820）。因此，严格口径的反向差异也受源分类年份影响，只能如实列作敏感性。

{category_risk}

## 2023零值和旧稿样本对账

以下省份数字按归档原稿入模候选样本计算，和全原始输入的覆盖分母不同。原归档高零规则为省年样本数至少20、零值比例至少90%；实际标记2023江苏及2023广东。江苏v3存在本地源且可匹配，不代表已经找到了原CSMAR归零原因；广东即使有214个公司年度在邻接源发现点位，也不能代替全省源文件，均按缺失处理。

{province_detail}

{old_reconciliation}

直接从原估计删2023后，留存的24,199条中另有492条在重估时成为单例，未发现其他样本损失。在完整候选面板中，金融和ST/PT标志均未出现1；如此可说明保留的上游输入已无可识别的这两类记录，现有面板本身无法证明更早的筛选步骤或把缺失标志解释为0。

## MCA版本与Table 7、A4、A5的关系

| 序列 | 记录可支持的构造和覆盖 | 本次使用 |
|---|---|---|
| Lei等（2023）论文序列 | 第一轮返修稿的来源说明为2000—2021年CNRDS年报。不能把后续工作簿中的2022值称为该论文样本。 | 没有单独重新生成这一序列。 |
| 2001—2023更新工作簿 | firm-level按公司代码、年度匹配；MCA_raw为气候词数占文档词数比，Scaled_MCA_raw缩放到0—100。工作簿没有独立记载截取章节、中文分词和重复文本规则。 | 逐条核对两列与归档面板；Table 7、A4的“官方MCA水平值”和v3的official均用Scaled_MCA_raw；缩尾基准分别按各自代码保存。 |
| 项目编制MCA | 原DTA的“管理层气候关注度指数”，2012—2023保留；源文本渠道与具体章节、完整词典、分词、重复文本处理及延伸协议未从留档恢复。 | v3的current是固定基准缩尾后的项目水平值，不等于工作簿的MCA_raw。 |

Table A5截至2021年合计20,218条是项目MCA基准候选。与工作簿取共同样本后，截至2021年为19,112条，加入工作簿2022年的3,633条后为22,745条，吸收固定效应后为22,385条。2022匹配进主面板的工作簿非缺失值是4,115条，包含不符合共同样本筛选的记录；不要与3,633混用。逐年对账在 `02_audit/mca_workbook_annual_reconciliation.csv`。

{overlap}

## 其他归档审稿核对

- 表6A原InvestorGreen标准化参照固定为原基准候选样本中的字段可用记录；排除2023没有重新算均值和标准差。归档排除2023交互模型为11,088条、2,334家企业及企业簇；v3比较的对应可用子样本为10,300条、2,140家企业及企业簇。供应商字段的真实分母和完整词典仍未知，不能用他文的问答占比公式替代。
- 归档原基准实际样本内有144家跨城市企业，4,307家企业、403个城市；系数在三种聚类下相同，p值不同。Trust两项在加入企业、行业×年效应后仍有变异，均未在本次复核的双Trust规格中被省略；不能将其解释为纯截面省级效应。
- 归档ClimateAny线性概率模型：企业与行业×年效应、企业聚类，28,208条，4,307个簇。归档条件Logit：按企业条件化并加年份虚拟变量、企业聚类，仅包含有0/1变化的企业，7,235条、874个簇；系数是对数胜算。该Logit来自原Stata日志，本次未重新拟合。新时间滞后只连接t和t−1，不跨年份缺口，2019不作为滞后暴露。v3与原归档分别保留asinh结果。
- 归档原Johnson–Neyman脚本、边际效应和图可复用。v3结果另保存，不将Python估计、原Stata日志或待运行的Stata核验入口冒称第二轮完整Stata复现包。

## 第一轮年内百分位方向核对

第一轮Table A4用 `egen rank(), field`，将最高原MCA排为第1，继而用 (rank−1)/(n−1) 把最高MCA映射为0。[Stata官方egen手册](https://www.stata.com/manuals/degen.pdf)给出了该排序规则。v3用低MCA到高MCA的平均秩。同一归档样本、原CSMAR与原模型重新计算如下；升序与降序还改变并列值处理，因此绝对系数不必完全对称。原负号不能直接视为相对MCA的实质方向翻转。水平值和实际年内标准化规格仍应各自报告，空间口径不一致问题也仍存在。

{rank_check}

## 年度可用性

{markdown(annual.reset_index())}

## CSV解析修复

{markdown(recovery_table) if len(recovery_table) else '没有触发跨行引号恢复。'}

快速解析器报错后，兼容流程从整个源文件重新开始，不向部分缓存重复追加。若一个损坏引号吞并多条物理行，仅恢复能独立通过字段结构检查的完整记录，再执行经纬度有效性检查；其余异常记录单列。原始F盘文件未修改。这里的恢复是输入解析修复，不能被描述为填补历史POI覆盖或恢复供应商快照。

## 主共同样本：平均关联

{markdown(baseline)}

change_in_y_sd是使用各模型实际样本的总体标准差换算的描述性量级，不是因果效应；两种MCA量纲不同，不直接比较原始系数大小。

## 主共同样本：Pollute组间斜率差

{markdown(pollute)}

交互项是斜率差，不能代替重污染企业自身斜率；两组斜率及置信区间见完整model_results.csv。

## InvestorGreen交互

{markdown(green)}

InvestorGreen定义仍是保留的供应商字段，本次没有找回其完整词典或分母。标准化参照为主共同样本中该字段可用的观测，后续敏感性保持这一参照。

## 排除2021时间风险年份后的共同样本

{markdown(risk)}

## 其他实验

完整结果表包含各半径、各类别及逐类剔除、提供时期、纳入可用2019年、稳定城市、逐年剔除、城市×年份固定效应、非酒类商业控制、双向聚类、年度z值/平均秩百分位，以及坐标假设场景。稳定城市不等于同城办公地址未变；不作这一更强解释。双向聚类采用公开的CGM合成协方差，逐模型自由度和实现已保留，未额外声称通过新Stata执行校准。

## 审稿覆盖与仍未解决的事项

| 问题 | 本次提供的实验或材料 | 限制 |
|---|---|---|
| 类别混合、烟酒零售影响 | 五类、夜生活、名称辅助、逐类剔除 | 不能证明高管实际社交行为 |
| 替代半径 | 同流程1/3/5/10公里 | 属独立测量的尺度敏感性，不是CSMAR原指标半径复现 |
| 原指标与重建不一致 | 三套血缘及同流程旧关键词/新分类比较 | 原供应商底层快照和去重仍未知 |
| 2014和2023异常 | 年度/省年覆盖及缺口记录 | 缺坐标和广东源文件未恢复 |
| 2023影响 | 共同样本含/不含2023和逐年剔除 | 仍需供应商说明原字段归零原因 |
| H2/H3稳定性 | 交互项、条件斜率、尺度、时期及坐标场景 | 显著性不构成机制或因果证据 |
| 可复现性 | 脚本、软件版本、输入指纹、缓存状态、逐模型e(sample)等价文件 | 许可证限制仍适用，历史采集协议并未凭空恢复 |
| MCA来源 | 关联工作簿原/缩放字段、核对年度及重做共同样本基准 | 没有重新挖掘源文本或恢复项目词典 |

本报告是实验记录，不能替代逐条回复信，也不表示全部审稿意见已经解决。
'''
    (ROOT/'07_report/POI_Experimental_Findings_CN.md').write_text(report,encoding='utf-8')
    print('DIAGNOSTICS_AND_REPORT_COMPLETE',flush=True)


if __name__=='__main__':main()
