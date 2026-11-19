"""Lossless index of explicitly identified canonical models.

The public catalog is the source of truth for offer details. This companion
index contains references only, so no price or capability crosses providers.
"""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import load, now

CANONICAL_URL = 'https://models.dev/catalog.json'
GROUP_PATH = Path('public/model-catalog.groups.v1.json')
PUBLIC_PATH = Path('public/model-catalog.v2.json')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Group(Strict):
    display_name: str | None = None
    canonical_entry: str | None = None
    members: list[str] = Field(min_length=1)

class GroupIndex(Strict):
    schema_version: str = Field(pattern=r'^1\.0$')
    generated_at: str
    catalog_checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    canonical_source_url: str
    groups: dict[str, Group]
    ungrouped: list[str]

    @model_validator(mode='after')
    def check_uniqueness(self):
        seen = set()
        for group in self.groups.values():
            for member in group.members:
                if member in seen: raise ValueError('entry belongs to multiple groups')
                seen.add(member)
            if group.canonical_entry is not None and group.canonical_entry not in group.members:
                raise ValueError('canonical entry is not a group member')
        for member in self.ungrouped:
            if member in seen: raise ValueError('duplicate or grouped entry in ungrouped')
            seen.add(member)
        return self

VALIDATOR = Draft202012Validator(GroupIndex.model_json_schema())

def checksum(groups, ungrouped):
    payload = {'groups': groups, 'ungrouped': ungrouped}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()).hexdigest()

def validate_index(data, catalog=None):
    VALIDATOR.validate(data)
    parsed = GroupIndex.model_validate(data)
    normalized = parsed.model_dump(mode='json')
    if checksum(normalized['groups'], normalized['ungrouped']) != normalized['checksum_sha256']:
        raise ValueError('group index checksum mismatch')
    if catalog is not None:
        if catalog['schema_version'] != '2.0' or catalog['checksum_sha256'] != normalized['catalog_checksum_sha256']:
            raise ValueError('group index does not match catalog checksum')
        indexed = set(normalized['ungrouped'])
        for group in normalized['groups'].values(): indexed.update(group['members'])
        if indexed != set(catalog['models']): raise ValueError('group index does not cover the catalog exactly')
    return normalized

def load_index(path, catalog=None):
    with open(path, encoding='utf-8') as f: return validate_index(json.load(f), catalog)

def build_index(catalog, canonical_models):
    if catalog['schema_version'] != '2.0': raise ValueError('expected public V2 catalog')
    if not isinstance(canonical_models, dict) or not canonical_models:
        raise ValueError('empty or invalid canonical model source')
    # Only exact canonical keys asserted by Models.dev are accepted.
    canon = {k:v for k,v in canonical_models.items() if isinstance(k,str) and '/' in k and isinstance(v,dict) and v.get('id') == k}
    if not canon: raise ValueError('canonical model schema changed')
    members = {}
    for entry_key, model in catalog['models'].items():
        ident = model['identity']
        source = model.get('provenance',{}).get('identity.canonical_id',{})
        ref = ident.get('canonical_id')
        if source.get('source_type') == 'models_dev' and ref in canon:
            members.setdefault(ref,set()).add(entry_key)
    # Add the creator's exact entry only when the canonical source confirms the
    # exact provider/model reference and the entry does not point elsewhere.
    for ref in canon:
        provider, api_id = ref.split('/',1)
        entry_key = f'{provider}:{api_id}'
        model = catalog['models'].get(entry_key)
        if model and model['identity'].get('canonical_id') in (None, ref):
            members.setdefault(ref,set()).add(entry_key)
    groups = {}
    assigned = set()
    for ref, member_set in sorted(members.items()):
        keys=sorted(member_set)
        if not keys: continue
        name=canon[ref].get('name')
        provider, api_id = ref.split('/',1)
        canonical_entry = f'{provider}:{api_id}'
        groups[ref]={'display_name':name if isinstance(name,str) else None,
                     'canonical_entry':canonical_entry if canonical_entry in member_set else None,
                     'members':keys}
        assigned.update(member_set)
    ungrouped=sorted(set(catalog['models'])-assigned)
    data={'schema_version':'1.0','generated_at':now(),'catalog_checksum_sha256':catalog['checksum_sha256'],
          'checksum_sha256':checksum(groups,ungrouped), 'canonical_source_url':CANONICAL_URL,
          'groups':groups,'ungrouped':ungrouped}
    return validate_index(data,catalog)

def fetch_canonical(client):
    for attempt in range(3):
        try:
            response = client.get(CANONICAL_URL)
            response.raise_for_status()
            result=response.json()
            if not isinstance(result,dict) or not isinstance(result.get('models'),dict):
                raise ValueError('canonical source schema changed')
            return result['models']
        except (httpx.TimeoutException,httpx.NetworkError,httpx.HTTPStatusError) as exc:
            retry = not isinstance(exc,httpx.HTTPStatusError) or exc.response.status_code >= 500
            if not retry or attempt == 2: raise
            time.sleep(0.2*(attempt+1))

def publish(path, data):
    validate_index(data)
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp',delete=False) as f:
            temp=f.name
            json.dump(data,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
            f.write('\n'); f.flush(); os.fchmod(f.fileno(),0o644); os.fsync(f.fileno())
        os.replace(temp,path); temp=None
    finally:
        if temp and os.path.exists(temp): os.unlink(temp)

def sync_index(catalog_path=PUBLIC_PATH, index_path=GROUP_PATH, client=None):
    catalog=load(catalog_path)
    own=client is None
    if own: client=httpx.Client(timeout=httpx.Timeout(40,connect=10),follow_redirects=True)
    try: canonical=fetch_canonical(client)
    finally:
        if own: client.close()
    index=build_index(catalog,canonical)
    # Detect another writer before publication; consumers must also compare checksums.
    with open(catalog_path,encoding='utf-8') as f: current=json.load(f)
    if current.get('checksum_sha256') != catalog['checksum_sha256']:
        raise RuntimeError('catalog changed while building group index')
    publish(index_path,index)
    return index
