import json
import os
from pathlib import Path
import httpx
import jsonschema
import pytest
from aurora_model_catalog import catalog
from aurora_model_catalog.normalization import blank, key, apply, lite_values, models_dev_values
from aurora_model_catalog.schema import Catalog, Model

SOURCE = {'url':'https://example.com/data','source_type':'models_dev','observed_at':'2026-01-01T00:00:00Z','published_at':None}

def fake_client(fail=False):
    def handler(req):
        if fail: raise httpx.ConnectError('offline', request=req)
        if req.url.host == 'models.dev':
            return httpx.Response(200,json={'openai':{'models':{'alpha':{'name':'Alpha','limit':{'context':100},'cost':{'input':2}}}},'anthropic':{'models':{'beta':{'name':'Beta'}}}})
        if req.url.host == 'raw.githubusercontent.com':
            return httpx.Response(200,json={'alpha':{'litellm_provider':'openai','max_input_tokens':200,'input_cost_per_token':0.000003,'input_cost_per_token_batches':0.000001,'supports_vision':True},'beta':{'litellm_provider':'anthropic'}})
        if req.url.host == 'api.openai.com': return httpx.Response(200,json={'data':[{'id':'alpha'}]})
        return httpx.Response(200,json={'data':[{'id':'beta','display_name':'Official Beta'}], 'has_more':False})
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_identity_is_exact_and_unknown():
    assert key('openai','GPT-x-2026') == 'openai:GPT-x-2026'
    with pytest.raises(ValueError): key('openai',' x ')
    m=blank('openai','foo-20260101')
    assert m['identity']['canonical_id'] is None
    assert m['limits']['context_window_tokens'] is None
    assert m['tools']['function_calling'] is None
    assert m['identity']['status'] == 'unknown'

def test_alias_only_explicit():
    m=blank('anthropic','alias')
    apply(m,{'identity.canonical_id':'snapshot','identity.aliases':['alias']},SOURCE,[])
    assert Model.model_validate(m).identity.canonical_id == 'snapshot'
    assert key('anthropic','alias') != key('anthropic','snapshot')

def test_source_priority_conflict_and_null():
    m=blank('openai','a'); conflicts=[]
    apply(m,{'limits.context_window_tokens':10},SOURCE,conflicts)
    official={**SOURCE,'source_type':'official_api'}
    apply(m,{'limits.context_window_tokens':20},official,conflicts)
    apply(m,{'limits.context_window_tokens':None},SOURCE,conflicts)
    apply(m,{'limits.context_window_tokens':30},SOURCE,conflicts)
    assert m['limits']['context_window_tokens'] == 20
    assert len(conflicts)==2

def test_prices_standard_and_unknown_conditional():
    values=lite_values({'input_cost_per_token':0.000002,'input_cost_per_token_batches':0.000001,'cache_read_input_token_cost':0.0000002})
    assert values['pricing.standard.input']==2
    assert values['pricing.standard.cache_read']==0.2
    assert len(values)==2
    assert models_dev_values({'cost':{'input':2}})['pricing.standard.input']==2

def test_sync_validate_changes_and_partial(tmp_path):
    path=tmp_path/'catalog.json'
    first=catalog.sync(path,client=fake_client(),env={})
    assert first['sync_status']['status']=='partial'
    assert first['sources']['openai_api']['status']=='skipped_missing_key'
    assert first['models']['openai:alpha']['limits']['context_window_tokens']==100
    assert first['models']['openai:alpha']['pricing']['standard']['input']==2
    assert first['sync_status']['conflicts']
    second=catalog.sync(path,client=fake_client(),env={})
    assert second['checksum_sha256']==first['checksum_sha256']
    assert second['sync_status']['changes']=={'added':[],'removed':[],'changed':[]}
    assert catalog.load(path)['models']['anthropic:beta']['identity']['display_name']=='Beta'
    jsonschema.validate(json.loads(path.read_text()),json.loads(Path('schema/model-catalog.v1.schema.json').read_text()))
    assert catalog.changes(first,second)=={'added':[],'removed':[],'changed':[]}

def test_official_api_priority(tmp_path):
    data=catalog.sync(tmp_path/'a.json',client=fake_client(),env={'ANTHROPIC_API_KEY':'hidden'})
    assert data['models']['anthropic:beta']['identity']['display_name']=='Official Beta'
    assert data['models']['anthropic:beta']['provenance']['identity.display_name']['source_type']=='official_api'
    assert 'hidden' not in json.dumps(data)

def test_network_error_keeps_existing(tmp_path,monkeypatch):
    monkeypatch.setattr(catalog.time,'sleep',lambda _:None)
    path=tmp_path/'a.json'; first=catalog.sync(path,client=fake_client(),env={}); content=path.read_bytes()
    with pytest.raises(RuntimeError): catalog.sync(path,client=fake_client(True),env={})
    assert path.read_bytes()==content
    assert 'openai:alpha' in first['models']

