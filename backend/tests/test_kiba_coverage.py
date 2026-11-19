import csv
import io
from pypdf import PdfReader

from app import kiba_coverage, kiba_features, ml
from app.config import ROOT
from test_workflows import register, run


def first_row(filename):
    with (ROOT / 'data/kiba_two_input' / filename).open(newline='') as handle:
        return next(csv.DictReader(handle))


def test_exact_training_exposure_is_separate_from_accuracy(client):
    fit = first_row('train.csv')
    known = kiba_coverage.for_input(fit['drug_smiles'], fit['protein_sequence'])
    assert known['pair_seen_in_fit'] is True
    assert known['drug_seen_in_fit'] and known['protein_seen_in_fit']

    novel = kiba_coverage.for_input('CCO', 'ACDEFGHIKL')
    assert novel['status'] == 'available'
    assert not novel['drug_seen_in_fit'] or not novel['protein_seen_in_fit']
    assert 'confidence' in novel['limitations']

    audit = ml.inspect('kiba')['test_exposure']
    assert audit['test_pairs'] == 19709
    assert audit['unseen_drug_rows'] == audit['unseen_protein_rows'] == 0
    assert audit['exact_fit_pair_repeats'] + audit['exact_validation_pair_only_repeats'] + audit['new_pairs_of_seen_entities'] == audit['test_pairs']

    register(client)
    response = run(client, {'smiles':fit['drug_smiles'], 'sequence':fit['protein_sequence'],
                            'dataset':'kiba', 'drug_name':'Training input', 'protein_name':'Training target'})
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['provenance']['data_context']['pair_seen_in_fit'] is True
    pdf = client.get('/api/predictions/' + saved['id'] + '/report')
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert 'Training-data context' in text and 'This exact SMILES and sequence pair appeared in fitting data' in text
    assert '19,709 deployed-model test rows' in text


def test_repeated_kiba_features_are_cached_without_mutation():
    a = kiba_features.vector('ACDEFGHIKL' * 100, 'protein')
    b = kiba_features.vector('ACDEFGHIKL' * 100, 'protein')
    assert a is b and not a.flags.writeable
