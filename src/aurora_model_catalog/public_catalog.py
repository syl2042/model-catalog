"""Build a public catalog using public inputs only, never account-scoped APIs."""
from copy import deepcopy
from pathlib import Path
import httpx
import time
import re
from .catalog import now, checksum, load, changes, atomic_publish, merge_variants
from .schema import IdentityV2, ModelV2, check_iso
from .normalization import apply, key, lite_values, models_dev_values, expand_scoped_provenance
from .sources import models_dev, litellm, official_docs

PUBLIC_PATH = Path('public/model-catalog.v2.json')
# Explicitly reviewed creator endpoints; ambiguous providers/platforms never supply prices.
DIRECT = {'openai', 'anthropic', 'google', 'mistral', 'xai', 'deepseek', 'cohere', 'perplexity', 'ai21', 'minimax', 'moonshotai', 'zhipuai'}
LITE_TO_MODELS = {'openai':'openai','anthropic':'anthropic','gemini':'google','mistral':'mistral','xai':'xai','deepseek':'deepseek','cohere':'cohere','perplexity':'perplexity','ai21':'ai21','minimax':'minimax','moonshot':'moonshotai'}

def direct_price(provider, record):
    canonical = record.get('canonical_model_id')
    return provider in DIRECT and (not canonical or canonical.startswith(provider+'/'))

