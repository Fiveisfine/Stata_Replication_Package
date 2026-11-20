version 18.0
clear all
set more off
capture log close _all
do "$ROOT/01_code/_config.do"
log using "$LOGS/02_tables_3_to_5.log", text replace

use "$PANEL", clear
xtset firm_id year

tempname R
postfile `R' str12 table str56 model str30 term double b se p lb ub N clusters df_a singletons using "$RESULTS/tables_3_to_5.dta", replace

* Table 3, column 1: firm and year fixed effects.
reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1, absorb(firm_id year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 3") ("Firm and year FE") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))
ereturn list

* Table 3, column 2 and the principal full-period result.
reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 3") ("Firm and industry-year FE") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))
gen byte esample_table3 = e(sample)
ereturn list

* Table 4: first-round common-sample sequential controls.
* This archived comparison excludes 2019 and requires nonfinancial/non-ST status,
* an available POI source, and complete city, regulation, trust, and commercial
* POI controls.  Keeping this historical sample definition reproduces the table
* reported in the manuscript rather than silently changing its composition.
foreach v in ln_total_poi_5km ln_restaurant_poi_5km ln_entertain_poi_5km {
    quietly summarize `v' if sample_current == 1 & year != 2019, detail
    replace `v' = r(p1) if `v' < r(p1) & !missing(`v')
    replace `v' = r(p99) if `v' > r(p99) & !missing(`v')
}
egen byte missing_common = rowmiss(ln_city_gdp ln_pc_gdp gdp_growth env_reg ln_night_light trust1 trust2 ln_total_poi_5km ln_restaurant_poi_5km ln_entertain_poi_5km)
gen byte sample_table4 = sample_current == 1 & year != 2019 & is_finance != 1 & is_stpt != 1 & poi_source_available == 1 & missing_common == 0

reghdfe mca_current alcohol_culture $CONTROLS if sample_table4, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 4") ("Common-sample baseline") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

reghdfe mca_current alcohol_culture $CONTROLS ln_city_gdp ln_pc_gdp gdp_growth env_reg ln_night_light if sample_table4, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 4") ("Add city controls") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

reghdfe mca_current alcohol_culture $CONTROLS ln_city_gdp ln_pc_gdp gdp_growth env_reg ln_night_light trust1 trust2 if sample_table4, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 4") ("Add trust controls") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

reghdfe mca_current alcohol_culture $CONTROLS ln_city_gdp ln_pc_gdp gdp_growth env_reg ln_night_light trust1 trust2 ln_total_poi_5km ln_restaurant_poi_5km ln_entertain_poi_5km if sample_table4, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 4") ("Add POI controls") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))
ereturn list

* Table 5, Panel A: clustering.
foreach cl in firm_id city_id {
    reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1, absorb(firm_id industry_year) vce(cluster `cl')
    lincom alcohol_culture
    post `R' ("Table 5") ("Clustering: `cl'") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))
}
reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1, absorb(firm_id industry_year) vce(cluster firm_id city_id)
lincom alcohol_culture
post `R' ("Table 5") ("Two-way firm-city clustering") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (.) (e(df_a)) (e(num_singletons))

* Table 5, Panel B: outcome forms.
gen double ln_mca = ln(1 + mca_current)
quietly summarize mca_current if sample_current == 1
gen double z_mca = (mca_current - r(mean)) / r(sd) if !missing(mca_current)
gen byte climate_any = mca_current_original > 0 if !missing(mca_current_original)

foreach y in ln_mca z_mca climate_any {
    reghdfe `y' alcohol_culture $CONTROLS if sample_current == 1, absorb(firm_id industry_year) vce(cluster firm_id)
    lincom alcohol_culture
    post `R' ("Table 5") ("Outcome: `y'") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))
}
reghdfe ln_mca alcohol_culture $CONTROLS if sample_current == 1 & year != 2023, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 5") ("lnMCA excluding 2023") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

capture noisily clogit climate_any alcohol_culture $CONTROLS i.year if sample_current == 1, group(firm_id) vce(cluster firm_id)
if !_rc {
    lincom alcohol_culture
    post `R' ("Table 5") ("ClimateAny conditional logit") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (.) (.)
    ereturn list
}

* Table 5, Panel C: period, fixed-effect, lag, and high-zero checks.
reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1 & year != 2023, absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 5") ("MCA excluding 2023") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))
gen byte esample_no2023 = e(sample)
ereturn list

reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1, absorb(firm_id city_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 5") ("City-year FE") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

gen double lag_alcohol = L.alcohol_culture
replace lag_alcohol = . if year - L.year != 1
reghdfe mca_current lag_alcohol $CONTROLS if sample_current == 1, absorb(firm_id industry_year) vce(cluster firm_id)
lincom lag_alcohol
post `R' ("Table 5") ("Calendar-consistent lag") ("L.AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1 & !(year == 2023 & inlist(province_id, 320000, 440000)), absorb(firm_id industry_year) vce(cluster firm_id)
lincom alcohol_culture
post `R' ("Table 5") ("Exclude high-zero province-years") ("AlcoholPOI") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust)) (e(df_a)) (e(num_singletons))

preserve
keep firm_id year esample_table3 esample_no2023 sample_table4
sort firm_id year
save "$RESULTS/samples/estimation_sample_flags.dta", replace
export delimited using "$RESULTS/samples/estimation_sample_flags.csv", replace
restore

postclose `R'
use "$RESULTS/tables_3_to_5.dta", clear
sort table model
export delimited using "$RESULTS/tables_3_to_5.csv", replace datafmt
log close
