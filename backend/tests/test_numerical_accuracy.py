import csv
import io
from pathlib import Path

from pypdf import PdfReader
from app import kiba_coverage, kiba_uncertainty, ml


ROOT = Path(__file__).resolve().parents[2]
HEADERS = {'X-Research-Client': 'web', 'Origin': 'http://testserver'}


def eligible_test_pair():
    index = kiba_coverage.load_index()
    with (ROOT / 'data/kiba_two_input/test.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            pair = kiba_coverage.pair_digest(row['drug_smiles'], row['protein_sequence'])
            if pair not in index['fit_pairs'] and pair not in index['validation_pairs']:
                return row
    raise AssertionError('No eligible KIBA test pair')


def test_kiba_accuracy_is_numerical_and_reported_in_pdf(client):
    row = eligible_test_pair()
    assert client.post('/api/auth/register', json={'name':'Accuracy researcher','email':'accuracy@example.org','password':'research-test-password-2026'}, headers=HEADERS).status_code == 201
    response = client.post('/api/predictions', json={'dataset':'kiba','smiles':row['drug_smiles'],'sequence':row['protein_sequence'],
        'drug_name':'Held-out example','protein_name':'Held-out target'}, headers=HEADERS)
    assert response.status_code == 201, response.text
    result = response.json()
    accuracy = result['provenance']['numerical_accuracy']
    assert accuracy['status'] == 'available'
    assert accuracy['kind'] == 'numerical_accuracy_within_tolerance'
    assert 0 < accuracy['estimated_accuracy_percent'] < 100
    assert accuracy['tolerance_kiba'] == 0.5
    assert accuracy['prediction_interval']['lower'] < result['score'] < accuracy['prediction_interval']['upper']
    assert accuracy['score_band_audit_pairs'] > 1000
    report = client.get(f"/api/predictions/{result['id']}/report")
    assert report.status_code == 200
    document = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(report.content)).pages)
    assert 'How accurate might this number be?' in document
    assert 'estimated within +/-0.5 KIBA units' in document


def test_accuracy_fails_closed_outside_calibrated_population():
    sample = eligible_test_pair()
    context = kiba_coverage.for_input(sample['drug_smiles'], sample['protein_sequence'])
    score = 11.5
    maximum = ml.inspect('kiba')['trained_max_lengths']
    assert kiba_uncertainty.for_prediction(score, sample['drug_smiles'], sample['protein_sequence'], context, maximum)['status'] == 'available'
    assert kiba_uncertainty.for_prediction(score, sample['drug_smiles'], sample['protein_sequence'],
        {**context,'pair_seen_in_fit':True}, maximum)['status'] == 'unavailable'
    assert kiba_uncertainty.for_prediction(score, sample['drug_smiles'], sample['protein_sequence'],
        {**context,'drug_seen_in_fit':False}, maximum)['status'] == 'unavailable'
