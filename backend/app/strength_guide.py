"""Plain-language screening guide for saved affinity predictions.

These cutoffs describe score ranges, not measured activity or clinical benefit.
The Davis pKd 7 and KIBA 12.1 benchmarks come from the DeepDTA paper;
the lower cutoffs make the three-band display usable and are labelled as such.
"""
import math

PAPER = 'https://doi.org/10.1093/bioinformatics/bty593'


def describe(dataset: str, score: float) -> dict:
    if not math.isfinite(score):
        return {'label': 'Unclassified', 'band': 'unknown', 'explanation': 'The score is not finite.',
                'basis': '', 'caution': 'No affinity interpretation is available.', 'source': PAPER}
    if dataset == 'davis':
        if score < 6:
            label, band = 'Weak', 'weak'
            explanation = 'Predicted pKd below 6 corresponds to an implied Kd above 1 µM.'
        elif score < 7:
            label, band = 'Moderate', 'moderate'
            explanation = 'Predicted pKd from 6 to below 7 corresponds to an implied Kd between 1 µM and 100 nM.'
        else:
            label, band = 'Strong', 'strong'
            explanation = 'Predicted pKd of 7 or higher corresponds to an implied Kd of 100 nM or lower.'
        return {'label': label, 'band': band, 'explanation': explanation,
                'basis': 'Screening guide: pKd 7 is a DeepDTA benchmark cutoff; pKd 6 separates the lower and middle display bands.',
                'caution': 'This is a model estimate, not measured Kd. Davis labels at pKd 5 may represent capped weaker measurements. Strength also depends on the target and assay.',
                'source': PAPER}
    if dataset == 'kiba':
        if score < 11.5:
            label, band = 'Weak (relative)', 'weak'
            explanation = 'Below the approximate median of the supplied KIBA scores (11.5).'
        elif score <= 12.1:
            label, band = 'Moderate (relative)', 'moderate'
            explanation = 'Near or above the dataset median, but not above the published 12.1 benchmark cutoff.'
        else:
            label, band = 'Strong (relative)', 'strong'
            explanation = 'Above the 12.1 KIBA cutoff used for benchmark classification in DeepDTA.'
        return {'label': label, 'band': band, 'explanation': explanation,
                'basis': 'Dataset-relative screening guide: 11.5 is approximately the supplied-data median; 12.1 is a published benchmark cutoff.',
                'caution': 'KIBA scores are not Kd, pKd, nM, or proof that a compound binds. Compare scores from the same model and verify experimentally.',
                'source': PAPER}
    return {'label': 'Unclassified', 'band': 'unknown', 'explanation': 'Unknown model scale.',
            'basis': '', 'caution': 'No affinity interpretation is available.', 'source': PAPER}
