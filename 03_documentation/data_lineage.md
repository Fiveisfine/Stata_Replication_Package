# Data lineage and redistribution notes

## Regression reproduction

The Stata master script reads the two derived panels in `02_data`. These panels reproduce the reported regressions and sensitivity checks without requiring access to the raw licensed inputs.

## MCA construction

MCA is the 0-100 TF-IDF-adjusted climate-related textual salience measure described in Section 3.2.1. The retained panel contains the resulting firm-year series. The upstream annual-report corpus, final versioned dictionary, Word2Vec model files, and original training logs are not present in this package, so the Stata archive reproduces models that use MCA but does not recreate MCA from source text.

## AlcoholPOI and ReconstructedPOI

AlcoholPOI is the historical supplier field used in the main analysis. ReconstructedPOI is built independently from available source files and is used only for sensitivity analysis. Historical supplier snapshots and processing manuals needed to reproduce AlcoholPOI exactly are not available. Audit files describing source coverage, coordinate declarations, deduplication, and 2023 province-year patterns are stored under `03_documentation/audits`.

## Licensed sources

Financial, governance, and some provider variables originate from licensed databases. They are identified in the source inventory and variable codebook. Researchers seeking the original releases must obtain authorization from the respective providers.
