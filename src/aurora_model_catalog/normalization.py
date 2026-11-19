"""Translate only explicitly supplied fields; identifiers are never inferred."""
from decimal import Decimal
import re
from .schema import Model, Identity, check_iso

PRIORITY = {'official_api': 0, 'official_docs': 1, 'models_dev': 2, 'litellm': 3}

def key(provider, api_id):
    if not isinstance(provider, str) or not provider or ':' in provider or not isinstance(api_id, str) or not api_id or api_id.strip() != api_id:
        raise ValueError('invalid model identifier')
    return f'{provider}:{api_id}'

def blank(provider, api_id):
    return Model(identity=Identity(provider=provider, api_id=api_id)).model_dump(mode='json')

def put(model, path, value, source, conflicts):
    if value is None:
        return
    obj = model
    parts = path.split('.')
    for part in parts[:-1]: obj = obj.setdefault(part, {})
    previous = obj.get(parts[-1])
    old_source = model['provenance'].get(path)
    if old_source and previous != value:
        conflicts.append({'model': key(model['identity']['provider'], model['identity']['api_id']), 'property': path, 'existing': previous, 'incoming': value, 'existing_source': old_source['source_type'], 'incoming_source': source['source_type']})
    if old_source and PRIORITY[old_source['source_type']] < PRIORITY[source['source_type']]:
        return
    if previous == value and old_source and old_source['source_type'] == source['source_type']:
        return
    obj[parts[-1]] = value
    model['provenance'][path] = source

def apply(model, values, source, conflicts):
    for path, value in values.items(): put(model, path, value, source, conflicts)

def lite_values(d):
    fields = {'max_input_tokens':'limits.context_window_tokens', 'max_output_tokens':'limits.max_output_tokens', 'supports_reasoning':'reasoning.supported', 'supports_function_calling':'tools.function_calling', 'supports_parallel_function_calling':'tools.parallel_tool_calls', 'supports_tool_choice':'tools.forced_tool_choice', 'supports_response_schema':'tools.json_schema_output', 'supports_prompt_caching':'cache.supported', 'supports_vision':'input_modalities.images', 'supports_pdf_input':'input_modalities.pdf', 'deprecation_date':'identity.deprecation_date'}
    values = {}
    for field,path in fields.items():
        value = d.get(field)
        if path.startswith('limits.'):
            if not isinstance(value,int) or isinstance(value,bool) or value <= 0: continue
        elif path == 'identity.deprecation_date':
            try: check_iso(value)
            except ValueError: continue
            if value is None: continue
        elif not isinstance(value,bool): continue
        values[path] = value
    for name, field in [('input','input_cost_per_token'),('output','output_cost_per_token'),('cache_read','cache_read_input_token_cost'),('cache_write','cache_creation_input_token_cost')]:
        if isinstance(d.get(field), (float,int)) and not isinstance(d.get(field), bool):
            values['pricing.standard.'+name] = float(Decimal(str(d[field])) * 1000000)
    thresholds = set()
    for field in d:
        match = re.fullmatch(r'(?:input_cost_per_token|output_cost_per_token|cache_read_input_token_cost|cache_creation_input_token_cost)_above_(\d+)k_tokens', field)
        if match: thresholds.add(int(match.group(1)))
    variants = []
    for threshold in sorted(thresholds):
        suffix = f'_above_{threshold}k_tokens'
        rates = {'currency':'USD', 'unit':'per_million_tokens', 'input':None, 'output':None, 'cache_read':None, 'cache_write':None}
        for name, field in [('input','input_cost_per_token'),('output','output_cost_per_token'),('cache_read','cache_read_input_token_cost'),('cache_write','cache_creation_input_token_cost')]:
            value = d.get(field+suffix)
            if isinstance(value,(int,float)) and not isinstance(value,bool): rates[name] = float(Decimal(str(value))*1000000)
        variants.append({'name':'long_context', 'service_tier':'standard', 'threshold_tokens':threshold*1000, 'cache_ttl_seconds':None, 'rates':rates})
    if variants: values['pricing.variants'] = variants
    return values

