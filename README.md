# Stata replication package

This package reproduces the regression and sensitivity analyses reported in the second-round revision of *Does the Local Alcohol-Related Environment Matter for Corporate Climate-Related Textual Salience? Evidence from Chinese Listed Firms*.

## Software used

- Stata/MP 18.0 for Windows, 64-bit, build 18.0.120
- `reghdfe` 6.13.1
- `ftools` 2.50.0

The exact Stata build and installed package locations are recorded in `05_logs/01_environment_and_data.log` when the package is run.

## Run instructions

1. Extract or copy the complete folder to a writable location.
2. Start Stata 18 and set the working directory to this folder.
3. Run `do 00_master.do`.
4. Check `05_logs` for the four execution logs and `04_results` for tables, estimation-sample indicators, margins, Johnson-Neyman roots, and figures.

All scripts use relative paths. No path needs to be edited when the directory structure is retained.

## Data files

- `02_data/analysis_panel.dta` is the retained firm-year panel used for the archived AlcoholPOI and MCA regressions. It contains the analysis variables, sample flags, controls, moderators, and identifiers needed for Tables 3-7.
- `02_data/reconstructed_poi_panel.dta` contains the common no-2023 panel used for the exploratory ReconstructedPOI sensitivity analyses.

The files are derived analysis panels. Licensed CSMAR inputs, raw annual-report text, and raw commercial provider records are not redistributed. Authorized users must obtain those materials from their respective providers if they wish to reconstruct the upstream measures.

## Script map

- `01_environment_and_data.do`: software versions, dependency checks, identifiers, duplicates, missingness, and annual sample coverage.
- `02_tables_3_to_5.do`: baseline models, sequential controls, cluster checks, alternative outcomes, no-2023 models, fixed effects, lag construction, high-zero cells, and `e(sample)` exports.
- `03_tables_6_to_7.do`: InvestorGreen and Pollute interaction models, conditional slopes, confidence intervals, margins, figures, and Johnson-Neyman roots.
- `04_appendix_sensitivity.do`: annual MCA scaling, leave-one-year influence, identical-sample AlcoholPOI/ReconstructedPOI comparisons, radii, categories, and leave-one-category-out checks.

`03_documentation/table_script_map.csv` links manuscript items to scripts and outputs.

## Reproducibility boundary

The Stata scripts reproduce the regressions from retained firm-year variables. The measurement-construction boundary is different:

- The retained MCA variable was constructed from annual and semiannual MD&A text following the procedure described in Section 3.2.1. The complete report corpus, versioned dictionary, embedding files, and original processing logs are not included in the retained archive.
- AlcoholPOI is a supplier-provided historical aggregate. The retained materials do not contain every annual snapshot, category crosswalk, coordinate conversion, geocoding diagnostic, or supplier deduplication rule.
- ReconstructedPOI is independently assembled from available POI files under documented rules. It is an exploratory sensitivity measure and is not an exact recreation of AlcoholPOI.

The scripts in `06_measurement_reconstruction_code` document the available POI reconstruction and audit workflow. They are not called by `00_master.do` because they require source files that cannot be redistributed.

## Expected principal results

The Stata run should reproduce the following retained estimates, subject only to display rounding:

- AlcoholPOI baseline: coefficient -0.0339, p = 0.077, N = 28,208.
- Table 4 common-sample sequence: -0.0579, -0.0577, -0.0574, and -0.0641, with N = 20,476 in every column. This archived comparison excludes 2019 and requires nonfinancial/non-ST status, available POI source data, and complete city, regulation, trust, and commercial-POI controls.
- AlcoholPOI excluding 2023: coefficient -0.0077, p = 0.798, N = 23,707.
- InvestorGreen interaction, full available sample: 0.0361, p = 0.023.
- InvestorGreen interaction excluding 2023: 0.0211, p = 0.307, N = 11,088.
- Pollute difference in slopes, full sample: 0.1750, p < 0.001.
- Pollute difference in slopes, excluding 2023: 0.1787, p < 0.001.

If these values are not reproduced, inspect the corresponding log before using any output.
