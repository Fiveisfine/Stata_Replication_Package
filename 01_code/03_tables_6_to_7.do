version 18.0
clear all
set more off
capture log close _all
do "$ROOT/01_code/_config.do"
log using "$LOGS/03_tables_6_to_7.log", text replace

use "$PANEL", clear
quietly summarize investor_green if sample_current == 1
gen double investor_green_z = (investor_green - r(mean)) / r(sd) if !missing(investor_green)

tempname R JN
postfile `R' str12 table str36 model str32 contrast double b se p lb ub N firms using "$RESULTS/tables_6_to_7.dta", replace
postfile `JN' str12 sample double root_low root_high observed_min observed_max N firms using "$RESULTS/johnson_neyman.dta", replace

* Table 6, Panel A: InvestorGreen moderation.
foreach window in full no2023 {
    local condition "sample_current == 1 & !missing(investor_green_z)"
    if "`window'" == "no2023" local condition "`condition' & year != 2023"
    reghdfe mca_current c.alcohol_culture##c.investor_green_z $CONTROLS if `condition', absorb(firm_id industry_year) vce(cluster firm_id)
    lincom c.alcohol_culture#c.investor_green_z
    post `R' ("Table 6") ("InvestorGreen `window'") ("Interaction") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    lincom alcohol_culture - c.alcohol_culture#c.investor_green_z
    post `R' ("Table 6") ("InvestorGreen `window'") ("Slope at -1 SD") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    lincom alcohol_culture
    post `R' ("Table 6") ("InvestorGreen `window'") ("Slope at mean") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    lincom alcohol_culture + c.alcohol_culture#c.investor_green_z
    post `R' ("Table 6") ("InvestorGreen `window'") ("Slope at +1 SD") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    ereturn list

    margins, dydx(alcohol_culture) at(investor_green_z=(-2(.1)2)) saving("$RESULTS/investorgreen_margins_`window'.dta", replace)
    marginsplot, recast(line) recastci(rarea) yline(0, lpattern(dash)) title("InvestorGreen moderation: `window'") name(ig_`window', replace)
    graph export "$RESULTS/figures/investorgreen_margins_`window'.png", replace width(2400)
    preserve
    use "$RESULTS/investorgreen_margins_`window'.dta", clear
    export delimited using "$RESULTS/investorgreen_margins_`window'.csv", replace datafmt
    restore

    scalar b1 = _b[alcohol_culture]
    scalar b3 = _b[c.alcohol_culture#c.investor_green_z]
    matrix V = e(V)
    scalar v11 = V["alcohol_culture","alcohol_culture"]
    scalar v33 = V["c.alcohol_culture#c.investor_green_z","c.alcohol_culture#c.investor_green_z"]
    scalar v13 = V["alcohol_culture","c.alcohol_culture#c.investor_green_z"]
    scalar tc = invttail(e(df_r), .025)
    scalar A = b3^2 - tc^2*v33
    scalar B = 2*b1*b3 - 2*tc^2*v13
    scalar C = b1^2 - tc^2*v11
    scalar D = B^2 - 4*A*C
    scalar lo = .
    scalar hi = .
    if D >= 0 & A != 0 {
        scalar r1 = (-B-sqrt(D))/(2*A)
        scalar r2 = (-B+sqrt(D))/(2*A)
        scalar lo = min(r1,r2)
        scalar hi = max(r1,r2)
    }
    quietly summarize investor_green_z if e(sample)
    post `JN' ("`window'") (lo) (hi) (r(min)) (r(max)) (e(N)) (e(N_clust))
}

* Table 6 Panel B and Table 7: Pollute conditional slopes.
foreach window in full no2023 {
    local condition "sample_current == 1 & !missing(Pollute)"
    if "`window'" == "no2023" local condition "`condition' & year != 2023"
    reghdfe mca_current c.alcohol_culture##i.Pollute $CONTROLS if `condition', absorb(firm_id industry_year) vce(cluster firm_id)
    lincom alcohol_culture
    post `R' ("Table 7") ("Pollute `window'") ("Slope Pollute=0") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    lincom alcohol_culture + 1.Pollute#c.alcohol_culture
    post `R' ("Table 7") ("Pollute `window'") ("Slope Pollute=1") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    lincom 1.Pollute#c.alcohol_culture
    post `R' ("Table 7") ("Pollute `window'") ("Difference in slopes") (r(estimate)) (r(se)) (r(p)) (r(lb)) (r(ub)) (e(N)) (e(N_clust))
    ereturn list
    if "`window'" == "full" {
        margins Pollute, dydx(alcohol_culture) saving("$RESULTS/pollute_slopes_full.dta", replace)
        marginsplot, recast(scatter) recastci(rcap) yline(0, lpattern(dash)) title("AlcoholPOI slopes by Pollute") name(pollute_slopes, replace)
        graph export "$RESULTS/figures/pollute_conditional_slopes.png", replace width(2400)
    }
}

postclose `R'
postclose `JN'
use "$RESULTS/tables_6_to_7.dta", clear
sort table model contrast
export delimited using "$RESULTS/tables_6_to_7.csv", replace datafmt
use "$RESULTS/johnson_neyman.dta", clear
export delimited using "$RESULTS/johnson_neyman.csv", replace datafmt
log close
