import json
import pytest
import httpx
from aurora_model_catalog.grouped_catalog import build_index, validate_index, publish, sync_index, checksum

def entry(provider, ident, canonical=None, source='models_dev'):
    return {'identity':{'provider':provider,'api_id':ident,'canonical_id':canonical},
            'provenance':{'identity.canonical_id':{'source_type':source}} if canonical else {}}

def fixture():
    catalog={'schema_version':'2.0','checksum_sha256':'a'*64,'models':{
        'openai:gpt-x':entry('openai','gpt-x'),
        'platform:alias':entry('platform','alias','openai/gpt-x'),
        'platform:snapshot':entry('platform','snapshot','openai/gpt-x'),
        'litellm.alias:guess':entry('litellm.alias','guess','openai/gpt-x','litellm'),
        'provider:unknown':entry('provider','unknown','missing/model')}}
    canonical={'openai/gpt-x':{'id':'openai/gpt-x','name':'GPT X'}}
    return catalog,canonical

def test_groups_preserve_routes_and_only_explicit_canonical_matches():
    catalog, canonical=fixture(); result=build_index(catalog,canonical)
    group=result['groups']['openai/gpt-x']
    assert group['canonical_entry']=='openai:gpt-x'
    assert group['members']==['openai:gpt-x','platform:alias','platform:snapshot']
    assert result['ungrouped']==['litellm.alias:guess','provider:unknown']
    assert result['catalog_checksum_sha256']==catalog['checksum_sha256']
    assert validate_index(result,catalog)==result

def test_duplicate_entries_and_mismatched_catalog_are_rejected():
    catalog, canonical=fixture(); result=build_index(catalog,canonical)
    result['ungrouped'].append('openai:gpt-x')
    result['checksum_sha256']=checksum(result['groups'],result['ungrouped'])
    with pytest.raises(ValueError,match='duplicate'): validate_index(result,catalog)
    result=build_index(catalog,canonical); catalog['checksum_sha256']='b'*64
    with pytest.raises(ValueError,match='checksum'): validate_index(result,catalog)

def test_index_atomic_failure_preserves_previous(tmp_path,monkeypatch):
    catalog, canonical=fixture(); data=build_index(catalog,canonical); path=tmp_path/'index.json'
    publish(path,data); before=path.read_bytes()
    def fail(*args): raise OSError('replace failed')
    monkeypatch.setattr('aurora_model_catalog.grouped_catalog.os.replace',fail)
    with pytest.raises(OSError): publish(path,data)
    assert path.read_bytes()==before
    assert not list(tmp_path.glob('*.tmp'))

def test_source_failure_does_not_overwrite_existing(tmp_path,monkeypatch):
    catalog, canonical=fixture(); path=tmp_path/'index.json'; publish(path,build_index(catalog,canonical)); before=path.read_bytes()
    monkeypatch.setattr('aurora_model_catalog.grouped_catalog.load',lambda _:catalog)
    monkeypatch.setattr('aurora_model_catalog.grouped_catalog.time.sleep',lambda _:None)
    client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(503)))
    with pytest.raises(httpx.HTTPError): sync_index(tmp_path/'catalog.json',path,client)
    assert path.read_bytes()==before

def test_reproducible_checksum_and_schema():
    from pathlib import Path
    from aurora_model_catalog.grouped_catalog import GroupIndex
    catalog, canonical=fixture()
    assert build_index(catalog,canonical)['checksum_sha256']==build_index(catalog,canonical)['checksum_sha256']
    assert json.loads(Path('schema/model-catalog.groups.v1.schema.json').read_text())==GroupIndex.model_json_schema()
