version 18.0
clear all
set more off
set linesize 255
* Run from the v3 workspace root. This file is supplied for independent
* verification; this experiment did not assume a locally available Stata binary.
capture log close _all
log using "06_logs/stata_independent_verification.log", text replace
about
which reghdfe
which ftools
use "04_data/experiment_panel_stata.dta", clear
global XC Size Lev ROA Growth CashFlow FirmAge SOE Board Indep Dual Top1 Inst Big4
capture confirm numeric variable v3_main_eligible
if _rc {
    gen byte primary = v3_main_eligible == "True"
}
else gen byte primary = v3_main_eligible == 1
foreach outcome in current official {
    foreach exposure in csmar old_v2 log_combined_5km log_assisted_combined_5km log_old_keyword_5km {
        reghdfe `outcome' `exposure' $XC if primary == 1, absorb(firm_id industry_year) vce(cluster firm_id)
        ereturn list
        matrix list e(b)
        matrix list e(V)
        lincom `exposure'
        preserve
            gen byte estimation_sample = e(sample)
            keep firm_id year estimation_sample
            export delimited "05_results/stata_sample_`outcome'_`exposure'.csv", replace
        restore
        reghdfe `outcome' c.`exposure'##i.Pollute $XC if primary == 1, absorb(firm_id industry_year) vce(cluster firm_id)
        ereturn list
        lincom `exposure'
        lincom `exposure' + 1.Pollute#c.`exposure'
        lincom 1.Pollute#c.`exposure'
    }
}
log close
