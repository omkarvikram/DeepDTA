"""Post-hoc numerical accuracy estimates for the active two-input KIBA model."""
import bisect
import json
from functools import lru_cache
from .config import BACKEND, ROOT

ARTIFACT = BACKEND / 'models/kiba_two_input/uncertainty.json'
METADATA = BACKEND / 'models/kiba_two_input/metadata.json'


@lru_cache(maxsize=1)
def calibration():
    try:
        result = json.loads(ARTIFACT.read_text())
        model = json.loads(METADATA.read_text())
        if (result.get('format') != 'kiba-split-conformal-absolute-residual-v1' or
            result.get('model_sha256') != model['sha256'] or
            result.get('feature_version') != model['feature_version'] or
            result.get('test_split_sha256') != model['split_manifest']['splits']['test']['sha256'] or
            len(result.get('score_bins', [])) != 5 or len(result.get('score_bin_edges', [])) != 4):
            return None
        return result
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def for_prediction(score, smiles, sequence, context, trained_max_lengths):
    evidence = calibration()
    if evidence is None:
        return {'status': 'unavailable', 'reason': 'The uncertainty calibration is missing or does not match the active KIBA model.'}
    if context.get('status') != 'available':
        return {'status': 'unavailable', 'reason': 'Training-data exposure could not be verified.'}
    if context['pair_seen_in_fit'] or context['pair_seen_in_validation']:
        return {'status': 'unavailable', 'reason': 'This exact pair was used in fitting or model selection; the new-pair calibration does not apply.'}
    if not context['drug_seen_in_fit'] or not context['protein_seen_in_fit']:
        return {'status': 'unavailable', 'reason': 'The model has no held-out calibration pairs with unseen compounds or proteins.'}
    if len(smiles) > trained_max_lengths['smiles'] or len(sequence) > trained_max_lengths['protein']:
        return {'status': 'unavailable', 'reason': 'This input is longer than the calibration population.'}
    bucket = evidence['score_bins'][bisect.bisect_right(evidence['score_bin_edges'], score)]
    width = evidence['levels']['90']['half_width']
    return {
        'status': 'available',
        'kind': 'numerical_accuracy_within_tolerance',
        'estimated_accuracy_percent': round(100 * bucket['estimated_within_tolerance'], 1),
        'tolerance_kiba': evidence['accuracy_tolerance_kiba'],
        'score_band_calibration_pairs': bucket['calibration_pairs'],
        'score_band_audit_pairs': bucket['audit_pairs'],
        'score_band_audit_percent': round(100 * bucket['audit_within_tolerance'], 1),
        'prediction_interval': {'level_percent': 90, 'lower': score - width, 'upper': score + width,
                                'half_width': width, 'audit_coverage_percent': round(100 * evidence['levels']['90']['audit_coverage'], 1)},
        'scope': evidence['scope'],
        'limitations': evidence['limitations'],
    }
