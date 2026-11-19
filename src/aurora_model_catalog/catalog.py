import hashlib
import json
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import ValidationError
from .schema import Catalog, Model, PublicCatalogV2
from jsonschema import Draft202012Validator

SCHEMA_VALIDATOR = Draft202012Validator(Catalog.model_json_schema())
from .normalization import apply, blank, key, lite_values, models_dev_values, anthropic_values, expand_scoped_provenance
from .sources import anthropic, litellm, models_dev, openai, official_docs
from .normalization import PRIORITY

DEFAULT_PATH = Path('output/model-catalog.v1.json')

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def checksum(models):
    # Observation times and sync metadata do not constitute a change for consumers.
    semantic = {k: {p:v for p,v in m.items() if p != 'provenance'} for k,m in models.items()}
    data = json.dumps(semantic, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()

def validate(data):
    if data.get('schema_version') == '2.0':
        Draft202012Validator(PublicCatalogV2.model_json_schema()).validate(data)
        parsed = PublicCatalogV2.model_validate(data)
    else:
        SCHEMA_VALIDATOR.validate(data)
        parsed = Catalog.model_validate(data)
    normalized = parsed.model_dump(mode='json')
    if checksum(normalized['models']) != data['checksum_sha256']:
        raise ValueError('catalog checksum mismatch')
    return normalized

def load(path):
    with open(path, encoding='utf-8') as f: return validate(json.load(f))

def atomic_publish(path, data):
    validate(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.'+path.name+'.', suffix='.tmp', delete=False) as f:
            tmp = f.name
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            f.write('\n'); f.flush(); os.fchmod(f.fileno(), 0o644); os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp): os.unlink(tmp)

def changes(old, new):
    a = old.get('models', {}) if old else {}
    b = new['models']
    removed = sorted(set(a)-set(b)); added = sorted(set(b)-set(a))
    changed = sorted(k for k in set(a)&set(b) if checksum({k:a[k]}) != checksum({k:b[k]}))
    return {'added': added, 'removed': removed, 'changed': changed}


def merge_variants(model, incoming, source, conflicts):
    """Reconcile each conditional rate independently, preserving its source."""
    variants = model['pricing']['variants']
    provenance = model['provenance']
    old_default = provenance.pop('pricing.variants', None)
    keyed = {}
    for index, variant in enumerate(variants):
        ident = (variant['name'], variant['service_tier'], variant['threshold_tokens'], variant['cache_ttl_seconds'])
        keyed[ident] = (variant, provenance.pop(f'pricing.variants.{index}', old_default))
    for variant in incoming:
        ident = (variant['name'], variant['service_tier'], variant['threshold_tokens'], variant['cache_ttl_seconds'])
        current, origin = keyed.get(ident, (None, None))
        if current is not None and origin and current != variant:
            conflicts.append({'model':key(model['identity']['provider'], model['identity']['api_id']), 'property':'pricing.variants', 'existing':current, 'incoming':variant, 'existing_source':origin['source_type'], 'incoming_source':source['source_type']})
        if not origin or PRIORITY[source['source_type']] <= PRIORITY[origin['source_type']]:
            if current == variant and origin and origin['source_type'] == source['source_type']:
                continue
            keyed[ident] = (variant, source)
    model['pricing']['variants'] = []
    for _, (variant, origin) in sorted(keyed.items(), key=lambda x: str(x[0])):
        index = len(model['pricing']['variants'])
        model['pricing']['variants'].append(variant)
        if origin: provenance[f'pricing.variants.{index}'] = origin

def credentials_environment(environ=None):
    """Read the persistent credentials for every sync; explicit environment wins."""
    environ = os.environ if environ is None else environ
    configured = environ.get('AURORA_CONFIG_FILE')
    path = Path(configured).expanduser() if configured else Path.home() / '.config/aurora-model-catalog/credentials.env'
    result = {k: v for k, v in dotenv_values(path, interpolate=False).items()
              if k in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY') and v is not None}
    result.update(environ)
    return result

def sync(path=DEFAULT_PATH, client=None, env=None):
    path = Path(path); env = credentials_environment() if env is None else env
    previous = None
    if path.exists():
        # Never overwrite an invalid existing catalog without an explicit repair.
        previous = load(path)
    models = deepcopy(previous['models']) if previous else {}
    expand_scoped_provenance(models)
    timestamp = now(); sources = {}; conflicts = []; successes = 0
    owned_client = client is None
    if owned_client: client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)
    def fetch(name, module, *args):
        nonlocal successes
        for attempt in range(3):
            try:
                result = module.fetch(client, *args)
                sources[name] = {'url':module.URL, 'status':'ok', 'observed_at':timestamp}
                successes += 1
                return result
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                # Do not include response bodies, headers, keys or exception messages.
                if attempt < 2 and (isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500):
                    time.sleep(0.2 * (attempt+1)); continue
                code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                sources[name] = {'url':module.URL, 'status':'error', 'error':type(exc).__name__, 'http_status':code, 'observed_at':timestamp}
                return None
    def record(provider, identifier, values, name, module, published_at=None, variants=None):
        ident = key(provider, identifier)
        is_new = ident not in models
        if is_new: models[ident] = blank(provider, identifier)
        source = {'url': module.URL, 'source_type':name, 'observed_at':timestamp, 'published_at':published_at}
        if is_new:
            models[ident]['provenance']['identity.provider'] = source
            models[ident]['provenance']['identity.api_id'] = source
        apply(models[ident], values, source, conflicts)
        if variants:
            merge_variants(models[ident], variants, source, conflicts)
    try:
        for provider, module, variable in [('openai',openai,'OPENAI_API_KEY'), ('anthropic',anthropic,'ANTHROPIC_API_KEY')]:
            if not env.get(variable):
                sources[provider+'_api'] = {'url':module.URL, 'status':'skipped_missing_key', 'observed_at':timestamp}
                continue
            data = fetch(provider+'_api', module, env[variable])
            if data is not None:
                for item in data:
                    values = anthropic_values(item) if provider == 'anthropic' else {}
                    # The listing is account-scoped, so its presence does not imply global status.
                    record(provider, item['id'], values, 'official_api', module)
        class DocSource:
            def __init__(self, url, parser): self.URL, self.parser = url, parser
            def fetch(self, http): return self.parser(official_docs.markdown(http, self.URL))
        openai_docs = DocSource(official_docs.OPENAI_URL, official_docs.parse_openai)
        openai_prices = fetch('openai_docs_pricing', openai_docs)
        if openai_prices is not None:
            for identifier, values in openai_prices.items():
                record('openai', identifier, values, 'official_docs', openai_docs)
        anthropic_overview = DocSource(official_docs.ANTHROPIC_MODELS_URL, official_docs.parse_anthropic_models)
        overview = fetch('anthropic_docs_models', anthropic_overview)
        if overview:
            names, details = overview
            for identifier, values in details.items():
                record('anthropic', identifier, values, 'official_docs', anthropic_overview)
            anthropic_docs = DocSource(official_docs.ANTHROPIC_URL, lambda text: official_docs.parse_anthropic_pricing(text, names))
            prices = fetch('anthropic_docs_pricing', anthropic_docs)
            if prices is not None:
                for identifier, (values, variants) in prices.items():
                    record('anthropic', identifier, values, 'official_docs', anthropic_docs, variants=variants)
        else:
            sources['anthropic_docs_pricing'] = {'url':official_docs.ANTHROPIC_URL, 'status':'skipped_dependency', 'observed_at':timestamp}
        community = fetch('models_dev', models_dev)
        if community is not None:
            for provider in ('openai','anthropic'):
                for identifier, item in community[provider]['models'].items():
                    if isinstance(identifier,str) and isinstance(item,dict):
                        values = models_dev_values(item)
                        canonical = values.pop('_canonical_ref', None)
                        if canonical and canonical.startswith(provider+'/'):
                            values['identity.canonical_id'] = canonical[len(provider)+1:]
                        record(provider, identifier, values, 'models_dev', models_dev, item.get('last_updated'))
            # Reverse only explicit canonical links from Models.dev; no names are interpreted.
            from .normalization import put
            aliases = {}
            for ident, model in models.items():
                canonical = model['identity'].get('canonical_id')
                origin = model['provenance'].get('identity.canonical_id')
                if canonical and canonical != model['identity']['api_id'] and origin and origin['source_type'] == 'models_dev':
                    target = key(model['identity']['provider'], canonical)
                    if target in models: aliases.setdefault(target, []).append(model['identity']['api_id'])
            for target, items in aliases.items():
                source = {'url': models_dev.URL, 'source_type':'models_dev', 'observed_at':timestamp, 'published_at':None}
                put(models[target], 'identity.aliases', sorted(set(items)), source, conflicts)
        complement = fetch('litellm', litellm)
        if complement is not None:
            for identifier, item in complement.items():
                if not isinstance(item,dict): continue
                provider = item.get('litellm_provider')
                # Keys with provider prefixes and fine-tuning templates are not direct model IDs.
                if provider not in ('openai','anthropic') or '/' in identifier or identifier.startswith('ft:'): continue
                values = lite_values(item)
                variants = values.pop('pricing.variants', None)
                record(provider, identifier, values, 'litellm', litellm, variants=variants)
    finally:
        if owned_client: client.close()
    if not successes:
        raise RuntimeError('All available sources failed; existing catalog preserved')
    models = {k: Model.model_validate(v).model_dump(mode='json') for k,v in sorted(models.items())}
    digest = checksum(models)
    result = {'schema_version':'1.0', 'generated_at':timestamp, 'catalog_version':digest[:16], 'checksum_sha256':digest, 'models':models, 'sources':sources,
              'sync_status':{'status':'partial' if any(s['status'] != 'ok' for s in sources.values()) else 'ok', 'conflicts':conflicts}}
    result['sync_status']['changes'] = changes(previous, result)
    validate(result)
    atomic_publish(path,result)
    return result
