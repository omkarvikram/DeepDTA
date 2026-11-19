import json
from app import advanced, docking
from fastapi import HTTPException

H={'X-Research-Client':'web','Origin':'http://testserver'}


def test_name_lookup_returns_source_pdb_entry_without_docking_it(client,monkeypatch):
    registered=client.post('/api/auth/register',json={'name':'Structure tester',
        'email':'structure-lookup@example.org','password':'research-test-password-2026'},headers=H)
    assert registered.status_code==201
    class Reply:
        status_code=200
        def __init__(self,value): self.value=value
        def json(self): return self.value
    def source(url,params=None):
        if url.startswith('https://search.rcsb.org/'):
            request=json.loads(params['json'])
            assert request['query']['parameters']['value']=='ABL kinase'
            assert request['return_type']=='entry'
            return Reply({'total_count':1,'result_set':[{'identifier':'1IEP','score':1.0}]})
        assert url=='https://data.rcsb.org/graphql'
        assert '1IEP' in params['query']
        return Reply({'data':{'entries':[{'rcsb_id':'1IEP',
            'struct':{'title':'ABL kinase in complex with an inhibitor'},
            'exptl':[{'method':'X-RAY DIFFRACTION'}],
            'rcsb_entry_info':{'resolution_combined':[2.1]}}]}})
    monkeypatch.setattr(advanced.search,'fetch',source)
    response=client.get('/api/structures/search',params={'q':'ABL kinase'})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['total']==1
    assert result['records'][0]['id']=='1IEP'
    assert result['records'][0]['coordinates'].endswith('/1IEP.cif')
    assert 'not prepared docking' in result['note']
    assert client.get('/api/structures/search',params={'q':' '}).status_code==422


def test_pubchem_3d_ligand_download_is_labeled_as_source(client,monkeypatch):
    registered=client.post('/api/auth/register',json={'name':'Ligand tester',
        'email':'ligand-lookup@example.org','password':'research-test-password-2026'},headers=H)
    assert registered.status_code==201
    def source(url,params=None):
        assert url.endswith('/compound/cid/2244/SDF')
        assert params=={'record_type':'3d'}
        class Reply: content=b'2244\n  PubChem3D\n\nM  END\n$$$$\n'
        return Reply()
    monkeypatch.setattr(docking.search,'fetch',source)
    response=client.get('/api/docking/ligand-3d/2244')
    assert response.status_code==200
    assert response.content.startswith(b'2244')
    assert 'pubchem-2244-3d.sdf' in response.headers['content-disposition']
    assert response.headers['x-structure-source']=='PubChem CID 2244'
    def missing(url,params=None): raise HTTPException(404,'No matching database record found.')
    monkeypatch.setattr(docking.search,'fetch',missing)
    unavailable=client.get('/api/docking/ligand-3d/2244')
    assert unavailable.status_code==404
    assert 'no 3D conformer' in unavailable.json()['detail']
