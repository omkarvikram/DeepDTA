# KIBA numerical accuracy in the Affinity predictor

The displayed percentage estimates how often the **recorded KIBA dataset value** is within **±0.5 KIBA units** of the model's predicted score. It is not the chance that binding occurs. Exact equality is not a useful accuracy target for a continuous number, so the tolerance is part of the claim.

The deployed two-input KIBA model was frozen. Its supplied test fold has 19,709 rows. We removed 149 rows whose exact SMILES and protein sequence pair was also in fitting or model-selection data. Every remaining row had its individual drug and protein inputs represented separately in fitting data and was within the training length range. Exact pairs were assigned deterministically to calibration (9,706) or audit (9,854), keeping duplicate pairs together.

Calibration predictions were divided into five equal-frequency groups by predicted score. Within each group, the displayed percentage is the fraction whose absolute prediction error was at most 0.5 KIBA units. The separate audit group checks that estimate. The audit rates for the five groups were 91.8%, 92.6%, 88.8%, 86.5%, and 63.1%; the estimated rates shown in the app were 91.9%, 94.0%, 89.2%, 89.1%, and 63.9%. Higher predicted scores were less reliable on this split, so the app does not show one common percentage for all values.

The 90% prediction range uses the split-conformal absolute-residual quantile of the calibration group. Its half-width is 0.653 KIBA units; 89.6% of audit labels fell inside the corresponding ranges. This is **marginal coverage** under a similar-data assumption, not a guarantee for a single pair. The method follows [Angelopoulos and Bates, *A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification*](https://arxiv.org/abs/2107.07511).

The percentage and range are withheld when the exact pair appeared in fitting or model-selection data, when a drug or protein input was absent from fitting data, when an input exceeds the training length range, or when the calibration artifact does not match the active model. Davis has no defensible estimate because its supplied artifacts lack an independent, overlap-checked evaluation dataset.

This is post-hoc calibration on the **supplied KIBA test fold**, not independent external biological validation. The audit is a held-back part of that same fold, not a new laboratory study. It does not establish performance for novel compounds or novel targets. A reliable claim for those cases needs a frozen-model evaluation on independently measured, overlap-checked cold-drug and cold-protein sets, followed by assays for important pairs.

Source generation: `scripts/calibrate_kiba_uncertainty.py`. Runtime artifact: `models/kiba_two_input/uncertainty.json`. The original test predictions and split CSV are kept in the development folder, while the portable package contains the smaller checked calibration artifact.
