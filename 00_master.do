version 18.0
clear all
set more off
set linesize 255

* Run this file from the Stata_Replication_Package directory.
global ROOT `"`c(pwd)'"'

capture mkdir "$ROOT/04_results"
capture mkdir "$ROOT/04_results/figures"
capture mkdir "$ROOT/04_results/samples"
capture mkdir "$ROOT/05_logs"

do "$ROOT/01_code/01_environment_and_data.do"
do "$ROOT/01_code/02_tables_3_to_5.do"
do "$ROOT/01_code/03_tables_6_to_7.do"
do "$ROOT/01_code/04_appendix_sensitivity.do"

display as result "Replication run completed. Review 05_logs and 04_results."
exit, clear