def sync_public(path=PUBLIC_PATH, client=None):
    path=Path(path)
    previous=load(path) if path.exists() else None
    if previous and previous['schema_version'] != '2.0': raise ValueError('expected a V2 public catalog')
    models=deepcopy(previous['models']) if previous else {}
    expand_scoped_provenance(models)
    timestamp=now(); statuses={}; conflicts=[]
    own=client is None
    if own: client=httpx.Client(timeout=httpx.Timeout(40,connect=10),follow_redirects=True)
    def get(name,module):
        for attempt in range(3):
            try:
                data=module.fetch(client)
                statuses[name]={'url':module.URL,'status':'ok','observed_at':timestamp}
                return data
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                retry = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code >= 500
                if retry and attempt < 2:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                statuses[name]={'url':module.URL,'status':'error','error':type(exc).__name__,'observed_at':timestamp}
                return None
    def add(provider,ident,values,module,source_type,published=None,variants=None):
        model_key=key(provider,ident)
        try: check_iso(published)
        except ValueError: published=None
        source={'url':module.URL,'source_type':source_type,'observed_at':timestamp,'published_at':published}
        if model_key not in models:
            models[model_key]=ModelV2(identity=IdentityV2(provider=provider,api_id=ident)).model_dump(mode='json')
            models[model_key]['provenance'].update({'identity.provider':source,'identity.api_id':source})
        apply(models[model_key],values,source,conflicts)
        if variants: merge_variants(models[model_key],variants,source,conflicts)
    try:
        class DocSource:
            def __init__(self,url,parser): self.URL,self.parser=url,parser
            def fetch(self,http): return self.parser(official_docs.markdown(http,self.URL))
        source=DocSource(official_docs.OPENAI_URL,official_docs.parse_openai)
        prices=get('openai_docs_pricing',source)
        if prices is not None:
            for identifier,values in prices.items(): add('openai',identifier,values,source,'official_docs')
        index_source=DocSource(official_docs.OPENAI_MODELS_URL,official_docs.parse_openai_index)
        paths=get('openai_docs_model_index',index_source)
        if paths:
            for doc_path in paths:
                model_source=DocSource('https://developers.openai.com'+doc_path,official_docs.parse_openai_model)
                detail=get('openai_model_doc:'+doc_path.rsplit('/',1)[-1],model_source)
                if detail is not None:
                    identifier,values=detail
                    add('openai',identifier,values,model_source,'official_docs')
        overview_source=DocSource(official_docs.ANTHROPIC_MODELS_URL,official_docs.parse_anthropic_models)
        overview=get('anthropic_docs_models',overview_source)
        if overview:
            names,details=overview
            for identifier,values in details.items(): add('anthropic',identifier,values,overview_source,'official_docs')
            for doc_name, url, parser in [('anthropic_docs_effort',official_docs.ANTHROPIC_EFFORT_URL,official_docs.parse_anthropic_effort),('anthropic_docs_thinking',official_docs.ANTHROPIC_THINKING_URL,official_docs.parse_anthropic_thinking)]:
                model_source=DocSource(url,lambda text, parser=parser: parser(text,names))
                extra=get(doc_name,model_source)
                if extra is not None:
                    for identifier,values in extra.items(): add('anthropic',identifier,values,model_source,'official_docs')
            price_source=DocSource(official_docs.ANTHROPIC_URL,lambda text: official_docs.parse_anthropic_pricing(text,names))
            prices=get('anthropic_docs_pricing',price_source)
            if prices is not None:
                for identifier,(values,variants) in prices.items(): add('anthropic',identifier,values,price_source,'official_docs',variants=variants)
        else: statuses['anthropic_docs_pricing']={'url':official_docs.ANTHROPIC_URL,'status':'skipped_dependency','observed_at':timestamp}
        deepseek_source=DocSource(official_docs.DEEPSEEK_THINKING_URL,official_docs.parse_deepseek_thinking)
        deepseek_details=get('deepseek_docs_thinking',deepseek_source)
        if deepseek_details is not None:
            for identifier,values in deepseek_details.items(): add('deepseek',identifier,values,deepseek_source,'official_docs')
        community=get('models_dev',models_dev)
        if community is not None:
            for provider, info in community.items():
                if not isinstance(info,dict) or not isinstance(info.get('models'),dict) or ':' in provider: continue
                for ident, item in info['models'].items():
                    if not isinstance(ident,str) or not ident or ident.strip()!=ident or not isinstance(item,dict): continue
                    values=models_dev_values(item)
                    canonical=values.pop('_canonical_ref',None)
                    if canonical: values['identity.canonical_id']=canonical
                    if not direct_price(provider,item):
                        values={p:v for p,v in values.items() if not p.startswith('pricing.')}
                    add(provider,ident,values,models_dev,'models_dev',item.get('last_updated'))
        complement=get('litellm',litellm)
        if complement is not None:
            for ident,item in complement.items():
                if not isinstance(ident,str) or not ident or ident.strip()!=ident or not isinstance(item,dict): continue
                lite_provider = item.get('litellm_provider')
                if not lite_provider and isinstance(item.get('alias_of'),str) and item['alias_of']:
                    add('litellm.alias',ident,{'identity.canonical_id':item['alias_of']},litellm,'litellm')
                    continue
                if not isinstance(lite_provider,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',lite_provider): continue
                direct = LITE_TO_MODELS.get(lite_provider)
                unqualified = direct and '/' not in ident and not ident.startswith('ft:')
                # Other keys remain exact LiteLLM catalog references with explicit namespace.
                provider = direct if unqualified else 'litellm.' + lite_provider.replace(':','%3A')
                values=lite_values(item)
                variants=values.pop('pricing.variants',None)
                existing=models.get(key(provider,ident))
                ref=existing['identity'].get('canonical_id') if existing else None
                if not unqualified or ref and not ref.startswith(provider+'/'):
                    values={p:v for p,v in values.items() if not p.startswith('pricing.')}
                    variants=None
                add(provider,ident,values,litellm,'litellm',variants=variants)
    finally:
        if own:client.close()
    if not any(s['status']=='ok' for s in statuses.values()):raise RuntimeError('All public sources failed; published catalog preserved')
    # Never retain platform prices, even when an older catalog contained them.
    for m in models.values():
        provider=m['identity']['provider']
        ref=m['identity'].get('canonical_id')
        if provider not in DIRECT or ref and not ref.startswith(provider+'/'):
            for field in ('input','output','cache_read','cache_write'):
                m['pricing']['standard'][field]=None
                m['provenance'].pop('pricing.standard.'+field,None)
            m['pricing']['variants']=[]
            for field in list(m['provenance']):
                if field == 'pricing.variants' or field.startswith('pricing.variants.'):
                    m['provenance'].pop(field,None)
    normalized={k:ModelV2.model_validate(v).model_dump(mode='json') for k,v in sorted(models.items())}
    digest=checksum(normalized)
    data={'schema_version':'2.0','generated_at':timestamp,'catalog_version':digest[:16],'checksum_sha256':digest,'models':normalized,'sources':statuses,
          'sync_status':{'status':'ok' if all(s['status']=='ok' for s in statuses.values()) else 'partial','conflicts':conflicts,'scope':'public sources only; no account-scoped discovery','direct_price_providers':sorted(DIRECT)}}
    data['sync_status']['changes']=changes(previous,data)
    atomic_publish(path,data)
    return data
