import copy
import json
from pathlib import Path
import pytest
from aurora_model_catalog.clean_catalog import CleanCatalog, build_clean, validate_clean, publish
from aurora_model_catalog.grouped_catalog import build_index
from aurora_model_catalog.public_catalog import sync_public
from test_public_catalog import client

def sample(tmp_path, monkeypatch):
    monkeypatch.setattr('aurora_model_catalog.public_catalog.time.sleep',lambda _:None)
    cat=sync_public(tmp_path/'v2.json',client=client())
    canonical={'openai/model-x':{'id':'openai/model-x','name':'Model X'}}
    idx=build_index(cat,canonical)
    return cat,idx

def test_single_file_groups_without_losing_offers_or_platform_prices(tmp_path,monkeypatch):
    cat,idx=sample(tmp_path,monkeypatch)
    data=build_clean(cat,idx)
    model=data['models']['canonical:openai/model-x']
    assert set(model['offers'])=={'openai:model-x','openrouter:openai/model-x'}
    assert model['offers']['openai:model-x']['pricing']['standard']['input']==2
    assert model['offers']['openrouter:openai/model-x']['pricing']['standard']['input'] is None
    assert 'unresolved:litellm.openrouter:foo/bar' in data['models']
    assert len({k for v in data['models'].values() for k in v['offers']})==len(cat['models'])
    assert data['sources']['models_dev_canonical']['url']=='https://models.dev/catalog.json'
    assert validate_clean(data)['checksum_sha256']==data['checksum_sha256']

def test_clean_checksum_stable_and_detects_tampering(tmp_path,monkeypatch):
    cat,idx=sample(tmp_path,monkeypatch)
    a=build_clean(cat,idx);b=build_clean(cat,idx)
    assert a['checksum_sha256']==b['checksum_sha256']
    b['models']['canonical:openai/model-x']['display_name']='changed'
    with pytest.raises(ValueError,match='checksum'): validate_clean(b)

def test_mismatched_sources_fail(tmp_path,monkeypatch):
    cat,idx=sample(tmp_path,monkeypatch)
    idx['catalog_checksum_sha256']='0'*64
    with pytest.raises(ValueError,match='does not match'):build_clean(cat,idx)

def test_failure_does_not_replace_valid_file(tmp_path,monkeypatch):
    cat,idx=sample(tmp_path,monkeypatch);data=build_clean(cat,idx);path=tmp_path/'out.json'
    publish(path,data);before=path.read_bytes()
    def fail(*args):raise OSError('failed')
    monkeypatch.setattr('aurora_model_catalog.clean_catalog.os.replace',fail)
    with pytest.raises(OSError):publish(path,data)
    assert path.read_bytes()==before
    assert not list(tmp_path.glob('*.tmp'))

def test_published_schema_matches_code():
    assert json.loads(Path('schema/model-catalog.clean.v1.schema.json').read_text())==CleanCatalog.model_json_schema()
