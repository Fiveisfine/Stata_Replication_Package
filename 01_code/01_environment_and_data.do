version 18.0
clear all
set more off
capture log close _all
do "$ROOT/01_code/_config.do"
log using "$LOGS/01_environment_and_data.log", text replace

about
which reghdfe
which ftools

use "$PANEL", clear
describe
isid firm_id year
duplicates report firm_id year
assert inrange(year, 2012, 2023)

foreach v in mca_current alcohol_culture investor_green Pollute $CONTROLS {
    capture confirm variable `v'
    if _rc {
        display as error "Required variable missing: `v'"
        exit 111
    }
}

count if sample_current == 1
tabulate year if sample_current == 1, missing
misstable summarize mca_current alcohol_culture investor_green Pollute $CONTROLS

use "$RECON", clear
describe
isid firm_id year
foreach v in current csmar log_combined_5km Pollute v3_main_eligible $CONTROLS {
    capture confirm variable `v'
    if _rc {
        display as error "Required reconstructed-panel variable missing: `v'"
        exit 111
    }
}

log close
