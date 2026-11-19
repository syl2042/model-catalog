import json
import httpx
from aurora_model_catalog.public_catalog import sync_public
from aurora_model_catalog.catalog import load

def client():
    def handler(request):
        if request.url.host == 'models.dev':
            return httpx.Response(200,json={'openai':{'models':{'model-x':{'name':'X','cost':{'input':2}}}},'anthropic':{'models':{}}, 'openrouter':{'models':{'openai/model-x':{'canonical_model_id':'openai/model-x','cost':{'input':99}}}}})
        if request.url.host == 'raw.githubusercontent.com':
            return httpx.Response(200,json={'model-x':{'litellm_provider':'openai','input_cost_per_token':0.000003},'foo/bar':{'litellm_provider':'openrouter','input_cost_per_token':0.000009},'friendly-alias':{'alias_of':'openrouter/foo/bar'}})
        return httpx.Response(503)
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_all_providers_and_only_direct_pricing(tmp_path,monkeypatch):
    monkeypatch.setattr('aurora_model_catalog.public_catalog.time.sleep',lambda _:None)
    path=tmp_path/'catalog.json'
    data=sync_public(path,client=client())
    assert data['models']['openai:model-x']['pricing']['standard']['input']==2
    assert data['models']['openrouter:openai/model-x']['pricing']['standard']['input'] is None
    assert data['models']['litellm.openrouter:foo/bar']['pricing']['standard']['input'] is None
    assert data['models']['litellm.alias:friendly-alias']['identity']['canonical_id']=='openrouter/foo/bar'
    assert data['sync_status']['status']=='partial'
    assert load(path)['checksum_sha256']==data['checksum_sha256']
    assert 'official_api' not in json.dumps(data)
    again=sync_public(path,client=client())
    assert again['checksum_sha256']==data['checksum_sha256']
    assert again['sync_status']['changes']=={'added':[],'removed':[],'changed':[]}

def test_direct_pricing_requires_creator_match():
    from aurora_model_catalog.public_catalog import direct_price
    assert direct_price('openai',{})
    assert not direct_price('openai',{'canonical_model_id':'another/model'})
    assert not direct_price('openrouter',{'canonical_model_id':'openrouter/model'})
