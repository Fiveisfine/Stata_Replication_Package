version 18.0
clear all
set more off
capture log close _all
do "$ROOT/01_code/_config.do"
log using "$LOGS/04_appendix_sensitivity.log", text replace

tempname R
postfile `R' str34 analysis str24 outcome str32 exposure str20 sample str28 contrast double b se p lb ub N firms using "$RESULTS/appendix_sensitivity.dta", replace

* AlcoholPOI results under MCA level, annual z-score, and increasing percentile.
use "$PANEL", clear
bysort year: egen double mca_z_year_check = std(mca_current)
bysort year: egen double mca_rank = rank(mca_current)
bysort year: egen double mca_n = count(mca_current)
gen double mca_pct_year = (mca_rank - 1) / (mca_n - 1) if mca_n > 1

foreach y in mca_current mca_z_year_check mca_pct_year {
    reghdfe `y' c.alcohol_culture##i.Pollute $CONTROLS if sample_current == 1 & year != 2023, absorb(firm_id industry_year) vce(cluster firm_id)
    lincom 1.Pollute#c.alcohol_culture
    post `R' ("H3 scaling") ("`y'") ("AlcoholPOI") ("no2023") ("Difference in slopes") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
}

* Leave-one-year influence for the archived AlcoholPOI baseline.
foreach omit in 2012 2013 2015 2016 2017 2018 2020 2021 2022 2023 {
    reghdfe mca_current alcohol_culture $CONTROLS if sample_current == 1 & year != `omit', absorb(firm_id industry_year) vce(cluster firm_id)
    lincom alcohol_culture
    post `R' ("Leave one year out") ("mca_current") ("AlcoholPOI") ("omit `omit'") ("Average association") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
}

* ReconstructedPOI comparisons on the identical no-2023 sample.
use "$RECON", clear
egen byte miss_controls = rowmiss($CONTROLS)
gen byte common_no2023 = v3_main_eligible == 1 & miss_controls == 0 & !missing(current, csmar, log_combined_5km, Pollute)
bysort year: egen double current_z_year = std(current)
bysort year: egen double current_rank = rank(current)
bysort year: egen double current_n = count(current)
gen double current_pct_year = (current_rank - 1) / (current_n - 1) if current_n > 1

foreach y in current current_z_year current_pct_year {
    foreach x in csmar log_combined_5km {
        reghdfe `y' c.`x'##i.Pollute $CONTROLS if common_no2023 == 1, absorb(firm_id industry_year) vce(cluster firm_id)
        lincom 1.Pollute#c.`x'
        post `R' ("H3 construction") ("`y'") ("`x'") ("common no2023") ("Difference in slopes") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    }
}

* ReconstructedPOI radius and category checks.
foreach x in log_combined_1km log_combined_3km log_combined_5km log_combined_10km log_retail_5km log_bar_5km log_nightclub_5km log_ktv_5km log_disco_5km {
    reghdfe current `x' $CONTROLS if common_no2023 == 1, absorb(firm_id industry_year) vce(cluster firm_id)
    lincom `x'
    post `R' ("ReconstructedPOI") ("current") ("`x'") ("common no2023") ("Average association") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
}
foreach x in log_without_retail_5km log_without_bar_5km log_without_nightclub_5km log_without_ktv_5km log_without_disco_5km {
    reghdfe current `x' $CONTROLS if common_no2023 == 1, absorb(firm_id industry_year) vce(cluster firm_id)
    lincom `x'
    post `R' ("Leave one category out") ("current") ("`x'") ("common no2023") ("Average association") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
}

postclose `R'
use "$RESULTS/appendix_sensitivity.dta", clear
sort analysis outcome exposure sample contrast
export delimited using "$RESULTS/appendix_sensitivity.csv", replace datafmt
log close