def models_dev_values(d):
    values = {}
    for field,path in [('name','identity.display_name'),('family','identity.family'),('reasoning','reasoning.supported'),('tool_call','tools.function_calling'),('structured_output','tools.json_schema_output')]:
        if d.get(field) is not None: values[path] = d[field]
    # The source explicitly enumerates effort values; this does not establish API-specific scope.
    options = d.get('reasoning_options')
    if isinstance(options, list):
        lists = [o.get('values') for o in options if isinstance(o, dict) and o.get('type') == 'effort']
        if len(lists) == 1 and isinstance(lists[0], list) and lists[0] and all(isinstance(v, str) and v for v in lists[0]):
            values['reasoning.effort_levels'] = lists[0]
    limit = d.get('limit') or {}
    for field,path in [('context','limits.context_window_tokens'),('output','limits.max_output_tokens')]:
        if isinstance(limit.get(field), int) and limit[field] > 0: values[path] = limit[field]
    cost = d.get('cost') or {}
    for field,path in [('input','input'),('output','output'),('cache_read','cache_read'),('cache_write','cache_write')]:
        if isinstance(cost.get(field), (int,float)) and not isinstance(cost[field],bool): values['pricing.standard.'+path] = cost[field]
    if d.get('status') in ('active', 'deprecated', 'retired'): values['identity.status'] = d['status']
    canonical = d.get('canonical_model_id')
    if isinstance(canonical,str) and '/' in canonical: values['_canonical_ref'] = canonical
    # An explicit input modality list is exhaustive only for that source's own schema.
    modalities = (d.get('modalities') or {}).get('input')
    if isinstance(modalities,list):
        values['input_modalities.images'] = 'image' in modalities
        if 'pdf' in modalities: values['input_modalities.pdf'] = True
    return values

def anthropic_values(item):
    values = {}
    fields = {'display_name':'identity.display_name','line':'identity.family','deprecated_at':'identity.deprecation_date','retires_at':'identity.retirement_date','max_input_tokens':'limits.context_window_tokens','max_tokens':'limits.max_output_tokens'}
    for source, target in fields.items():
        value = item.get(source)
        if value is not None and (not isinstance(value, int) or value > 0): values[target] = value
    if item.get('lifecycle') in ('active','deprecated','retired'): values['identity.status'] = item['lifecycle']
    caps = item.get('capabilities') or {}
    for cap, path in [('image_input','input_modalities.images'),('pdf_input','input_modalities.pdf'),('structured_outputs','tools.json_schema_output'),('thinking','reasoning.supported')]:
        val = (caps.get(cap) or {}).get('supported')
        if isinstance(val,bool): values[path] = val
    types = (caps.get('thinking') or {}).get('types') or {}
    for cap, path in [('adaptive','reasoning.adaptive'),('between_tools','reasoning.interleaved_tool_thinking'),('disabled','reasoning.can_disable'),('enabled','reasoning.fixed_budget')]:
        val = (types.get(cap) or {}).get('supported')
        if isinstance(val,bool): values[path] = val
    effort = caps.get('effort') or {}
    levels = [name for name in ('low','medium','high','xhigh','max') if isinstance(effort.get(name),dict) and effort[name].get('supported') is True]
    if levels: values['reasoning.effort_levels'] = levels
    if any(path.startswith('reasoning.') for path in values): values['reasoning.api'] = 'messages'
    return values


def expand_scoped_provenance(models):
    """Migrate old whole-API provenance to individual properties before merging."""
    for model in models.values():
        for section in ('reasoning', 'tools'):
            for api, fields in model[section]['by_api'].items():
                parent = f'{section}.by_api.{api}'
                origin = model['provenance'].pop(parent, None)
                if origin:
                    for field in fields:
                        model['provenance'].setdefault(f'{parent}.{field}', origin)
