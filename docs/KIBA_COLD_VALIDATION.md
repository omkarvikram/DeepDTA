# KIBA cold-split benchmark - 3 November 2026

Three **new, separately trained benchmark models** were evaluated on group-held-out KIBA pairs. They have the active KIBA model's feature transform and two-branch architecture, but **their weights are not the weights served by the website**. Results estimate the approach's ability to generalize to unseen entities; they are not per-prediction uncertainty estimates or direct metrics for the deployed model.

| Split | Test pairs | Unseen test drugs | Unseen test proteins | RMSE | Train-mean baseline RMSE | Spearman |
|---|---:|---:|---:|---:|---:|---:|
| Held-out pairs, deployed model | 19,709 | Not enforced | Not enforced | 0.4313 | 0.8244 | 0.8434 |
| Cold drug, separate model | 17,889 | 318 | 0 | 0.6518 | 0.8333 | 0.6303 |
| Cold protein, separate model | 19,026 | 0 | 35 | 0.6393 | 0.8149 | 0.6121 |
| Cold both, separate model | 1,215 | 194 | 24 | 0.7348 | 0.8569 | 0.4141 |

The pair-level baseline RMSE is sqrt(0.6796637685). All scores and errors are on the KIBA dataset scale, not pKd or nM. These differing splits should not be read as a controlled comparison of identical test cases; their target distributions and sample counts differ.

## What the deployed model's test actually covers

An exact-input audit of the frozen training, validation and test CSVs found that **all 19,709 deployed-model test rows use a drug SMILES and protein sequence already present in fitting data**. Of those rows, 121 repeat an exact fitting input pair and 28 more repeat a validation-only input pair. The other 19,560 rows are new combinations of familiar exact inputs; their RMSE is 0.4308 KIBA units. These categories are mutually exclusive. No test row assesses the deployed weights on an unseen exact drug or unseen exact protein. The three cold-split rows above come from separately trained weights, so their errors must not be assigned to a prediction from the deployed model.

`scripts/build_kiba_coverage_index.py` reproduces the audit and writes a label-free, SHA-256-based exposure index. The predictor and PDF use this index to state whether an individual input appeared during fitting or model selection. This checks exact representations only: alternate SMILES for the same molecule, related chemistry and homologous proteins are not recognized. Exposure is neither a confidence score nor evidence of biological accuracy.

## Protocol

`platform/scripts/evaluate_kiba_cold_splits.py` uses the supplied finite KIBA affinity matrix and canonical ligand/target sequences. It deterministically partitions *drug IDs* for cold drug, *protein IDs* for cold protein, and both ID sets for cold both. Validation and test groups do not enter training. Cold-both cross-partition pairs are excluded rather than moved into training. Train-only target mean and standard deviation set output scaling. Each model uses early stopping on its own validation set and is evaluated once on its test split. The output JSON records source hashes, seed, pair counts, overlap counts, epochs and metrics.

The benchmark uses the same supplied dataset as the active KIBA model, repartitioned. It does not establish independent external or biological validation. Similar molecules, homologous proteins, assay biases and source-data errors can remain even across ID-disjoint splits. The smaller cold-both test set also warrants caution. No calibrated uncertainty or confidence percentage is available.

## External validation status

No independently sourced, overlap-checked experimental benchmark is available in this project. Live ChEMBL lookups for selected predictions are literature comparisons, not an unbiased test set. A defensible external evaluation needs predeclared compound and exact target identifiers, assay endpoints/units and qualifiers, training-overlap audit, and reporting of rejected/unsupported pairs as well as error metrics. Until such data are evaluated, the website labels external validation as **not established**.

For an externally sourced exact-Kd CSV, `platform/scripts/audit_external_davis.py` provides a repeatable *literature audit*: it requires `smiles,sequence,standard_type,relation,kd_nM,activity_id,source_url`, rejects ineligible/unsupported rows, and reports coverage, RMSE, MAE and bias on eligible rows. Its output always marks `independent_validation: false` because the supplied Davis model's complete training set is unavailable. The CSV must be curated and assessed by a domain expert before its numbers are interpreted.
