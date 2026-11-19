"""PDFs must use owned server results and source-backed structural facts."""
import io

from pypdf import PdfReader

from app import advanced
from test_workflows import H, INPUT, register, run


def pdf_text(response):
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    return '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


def test_prediction_report_explains_uses_and_next_steps(client):
    register(client)
    record = run(client).json()
    text = pdf_text(client.get(f"/api/predictions/{record['id']}/report"))
    assert 'What this value means' in text
    assert 'What you can do with it' in text
    assert 'Limits and how to address them' in text
    assert 'Measure Kd' in text
    assert 'No calibrated confidence interval' in text


def test_mutation_and_optimisation_reports_use_saved_owned_predictions(client):
    register(client)
    mutation = client.post('/api/engineering', json={
        'smiles': INPUT['smiles'], 'sequence': INPUT['sequence'], 'mutations': ['A1V']}, headers=H).json()
    path = f"/api/engineering/report?original_id={mutation['original_id']}&mutant_id={mutation['mutant_id']}"
    text = pdf_text(client.get(path))
    assert 'Protein mutation comparison' in text and 'A1V' in text
    assert 'Folding and function were not checked' in text
    assert mutation['original_id'] in text and mutation['mutant_id'] in text
    bad = client.get(f"/api/engineering/report?original_id={mutation['original_id']}&mutant_id={mutation['original_id']}")
    assert bad.status_code == 422

    result = client.post('/api/optimisation', json={
        'sequence': INPUT['sequence'], 'candidates': ['CCO', 'invalid']}, headers=H).json()
    ids = [row['prediction_id'] for row in result['results'] if row.get('prediction_id')]
    text = pdf_text(client.post('/api/optimisation/report', json={'ids': ids}, headers=H))
    assert 'Drug candidate comparison' in text and 'What the ranking means' in text
    assert 'Rejected input rows have no score' in text
    assert 'invalid' not in text
    assert client.post('/api/optimisation/report', json={'ids': ids + ids}, headers=H).status_code == 422

    client.post('/api/auth/logout', headers=H)
    assert client.get(path).status_code == 401
    register(client, 'other-researcher@example.org')
    assert client.get(path).status_code == 404
    assert client.post('/api/optimisation/report', json={'ids': ids}, headers=H).status_code == 404


def test_structure_report_names_source_compound_and_handles_no_ligand(client, monkeypatch):
    register(client)

    class SourceResponse:
        def __init__(self, body=None, text='ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00 20.00           N'):
            self.body = body or {}
            self.text = text
            self.content = text.encode()

        def json(self):
            return self.body

    def fake_fetch(url, *args, **kwargs):
        if url.endswith('/1IEP.pdb') or url.endswith('/1CRN.pdb'):
            return SourceResponse()
        if url.endswith('/entry/1IEP'):
            return SourceResponse({'struct': {'title': 'ABL kinase with STI-571'},
                'exptl': [{'method': 'X-RAY DIFFRACTION'}],
                'rcsb_entry_container_identifiers': {'polymer_entity_ids': ['1'], 'non_polymer_entity_ids': ['2']}})
        if url.endswith('/entry/1CRN'):
            return SourceResponse({'struct': {'title': 'Crambin structure'},
                'exptl': [{'method': 'X-RAY DIFFRACTION'}],
                'rcsb_entry_container_identifiers': {'polymer_entity_ids': [], 'non_polymer_entity_ids': []}})
        if url.endswith('/polymer_entity/1IEP/1'):
            return SourceResponse({'rcsb_polymer_entity': {'pdbx_description': 'ABL kinase'}})
        if url.endswith('/nonpolymer_entity/1IEP/2'):
            return SourceResponse({'pdbx_entity_nonpoly': {'comp_id': 'STI', 'name': 'STI-571'}})
        if url.endswith('/chemcomp/STI'):
            return SourceResponse({'chem_comp': {'formula': 'C29 H31 N7 O', 'type': 'non-polymer'}})
        if url.endswith('/drugbank/STI'):
            return SourceResponse({'drugbank_container_identifiers': {'drugbank_id': 'DB00619'},
                'drugbank_info': {'name': 'Imatinib',
                                  'drug_categories': ['Bcr-Abl Tyrosine Kinase Inhibitors'],
                                  'indication': 'Imatinib is indicated for treatment of chronic myeloid leukemia.'}})
        raise AssertionError(url)

    monkeypatch.setattr(advanced.search, 'fetch', fake_fetch)
    text = pdf_text(client.get('/api/structures/1IEP/report'))
    assert 'Imatinib (STI)' in text and 'Deposited chemical name: STI-571' in text
    assert 'Bcr-Abl Tyrosine Kinase Inhibitors' in text
    assert 'Database-listed use' in text and 'chronic myeloid leukemia' in text
    assert 'This is not a docking prediction' in text
    empty = pdf_text(client.get('/api/structures/1CRN/report'))
    assert 'No named non-polymer compound' in empty
