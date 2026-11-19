"""A single self-contained catalog, grouped without merging distinct offers."""
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import load, now
from .grouped_catalog import load_index
from .schema import ModelV2

CLEAN_PATH = Path('public/model-catalog.json')
PUBLIC_PATH = Path('public/model-catalog.v2.json')
GROUP_PATH = Path('public/model-catalog.groups.v1.json')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class CleanModel(Strict):
    grouping: Literal['canonical', 'unresolved']
    canonical_ref: str | None = None
    display_name: str | None = None
    canonical_entry: str | None = None
    offers: dict[str, ModelV2] = Field(min_length=1)

class CleanCatalog(Strict):
    schema_version: Literal['clean-1.0'] = 'clean-1.0'
    generated_at: datetime
    checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    catalog_version: str
    source_catalog_checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    group_index_checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    sources: dict[str, dict]
    sync_status: dict
    models: dict[str, CleanModel]

    @model_validator(mode='after')
    def consistency(self):
        seen=set()
        for model_key, model in self.models.items():
            if model.grouping == 'canonical':
                if not model.canonical_ref or model_key != 'canonical:'+model.canonical_ref:
                    raise ValueError('invalid canonical group key')
            elif model.canonical_ref is not None or len(model.offers) != 1:
                raise ValueError('unresolved group must contain exactly one offer')
            elif model_key != 'unresolved:'+next(iter(model.offers)):
                raise ValueError('invalid unresolved group key')
            if model.canonical_entry is not None and model.canonical_entry not in model.offers:
                raise ValueError('canonical entry is absent')
            for offer_key, offer in model.offers.items():
                if offer_key != f'{offer.identity.provider}:{offer.identity.api_id}':
                    raise ValueError('offer key does not match identity')
                if offer_key in seen: raise ValueError('offer appears more than once')
                offer.properties_have_provenance()
                seen.add(offer_key)
        return self

VALIDATOR = Draft202012Validator(CleanCatalog.model_json_schema())

def checksum(models):
    semantic={}
    for key, model in models.items():
        semantic[key]={k:v for k,v in model.items() if k!='offers'}
        semantic[key]['offers']={offer_key:{k:v for k,v in offer.items() if k!='provenance'} for offer_key,offer in model['offers'].items()}
    data=json.dumps(semantic,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()

def validate_clean(data):
    VALIDATOR.validate(data)
    normalized=CleanCatalog.model_validate(data).model_dump(mode='json')
    if checksum(normalized['models']) != normalized['checksum_sha256']:
        raise ValueError('clean catalog checksum mismatch')
    if normalized['catalog_version'] != normalized['checksum_sha256'][:16]:
        raise ValueError('catalog version does not match checksum')
    return normalized

def load_clean(path):
    with open(path,encoding='utf-8') as f:return validate_clean(json.load(f))

def build_clean(catalog,index):
    if catalog['schema_version'] != '2.0' or index['catalog_checksum_sha256'] != catalog['checksum_sha256']:
        raise ValueError('group index does not match catalog')
    models={}
    for ref,group in sorted(index['groups'].items()):
        models['canonical:'+ref]={'grouping':'canonical','canonical_ref':ref,'display_name':group['display_name'],
            'canonical_entry':group['canonical_entry'], 'offers':{k:catalog['models'][k] for k in group['members']}}
    for key in index['ungrouped']:
        offer=catalog['models'][key]
        models['unresolved:'+key]={'grouping':'unresolved','canonical_ref':None,'display_name':offer['identity']['display_name'],
                                   'canonical_entry':None,'offers':{key:offer}}
    models=dict(sorted(models.items()))
    digest=checksum(models)
    return {'schema_version':'clean-1.0','generated_at':now(),'checksum_sha256':digest,'catalog_version':digest[:16],
            'source_catalog_checksum_sha256':catalog['checksum_sha256'],'group_index_checksum_sha256':index['checksum_sha256'],
            'sources':{**catalog['sources'], 'models_dev_canonical': {'url':index['canonical_source_url'], 'status':'ok', 'observed_at':index['generated_at']}},
            'sync_status':catalog['sync_status'],'models':models}

def publish(path,data):
    validate_clean(data)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True); temp=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp',delete=False) as f:
            temp=f.name
            json.dump(data,f,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False)
            f.write('\n'); f.flush(); os.fchmod(f.fileno(),0o644); os.fsync(f.fileno())
        os.replace(temp,path);temp=None
    finally:
        if temp and os.path.exists(temp):os.unlink(temp)

def sync_clean(catalog_path=PUBLIC_PATH,index_path=GROUP_PATH,clean_path=CLEAN_PATH):
    catalog=load(catalog_path)
    index=load_index(index_path,catalog)
    result=build_clean(catalog,index)
    # Detect concurrent source changes; daily synchronization also takes a lock.
    with open(catalog_path,encoding='utf-8') as f: current_catalog=json.load(f)
    with open(index_path,encoding='utf-8') as f: current_index=json.load(f)
    if current_catalog['checksum_sha256']!=catalog['checksum_sha256'] or current_index['checksum_sha256']!=index['checksum_sha256']:
        raise RuntimeError('source data changed while building clean catalog')
    publish(clean_path,result)
    return result
