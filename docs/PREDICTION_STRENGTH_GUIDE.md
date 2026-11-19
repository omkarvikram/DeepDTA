# Predicted binding strength guide

The website labels each **predicted** affinity as weak, moderate, or strong. The label is a screening aid for that model's score. It is not an experimental result, confidence percentage, or proof of biological activity.

| Model | Weak | Moderate | Strong | Meaning |
| --- | --- | --- | --- | --- |
| Davis | pKd below 6 | pKd 6 to below 7 | pKd 7 or above | Larger predicted pKd implies lower Kd and stronger affinity. pKd 6 corresponds to 1 µM; pKd 7 to 100 nM. |
| KIBA | Score below 11.5 | Score 11.5 to 12.1 | Score above 12.1 | Relative ranges on the supplied KIBA score scale. A KIBA score cannot be converted to pKd, Kd, or nM. |

The [DeepDTA paper](https://doi.org/10.1093/bioinformatics/bty593) uses pKd 7 for the Davis benchmark cutoff and KIBA 12.1 for the KIBA benchmark cutoff. The pKd 6 boundary is a display choice to make a middle band. The KIBA 11.5 boundary is approximately the median of the supplied KIBA data; it is also a display choice. These categories are not universal pharmacological standards.

The source Davis measurements include a pKd 5 cap for weak measurements. Interpret predictions near that floor carefully. To establish real binding strength, measure the exact compound and target in a suitable assay, then compare the experimental result with the prediction.