def test_discovery_failure_preserves_model(tmp_path,monkeypatch):
    path=tmp_path/'a.json'; catalog.sync(path,client=fake_client(),env={})
    def handler(req):
        if req.url.host in ('api.openai.com','models.dev'): return httpx.Response(503)
        return httpx.Response(200,json={'beta':{'litellm_provider':'anthropic'}})
    monkeypatch.setattr(catalog.time,'sleep',lambda _:None)
    result=catalog.sync(path,client=httpx.Client(transport=httpx.MockTransport(handler)),env={'OPENAI_API_KEY':'key'})
    assert 'openai:alpha' in result['models']
    assert result['models']['openai:alpha']['identity']['status']=='unknown'

def test_atomic_failure(tmp_path,monkeypatch):
    path=tmp_path/'a.json'; data=catalog.sync(path,client=fake_client(),env={}); content=path.read_bytes()
    def fail(*args): raise OSError('failed')
    monkeypatch.setattr(catalog.os,'replace',fail)
    with pytest.raises(OSError): catalog.atomic_publish(path,data)
    assert path.read_bytes()==content
    assert list(tmp_path.glob('*.tmp'))==[]

def test_tamper_detected(tmp_path):
    path=tmp_path/'a.json'; data=catalog.sync(path,client=fake_client(),env={})
    data['models']['openai:alpha']['identity']['display_name']='changed'
    with pytest.raises(ValueError,match='checksum'): catalog.validate(data)

@pytest.mark.integration
def test_live(tmp_path):
    if not os.getenv('AURORA_LIVE_TEST'): pytest.skip('set AURORA_LIVE_TEST=1')
    assert catalog.sync(tmp_path/'catalog.json')['models']

def test_official_anthropic_fields():
    from aurora_model_catalog.normalization import anthropic_values
    item={'lifecycle':'deprecated', 'line':'opus', 'max_input_tokens':200000, 'max_tokens':64000,
          'capabilities':{'image_input':{'supported':False}, 'thinking':{'supported':True,'types':{'adaptive':{'supported':True}, 'disabled':{'supported':False}}}, 'effort':{'low':{'supported':True},'high':{'supported':True}}}}
    values=anthropic_values(item)
    assert values['identity.status']=='deprecated'
    assert values['limits.context_window_tokens']==200000
    assert values['input_modalities.images'] is False
    assert values['reasoning.effort_levels']==['low','high']
    assert values['reasoning.can_disable'] is False
    assert values['reasoning.api']=='messages'

def test_conditional_rates_do_not_become_standard():
    values=lite_values({'input_cost_per_token':0.000002, 'input_cost_per_token_above_100k_tokens':0.000004,'output_cost_per_token_above_100k_tokens':0.000008,'input_cost_per_token_above_100k_tokens_batches':0.000001})
    assert values['pricing.standard.input']==2
    assert values['pricing.variants'][0]['threshold_tokens']==100000
    assert values['pricing.variants'][0]['rates']['input']==4
    assert values['pricing.variants'][0]['service_tier']=='standard'

def test_explicit_canonical_relation():
    values=models_dev_values({'canonical_model_id':'openai/snapshot'})
    assert values['_canonical_ref']=='openai/snapshot'

def test_persistent_credentials_and_environment_priority(tmp_path):
    path=tmp_path/'credentials.env'
    path.write_text('OPENAI_API_KEY="stored-openai"\nANTHROPIC_API_KEY=stored-anthropic\nOTHER=ignored\n')
    env=catalog.credentials_environment({'AURORA_CONFIG_FILE':str(path), 'OPENAI_API_KEY':'environment-openai'})
    assert env['OPENAI_API_KEY']=='environment-openai'
    assert env['ANTHROPIC_API_KEY']=='stored-anthropic'
    assert 'OTHER' not in env
    assert catalog.credentials_environment({'AURORA_CONFIG_FILE':str(tmp_path/'missing')}).get('OPENAI_API_KEY') is None

def test_sync_automatically_loads_persistent_credentials(tmp_path, monkeypatch):
    path=tmp_path/'credentials.env'
    path.write_text('ANTHROPIC_API_KEY=stored-secret\n')
    monkeypatch.setenv('AURORA_CONFIG_FILE', str(path))
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    result=catalog.sync(tmp_path/'catalog.json', client=fake_client())
    assert result['sources']['anthropic_api']['status']=='ok'
    assert result['models']['anthropic:beta']['identity']['display_name']=='Official Beta'
    assert 'stored-secret' not in json.dumps(result)
