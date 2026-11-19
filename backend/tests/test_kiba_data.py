import numpy as np
from app.kiba_data import dataset
from test_workflows import register

def test_kiba_reference_scores_splits_missing_and_auth(client):
    assert client.get('/api/kiba/summary').status_code == 401
    register(client)
    meta = client.get('/api/kiba/summary').json()
    assert (meta['drugs'], meta['proteins'], meta['observed_pairs']) == (2111,229,118254)
    assert meta['train_pairs'] + meta['test_pairs'] == meta['observed_pairs']
    drugs, iso, proteins, values, rows, cols, splits, _ = dataset()
    record = client.get('/api/kiba/records', params={'split':'test','limit':1}).json()['records'][0]
    index = record['pair_index']
    assert record['score'] == values[rows[index],cols[index]]
    assert record['kind'] == 'recorded_dataset_value' and record['split'] == 'test'
    exact = client.get('/api/kiba/pair', params={'drug_id':record['drug_id'],'protein_id':record['protein_id']})
    assert exact.json() == record
    r,c = np.argwhere(np.isnan(values))[0]
    missing = client.get('/api/kiba/pair', params={'drug_id':list(drugs)[r],'protein_id':list(proteins)[c]}).json()
    assert missing['score'] is None and missing['status'] == 'unmeasured'
    assert client.get('/api/kiba/records?drug=not-a-compound').json()['total'] == 0
    assert client.get('/api/kiba/pair?drug_id=missing&protein_id=O00141').status_code == 404
    assert client.get('/api/kiba/records?offset=-1').status_code == 422
    assert client.get('/api/kiba/records?limit=101').status_code == 422
    assert client.get('/api/kiba/records?split=invalid').status_code == 422
    assert client.get('/api/dashboard').json()['used'] == 0
    assert client.get('/api/predictions').json() == []
